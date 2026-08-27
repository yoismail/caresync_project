"""
Notification module for sending alerts via Slack and Email.
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


def build_alert_payload(event_type, dataset_name, **kwargs):
    """
    Standardized alert payload — same structure across ALL events.

    event_type: PRE_VALIDATION_FAIL | TASK_ERROR | POST_VALIDATION_FAIL | RUN_SUCCESS | SENSOR_COMPLETE
    """
    base = {
        "event_type": event_type,
        "run_id": RUN_ID,
        "dataset": dataset_name,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "environment": platform.node()
    }

    # Merge event-specific fields
    base.update(kwargs)
    return base


def format_alert_message(payload):
    """Convert payload to clean Slack/Email message"""
    et = payload["event_type"]
    title = f"PIPELINE {et.replace('_', ' ')} — Run {payload['run_id']}"

    body = f"""
Run ID:     {payload['run_id']}
Dataset:    {payload['dataset']}
Timestamp:  {payload['timestamp']}
Host:       {payload['environment']}
"""

    # SENSOR COMPLETE
    if et == "SENSOR_COMPLETE":
        body += f"""
Files Downloaded: {payload.get('count_downloaded', 0)}
Ready for pre-validation.
"""

    # PRE-VALIDATION FAILURE
    elif et == "PRE_VALIDATION_FAIL":
        body += f"""
Failed Rules Count: {payload.get('failed_rules_count', 0)}
Quarantined At:     {payload.get('quarantine_path', 'N/A')}
Cascade-Skipped:    {payload.get('cascade_skipped', 'None')}

Failed Rules:
{payload.get('failed_rules_text', 'No details')}
"""

    # TASK / INFRASTRUCTURE ERROR
    elif et == "TASK_ERROR":
        body += f"""
Task:            {payload.get('task_name', 'Unknown')}
Error Summary:   {payload.get('error_summary', 'Unknown error')}
Log Reference:   {payload.get('log_ref', 'N/A')}
Cascade-Skipped: {payload.get('cascade_skipped', 'All downstream')}
"""

    # POST-VALIDATION FAILURE
    elif et == "POST_VALIDATION_FAIL":
        body += f"""
Failed Rules Count: {payload.get('failed_rules_count', 0)}
Tables Affected:    {payload.get('tables_affected', 'None')}

Failed Business Rules:
{payload.get('failed_rules_text', 'No details')}
"""

    # RUN SUCCESS
    elif et == "RUN_SUCCESS":
        body += f"""
Gate 1 (Pre-Validation): PASSED
Gate 2 (Post-Load):      PASSED

Counts:
- Read:       {payload.get('count_read', 0)}
- Validated:  {payload.get('count_validated', 0)}
- Loaded:     {payload.get('count_loaded', 0)}
"""

    return title, body.strip()


# Convenience Functions
def notify_sensor_complete(dataset_name, count_downloaded):
    payload = build_alert_payload(
        event_type="SENSOR_COMPLETE",
        dataset_name=dataset_name,
        count_downloaded=count_downloaded
    )
    subject, body = format_alert_message(payload)
    send_alert(subject, body)


def notify_pre_validation_failure(dataset_name, failed_rules_list, quarantine_path, cascade_skipped=None):
    count = len(failed_rules_list)
    rules_text = "\n".join([f"- {r}" for r in failed_rules_list])
    payload = build_alert_payload(
        event_type="PRE_VALIDATION_FAIL",
        dataset_name=dataset_name,
        failed_rules_count=count,
        failed_rules_text=rules_text,
        quarantine_path=quarantine_path,
        cascade_skipped=", ".join(
            cascade_skipped) if cascade_skipped else "None"
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


def notify_run_success(dataset_name, count_read, count_validated, count_loaded):
    payload = build_alert_payload(
        event_type="RUN_SUCCESS",
        dataset_name=dataset_name,
        count_read=count_read,
        count_validated=count_validated,
        count_loaded=count_loaded
    )
    subject, body = format_alert_message(payload)
    send_alert(subject, body)


def main():
    # Setup logging for standalone testing
    setup_logging()
    send_alert("Test Alert", "This is a test alert message.")


if __name__ == "__main__":
    main()
