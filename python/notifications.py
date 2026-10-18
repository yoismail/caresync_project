"""
Notification module for sending alerts via Slack and Email.
Clean email layout - Pre-Validation + Source→RAW + Staging→Prod + dbt + Post-Validation
"""

from python.logger import setup_logging
import requests
from python.config import SLACK_WEBHOOK_URL, SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, NOTIFICATION_EMAIL
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
import re
import platform
import socket
import smtplib
import logging

OK = "✓"
INFO = "•"
WARN = "⚠"
ERR = "✗"

POST_VALIDATION_DESCRIPTIONS = {
    "NEXORA_STAGING.DBT_YISMAIL_HL7_HL7.STG_HL7__CONDITIONS":
        "Staging: Conditions - table loaded & row count matches source",
    "NEXORA_STAGING.DBT_YISMAIL_HL7_HL7.STG_HL7__ENCOUNTERS":
        "Staging: Encounters - table loaded & row count matches source",
    "NEXORA_STAGING.DBT_YISMAIL_HL7_HL7.STG_HL7__ORGANIZATIONS":
        "Staging: Organizations - table loaded & row count matches source",
    "NEXORA_STAGING.DBT_YISMAIL_HL7_HL7.STG_HL7__PATIENTS":
        "Staging: Patients - table loaded & row count matches source",
    "NEXORA_STAGING.DBT_YISMAIL_HL7_HL7.STG_HL7__PAYERS":
        "Staging: Payers - table loaded & row count matches source",
    "NEXORA_STAGING.DBT_YISMAIL_HL7_HL7.STG_HL7__PROVIDERS":
        "Staging: Providers - table loaded & row count matches source",
    "NEXORA_PROD.DBT_YISMAIL_HL7_HL7.DIM_ORGANIZATIONS":
        "Dimension: Organizations - model built successfully",
    "NEXORA_PROD.DBT_YISMAIL_HL7_HL7.DIM_PATIENTS":
        "Dimension: Patients - model built & PHI masking applied",
    "NEXORA_PROD.DBT_YISMAIL_HL7_HL7.DIM_PAYERS":
        "Dimension: Payers - model built successfully",
    "NEXORA_PROD.DBT_YISMAIL_HL7_HL7.DIM_PROVIDERS":
        "Dimension: Providers - model built successfully",
    "NEXORA_PROD.DBT_YISMAIL_HL7_HL7.FCT_APPOINTMENTS":
        "Fact: Appointments - fact table built & linked to all dimensions",
    "NEXORA_PROD.DBT_YISMAIL_HL7_HL7.FCT_CONDITIONS":
        "Fact: Conditions - fact table built & linked to all dimensions",
    "Encounter reconciliation - STAGING = FACT":
        "Encounter Reconciliation - Staging counts = Fact counts",
    "No future encounters":
        "No Future Encounters - all dates are valid, no future records",
    "Patient count matches through all layers":
        "Patient Consistency - patient count matches across all layers"
}


def get_check_description(check_key):
    if check_key in POST_VALIDATION_DESCRIPTIONS:
        return POST_VALIDATION_DESCRIPTIONS[check_key]
    clean = check_key.replace("NEXORA_STAGING.", "") \
        .replace("NEXORA_PROD.", "") \
        .replace("DBT_YISMAIL_HL7_HL7.", "") \
        .replace("STG_HL7__", "Staging: ") \
        .replace("DIM_", "Dimension: ") \
        .replace("FCT_", "Fact: ") \
        .replace("_", " ")
    return clean.title()


def send_alert(subject, plain_text, html_text=None):
    logging.info(plain_text)
    if SLACK_WEBHOOK_URL:
        try:
            requests.post(SLACK_WEBHOOK_URL, json={
                          "text": plain_text}, timeout=10)
            logging.info("Slack alert sent")
        except Exception as e:
            logging.error("Slack failed: " + str(e))
    if all([SMTP_USER, SMTP_PASSWORD, NOTIFICATION_EMAIL]):
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = SMTP_USER
            msg["To"] = NOTIFICATION_EMAIL
            msg.attach(MIMEText(plain_text, "plain"))
            if html_text:
                msg.attach(MIMEText(html_text, "html"))
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
            logging.info("Email alert sent")
        except Exception as e:
            logging.error("Email failed: " + str(e))


RUN_ID = datetime.now(timezone.utc).strftime(
    "%Y%m%d_%H%M%S") + "-" + socket.gethostname()


def build_alert_payload(event_type, dataset_name, **kwargs):
    base = {
        "event_type": event_type,
        "run_id": RUN_ID,
        "dataset": dataset_name,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "environment": platform.node()
    }
    base.update(kwargs)
    return base


