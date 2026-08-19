import os
import snowflake.connector
import logging
from python.logger import setup_logging
from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv()

# Configure logging
setup_logging()

logging.info("Attempting to connect to Snowflake...")


def test_snowflake_connection():
    try:
        # CONNECT
        conn = snowflake.connector.connect(
            account=os.getenv("SNOWFLAKE_ACCOUNT"),
            user=os.getenv("SNOWFLAKE_USER"),
            password=os.getenv("SNOWFLAKE_PASSWORD"),
            warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
            passcode=int(os.getenv("SNOWFLAKE_PASSCODE")),
            # database=os.getenv("SNOWFLAKE_DATABASE"),
            # schema=os.getenv("SNOWFLAKE_SCHEMA")
        )

        # TEST CONNECTION - run a simple query
        cursor = conn.cursor()
        cursor.execute("SELECT CURRENT_VERSION()")
        version = cursor.fetchone()
        logging.info(f"CONNECTED SUCCESSFULLY!")
        logging.info(f"Snowflake Version: {version[0]}")

        # Check available databases
        cursor.execute("SHOW DATABASES")
        dbs = cursor.fetchall()
        logging.info("\n Your Databases:")
        for db in dbs:
            logging.info(f"   - {db[1]}")

        cursor.close()
        conn.close()
        logging.info("\n Connection closed cleanly. All working!")

    except Exception as e:
        logging.error(f"CONNECTION FAILED")
        logging.error(f"Error: {str(e)}")
        logging.info("\n Common fixes:")
        logging.info(
            "   • Check account ID (needs region + cloud if not US-West)")
        logging.info("   • Verify username & password")
        logging.info(
            "   • Check your IP is allowed in Snowflake → Admin → Security → Network Policies")


def main():
    test_snowflake_connection()


if __name__ == "__main__":
    main()
