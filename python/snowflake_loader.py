"""
snowflake_loader.py - Stage CSV file and load into NEXORA_RAW
Workflow: PUT file → internal stage → COPY INTO table → verify row count
All columns loaded as STRING; typing and transformation happen in dbt.
Automatically adds LOADED_AT timestamp column to track load time.
"""
import logging
import os
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from python.config import (
    SNOWFLAKE_ACCOUNT,
    SNOWFLAKE_USER,
    SNOWFLAKE_WAREHOUSE,
    SNOWFLAKE_ROLE,
    PRIVATE_KEY_PATH
)


def get_connection(database, schema):
    """Establish and return Snowflake connection using Key Pair authentication"""
    # Load and parse the private key
    with open(PRIVATE_KEY_PATH, "rb") as key_file:
        p_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,   # Set to passphrase string if you protected your key
            backend=default_backend()
        )

    # Format key into DER format Snowflake expects
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Connect - NO PASSWORD! Uses RSA key instead (bypasses MFA)
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


def load_csv_to_snowflake(file_path, table_name, schema="HL7", database="NEXORA_RAW"):
    """
    Stage local CSV file and load into target table.
    Automatically adds LOADED_AT = current UTC timestamp to every row.
    Returns number of rows written.
    """
    filename = os.path.basename(file_path)
    stage_name = f"RAW_STAGE_{table_name}"
    conn = get_connection(database, schema)
    cur = conn.cursor()
    try:
        # Create stage if it does not exist
        cur.execute(f"""
            CREATE STAGE IF NOT EXISTS {stage_name}
            FILE_FORMAT = (
                TYPE = CSV
                FIELD_OPTIONALLY_ENCLOSED_BY = '"'
                SKIP_HEADER = 1
            )
        """)

        # Upload file to stage
        put_command = f"PUT file://{file_path} @{stage_name} AUTO_COMPRESS=TRUE OVERWRITE=TRUE"
        logging.info(f"Uploading: {filename}")
        cur.execute(put_command)

        # Truncate table
        cur.execute(
            f"TRUNCATE TABLE IF EXISTS {database}.{schema}.{table_name}")

        # Copy data from staged CSV into the target table
        copy_command = f"""
            COPY INTO {database}.{schema}.{table_name}
            FROM @{stage_name}/{filename}.gz
            FILE_FORMAT = (
                TYPE = CSV
                FIELD_OPTIONALLY_ENCLOSED_BY = '"'
                SKIP_HEADER = 1
                ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE
            )
            PURGE = TRUE
        """
        cur.execute(copy_command)

        # SET LOADED_AT for ALL rows in one simple UPDATE
        cur.execute(f"""
            UPDATE {database}.{schema}.{table_name}
            SET LOADED_AT = CURRENT_TIMESTAMP()::TIMESTAMP_NTZ
            WHERE LOADED_AT IS NULL
        """)
        logging.info(f"Set LOADED_AT timestamp for {table_name}")

        # Verify row count
        cur.execute(f"SELECT COUNT(*) FROM {database}.{schema}.{table_name}")
        rows_written = cur.fetchone()[0]
        logging.info(f"Rows written to {table_name}: {rows_written}")
        return rows_written

    finally:
        cur.close()
        conn.close()