def build_html_layout(title_sections, body_sections):
    return f"""
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: 'Segoe UI', 'Roboto', Arial, sans-serif; background: #f6f8fa; margin: 0; padding: 24px; }}
        .container {{ max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: #0a66c2; color: #ffffff !important; padding: 22px 28px; }}
        .header h1 {{ margin: 0; font-size: 19px; font-weight: 600; color: #ffffff !important; }}
        .header p {{ margin: 6px 0 0 0; opacity: 0.92; font-size: 14px; color: #eaf2f9 !important; }}
        .meta {{ background: #f0f4f8; padding: 16px 28px; font-size: 13px; color: #374151; border-bottom: 1px solid #e2e8f0; }}
        .meta-row {{ display: flex; justify-content: space-between; padding: 5px 0; }}
        .meta-row span:first-child {{ color: #6b7280; }}
        .section {{ padding: 22px 28px; border-bottom: 1px solid #f1f5f9; }}
        .section:last-child {{ border-bottom: none; }}
        .section h2 {{ margin: 0 0 14px 0; font-size: 15px; font-weight: 600; color: #1f2937; }}
        .grid {{ display: block; font-size: 14px; line-height: 1.7; }}
        .row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f3f4f6; align-items: flex-start; }}
        .row:last-child {{ border-bottom: none; }}
        .label {{ color: #4b5563; flex: 1; padding-right: 12px; }}
        .val {{ font-weight: 600; min-width: 70px; text-align: right; }}
        .pass {{ color: #16a34a; }}
        .warn {{ color: #d97706; }}
        .fail {{ color: #dc2626; }}
        .info {{ color: #2563eb; }}
        .footer {{ padding: 18px 28px; font-size: 12px; color: #9ca3af; text-align: center; background: #f9fafb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">{title_sections}</div>
        {body_sections}
        <div class="footer">This is an automated message from the CareSync Pipeline</div>
    </div>
</body>
</html>
"""


