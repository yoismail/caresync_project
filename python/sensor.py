"""
This script connects to a specified Google Drive folder,
checks for the presence of expected files,
and downloads them to a local landing folder.
It also checks if the files arrived within the defined SLA window.
If any files are missing, late, empty, or early, it sends alerts via Slack and email.
DESIGNED FOR SWAPABILITY: All file-source logic is isolated.
To swap → SFTP: replace ONLY the file-listing/timestamp section.
SLA checks, reporting, alerts, and pipeline flow → ZERO changes.
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
    EXPECTED_FILES, SCHEDULED_DROP_TIME, GOOGLE_CREDENTIALS
)
from python.notifications import (
    send_alert,
    notify_sensor_complete
)


def connect_to_drive():
    service_account_json = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT")
    if service_account_json and service_account_json.strip():
        # GitHub Actions / .env path — use directly from env
        creds = service_account.Credentials.from_service_account_info(
            json.loads(service_account_json), scopes=SCOPES
        )
    else:
        # Local dev fallback — use file if env not set
        creds = service_account.Credentials.from_service_account_file(
            "service-account-key.json", scopes=SCOPES
        )
    return build("drive", "v3", credentials=creds)


def ensure_landing_folder():
    if not os.path.exists(LANDING_FOLDER):
        os.makedirs(LANDING_FOLDER, exist_ok=True)


# ==================================================
# INTERFACE LAYER - FILE SOURCE
# SWAP THIS BLOCK FOR SFTP IN WEEK 3
# ==================================================
def fetch_source_files(service):
    """
    Get list of files, their arrival times, size, and IDs.
    SWAP THIS FUNCTION for SFTP later - rest of pipeline NEVER changes.
    Returns: {filename: {"arrived": datetime(UTC), "size": int, "id": str}}
    """
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType != 'application/vnd.google-apps.folder'",
        fields="files(name, createdTime, size, id)"
    ).execute()
    source_files = {}
    for f in results.get("files", []):
        name = f["name"]
        created = datetime.fromisoformat(
            f["createdTime"].replace("Z", "+00:00"))
        source_files[name] = {
            "arrived": created,
            "size": int(f.get("size", 0)),
            "id": f["id"],
            "raw": f
        }
    return source_files


def download_file(source_info, destination_path, service):
    """Download a single file from source to landing folder."""
    file_id = source_info["id"]
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(destination_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return True


# ==================================================
# END OF INTERFACE - EVERYTHING BELOW STAYS THE SAME
# ==================================================
def check_and_download():
    section("STARTING SENSOR CHECK")
    ensure_landing_folder()
    service = connect_to_drive()

    # SLA TIMES
    scheduled_time = SCHEDULED_DROP_TIME
    deadline_time = scheduled_time + timedelta(hours=SLA_HOURS)
    check_time = datetime.now(timezone.utc)
    scheduled_str = scheduled_time.strftime("%Y-%m-%d %H:%M UTC")
    deadline_str = deadline_time.strftime("%Y-%m-%d %H:%M UTC")
    check_str = check_time.strftime("%Y-%m-%d %H:%M UTC")

    logging.info("Scheduled Drop Time: " + scheduled_str)
    logging.info("SLA Deadline (+" + str(SLA_HOURS) + "h): " + deadline_str)
    logging.info("Sensor Check Time: " + check_str)

    source_files = fetch_source_files(service)

    missing_files = []
    late_files = []
    early_files = []
    ready_files = []
    zero_byte_files = []
    downloaded_paths = []
    skipped_local = []
    report_entries = []

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

        if name not in source_files:
            missing_files.append(name)
            report_entries.append(entry)
            continue

        info = source_files[name]
        entry["found"] = True

        if info["size"] == 0:
            zero_byte_files.append(name)
            entry["status"] = "EMPTY"
            alert_msg = f"File {name} is EMPTY (0 bytes). Will not download."
            logging.warning(alert_msg)
            send_alert("PIPELINE ALERT - Empty File: " + name, alert_msg)
            report_entries.append(entry)
            continue

        arrived = info["arrived"]
        entry["arrived_time"] = arrived.strftime("%Y-%m-%d %H:%M:%S UTC")
        elapsed = arrived - scheduled_time
        entry["elapsed_minutes"] = round(elapsed.total_seconds() / 60, 1)

        if arrived < scheduled_time:
            early_files.append(name)
            entry["sla_met"] = False
            entry["status"] = "TOO EARLY"
        elif arrived > deadline_time:
            late_files.append(name)
            entry["sla_met"] = False
            entry["status"] = "LATE"
        else:
            ready_files.append((name, info))
            entry["sla_met"] = True
            entry["status"] = "ON TIME"

        report_entries.append(entry)

    # Save report
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

    # Early alert
    if early_files:
        lines = [
            f"- {name}: arrived {abs(next(e['elapsed_minutes'] for e in report_entries if e['filename'] == name)):.1f} minutes BEFORE scheduled time."
            for name in early_files
        ]
        alert_msg = (
            "FILES ARRIVED TOO EARLY - OUTSIDE SLA WINDOW (NOT DOWNLOADED):\n" +
            "\n".join(lines) +
            f"\n\nScheduled: {scheduled_str}\nDeadline:  {deadline_str}\n" +
            "Files must arrive WITHIN the SLA window. Not downloaded."
        )
        logging.warning(alert_msg)
        send_alert("PIPELINE ALERT: Files Arrived Too Early", alert_msg)

    # Missing alert
    if missing_files:
        msg = (
            "The following files are MISSING:\n- " + "\n- ".join(missing_files) +
            f"\n\nScheduled: {scheduled_str}\nDeadline:  {deadline_str}\n" +
            "Pipeline continues with available files."
        )
        logging.warning(msg)
        send_alert("SLA ALERT: Missing Files", msg)

    # Late alert
    if late_files:
        lines = []
        for name in late_files:
            mins = next(e["elapsed_minutes"]
                        for e in report_entries if e["filename"] == name)
            lines.append(f"- {name}: {mins:.1f} minutes LATE")
        alert_msg = (
            "SLA MISSED: FILES ARRIVED AFTER DEADLINE (NOT DOWNLOADED):\n" +
            "\n".join(lines) +
            f"\n\nScheduled: {scheduled_str}\nDeadline:  {deadline_str}\n" +
            "Files did not arrive by deadline. Not downloaded."
        )
        logging.warning(alert_msg)
        send_alert("SLA ALERT: Files Missed Deadline", alert_msg)

    # Nothing ready → stop
    if not ready_files:
        logging.warning("No files available for processing. Pipeline stopped.")
        send_alert("PIPELINE STOPPED - No Files",
                   "All files missing, early, empty, or late. Nothing to process.")
        notify_sensor_complete(
            dataset_name="Sensor Check Complete",
            files_found=[],
            files_missing=missing_files,
            files_late=late_files
        )
        return []

    # Download ready files
    for name, info in ready_files:
        dest = os.path.join(LANDING_FOLDER, name)
        if os.path.exists(dest):
            logging.info(
                f"File already exists locally: {name} - skipping download.")
            skipped_local.append(name)
            downloaded_paths.append(dest)
            continue
        logging.info("Downloading: " + name)
        download_file(info, dest, service)
        downloaded_paths.append(dest)

    # Final alert — matches new unified signature
    notify_sensor_complete(
        dataset_name=f"{len(ready_files)} file(s) ready",
        files_found=[n for n, _ in ready_files],
        files_missing=missing_files,
        files_late=late_files
    )

    logging.info("SENSOR COMPLETE")
    return downloaded_paths


def main():
    setup_logging()
    downloaded = check_and_download()
    if not downloaded:
        logging.info("Sensor returned no files — pipeline will stop here.")
    return downloaded


if __name__ == "__main__":
    main()
