"""
Notification module for sending alerts via Slack and Email.
Standardized alert format across all pipeline stages.
"""
import logging
import smtplib
import socket
import platform
import requests
from datetime import datetime, timezone
from email.mime.text import MIMEText
from python.config import SLACK_WEBHOOK_URL, SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, NOTIFICATION_EMAIL
from python.logger import setup_logging


def send_alert(subject, message):
    full_msg = subject + "\n\n" + message
    logging.info(full_msg)

    # Send Slack
    if SLACK_WEBHOOK_URL:
        try:
            requests.post(SLACK_WEBHOOK_URL, json={
                          "text": full_msg}, timeout=10)
            logging.info("Slack alert sent")
        except Exception as e:
            logging.error("Slack failed: " + str(e))

    # Send Email
    if all([SMTP_USER, SMTP_PASSWORD, NOTIFICATION_EMAIL]):
        try:
            msg = MIMEText(message)
            msg["Subject"] = subject
            msg["From"] = SMTP_USER
            msg["To"] = NOTIFICATION_EMAIL
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
            logging.info("Email alert sent")
        except Exception as e:
            logging.error("Email failed: " + str(e))


# Generate consistent Run ID for every pipeline execution
RUN_ID = datetime.now(timezone.utc).strftime(
    "%Y%m%d_%H%M%S") + "-" + socket.gethostname()
LINE = "----------------------------------------"


def build_alert_payload(event_type, dataset_name, **kwargs):
    """
    Standardized alert payload - same structure across ALL events.
    event_type: SLA_MISS | SENSOR_COMPLETE | PRE_VALIDATION_FAIL | PRE_VALIDATION_SUMMARY | TASK_ERROR | POST_VALIDATION_FAIL | RUN_SUCCESS
    """
    base = {
        "event_type": event_type,
        "run_id": RUN_ID,
        "dataset": dataset_name,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "environment": platform.node()
    }
    base.update(kwargs)
    return base


def format_alert_message(payload):
    """Convert payload to clean, consistent message format."""
    et = payload["event_type"]
    title = f"PIPELINE {et.replace('_', ' ')}: Run {payload['run_id']}"

    body = f"""
Run ID:     {payload['run_id']}
Dataset:    {payload['dataset']}
Timestamp:  {payload['timestamp']}
Host:       {payload['environment']}
{LINE}
"""

    # SLA MISS - expected vs arrival time
    if et == "SLA_MISS":
        body += f"""
Scheduled Drop:   {payload.get('scheduled_drop', 'N/A')}
SLA Deadline:     {payload.get('sla_deadline', 'N/A')}
Arrival Time:     {payload.get('arrival_time', 'N/A')}
Elapsed Time:     {payload.get('elapsed_minutes', 'N/A')} minutes
Status:           MISSED DEADLINE
"""

    # SENSOR COMPLETE - full SLA + file summary
    elif et == "SENSOR_COMPLETE":
        file_list = payload.get('file_list', [])
        files_block = "\n".join(
            f"- {f}" for f in file_list) if file_list else "- None"
        body += f"""
Scheduled Drop:   {payload.get('scheduled_drop', 'N/A')}
SLA Deadline:     {payload.get('sla_deadline', 'N/A')}
Check Time:       {payload.get('check_time', 'N/A')}
SLA Status:       {payload.get('sla_status', 'N/A')}

Summary
Expected:         {payload.get('count_expected', 0)}
Downloaded:       {payload.get('count_downloaded', 0)}
Skipped:          {payload.get('count_skipped', 0)}
Missing:          {payload.get('count_missing', 0)}

Files Processed
{files_block}
"""

    # PRE-VALIDATION FAILURE - per-file failure
    elif et == "PRE_VALIDATION_FAIL":
        rules_text = payload.get('failed_rules_text', 'No details')
        body += f"""
Failed Rules:     {payload.get('failed_rules_count', 0)}
Quarantine Path:  {payload.get('quarantine_path', 'N/A')}
Rows in File:     {payload.get('file_rows', 'N/A')}
Cascade-Skipped:  {payload.get('cascade_skipped', 'None')}

Issues
{rules_text}
"""

    # PRE-VALIDATION SUMMARY - overall result with file lists
    elif et == "PRE_VALIDATION_SUMMARY":
        passed = payload.get('passed_files', [])
        quarantined = payload.get('quarantined_files', [])
        passed_block = "\n".join(
            f"- {f}" for f in passed) if passed else "- None"
        quar_block = "\n".join(
            f"- {f}" for f in quarantined) if quarantined else "- None"
        body += f"""
Files Scanned:    {payload.get('count_scanned', 0)}
Passed:           {payload.get('count_passed', 0)}
Quarantined:      {payload.get('count_quarantined', 0)}

Passed Files
{passed_block}

Quarantined Files
{quar_block}

Next Steps
{payload.get('count_passed', 0)} file(s) ready for load.
{payload.get('count_quarantined', 0)} file(s) moved to quarantine.
"""

    # TASK / INFRASTRUCTURE ERROR -
    elif et == "TASK_ERROR":
        body += f"""
Task:             {payload.get('task_name', 'Unknown')}
Error Summary:    {payload.get('error_summary', 'Unknown error')}
Log Reference:    {payload.get('log_ref', 'N/A')}
Cascade-Skipped:  {payload.get('cascade_skipped', 'All downstream')}
"""

    # POST-VALIDATION FAILURE -
    elif et == "POST_VALIDATION_FAIL":
        rules_text = payload.get('failed_rules_text', 'No details')
        body += f"""
Failed Rules:     {payload.get('failed_rules_count', 0)}
Tables Affected:  {payload.get('tables_affected', 'None')}

Failed Business Rules
{rules_text}
"""

    # RUN SUCCESS - both gates passed, final counts
    elif et == "RUN_SUCCESS":
        tables = payload.get('loaded_tables', [])
        tables_block = "\n".join(
            f"- {t}" for t in tables) if tables else "- None"
        body += f"""
Gate 1 (Pre-Validation): PASSED
Gate 2 (Post-Load):      PASSED

Counts
- Read:           {payload.get('count_read', 0)}
- Validated:      {payload.get('count_validated', 0)}
- Loaded:         {payload.get('count_loaded', 0)}

Tables Loaded
{tables_block}

Pipeline completed successfully.
"""

    return title, body.strip()


