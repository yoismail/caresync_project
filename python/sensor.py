"""
This script connects to a specified Google Drive folder, 
checks for the presence of expected files, 
and downloads them to a local landing folder. 
It also checks if the files arrived within the defined SLA window. 
If any files are missing, late, or empty, it sends alerts via Slack and email.
"""

import logging
import os
import io
import json
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from python.logger import setup_logging, section
from python.config import (
    SCOPES, FOLDER_ID, LANDING_FOLDER, SLA_HOURS,
    EXPECTED_FILES, SCHEDULED_DROP_TIME
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
    section("STARTING SENSOR CHECK")
    ensure_landing_folder()

    service = connect_to_drive()

    # SLA TIMES, based on scheduled drop time and SLA hours from config.py
    scheduled_time = SCHEDULED_DROP_TIME
    deadline_time = scheduled_time + timedelta(hours=SLA_HOURS)
    sla_cutoff = deadline_time  # File must be have landed in Google Drive BY deadline

    logging.info("Scheduled Drop Time: " +
                 scheduled_time.strftime("%Y-%m-%d %H:%M UTC"))
    logging.info("SLA Deadline (+" + str(SLA_HOURS) + "h): " +
                 deadline_time.strftime("%Y-%m-%d %H:%M UTC"))

    # List files in Drive folder
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
    report_entries = []

    # Check each expected file
    for name in EXPECTED_FILES:
        entry = {
            "filename": name,
            "scheduled_time": scheduled_time.strftime("%Y-%m-%d %H:%M:%S"),
            "deadline_time": deadline_time.strftime("%Y-%m-%d %H:%M:%S"),
            "found": False,
            "arrived_time": None,
            "elapsed_minutes": None,
            "sla_met": None,
            "status": "MISSING"
        }

        if name not in drive_files:
            missing_files.append(name)
            report_entries.append(entry)
            continue

        f = drive_files[name]
        entry["found"] = True

        # Check for zero-byte file
        if f.get("size", "0") == "0" or int(f.get("size", 0)) == 0:
            zero_byte_files.append(name)
            entry["status"] = "EMPTY"
            alert_msg = "File " + name + \
                " is EMPTY (0 bytes). Will not download."
            logging.warning(alert_msg)
            send_alert("PIPELINE ALERT - Empty File: " + name, alert_msg)
            report_entries.append(entry)
            continue

        # Parse creation time
        created = datetime.fromisoformat(
            f["createdTime"].replace("Z", "+00:00")
        )
        entry["arrived_time"] = created.strftime("%Y-%m-%d %H:%M:%S")

        # Calculate elapsed time
        elapsed = created - scheduled_time
        entry["elapsed_minutes"] = round(elapsed.total_seconds() / 60, 1)

        # Check SLA
        if created > deadline_time:
            late_files.append((name, entry["elapsed_minutes"]))
            entry["sla_met"] = False
            entry["status"] = "LATE"
        else:
            ready_files.append((name, f))
            entry["sla_met"] = True
            entry["status"] = "ON TIME"

        report_entries.append(entry)

    # Save machine-readable report
    report = {
        "batch_checked": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "scheduled_time": scheduled_time.strftime("%Y-%m-%d %H:%M:%S"),
        "deadline_time": deadline_time.strftime("%Y-%m-%d %H:%M:%S"),
        "sla_hours": SLA_HOURS,
        "files": report_entries
    }

    report_path = os.path.join(LANDING_FOLDER, "sla_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logging.info("SLA Report saved: " + report_path)

    # Alert: Missing files
    if missing_files:
        msg = "The following files are MISSING:\n- " + "\n- ".join(missing_files) + \
              "\n\nScheduled: " + scheduled_time.strftime("%Y-%m-%d %H:%M UTC") + \
              "\nDeadline:  " + deadline_time.strftime("%Y-%m-%d %H:%M UTC") + \
              "\n\nPipeline continues with available files."
        logging.warning(msg)
        send_alert("SLA ALERT - Missing Files", msg)

    # Alert: Late files — with elapsed time
    if late_files:
        lines = []
        for name, mins in late_files:
            lines.append(f"- {name}: {mins} minutes LATE")
        alert_msg = "SLA MISSED - Files arrived AFTER deadline:\n" + \
            "\n".join(lines) + \
            f"\n\nScheduled: {scheduled_time.strftime('%Y-%m-%d %H:%M UTC')}" + \
            f"\nDeadline:  {deadline_time.strftime('%Y-%m-%d %H:%M UTC')}" + \
            "\n\nPipeline continues with on-time files."
        logging.warning(alert_msg)
        send_alert("SLA ALERT - Files Missed Deadline", alert_msg)

    # Stop if nothing to process
    if not ready_files:
        logging.warning("No files available for processing. Pipeline stopped.")
        send_alert("PIPELINE STOPPED - No Files",
                   "All files missing, empty, or late. Nothing to process.")
        return []

    logging.info(str(len(ready_files)) + " file(s) ready for download.")

    # Download ready files — skip if already exists
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

    # Final alert
    send_alert("PIPELINE ALERT - Files Downloaded",
               "Files downloaded successfully: " + ", ".join([name for name, _ in ready_files]))

    logging.info("SENSOR COMPLETE....")
    return downloaded_paths


def main():
    setup_logging()
    check_and_download()


if __name__ == "__main__":
    main()
