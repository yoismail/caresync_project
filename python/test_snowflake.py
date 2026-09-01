"""
This script tests the connection to a Snowflake database using Key Pair authentication.
NO password required - uses RSA private key (bypasses MFA automatically).
"""

import snowflake.connector
import logging
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from python.logger import setup_logging
from python.config import (
    SNOWFLAKE_ACCOUNT,
    SNOWFLAKE_USER,
    SNOWFLAKE_WAREHOUSE,
    PRIVATE_KEY_PATH
)
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.info("Attempting to connect to Snowflake...")


def test_snowflake_connection():
    try:
        # Load and parse the private key
        with open(PRIVATE_KEY_PATH, "rb") as key_file:
            p_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,   # Set to passphrase string if your key is protected
                backend=default_backend()
            )

        # Format key into DER format Snowflake expects
        pkb = p_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        # CONNECT — Key Pair Authentication (NO password, NO MFA)
        conn = snowflake.connector.connect(
            account=SNOWFLAKE_ACCOUNT,
            user=SNOWFLAKE_USER,
            private_key=pkb,
            warehouse=SNOWFLAKE_WAREHOUSE,
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
        logging.info("   • Verify username and private key path")
        logging.info(f"   • Private key path: {PRIVATE_KEY_PATH}")
        logging.info(
            "   • Check your IP is allowed in Snowflake → Admin → Security → Network Policies")


def main():
    setup_logging()
    test_snowflake_connection()


if __name__ == "__main__":
    main()