# --- PUBLIC CONVENIENCE FUNCTIONS ---

def notify_sla_miss(dataset_name, scheduled_drop, sla_deadline, arrival_time, elapsed_minutes):
    payload = build_alert_payload(
        event_type="SLA_MISS",
        dataset_name=dataset_name,
        scheduled_drop=scheduled_drop,
        sla_deadline=sla_deadline,
        arrival_time=arrival_time,
        elapsed_minutes=elapsed_minutes
    )
    subject, body = format_alert_message(payload)
    send_alert(subject, body)


def notify_sensor_complete(dataset_name, count_expected=0, count_downloaded=0, count_skipped=0,
                           count_missing=0, scheduled_drop="N/A", sla_deadline="N/A",
                           check_time="N/A", sla_status="N/A", file_list=None):
    payload = build_alert_payload(
        event_type="SENSOR_COMPLETE",
        dataset_name=dataset_name,
        count_expected=count_expected,
        count_downloaded=count_downloaded,
        count_skipped=count_skipped,
        count_missing=count_missing,
        scheduled_drop=scheduled_drop,
        sla_deadline=sla_deadline,
        check_time=check_time,
        sla_status=sla_status,
        file_list=file_list or []
    )
    subject, body = format_alert_message(payload)
    send_alert(subject, body)


def notify_pre_validation_failure(dataset_name, failed_rules_list, quarantine_path, file_rows="N/A", cascade_skipped=None):
    count = len(failed_rules_list)
    rules_text = "\n".join([f"- {r}" for r in failed_rules_list])
    payload = build_alert_payload(
        event_type="PRE_VALIDATION_FAIL",
        dataset_name=dataset_name,
        failed_rules_count=count,
        failed_rules_text=rules_text,
        quarantine_path=quarantine_path,
        file_rows=file_rows,
        cascade_skipped=", ".join(
            cascade_skipped) if cascade_skipped else "None"
    )
    subject, body = format_alert_message(payload)
    send_alert(subject, body)


def notify_pre_validation_summary(count_scanned, count_passed, count_quarantined, passed_files, quarantined_files):
    payload = build_alert_payload(
        event_type="PRE_VALIDATION_SUMMARY",
        dataset_name=f"{count_scanned} file(s) scanned",
        count_scanned=count_scanned,
        count_passed=count_passed,
        count_quarantined=count_quarantined,
        passed_files=passed_files,
        quarantined_files=quarantined_files
    )
    subject, body = format_alert_message(payload)
    send_alert(subject, body)


def notify_task_error(task_name, error_exception, log_ref=None, cascade_skipped_datasets=None):
    error_summary = str(error_exception)[:300]
    payload = build_alert_payload(
        event_type="TASK_ERROR",
        dataset_name="Multiple / See Details",
        task_name=task_name,
        error_summary=error_summary,
        log_ref=log_ref or "Check sensor/validation log at timestamp",
        cascade_skipped=", ".join(
            cascade_skipped_datasets) if cascade_skipped_datasets else "All downstream"
    )
    subject, body = format_alert_message(payload)
    send_alert(subject, body)


def notify_post_validation_failure(dataset_name, failed_rules_list, tables_affected):
    count = len(failed_rules_list)
    rules_text = "\n".join([f"- {r}" for r in failed_rules_list])
    payload = build_alert_payload(
        event_type="POST_VALIDATION_FAIL",
        dataset_name=dataset_name,
        failed_rules_count=count,
        failed_rules_text=rules_text,
        tables_affected=", ".join(tables_affected)
    )
    subject, body = format_alert_message(payload)
    send_alert(subject, body)


def notify_run_success(count_read, count_validated, count_loaded, loaded_tables=None):
    payload = build_alert_payload(
        event_type="RUN_SUCCESS",
        dataset_name="All Files",
        count_read=count_read,
        count_validated=count_validated,
        count_loaded=count_loaded,
        loaded_tables=loaded_tables or []
    )
    subject, body = format_alert_message(payload)
    send_alert(subject, body)


def main():
    setup_logging()
    send_alert("Test Alert", "Notification module loaded successfully.")


if __name__ == "__main__":
    main()
