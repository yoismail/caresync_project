import io
import logging
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from dotenv import load_dotenv
from python.logger import setup_logging

# Load environment variables from .env file
load_dotenv()

# Configuration
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_ID = os.getenv("FOLDER_ID")
LANDING_FOLDER = os.getenv("LANDING_FOLDER", "data/landing/")

_default_files = "conditions.csv,payers.csv,providers.csv,organizations.csv,patients.csv,encounters.csv"
EXPECTED_FILES = os.getenv("EXPECTED_FILES", _default_files).strip().split(",")
EXPECTED_FILES = [f.strip() for f in EXPECTED_FILES if f.strip()]


# Ensure the landing folder exists
def ensure_landing_folder():
    if not os.path.exists(LANDING_FOLDER):
        os.makedirs(LANDING_FOLDER, exist_ok=True)


# Authenticate & Connect to Google Drive
def connect_to_drive():
    creds = service_account.Credentials.from_service_account_file(
        "service-account-key.json", scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


# Download NEW files from Drive
def download_from_drive():
    logging.info("Downloading from Google Drive...")
    service = connect_to_drive()

    # Get files from drive, including their size to check for empty files
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType != 'application/vnd.google-apps.folder'",
        fields="files(id, name, createdTime, size)"
    ).execute()
    files = results.get("files", [])

    # Build a simple lookup: { filename: all-details }
    drive_files = {f["name"]: f for f in files}
    drive_filenames = set(drive_files.keys())
    expected_filenames = set(EXPECTED_FILES)

    # STEP 1: CHECK FOR MISSING FILES
    missing_files = sorted(expected_filenames - drive_filenames)
    if missing_files:
        logging.warning("=" * 60)
        logging.warning(
            f"MISSING FILES DETECTED: {len(missing_files)} file(s) not found in Drive!")
        for name in missing_files:
            logging.warning(f" MISSING: {name}")
        logging.warning("=" * 60)
        # UNCOMMENT below to STOP everything if files are missing
        # raise FileNotFoundError(f"Missing critical files: {missing_files}")
    else:
        logging.info("All expected files are present in Drive")

    # STEP 2: FLAG EMPTY FILES
    for name in expected_filenames:
        if name in drive_filenames:
            f = drive_files[name]
            size = f.get("size", "unknown")
            if size == "0":
                logging.warning(f"EMPTY FILE: {name} exists but is 0 bytes!")

    # STEP 3: Download only new/non-empty files
    for f in files:
        file_size = f.get("size", "unknown")
        if file_size == "0":
            logging.warning(f"Skipping empty file: {f['name']} (0 bytes)")
            continue

        dest_path = os.path.join(LANDING_FOLDER, f["name"])
        if os.path.exists(dest_path):
            logging.info(f"Already exists: {f['name']}")
            continue

        request = service.files().get_media(fileId=f["id"])
        with io.FileIO(dest_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        logging.info(f"Downloaded: {f['name']}")


def main():
    setup_logging()
    ensure_landing_folder()
    download_from_drive()


# Main Pipeline
if __name__ == "__main__":
    main()