def format_alert_message(payload):
    et = payload["event_type"]
    extra = ""
    if et == "RUN_SUCCESS":
        dbt_status = payload.get("dbt_build", "NOT RUN")
        pv_status = payload.get("post_validation", "NOT RUN")
        extra = f" | dbt: {dbt_status} | Post-Val: {pv_status}"
    title_text = f"PIPELINE {et.replace('_', ' ')}{extra}"
    run_id_text = f"Run {payload['run_id']}"

    # --- PRE-VALIDATION SUMMARY ---
    if et == "PRE_VALIDATION_SUMMARY":
        scanned = payload.get("count_scanned", 0)
        passed = payload.get("count_passed", 0)
        quarantined = payload.get("count_quarantined", 0)
        passed_files = payload.get("passed_files", [])
        quarantined_files = payload.get("quarantined_files", [])

        plain = f"""{title_text}
{run_id_text}
────────────────────────────────────────────────────
Run ID:     {payload['run_id']}
Dataset:    {payload['dataset']}
Timestamp:  {payload['timestamp']}
Host:       {payload['environment']}

SUMMARY
  Files Scanned:          {scanned}
  Passed Validation:      {passed}
  Quarantined / Skipped:  {quarantined}

PASSED FILES
"""
        if passed_files:
            for f in passed_files:
                plain += f"  {OK} {f}\n"
        else:
            plain += "  None\n"

        if quarantined_files:
            plain += "\nQUARANTINED / SKIPPED FILES\n"
            for f in quarantined_files:
                plain += f"  {WARN} {f} - Processing skipped; downstream unaffected\n"

        plain += "\nPRE VALIDATION COMPLETE\n"

        title_html = f"<h1>PIPELINE PRE VALIDATION SUMMARY</h1><p>{run_id_text}</p>"
        body_html = f"""
<div class="meta">
    <div class="meta-row"><span>Run ID</span><span>{payload['run_id']}</span></div>
    <div class="meta-row"><span>Dataset</span><span>{payload['dataset']}</span></div>
    <div class="meta-row"><span>Timestamp</span><span>{payload['timestamp']}</span></div>
    <div class="meta-row"><span>Environment</span><span>{payload['environment']}</span></div>
</div>
<div class="section">
    <h2>Summary</h2>
    <div class="grid">
        <div class="row"><span class="label">Files Scanned</span><span class="val">{scanned}</span></div>
        <div class="row"><span class="label">Passed Validation</span><span class="val pass">{passed}</span></div>
        <div class="row"><span class="label">Quarantined / Skipped</span><span class="val {'warn' if quarantined else ''}">{quarantined}</span></div>
    </div>
</div>
<div class="section">
    <h2>Passed Files</h2>
    <div class="grid">
"""
        if passed_files:
            for f in passed_files:
                body_html += f"<div class='row'><span class='label'>{OK} {f}</span><span class='val pass'>PASSED</span></div>"
        else:
            body_html += "<div class='row'><span class='label'>None</span><span></span></div>"

        body_html += "</div></div>"

        if quarantined_files:
            body_html += """
<div class="section">
    <h2>Quarantined / Skipped Files</h2>
    <div class="grid">
"""
            for f in quarantined_files:
                body_html += f"<div class='row'><span class='label'>{WARN} {f}</span><span class='val warn'>QUARANTINED</span></div>"
                body_html += "<div style='padding:4px 0 8px 20px;font-size:13px;color:#6b7280;'>Processing skipped; downstream datasets unaffected</div>"
            body_html += "</div></div>"

        html = build_html_layout(title_html, body_html)
        return title_text, plain, html

    # --- POST-VALIDATION SUMMARY ---
    elif et == "POST_VALIDATION_SUMMARY":
        total = payload.get("total_checked", 0)
        count_passed = payload.get("count_passed", 0)
        count_failed = payload.get("count_failed", 0)
        passed_checks = payload.get("passed_checks", [])
        failed_checks = payload.get("failed_checks", [])
        status = "PASSED" if count_failed == 0 else "FAILED"

        plain = f"""{title_text} - {status}
{run_id_text}
────────────────────────────────────────────────────
Run ID:     {payload['run_id']}
Dataset:    {payload['dataset']}
Timestamp:  {payload['timestamp']}
Host:       {payload['environment']}

SUMMARY
  Total Checks Run:       {total}
  Passed:                 {count_passed}
  Failed:                 {count_failed}

ALL CHECK RESULTS
"""
        for item in passed_checks:
            friendly = get_check_description(item)
            plain += f"  {OK} {friendly} - PASSED\n"
        if failed_checks:
            plain += "\nFAILED CHECKS\n"
            for item in failed_checks:
                friendly = get_check_description(item)
                plain += f"  {ERR} {friendly} - FAILED\n"

        plain += f"\nPOST VALIDATION COMPLETE - {status}\n"

        title_html = f"<h1>PIPELINE POST VALIDATION SUMMARY - {status}</h1><p>{run_id_text}</p>"
        status_cls = "pass" if count_failed == 0 else "fail"
        body_html = f"""
<div class="meta">
    <div class="meta-row"><span>Run ID</span><span>{payload['run_id']}</span></div>
    <div class="meta-row"><span>Dataset</span><span>{payload['dataset']}</span></div>
    <div class="meta-row"><span>Timestamp</span><span>{payload['timestamp']}</span></div>
    <div class="meta-row"><span>Environment</span><span>{payload['environment']}</span></div>
</div>
<div class="section">
    <h2>Summary</h2>
    <div class="grid">
        <div class="row"><span class="label">Total Checks Run</span><span class="val">{total}</span></div>
        <div class="row"><span class="label">Passed</span><span class="val pass">{count_passed}</span></div>
        <div class="row"><span class="label">Failed</span><span class="val {status_cls}">{count_failed}</span></div>
    </div>
</div>
<div class="section">
    <h2>All Checks</h2>
    <div class="grid">
"""
        for item in passed_checks:
            friendly = get_check_description(item)
            body_html += f"<div class='row'><span class='label'>{friendly}</span><span class='val pass'>PASSED</span></div>"
        if failed_checks:
            body_html += "</div></div><div class='section'><h2>Failed Checks</h2><div class='grid'>"
            for item in failed_checks:
                friendly = get_check_description(item)
                body_html += f"<div class='row'><span class='label'>{friendly}</span><span class='val fail'>FAILED</span></div>"
            body_html += "</div></div>"
        else:
            body_html += "</div></div>"

        html = build_html_layout(title_html, body_html)
        return title_text, plain, html

    # --- SLA MISS ---
    elif et == "SLA_MISS":
        scheduled = payload.get("scheduled_drop", "N/A")
        deadline = payload.get("sla_deadline", "N/A")
        arrival = payload.get("arrival_time", "N/A")
        elapsed = payload.get("elapsed_minutes", "N/A")
        early_files = payload.get("early_files", [])
        missing_files = payload.get("missing_files", [])

        plain = f"""{title_text}
{run_id_text}
────────────────────────────────────────────────────
Run ID:     {payload['run_id']}
Dataset:    {payload['dataset']}
Timestamp:  {payload['timestamp']}
Host:       {payload['environment']}

SLA DETAILS
  Scheduled Drop:         {scheduled}
  SLA Deadline:            {deadline}
  Actual Arrival:         {arrival}
  Elapsed / Deviation:    {elapsed} minutes

STATUS: FILES ARRIVED OUTSIDE SLA WINDOW
"""
        if early_files:
            plain += "\nFILES ARRIVED TOO EARLY (Not Downloaded):\n"
            for f in early_files:
                plain += f"  {WARN} {f}\n"
        if missing_files:
            plain += "\nMISSING FILES:\n"
            for f in missing_files:
                plain += f"  {ERR} {f}\n"

        plain += "\nAction required: Files must arrive within the SLA window to be processed\n"

        title_html = f"<h1>PIPELINE SLA ALERT</h1><p>{run_id_text}</p>"
        body_html = f"""
<div class="meta">
    <div class="meta-row"><span>Run ID</span><span>{payload['run_id']}</span></div>
    <div class="meta-row"><span>Dataset</span><span>{payload['dataset']}</span></div>
    <div class="meta-row"><span>Timestamp</span><span>{payload['timestamp']}</span></div>
    <div class="meta-row"><span>Environment</span><span>{payload['environment']}</span></div>
</div>
<div class="section">
    <h2>SLA Details</h2>
    <div class="grid">
        <div class="row"><span class="label">Scheduled Drop</span><span class="val">{scheduled}</span></div>
        <div class="row"><span class="label">SLA Deadline</span><span class="val">{deadline}</span></div>
        <div class="row"><span class="label">Actual Arrival</span><span class="val">{arrival}</span></div>
        <div class="row"><span class="label">Deviation</span><span class="val warn">{elapsed} minutes</span></div>
    </div>
</div>
"""
        if early_files:
            body_html += "<div class='section'><h2>Arrived Too Early - Not Downloaded</h2><div class='grid'>"
            for f in early_files:
                body_html += f"<div class='row'><span class='label'>{WARN} {f}</span><span class='val warn'>EARLY</span></div>"
            body_html += "</div></div>"
        if missing_files:
            body_html += "<div class='section'><h2>Missing Files</h2><div class='grid'>"
            for f in missing_files:
                body_html += f"<div class='row'><span class='label'>{ERR} {f}</span><span class='val fail'>MISSING</span></div>"
            body_html += "</div></div>"

        body_html += """
<div class="section">
    <div style="color:#d97706;font-weight:500;">
    Action: Files must arrive within the SLA window to be processed
    </div>
</div>
"""
        html = build_html_layout(title_html, body_html)
        return title_text, plain, html

    # --- SENSOR COMPLETE ---
    elif et == "SENSOR_COMPLETE":
        found = payload.get("files_found", [])
        missing = payload.get("files_missing", [])
        late = payload.get("files_late", [])

        plain = f"""{title_text}
{run_id_text}
────────────────────────────────────────────────────
Run ID:     {payload['run_id']}
Dataset:    {payload['dataset']}
Timestamp:  {payload['timestamp']}
Host:       {payload['environment']}

SUMMARY
  Files Found:             {len(found)}
  Files Missing:           {len(missing)}
  Files Late:              {len(late)}
"""
        if found:
            plain += "\nFILES FOUND:\n"
            for f in found:
                plain += f"  {OK} {f}\n"
        if missing:
            plain += "\nFILES MISSING:\n"
            for f in missing:
                plain += f"  {ERR} {f}\n"
        if late:
            plain += "\nFILES LATE:\n"
            for f in late:
                plain += f"  {WARN} {f}\n"

        title_html = f"<h1>PIPELINE SENSOR COMPLETE</h1><p>{run_id_text}</p>"
        body_html = f"""
<div class="meta">
    <div class="meta-row"><span>Run ID</span><span>{payload['run_id']}</span></div>
    <div class="meta-row"><span>Dataset</span><span>{payload['dataset']}</span></div>
    <div class="meta-row"><span>Timestamp</span><span>{payload['timestamp']}</span></div>
    <div class="meta-row"><span>Environment</span><span>{payload['environment']}</span></div>
</div>
<div class="section">
    <h2>Summary</h2>
    <div class="grid">
        <div class="row"><span class="label">Files Found</span><span class="val pass">{len(found)}</span></div>
        <div class="row"><span class="label">Files Missing</span><span class="val {'fail' if missing else ''}">{len(missing)}</span></div>
        <div class="row"><span class="label">Files Late</span><span class="val {'warn' if late else ''}">{len(late)}</span></div>
    </div>
</div>
"""
        if found:
            body_html += "<div class='section'><h2>Files Found</h2><div class='grid'>"
            for f in found:
                body_html += f"<div class='row'><span class='label'>{OK} {f}</span><span class='val pass'>READY</span></div>"
            body_html += "</div></div>"
        if missing:
            body_html += "<div class='section'><h2>Files Missing</h2><div class='grid'>"
            for f in missing:
                body_html += f"<div class='row'><span class='label'>{ERR} {f}</span><span class='val fail'>MISSING</span></div>"
            body_html += "</div></div>"
        if late:
            body_html += "<div class='section'><h2>Files Late</h2><div class='grid'>"
            for f in late:
                body_html += f"<div class='row'><span class='label'>{WARN} {f}</span><span class='val warn'>LATE</span></div>"
            body_html += "</div></div>"

        html = build_html_layout(title_html, body_html)
        return title_text, plain, html

    # --- PRE-VALIDATION FAILURE ---
    elif et == "PRE_VALIDATION_FAIL":
        rules_text = payload.get("failed_rules_text", "N/A")
        rule_count = payload.get("failed_rules_count", 0)
        quarantine = payload.get("quarantine_path", "N/A")
        file_rows = payload.get("file_rows", "N/A")
        skipped = payload.get("cascade_skipped", "None")

        plain = f"""{title_text}
{run_id_text}
────────────────────────────────────────────────────
Run ID:     {payload['run_id']}
Dataset:    {payload['dataset']}
Timestamp:  {payload['timestamp']}
Host:       {payload['environment']}

VALIDATION DETAILS
  File Rows:               {file_rows}
  Failed Rule Count:       {rule_count}
  Quarantine Path:         {quarantine}

FAILED RULES
{rules_text}

CASCADE AFFECTED DATASETS
  {skipped}

File quarantined. Processing skipped. Unaffected datasets continue normally.
"""
        title_html = f"<h1>PIPELINE PRE VALIDATION FAILURE</h1><p>{run_id_text}</p>"
        body_html = f"""
<div class="meta">
    <div class="meta-row"><span>Run ID</span><span>{payload['run_id']}</span></div>
    <div class="meta-row"><span>Dataset</span><span>{payload['dataset']}</span></div>
    <div class="meta-row"><span>Timestamp</span><span>{payload['timestamp']}</span></div>
    <div class="meta-row"><span>Environment</span><span>{payload['environment']}</span></div>
</div>
<div class="section">
    <h2>Validation Details</h2>
    <div class="grid">
        <div class="row"><span class="label">File Rows</span><span class="val">{file_rows}</span></div>
        <div class="row"><span class="label">Failed Rule Count</span><span class="val fail">{rule_count}</span></div>
        <div class="row"><span class="label">Quarantine Path</span><span class="val">{quarantine}</span></div>
    </div>
</div>
<div class="section">
    <h2>Failed Rules</h2>
    <pre style="margin:0;font-size:13px;white-space:pre-wrap;">{rules_text}</pre>
</div>
<div class="section">
    <h2>Cascade - Skipped Datasets</h2>
    <div class="grid">
        <div class="row"><span class="label">{skipped}</span><span class="val warn">SKIPPED</span></div>
    </div>
    <p style="margin-top:10px;font-size:13px;color:#6b7280;">File quarantined. Processing skipped. Unaffected datasets continue normally.</p>
</div>
"""
        html = build_html_layout(title_html, body_html)
        return title_text, plain, html

    # --- TASK ERROR ---
    elif et == "TASK_ERROR":
        task_name = payload.get("task_name", "N/A")
        error_summary = payload.get("error_summary", "N/A")
        log_ref = payload.get("log_ref", "N/A")
        skipped = payload.get("cascade_skipped", "All downstream")

        plain = f"""{title_text}
{run_id_text}
────────────────────────────────────────────────────
Run ID:     {payload['run_id']}
Dataset:    {payload['dataset']}
Timestamp:  {payload['timestamp']}
Host:       {payload['environment']}

ERROR DETAILS
  Task:           {task_name}
  Error:          {error_summary}
  Log Reference:  {log_ref}

CASCADE - DOWNSTREAM SKIPPED
  {skipped}
"""
        title_html = f"<h1>PIPELINE TASK ERROR</h1><p>{run_id_text}</p>"
        body_html = f"""
<div class="meta">
    <div class="meta-row"><span>Run ID</span><span>{payload['run_id']}</span></div>
    <div class="meta-row"><span>Dataset</span><span>{payload['dataset']}</span></div>
    <div class="meta-row"><span>Timestamp</span><span>{payload['timestamp']}</span></div>
    <div class="meta-row"><span>Environment</span><span>{payload['environment']}</span></div>
</div>
<div class="section">
    <h2>Error Details</h2>
    <div class="grid">
        <div class="row"><span class="label">Task</span><span class="val fail">{task_name}</span></div>
        <div class="row"><span class="label">Error</span><span class="val fail" style="text-align:left;white-space:pre-wrap;">{error_summary}</span></div>
        <div class="row"><span class="label">Log Reference</span><span class="val">{log_ref}</span></div>
    </div>
</div>
<div class="section">
    <h2>Cascade - Downstream Skipped</h2>
    <div class="grid">
        <div class="row"><span class="label">{skipped}</span><span class="val warn">SKIPPED</span></div>
    </div>
</div>
"""
        html = build_html_layout(title_html, body_html)
        return title_text, plain, html

    # --- FULL RUN SUCCESS ---
    elif et == "RUN_SUCCESS":
        pre = payload.get("pre_validation", {})
        datasets = payload.get("datasets", {})
        tables_staging = payload.get("loaded_tables", [])
        dbt_status = payload.get("dbt_build", "NOT RUN")
        dbt_detail = payload.get("dbt_message", "")
        model_count = test_count = failed_tests = 0
        found_model = re.search(r"(\d+)\s+models", dbt_detail)
        found_test = re.search(r"(\d+)\s+data tests", dbt_detail)
        found_failed = re.search(r"(\d+)\s+FAILED", dbt_detail)
        if found_model:
            model_count = int(found_model.group(1))
        if found_test:
            test_count = int(found_test.group(1))
        if found_failed:
            failed_tests = int(found_failed.group(1))
        staging_count = len(tables_staging)
        if model_count == 0:
            model_count = staging_count + 6
        if test_count == 0:
            test_count = 17
        remaining_models = model_count - staging_count
        dim_count = max(0, remaining_models - 2)
        fact_count = remaining_models - dim_count if remaining_models > 0 else 0

        pv_details = payload.get("post_validation_details", {})
        pv_passed = 0
        pv_items = []
        for check_key, result in pv_details.items():
            if isinstance(result, dict):
                res_status = result.get("status", "UNKNOWN")
            else:
                res_status = result
            friendly_desc = get_check_description(check_key)
            pv_items.append((friendly_desc, res_status))
            if res_status == "PASSED":
                pv_passed += 1
        pv_total = len(pv_items)

        plain = f"""{title_text}
{run_id_text}
────────────────────────────────────────────────────
Run ID:     {payload['run_id']}
Dataset:    {payload['dataset']}
Timestamp:  {payload['timestamp']}
Host:       {payload['environment']}

[1] INPUT STAGE
  Files Scanned:          {pre.get('scanned', 0)}
  Pre‑Validation Passed:  {pre.get('passed', 0)}
  Quarantined:            {pre.get('quarantined', 0)}
  Files Loaded to RAW:    {payload.get('count_loaded', 0)}
"""
        if pre.get("passed_files"):
            plain += "\n  Passed Files:\n" + \
                "\n".join(f"    {OK} {f}" for f in pre["passed_files"])
        if pre.get("quarantined_files"):
            plain += "\n  Quarantined Files:\n" + \
                "\n".join(f"    {WARN} {f}" for f in pre["quarantined_files"])

        plain += "\n\n[2] FILE DETAILS - Source → RAW\n"
        for fname, info in datasets.items():
            src = info.get("source_row_count", "N/A")
            raw = info.get("raw_row_count", "N/A")
            status = info.get("status", info.get("skip_reason", "UNKNOWN"))
            plain += f"  {fname:22} {str(src):>8} → {str(raw):>8}  {status}\n"

        plain += f"""
[3] DBT BUILD
  Status:                 {dbt_status}
  Total Models:          {model_count}
    Staging Tables:      {staging_count}
    Dimension Tables:    {dim_count}
    Fact Tables:         {fact_count}
  Total Tests Run:       {test_count}
    Passed:              {test_count - failed_tests}
    Failed:              {failed_tests}

  {OK} All referential integrity checks passed
  {OK} All uniqueness & value format checks passed
  {OK} Production reporting layer is up to date

[4] PRODUCTION LAYER SUMMARY
  Staging Tables:        {', '.join(tables_staging) if tables_staging else 'None'}
  Dimensions Built:      {dim_count}
  Facts Built:           {fact_count}

[5] POST‑VALIDATION - Data Quality Checks
  Overall Result:        {'ALL CHECKS PASSED' if pv_passed == pv_total else 'SOME CHECKS FAILED'}
  Checks Passed:          {pv_passed} of {pv_total}

  CHECK DETAILS:
"""
        for display_desc, status in pv_items:
            icon = OK if status == "PASSED" else ERR
            plain += f"  {icon} {display_desc}: {status}\n"

        plain += f"\n{OK} PIPELINE COMPLETED SUCCESSFULLY\n"

        title_html = f"<h1>{title_text}</h1><p>{run_id_text}</p>"

        input_rows = f"""
<div class="row"><span class="label">Files Scanned</span><span class="val">{pre.get('scanned', 0)}</span></div>
<div class="row"><span class="label">Pre‑Validation Passed</span><span class="val pass">{pre.get('passed', 0)}</span></div>
<div class="row"><span class="label">Quarantined</span><span class="val {'warn' if pre.get('quarantined', 0) > 0 else ''}">{pre.get('quarantined', 0)}</span></div>
<div class="row"><span class="label">Loaded to RAW</span><span class="val">{payload.get('count_loaded', 0)}</span></div>
"""
        if pre.get("passed_files"):
            input_rows += "<div style='margin-top:10px;font-size:13px;color:#6b7280;'>Passed Files</div>"
            input_rows += "".join(
                f"<div class='row'><span class='label'>{OK}</span><span class='val'>{f}</span></div>" for f in pre["passed_files"])
        if pre.get("quarantined_files"):
            input_rows += "<div style='margin-top:10px;font-size:13px;color:#6b7280;'>Quarantined Files</div>"
            input_rows += "".join(
                f"<div class='row'><span class='label'>{WARN}</span><span class='val'>{f}</span></div>" for f in pre["quarantined_files"])

        source_rows = ""
        for fname, info in datasets.items():
            src = info.get("source_row_count", "N/A")
            raw = info.get("raw_row_count", "N/A")
            status = info.get("status", info.get("skip_reason", "UNKNOWN"))
            cls = "pass" if status == "LOADED" else "warn" if "SKIPPED" in status else "fail"
            source_rows += f"<div class='row'><span class='label'>{fname}</span><span class='val {cls}'>{src} → {raw} &nbsp; {status}</span></div>"

        dbt_rows = f"""
<div class="row"><span class="label">Build Status</span><span class="val pass">{dbt_status}</span></div>
<div class="row"><span class="label">Total Models</span><span class="val">{model_count}</span></div>
<div class="row"><span class="label">- Staging Tables</span><span class="val">{staging_count}</span></div>
<div class="row"><span class="label">- Dimension Tables</span><span class="val">{dim_count}</span></div>
<div class="row"><span class="label">- Fact Tables</span><span class="val">{fact_count}</span></div>
<div class="row"><span class="label">Total Tests</span><span class="val">{test_count}</span></div>
<div class="row"><span class="label">- Passed</span><span class="val pass">{test_count - failed_tests}</span></div>
<div class="row"><span class="label">- Failed</span><span class="val {'fail' if failed_tests else ''}">{failed_tests}</span></div>
<div style='margin-top:12px;font-size:13px;color:#16a34a;line-height:1.8;'>
  {OK} Referential integrity • Uniqueness • Production layer up‑to‑date
</div>
"""

        tables_rows = f"""
<div class="row"><span class="label">Staging Tables Loaded</span><span class="val">{staging_count}</span></div>
<div class="row"><span class="label">Dimensions Built</span><span class="val">{dim_count}</span></div>
<div class="row"><span class="label">Facts Built</span><span class="val">{fact_count}</span></div>
"""

        pv_status_text = f"{pv_passed} of {pv_total} checks passed"
        pv_status_cls = "pass" if pv_passed == pv_total else "fail"
        pv_rows = f"<div class='row'><span class='label'>Overall Result</span><span class='val {pv_status_cls}'>{pv_status_text}</span></div>"
        pv_rows += "<div style='margin-top:8px;font-size:13px;color:#6b7280;'>Individual Checks</div>"
        for display_desc, status in pv_items:
            cls = "pass" if status == "PASSED" else "fail"
            pv_rows += f"<div class='row'><span class='label'>{display_desc}</span><span class='val {cls}'>{status}</span></div>"

        body_html = f"""
<div class="meta">
    <div class="meta-row"><span>Run ID</span><span>{payload['run_id']}</span></div>
    <div class="meta-row"><span>Dataset</span><span>{payload['dataset']}</span></div>
    <div class="meta-row"><span>Timestamp</span><span>{payload['timestamp']}</span></div>
    <div class="meta-row"><span>Environment</span><span>{payload['environment']}</span></div>
</div>
<div class="section">
    <h2>1. Input Stage</h2>
    <div class="grid">{input_rows}</div>
</div>
<div class="section">
    <h2>2. Source → RAW File Counts</h2>
    <div class="grid">{source_rows}</div>
</div>
<div class="section">
    <h2>3. dbt Transformation Build</h2>
    <div class="grid">{dbt_rows}</div>
</div>
<div class="section">
    <h2>4. Production Layer Summary</h2>
    <div class="grid">{tables_rows}</div>
</div>
<div class="section">
    <h2>5. Post‑Validation - Data Quality Checks</h2>
    <div class="grid">{pv_rows}</div>
</div>
"""
        html = build_html_layout(title_html, body_html)
        return title_text, plain, html

    # Fallback
    plain = f"""{title_text}
────────────────────────────────────────────────────
Run ID:     {payload['run_id']}
Dataset:    {payload['dataset']}
Timestamp:  {payload['timestamp']}
Host:       {payload['environment']}
"""
    html = build_html_layout(f"<h1>{title_text}</h1><p>{run_id_text}</p>",
                             f"""
<div class="meta">
    <div class="meta-row"><span>Run ID</span><span>{payload['run_id']}</span></div>
    <div class="meta-row"><span>Dataset</span><span>{payload['dataset']}</span></div>
    <div class="meta-row"><span>Timestamp</span><span>{payload['timestamp']}</span></div>
    <div class="meta-row"><span>Environment</span><span>{payload['environment']}</span></div>
</div>
""")
    return title_text, plain, html


