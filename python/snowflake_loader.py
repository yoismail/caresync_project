"""
snowflake_loader.py - Stage CSV file and load into NEXORA_RAW
Idempotent design:
- No TRUNCATE: safe to run multiple times with the same file
- Uses source file name + content hash to avoid duplicates
- Automatically adds tracking columns to existing tables
- New runs only add rows that do not already exist
- Compatible with all Snowflake versions
- Direct run: python -m python.snowflake_loader
- Orchestrator: called automatically
"""

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import snowflake.connector
from datetime import datetime, timezone
import hashlib
import os
import logging
from python.logger import setup_logging

# Use config values if available, otherwise fall back to environment
try:
    from python.config import (
        SNOWFLAKE_ACCOUNT,
        SNOWFLAKE_USER,
        SNOWFLAKE_WAREHOUSE,
        SNOWFLAKE_ROLE,
        PRIVATE_KEY_PATH
    )
except ImportError:
    SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT")
    SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER")
    SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE")
    SNOWFLAKE_ROLE = os.getenv("SNOWFLAKE_ROLE")
    PRIVATE_KEY_PATH = os.getenv("PRIVATE_KEY_PATH")


def get_connection(database, schema):
    with open(PRIVATE_KEY_PATH, "rb") as key_file:
        p_key = serialization.load_pem_private_key(
            key_file.read(), password=None, backend=default_backend()
        )
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    return snowflake.connector.connect(
        account=SNOWFLAKE_ACCOUNT,
        user=SNOWFLAKE_USER,
        private_key=pkb,
        warehouse=SNOWFLAKE_WAREHOUSE,
        database=database,
        schema=schema,
        role=SNOWFLAKE_ROLE,
        client_session_keep_alive=True
    )


def compute_file_hash(file_path):
    hasher = hashlib.sha256()
    filename = os.path.basename(file_path)
    hasher.update(filename.encode("utf-8"))
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def column_exists(cur, full_table, col_name):
    db, schema, table = full_table.split(".")
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_CATALOG = %s AND TABLE_SCHEMA = %s "
        "AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (db, schema.upper(), table.upper(), col_name.upper())
    )
    return cur.fetchone()[0] > 0


def add_column_safe(cur, full_table, col_name, col_type):
    if not column_exists(cur, full_table, col_name):
        cur.execute(
            f"ALTER TABLE {full_table} ADD COLUMN {col_name} {col_type}")
        logging.info(f"Added column: {col_name}")


def load_csv_to_snowflake(file_path, table_name, schema="HL7", database="NEXORA_RAW"):
    filename = os.path.basename(file_path)
    stage_name = f"STAGE_{table_name}"
    file_hash = compute_file_hash(file_path)
    batch_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{file_hash[:12]}"
    full_table = f"{database}.{schema}.{table_name}"

    conn = get_connection(database, schema)
    cur = conn.cursor()
    try:
        cur.execute(f"CREATE STAGE IF NOT EXISTS {stage_name}")

        cur.execute(
            f"PUT file://{file_path} @{stage_name} AUTO_COMPRESS=TRUE OVERWRITE=TRUE")
        logging.info(f"Uploaded: {filename}")

        temp_table = f"TEMP_{table_name}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        cur.execute(
            f"CREATE OR REPLACE TEMP TABLE {temp_table} LIKE {full_table}")

        cur.execute(f"""
            COPY INTO {temp_table}
            FROM @{stage_name}/{filename}.gz
            FILE_FORMAT = (
                TYPE = CSV
                FIELD_OPTIONALLY_ENCLOSED_BY = '"'
                SKIP_HEADER = 1
                ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE
            )
        """)

        for col in ["SOURCE_FILE", "BATCH_ID", "FILE_HASH", "LOADED_AT"]:
            add_column_safe(
                cur, f"{database}.{schema}.{temp_table}", col, "STRING")

        cur.execute(f"""
            UPDATE {temp_table}
            SET SOURCE_FILE = %s, BATCH_ID = %s, FILE_HASH = %s,
                LOADED_AT = CURRENT_TIMESTAMP()::TIMESTAMP_NTZ
        """, (filename, batch_id, file_hash))

        for col in ["SOURCE_FILE", "BATCH_ID", "FILE_HASH", "LOADED_AT"]:
            add_column_safe(cur, full_table, col, "STRING")

        cur.execute(
            f"SELECT COUNT(*) FROM {full_table} WHERE FILE_HASH = %s", (file_hash,))
        if cur.fetchone()[0] > 0:
            logging.info(f"SKIP - {filename} already loaded")
            return 0

        cur.execute(f"""
            INSERT INTO {full_table}
            SELECT * FROM {temp_table}
        """)
        rows = cur.rowcount
        logging.info(f"Loaded {rows} rows to {full_table}")
        return rows

    except Exception as e:
        logging.error(f"FAILED {filename}: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def main():
    setup_logging()
    logging.info("=" * 60)
    logging.info("SNOWFLAKE LOADER - DIRECT TEST")
    logging.info("=" * 60)

    base = os.path.join("data", "landing")
    files = [
        ("organizations.csv", "ORGANIZATIONS"),
        ("payers.csv", "PAYERS"),
        ("providers.csv", "PROVIDERS"),
        ("patients.csv", "PATIENTS"),
        ("encounters.csv", "ENCOUNTERS"),
        ("conditions.csv", "CONDITIONS"),
    ]

    total = 0
    for csv, tbl in files:
        path = os.path.join(base, csv)
        if not os.path.exists(path):
            logging.warning(f"File not found: {path}")
            continue
        total += load_csv_to_snowflake(path, tbl)

    logging.info("=" * 60)
    logging.info(f"Run complete. Total rows inserted: {total}")
    logging.info("=" * 60)


if __name__ == "__main__":
    main()
