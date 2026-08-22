"""
This script connects to a specified Google Drive folder, 
checks for the presence of expected files, 
and downloads them to a local landing folder. 
It also checks if the files arrived within the defined SLA (Service Level Agreement) window. 
If any files are missing or late, it sends alerts via Slack and/or email.
"""


import logging
import os
import io
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from python.logger import setup_logging, section
from python.config import (
    SCOPES, FOLDER_ID, LANDING_FOLDER, SLA_HOURS, EXPECTED_FILES
)
from python.notifications import send_alert


def connect_to_drive():
    creds = service_account.Credentials.from_service_account_file(
        "service-account-key.json", scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def ensure_landing_folder():
    if not os.path.exists(LANDING_FOLDER):
        os.makedirs(LANDING_FOLDER, exist_ok=True)


def check_and_download():
    logging.info("\033[92m=== STARTING SENSOR ===\033[0m")
    ensure_landing_folder()

    service = connect_to_drive()
    sla_cutoff = datetime.now(timezone.utc).replace(
        tzinfo=None) - timedelta(hours=SLA_HOURS)
    logging.info("SLA Window: Files must arrive within last " +
                 str(SLA_HOURS) + " hour(s)")

    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType != 'application/vnd.google-apps.folder'",
        fields="files(name, createdTime, size, id)"
    ).execute()
    drive_files = {f["name"]: f for f in results.get("files", [])}

    missing_files = []
    late_files = []
    ready_files = []
    zero_byte_files = []
    downloaded_paths = []

    for name in EXPECTED_FILES:
        if name not in drive_files:
            missing_files.append(name)
            continue

        f = drive_files[name]

        # Check for zero-byte file
        if f.get("size", "0") == "0" or int(f.get("size", 0)) == 0:
            zero_byte_files.append(name)
            alert_msg = "File " + name + \
                " is EMPTY (0 bytes). Will not download."
            logging.warning(alert_msg)
            send_alert("PIPELINE ALERT - Empty File: " + name, alert_msg)
            continue

        # Check SLA
        created = datetime.fromisoformat(
            f["createdTime"].replace("Z", "+00:00")).replace(tzinfo=None)

        if created < sla_cutoff:
            late_files.append(name)  # Arrived BEFORE cutoff → LATE
        else:
            ready_files.append((name, f))  # Arrived AFTER cutoff → ON TIME

    # Alert Missing Files → Continue
    if missing_files:
        msg = "The following files are MISSING from this week run:\n" + \
            ", ".join(missing_files) + \
            "\n\nPipeline will continue with available files."
        logging.warning(msg)
        send_alert("PIPELINE ALERT - Missing Files", msg)

    # Alert Late Files → Continue
    if late_files:
        alert_msg = "The following files arrived LATE (outside " + str(SLA_HOURS) + "-hour SLA):\n" + ", ".join(
            late_files) + "\n\nPipeline will continue with on-time files."
        logging.warning(alert_msg)
        send_alert("PIPELINE ALERT - Late Files", alert_msg)

    # Stop if nothing to process
    if not ready_files:
        logging.warning("No files available for processing. Pipeline stopped.")
        send_alert("PIPELINE STOPPED - No Files",
                   "All files missing or late for this week. Nothing to process.")
        return []

    logging.info(str(len(ready_files)) + " file(s) ready for download.")

    # Download Ready Files — SKIP if already exists
    for name, f in ready_files:
        dest = os.path.join(LANDING_FOLDER, name)

        if os.path.exists(dest):
            logging.info("File already exists locally: " +
                         name + " - skipping download.")
            downloaded_paths.append(dest)
            continue

        logging.info("Downloading: " + name)
        request = service.files().get_media(fileId=f["id"])
        with io.FileIO(dest, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        downloaded_paths.append(dest)
    logging.info("\033[92m=== SENSOR COMPLETE ===\033[0m")
    return downloaded_paths


def main():
    setup_logging()
    check_and_download()


if __name__ == "__main__":
    main()