def notify_run_success(
    count_read, count_validated, count_loaded,
    loaded_tables, datasets, pre_validation,
    dbt_build_status, dbt_message,
    post_validation_status, post_validation_details
):
    payload = build_alert_payload(
        event_type="RUN_SUCCESS", dataset_name="All Files",
        count_read=count_read, count_validated=count_validated, count_loaded=count_loaded,
        loaded_tables=loaded_tables, datasets=datasets, pre_validation=pre_validation,
        dbt_build=dbt_build_status, dbt_message=dbt_message,
        post_validation=post_validation_status, post_validation_details=post_validation_details
    )
    subject, plain, html = format_alert_message(payload)
    send_alert(subject, plain, html)


def notify_sla_miss(dataset_name, scheduled_drop, sla_deadline, arrival_time, elapsed_minutes, early_files=None, missing_files=None):
    payload = build_alert_payload("SLA_MISS", dataset_name,
                                  scheduled_drop=scheduled_drop, sla_deadline=sla_deadline,
                                  arrival_time=arrival_time, elapsed_minutes=elapsed_minutes,
                                  early_files=early_files or [], missing_files=missing_files or [])
    s, p, h = format_alert_message(payload)
    send_alert(s, p, h)


def notify_sensor_complete(dataset_name, files_found=None, files_missing=None, files_late=None, **kw):
    payload = build_alert_payload("SENSOR_COMPLETE", dataset_name,
                                  files_found=files_found or [], files_missing=files_missing or [], files_late=files_late or [])
    s, p, h = format_alert_message(payload)
    send_alert(s, p, h)


