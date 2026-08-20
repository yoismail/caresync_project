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
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType != 'application/vnd.google-apps.folder'",
        fields="files(id, name, createdTime, size)"
    ).execute()
    files = results.get("files", [])

    for f in files:

        # Check for EMPTY file (size = "0" or missing)
        file_size = f.get("size", "unknown")
        if file_size == "0":
            logging.warning(
                f"EMPTY FILE DETECTED: {f['name']} - 0 bytes. SKIPPING!")
            continue  # Skip it - don't download empty file

        # Check if the file already exists in the landing folder
        dest_path = os.path.join(LANDING_FOLDER, f["name"])
        if os.path.exists(dest_path):
            logging.info(f" Skipping (already exists): {f['name']}")
            continue  # Skip already downloaded

        # Download only if NOT empty and NOT already present
        request = service.files().get_media(fileId=f["id"])
        with io.FileIO(dest_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        logging.info(f" Downloaded: {f['name']}")


def main():
    setup_logging()
    ensure_landing_folder()
    download_from_drive()


# Main Pipeline
if __name__ == "__main__":
    main()
