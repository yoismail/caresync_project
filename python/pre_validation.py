import logging
import os
import re
import shutil
import pandas as pd
from datetime import datetime, timezone
from python.config import (LANDING_FOLDER, EXPECTED, QUARANTINE_FOLDER)
from python.notifications import send_alert
from python.logger import setup_logging, section


# QUARANTINE_FOLDER is imported from config.py and if it doesn't exist, it will be created here
def ensure_quarantine_folder():
    if not os.path.exists(QUARANTINE_FOLDER):
        os.makedirs(QUARANTINE_FOLDER, exist_ok=True)


# UUID pattern for validating UUID columns
UUID_PATTERN = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')

# Validate a single file against the expected schema and rules. Expected schema is defined in the EXPECTED dictionary in config.py.


def validate_file(file_path):
    """Run all 7 checks. Return (PASS/FAIL, list_of_issues)."""
    filename = os.path.basename(file_path).replace(".csv", "").lower()
    if filename not in EXPECTED:
        return False, ["Unknown file type - cannot validate"]

    cfg = EXPECTED[filename]
    reasons = []

    # Check 0: Parseability
    try:
        df = pd.read_csv(file_path, dtype=str, low_memory=False)
        df.columns = df.columns.str.strip()
    except Exception as e:
        return False, [f"Parse failed: {str(e)[:150]}"]

    # Check 1: Columns
    expected_cols = set(cfg["columns"])
    actual_cols = set(df.columns)
    missing = expected_cols - actual_cols
    if missing:
        reasons.append(f"Missing columns: {', '.join(missing)}")

    # Check 2: Mandatory Fields
    for col in cfg["mandatory"]:
        if col in df.columns:
            blanks = df[col].isna() | (df[col].astype(str).str.strip() == "")
            if blanks.any():
                reasons.append(
                    f"{blanks.sum()} empty values in mandatory column: {col}")

    # Check 3: UUID Format
    for col in cfg["uuid_cols"]:
        if col in df.columns:
            invalid = df[col].dropna().astype(str).apply(
                lambda x: not UUID_PATTERN.match(x.strip()))
            if invalid.any():
                reasons.append(f"{invalid.sum()} invalid UUIDs in: {col}")

    # Check 4: Allowed Values
    for col, allowed in cfg["allowed_values"].items():
        if col in df.columns:
            bad = df[df[col].notna() & ~df[col].isin(allowed)]
            if len(bad):
                reasons.append(f"{len(bad)} invalid values in {col}")

    # Check 5: Chronology
    if "START" in df.columns and "STOP" in df.columns:
        df["START_DT"] = pd.to_datetime(df["START"], errors="coerce")
        df["STOP_DT"] = pd.to_datetime(df["STOP"], errors="coerce")
        bad = df[df["START_DT"] > df["STOP_DT"]]
        if len(bad):
            reasons.append(f"{len(bad)} rows where START > STOP")

    if "BIRTHDATE" in df.columns and "DEATHDATE" in df.columns:
        df["BIRTH_DT"] = pd.to_datetime(df["BIRTHDATE"], errors="coerce")
        df["DEATH_DT"] = pd.to_datetime(df["DEATHDATE"], errors="coerce")
        bad = df[df["DEATH_DT"].notna() & (df["BIRTH_DT"] > df["DEATH_DT"])]
        if len(bad):
            reasons.append(f"{len(bad)} rows where BIRTHDATE > DEATHDATE")

    # Check 6: Duplicates
    if "Id" in df.columns:
        dupes = df.duplicated(subset=["Id"], keep=False)
        if dupes.any():
            reasons.append(f"{dupes.sum()} duplicate Id values")

    # Check 7: Row Count Band
    rows = len(df)
    if rows < cfg["row_min"]:
        reasons.append(f"Row count too low: {rows} (min {cfg['row_min']})")
    if rows > cfg["row_max"]:
        reasons.append(f"Row count too high: {rows} (max {cfg['row_max']})")

    passed = len(reasons) == 0
    return passed, reasons


def quarantine_file(file_path, issues):
    """Move failed file to quarantine and send alert."""
    filename = os.path.basename(file_path)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    quarantined_name = f"{timestamp}_{filename}"
    dest_path = os.path.join(QUARANTINE_FOLDER, quarantined_name)

    # Move file out of landing zone
    shutil.move(file_path, dest_path)
    logging.warning(f"File quarantined: {quarantined_name}")

    # Build alert message
    issue_text = "\n".join(issues)
    alert_subject = f"PRE-VALIDATION FAILED - {filename}"
    alert_body = f"""
File: {filename}
Moved to: quarantine/{quarantined_name}

REASONS:
{issue_text}

File has been quarantined and skipped. Pipeline continues with other files.
    """.strip()

    # Send notification
    send_alert(alert_subject, alert_body)
    logging.info(f"Alert sent for failed file: {filename}")

    return dest_path


def run_validation(file_paths):
    """Validate all files - quarantine and skip failures, return only passing paths."""
    section("STARTING PRE-VALIDATION")

    valid_paths = []
    quarantined = []

    for path in file_paths:
        filename = os.path.basename(path)
        logging.info(f"Validating: {filename}")

        passed, issues = validate_file(path)

        if passed:
            logging.info(f"PASS - {filename}")
            valid_paths.append(path)
        else:
            logging.warning(f"FAIL - {filename}")
            for issue in issues:
                logging.warning(f"   {issue}")
            quarantine_file(path, issues)
            quarantined.append(filename)
            # Skip this file only - continue to next file

    # Save list of valid files for loader
    valid_list_path = os.path.join(LANDING_FOLDER, ".valid_files.txt")
    with open(valid_list_path, "w") as f:
        for p in valid_paths:
            f.write(p + "\n")

    if quarantined:
        logging.info(f"Quarantined files: {', '.join(quarantined)}")

    return valid_paths, quarantined


def main():
    # Setup logging
    setup_logging()

    # Ensure the quarantine folder exists before processing files
    ensure_quarantine_folder()

    # Scan landing folder for CSV files
    all_files = [
        os.path.join(LANDING_FOLDER, f)
        for f in os.listdir(LANDING_FOLDER)
        if f.endswith(".csv")
    ]
    # Call run_validation to process all discovered files
    valid_paths, quarantined = run_validation(all_files)

    # Send summary alert
    alert_msg = f"Pre-validation completed. {len(all_files)} file(s) scanned.\n"
    alert_msg += f"Passed: {len(valid_paths)} file(s)\n"
    alert_msg += f"Quarantined: {len(quarantined)} file(s)"
    send_alert("PRE-VALIDATION COMPLETE", alert_msg)


if __name__ == "__main__":
    main()