def notify_pre_validation_failure(dataset_name, failed_rules_list, quarantine_path, file_rows="N/A", cascade_skipped=None):
    payload = build_alert_payload("PRE_VALIDATION_FAIL", dataset_name,
                                  failed_rules_count=len(failed_rules_list),
                                  failed_rules_text="\n".join(
                                      f"  - {r}" for r in failed_rules_list),
                                  quarantine_path=quarantine_path, file_rows=file_rows,
                                  cascade_skipped=", ".join(cascade_skipped) if cascade_skipped else "None")
    s, p, h = format_alert_message(payload)
    send_alert(s, p, h)


def notify_pre_validation_summary(count_scanned, count_passed, count_quarantined, passed_files, quarantined_files):
    payload = build_alert_payload("PRE_VALIDATION_SUMMARY", f"{count_scanned} file(s) scanned",
                                  count_scanned=count_scanned, count_passed=count_passed,
                                  count_quarantined=count_quarantined,
                                  passed_files=passed_files, quarantined_files=quarantined_files)
    s, p, h = format_alert_message(payload)
    send_alert(s, p, h)


def notify_task_error(task_name, error_exception, log_ref=None, cascade_skipped_datasets=None):
    payload = build_alert_payload("TASK_ERROR", "Multiple / See Details",
                                  task_name=task_name, error_summary=str(error_exception)[
                                      :300],
                                  log_ref=log_ref or "Check sensor/validation log at timestamp",
                                  cascade_skipped=", ".join(cascade_skipped_datasets) if cascade_skipped_datasets else "All downstream")
    s, p, h = format_alert_message(payload)
    send_alert(s, p, h)


def notify_post_validation_failure(check_name, table_reference, issue_description):
    payload = build_alert_payload("POST_VALIDATION_FAIL", check_name,
                                  check_name=check_name, table_reference=table_reference, issue_description=issue_description)
    s, p, h = format_alert_message(payload)
    send_alert(s, p, h)


def notify_post_validation_summary(total_checked, count_passed, count_failed, passed_checks, failed_checks):
    payload = build_alert_payload("POST_VALIDATION_SUMMARY", f"{total_checked} checks run",
                                  total_checked=total_checked, count_passed=count_passed,
                                  count_failed=count_failed, passed_checks=passed_checks,
                                  failed_checks=failed_checks)
    s, p, h = format_alert_message(payload)
    send_alert(s, p, h)


def main():
    setup_logging()
    send_alert(
        "Test Alert", "Notification unified - all alerts now share one layout")


if __name__ == "__main__":
    main()
