"""
Configuration for environment variables and Snowflake connection.
This module loads environment variables from a .env file and provides a CONFIG dictionary
for connecting to Snowflake, as well as other configuration constants.
"""


import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Google Drive configuration, set via environment variables.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_ID = os.getenv("FOLDER_ID")
LANDING_FOLDER = os.getenv("LANDING_FOLDER", "data/landing/")


# Expected Files, set via environment variables.
_default_files = "conditions.csv,payers.csv,providers.csv,organizations.csv,patients.csv,encounters.csv"
EXPECTED_FILES = os.getenv("EXPECTED_FILES", _default_files).strip().split(",")
EXPECTED_FILES = [f.strip() for f in EXPECTED_FILES if f.strip()]


# Notifications for pipeline alerts, set via environment variables.
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL")


# WEEKLY NOTIFICATION SCHEDULE CONFIG
# 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday
DELIVERY_WEEKDAY = 0
DELIVERY_HOUR_UTC = 13
DELIVERY_MINUTE = 0
SLA_HOURS = 1

# CALCULATE THIS WEEK'S DELIVERY DAY ONLY
today = datetime.now(timezone.utc).date()
current_week_start = today - \
    timedelta(days=today.weekday())  # Monday of THIS week
scheduled_this_week = current_week_start + \
    timedelta(days=DELIVERY_WEEKDAY)  # This Friday

# Determine the scheduled drop time based on today's date and the configured delivery weekday.
if today > scheduled_this_week:
    # Friday already passed → expect NEXT week
    scheduled_date = scheduled_this_week + timedelta(weeks=1)
else:
    # Friday is coming up or today → expect THIS week
    scheduled_date = scheduled_this_week

# Build final timestamp for scheduled drop time
SCHEDULED_DROP_TIME = datetime(
    year=scheduled_date.year,
    month=scheduled_date.month,
    day=scheduled_date.day,
    hour=DELIVERY_HOUR_UTC,
    minute=DELIVERY_MINUTE,
    second=0,
    tzinfo=timezone.utc
)

# EXPECTED SCHEMA DICTIONARY PER FILE
EXPECTED = {
    "patients": {
        "columns": ['Id', 'BIRTHDATE', 'DEATHDATE', 'SSN', 'DRIVERS', 'PASSPORT', 'PREFIX',
                    'FIRST', 'LAST', 'SUFFIX', 'MAIDEN', 'MARITAL', 'RACE', 'ETHNICITY',
                    'GENDER', 'BIRTHPLACE', 'ADDRESS', 'CITY', 'STATE', 'COUNTY', 'ZIP',
                    'LAT', 'LON', 'HEALTHCARE_EXPENSES', 'HEALTHCARE_COVERAGE'],

        "mandatory": ["Id", "BIRTHDATE", "FIRST", "LAST"],
        "uuid_cols": ["Id"],
        "allowed_values": {
            "GENDER": ["M", "F", "male", "female", "Male", "Female", "Unknown", ""],
            "MARITAL": ["M", "S", "D", "W", "", None]
        },
        "row_min": 0, "row_max": 500000
    },
    "encounters": {
        "columns": ['Id', 'START', 'STOP', 'PATIENT', 'ORGANIZATION', 'PROVIDER', 'PAYER',
                    'ENCOUNTERCLASS', 'CODE', 'DESCRIPTION', 'BASE_ENCOUNTER_COST',
                    'TOTAL_CLAIM_COST', 'PAYER_COVERAGE', 'REASONCODE',
                    'REASONDESCRIPTION'],
        "mandatory": ["Id", "START", "PATIENT"],
        "uuid_cols": ["Id", "PATIENT", "ORGANIZATION", "PROVIDER", "PAYER"],
        "allowed_values": {
            "ENCOUNTERCLASS": ["ambulatory", "inpatient", "outpatient", "emergency", "urgentcare", "wellness", "other"]
        },
        "row_min": 0, "row_max": 1000000
    },
    "conditions": {
        "columns": ['START', 'STOP', 'PATIENT', 'ENCOUNTER', 'CODE', 'DESCRIPTION'],
        "mandatory": ["ENCOUNTER", "PATIENT", "CODE"],
        "uuid_cols": ["ENCOUNTER", "PATIENT"],
        "allowed_values": {},
        "row_min": 0, "row_max": 500000
    },
    "payers": {
        "columns": ['Id', 'NAME', 'ADDRESS', 'CITY', 'STATE_HEADQUARTERED', 'ZIP', 'PHONE',
                    'AMOUNT_COVERED', 'AMOUNT_UNCOVERED', 'REVENUE', 'COVERED_ENCOUNTERS',
                    'UNCOVERED_ENCOUNTERS', 'COVERED_MEDICATIONS', 'UNCOVERED_MEDICATIONS',
                    'COVERED_PROCEDURES', 'UNCOVERED_PROCEDURES', 'COVERED_IMMUNIZATIONS',
                    'UNCOVERED_IMMUNIZATIONS', 'UNIQUE_CUSTOMERS', 'QOLS_AVG',
                    'MEMBER_MONTHS'],
        "mandatory": ["Id", "NAME"],
        "uuid_cols": ["Id"],
        "allowed_values": {},
        "row_min": 5, "row_max": 50
    },
    "providers": {
        "columns": ['Id', 'ORGANIZATION', 'NAME', 'GENDER', 'SPECIALITY', 'ADDRESS', 'CITY',
                    'STATE', 'ZIP', 'LAT', 'LON', 'UTILIZATION'],
        "mandatory": ["Id", "NAME"],
        "uuid_cols": ["Id", "ORGANIZATION"],
        "allowed_values": {},
        "row_min": 5, "row_max": 6000
    },
    "organizations": {
        "columns": ['Id', 'NAME', 'ADDRESS', 'CITY', 'STATE', 'ZIP', 'LAT', 'LON', 'PHONE',
                    'REVENUE', 'UTILIZATION'],
        "mandatory": ["Id", "NAME"],
        "uuid_cols": ["Id"],
        "allowed_values": {},
        "row_min": 3, "row_max": 2000
    }
}


# Quarantine folder for files that fail pre-validation. This is set via environment variable or defaults to "data/landing/quarantine".
QUARANTINE_FOLDER = os.getenv("QUARANTINE_FOLDER", "data/landing/quarantine")


# Configuration for Snowflake connection and raw data folder,
# set via environment variables.
# The passcode is a 6-digit MFA code that must be updated for each run.
CONFIG = {
    "account": os.getenv("SNOWFLAKE_ACCOUNT"),
    "user": os.getenv("SNOWFLAKE_USER"),
    "password": os.getenv("SNOWFLAKE_PASSWORD"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
    "database": os.getenv("SNOWFLAKE_DATABASE"),
    "schema": os.getenv("SNOWFLAKE_SCHEMA"),
    "role": os.getenv("SNOWFLAKE_ROLE"),
    "raw_data_folder": Path(os.getenv("RAW_DATA_PATH")),
    "passcode": os.getenv("SNOWFLAKE_PASSCODE")
}
