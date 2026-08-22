"""
This script loads raw CSV files from the landing folder into Snowflake tables.
It connects to Snowflake using credentials from environment variables 
and uses the write_pandas function for efficient loading.
"""


import os
import pandas as pd
import logging
from python.logger import setup_logging
from dotenv import load_dotenv
from snowflake.connector import connect
from snowflake.connector.pandas_tools import write_pandas
from python.config import CONFIG


# Load environment variables from .env file
load_dotenv()

# File Mapping: CSV filename → Snowflake table name
FILES = [
    {"csv": "patients.csv",     "table": "PATIENTS"},
    {"csv": "encounters.csv",   "table": "ENCOUNTERS"},
    {"csv": "organizations.csv", "table": "ORGANIZATIONS"},
    {"csv": "payers.csv",        "table": "PAYERS"},
    {"csv": "providers.csv",     "table": "PROVIDERS"},
    {"csv": "conditions.csv",     "table": "CONDITIONS"},
]


def load_raw_to_snowflake():
    logging.info(" Connecting to Snowflake...")
    conn = connect(
        account=CONFIG["account"],
        user=CONFIG["user"],
        password=CONFIG["password"],
        warehouse=CONFIG["warehouse"],
        database=CONFIG["database"],
        schema=CONFIG["schema"],
        role=CONFIG["role"],
        passcode=CONFIG["passcode"]
    )
    logging.info("Connected!\n")

    for item in FILES:
        csv_path = os.path.join(CONFIG["raw_data_folder"], item["csv"])
        table_name = item["table"]

        if not os.path.exists(csv_path):
            logging.warning(f"SKIP: {item['csv']} not found at {csv_path}")
            continue

        logging.info(f"Loading {item['csv']} → {table_name}...")

        # Read CSV - ALL columns as STRING (matches RAW layer!)
        df = pd.read_csv(csv_path, dtype=str, low_memory=False)

        # Clean column names to match Snowflake (UPPERCASE)
        df.columns = [col.upper() for col in df.columns]

        # Safely rename reserved words, START & STOP from Encounters and Conditions Table BEFORE loading
        rename_map = {
            "START": "ENCOUNTER_START" if table_name == "ENCOUNTERS" else "CONDITION_START",
            "STOP": "ENCOUNTER_STOP" if table_name == "ENCOUNTERS" else "CONDITION_STOP"
        }
        df = df.rename(columns=rename_map)

        # Truncate table first: Remove duplicates!
        logging.info(f"Clearing {table_name} before loading...")
        conn.cursor().execute(f"TRUNCATE TABLE NEXORA_RAW.HL7.{table_name}")

        # Load to Snowflake: FRESH DATA ONLY
        success, nchunks, nrows, _ = write_pandas(
            conn=conn,
            df=df,
            table_name=table_name,
            database=CONFIG["database"],
            schema=CONFIG["schema"],
            chunk_size=5000,  # Batch size - adjust if files are huge
            quote_identifiers=False  # Already handled reserved words above
        )

        if success:
            logging.info(f"{table_name}: Loaded {nrows:,} rows\n")
        else:
            logging.error(f"FAILED: {table_name}\n")

    conn.close()
    logging.info("ALL DONE! Connection closed.")


def main():
    setup_logging()
    logging.info("Starting RAW → Snowflake load process...")
    load_raw_to_snowflake()


if __name__ == "__main__":
    main()
