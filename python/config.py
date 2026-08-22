import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Google Drive
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_ID = os.getenv("FOLDER_ID")
LANDING_FOLDER = os.getenv("LANDING_FOLDER", "data/landing/")

# SLA
SLA_HOURS = int(os.getenv("SLA_HOURS", "1"))

# Expected Files
_default_files = "conditions.csv,payers.csv,providers.csv,organizations.csv,patients.csv,encounters.csv"
EXPECTED_FILES = os.getenv("EXPECTED_FILES", _default_files).strip().split(",")
EXPECTED_FILES = [f.strip() for f in EXPECTED_FILES if f.strip()]

# Notifications
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL")


# Configuration for Snowflake connection and raw data folder
CONFIG = {
    "account": os.getenv("SNOWFLAKE_ACCOUNT"),
    "user": os.getenv("SNOWFLAKE_USER"),
    "password": os.getenv("SNOWFLAKE_PASSWORD"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
    "database": os.getenv("SNOWFLAKE_DATABASE"),
    "schema": os.getenv("SNOWFLAKE_SCHEMA"),
    "role": os.getenv("SNOWFLAKE_ROLE"),
    "raw_data_folder": Path(os.getenv("RAW_DATA_PATH")),
    # 6-DIGIT MFA CODE (update every run!)
    "passcode": os.getenv("SNOWFLAKE_PASSCODE")
}
