"""
This script connects to a specified Google Drive folder,
checks for the presence of expected files,
and downloads them to a local landing folder.
It also checks if the files arrived within the defined SLA window.
If any files are missing, late, empty, or early, it sends alerts via Slack and email.
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
from python.notifications import (
    send_alert,
    notify_sensor_complete
)


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

    # SLA TIMES - based on scheduled drop time and SLA hours from config.py
    scheduled_time = SCHEDULED_DROP_TIME
    deadline_time = scheduled_time + timedelta(hours=SLA_HOURS)
    check_time = datetime.now(timezone.utc)

    scheduled_str = scheduled_time.strftime("%Y-%m-%d %H:%M UTC")
    deadline_str = deadline_time.strftime("%Y-%m-%d %H:%M UTC")
    check_str = check_time.strftime("%Y-%m-%d %H:%M UTC")

    logging.info("Scheduled Drop Time: " + scheduled_str)
    logging.info("SLA Deadline (+" + str(SLA_HOURS) + "h): " + deadline_str)
    logging.info("Sensor Check Time: " + check_str)

    # List files in Drive folder
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType != 'application/vnd.google-apps.folder'",
        fields="files(name, createdTime, size, id)"
    ).execute()
    drive_files = {f["name"]: f for f in results.get("files", [])}

    missing_files = []
    late_files = []
    early_files = []
    ready_files = []
    zero_byte_files = []
    downloaded_paths = []
    skipped_local = []
    report_entries = []
    file_list_for_alert = []

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
        size = int(f.get("size", 0))
        if size == 0:
            zero_byte_files.append(name)
            entry["status"] = "EMPTY"
            alert_msg = "File " + name + \
                " is EMPTY (0 bytes). Will not download."
            logging.warning(alert_msg)
            send_alert("PIPELINE ALERT - Empty File: " + name, alert_msg)
            report_entries.append(entry)
            continue

        # Parse creation time - keep timezone-aware
        created = datetime.fromisoformat(
            f["createdTime"].replace("Z", "+00:00")
        )
        entry["arrived_time"] = created.strftime("%Y-%m-%d %H:%M:%S UTC")

        # Calculate elapsed time
        elapsed = created - scheduled_time
        entry["elapsed_minutes"] = round(elapsed.total_seconds() / 60, 1)

        # STRICT SLA WINDOW CHECK
        # Only files between scheduled_time and deadline_time are downloaded
        # Anything outside triggers alert and is skipped
        if created < scheduled_time:
            # Arrived BEFORE scheduled time - TOO EARLY
            early_files.append((name, entry["elapsed_minutes"]))
            entry["sla_met"] = False
            entry["status"] = "TOO EARLY"
        elif created > deadline_time:
            # Arrived AFTER deadline - LATE
            late_files.append((name, entry["elapsed_minutes"]))
            entry["sla_met"] = False
            entry["status"] = "LATE"
        else:
            # Arrived within SLA window - ON TIME
            ready_files.append((name, f))
            entry["sla_met"] = True
            entry["status"] = "ON TIME"
            file_list_for_alert.append(name)

        report_entries.append(entry)

    # Save machine-readable report
    report = {
        "batch_checked": check_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "scheduled_time": scheduled_time.strftime("%Y-%m-%d %H:%M:%S"),
        "deadline_time": deadline_time.strftime("%Y-%m-%d %H:%M:%S"),
        "sla_hours": SLA_HOURS,
        "files": report_entries
    }
    report_path = os.path.join(LANDING_FOLDER, "sla_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logging.info("SLA Report saved: " + report_path)

    # ALERT: FILES ARRIVED TOO EARLY
    if early_files:
        lines = []
        for name, mins in early_files:
            lines.append(
                f"- {name}: arrived {abs(mins):.1f} minutes BEFORE scheduled time.")
        alert_msg = "FILES ARRIVED TOO EARLY - OUTSIDE SLA WINDOW (NOT DOWNLOADED):\n" + \
                    "\n".join(lines) + \
                    f"\n\nScheduled: {scheduled_str}\nDeadline:  {deadline_str}\n" + \
                    "Files must arrive WITHIN the SLA window. Not downloaded."
        logging.warning(alert_msg)
        send_alert("PIPELINE ALERT - Files Arrived Too Early", alert_msg)

    # ALERT: MISSING FILES
    if missing_files:
        msg = "The following files are MISSING:\n- " + "\n- ".join(missing_files) + \
              f"\n\nScheduled: {scheduled_str}\nDeadline:  {deadline_str}\n" + \
              "Pipeline continues with available files."
        logging.warning(msg)
        send_alert("SLA ALERT - Missing Files", msg)

    # ALERT: LATE FILES
    if late_files:
        lines = []
        for name, mins in late_files:
            lines.append(f"- {name}: {mins:.1f} minutes LATE")
        alert_msg = "SLA MISSED - FILES ARRIVED AFTER DEADLINE (NOT DOWNLOADED):\n" + \
                    "\n".join(lines) + \
                    f"\n\nScheduled: {scheduled_str}\nDeadline:  {deadline_str}\n" + \
                    "Files did not arrive by deadline. Not downloaded."
        logging.warning(alert_msg)
        send_alert("SLA ALERT - Files Missed Deadline", alert_msg)

    # ACCURATE SLA STATUS CALCULATION
    files_on_time = len(ready_files)
    files_missing = len(missing_files)
    files_late = len(late_files)
    files_early = len(early_files)
    files_empty = len(zero_byte_files)
    deadline_passed = check_time > deadline_time
    any_issues = files_missing > 0 or files_late > 0 or files_early > 0 or files_empty > 0

    if any_issues:
        parts = []
        if files_missing:
            parts.append(f"{files_missing} MISSING")
        if files_late:
            parts.append(f"{files_late} LATE")
        if files_early:
            parts.append(f"{files_early} TOO EARLY")
        if files_empty:
            parts.append(f"{files_empty} EMPTY")
        sla_status = "ISSUES: " + ", ".join(parts)
    elif deadline_passed:
        sla_status = "ALL FILES ON TIME - DEADLINE PASSED"
    else:
        mins_remaining = round(
            (deadline_time - check_time).total_seconds() / 60)
        sla_status = f"CHECK IN PROGRESS - {mins_remaining} min until deadline"

    logging.info("SLA Status: " + sla_status)

    # Stop if nothing to process
    if not ready_files:
        logging.warning("No files available for processing. Pipeline stopped.")
        send_alert("PIPELINE STOPPED - No Files",
                   "All files missing, early, empty, or late. Nothing to process.")
        notify_sensor_complete(
            dataset_name="Sensor Check Complete",
            count_expected=len(EXPECTED_FILES),
            count_downloaded=0,
            count_skipped=files_missing + files_late + files_early + files_empty,
            count_missing=files_missing,
            scheduled_drop=scheduled_str,
            sla_deadline=deadline_str,
            check_time=check_str,
            sla_status=sla_status,
            file_list=file_list_for_alert
        )
        return []

    logging.info(str(len(ready_files)) + " file(s) ready for download.")

    # Download ready files - skip if already exists locally
    for name, f in ready_files:
        dest = os.path.join(LANDING_FOLDER, name)
        if os.path.exists(dest):
            logging.info("File already exists locally: " +
                         name + " - skipping download.")
            skipped_local.append(name)
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

    # Update file list with status: downloaded or already local
    for i in range(len(file_list_for_alert)):
        name = file_list_for_alert[i]
        if name in skipped_local:
            file_list_for_alert[i] = name + " (already local)"
        else:
            file_list_for_alert[i] = name + " (downloaded)"

    # Final standardized sensor complete alert
    total_skipped = len(skipped_local) + files_missing + \
        files_late + files_early + files_empty
    notify_sensor_complete(
        dataset_name=f"{len(ready_files)} file(s) ready",
        count_expected=len(EXPECTED_FILES),
        count_downloaded=len(downloaded_paths),
        count_skipped=total_skipped,
        count_missing=files_missing,
        scheduled_drop=scheduled_str,
        sla_deadline=deadline_str,
        check_time=check_str,
        sla_status=sla_status,
        file_list=file_list_for_alert
    )

    logging.info("SENSOR COMPLETE")
    return downloaded_paths


def main():
    setup_logging()
    check_and_download()


if __name__ == "__main__":
    main()
