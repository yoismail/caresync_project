"""
Pre-validation module — validates downloaded files against schema rules.
Files that fail are moved to quarantine and skipped. Pipeline continues with passing files.
"""


import logging
import os
import re
import shutil
import pandas as pd
from datetime import datetime, timezone
from python.config import (LANDING_FOLDER, EXPECTED, QUARANTINE_FOLDER)
from python.notifications import send_alert, notify_pre_validation_failure
from python.logger import setup_logging, section


# Create quarantine folder if it does not exist
def ensure_quarantine_folder():
    if not os.path.exists(QUARANTINE_FOLDER):
        os.makedirs(QUARANTINE_FOLDER, exist_ok=True)


# UUID pattern for validating UUID columns
UUID_PATTERN = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


def validate_file(file_path):
    """
    Run all 7 validation checks.
    Return (PASS/FAIL boolean, list_of_issues, row_count).
    """
    filename = os.path.basename(file_path).replace(".csv", "").lower()
    if filename not in EXPECTED:
        return False, ["Unknown file type - cannot validate"], 0

    cfg = EXPECTED[filename]
    reasons = []
    rows = 0

    # Check 0: Parseability
    try:
        df = pd.read_csv(file_path, dtype=str, low_memory=False)
        df.columns = df.columns.str.strip()
        rows = len(df)
    except Exception as e:
        return False, [f"Parse failed: {str(e)[:150]}"], 0

    # Check 1: Expected Columns
    expected_cols = set(cfg["columns"])
    actual_cols = set(df.columns)
    missing = expected_cols - actual_cols
    if missing:
        reasons.append(f"Missing columns: {', '.join(missing)}")

    # Check 2: Mandatory Fields Not Empty
    for col in cfg["mandatory"]:
        if col in df.columns:
            blanks = df[col].isna() | (df[col].astype(str).str.strip() == "")
            if blanks.any():
                reasons.append(
                    f"{blanks.sum()} empty values in mandatory column: {col}")

    # Check 3: Valid UUID Format
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

    # Check 5: Chronology / Date Order
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

    # Check 6: Duplicate IDs
    if "Id" in df.columns:
        dupes = df.duplicated(subset=["Id"], keep=False)
        if dupes.any():
            reasons.append(f"{dupes.sum()} duplicate Id values")

    # Check 7: Row Count Within Expected Range
    if rows < cfg["row_min"]:
        reasons.append(f"Row count too low: {rows} (min {cfg['row_min']})")
    if rows > cfg["row_max"]:
        reasons.append(f"Row count too high: {rows} (max {cfg['row_max']})")

    passed = len(reasons) == 0
    return passed, reasons, rows


def quarantine_file(file_path, issues):
    """
    Move failed file to quarantine folder and send PRE_VALIDATION_FAIL alert.
    """
    filename = os.path.basename(file_path)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    quarantined_name = f"{timestamp}_{filename}"
    dest_path = os.path.join(QUARANTINE_FOLDER, quarantined_name)

    # Move file out of landing zone
    shutil.move(file_path, dest_path)
    logging.warning(f"File quarantined: {quarantined_name}")

    # Send structured PRE_VALIDATION_FAIL alert
    notify_pre_validation_failure(
        dataset_name=filename,
        failed_rules_list=issues,
        quarantine_path=f"quarantine/{quarantined_name}",
        cascade_skipped=None
    )
    logging.info(f"Alert sent for quarantined file: {filename}")

    return dest_path


def run_validation(file_paths):
    """
    Validate all files. Quarantine failures individually.
    Return (list_of_valid_entries, list_of_quarantined_filenames).
    valid_entries = [{"path": "...", "rows": N}]
    """
    section("STARTING PRE-VALIDATION")

    valid_entries = []
    quarantined = []

    for path in file_paths:
        filename = os.path.basename(path)
        logging.info(f"Validating: {filename}")

        passed, issues, rows = validate_file(path)

        if passed:
            logging.info(f"PASS - {filename} ({rows} rows)")
            valid_entries.append({"path": path, "rows": rows})
        else:
            logging.warning(f"FAIL - {filename}")
            for issue in issues:
                logging.warning(f"   {issue}")
            quarantine_file(path, issues)
            quarantined.append(filename)
            # Skip failed file, continue to next file

    # Save list of valid files for loader
    valid_list_path = os.path.join(LANDING_FOLDER, ".valid_files.txt")
    with open(valid_list_path, "w") as f:
        for entry in valid_entries:
            f.write(entry["path"] + "\n")

    if quarantined:
        logging.info(f"Quarantined files: {', '.join(quarantined)}")

    return valid_entries, quarantined


def main():
    setup_logging()
    ensure_quarantine_folder()

    # Scan landing folder for CSV files
    all_files = [
        os.path.join(LANDING_FOLDER, f)
        for f in os.listdir(LANDING_FOLDER)
        if f.endswith(".csv")
    ]

    valid_entries, quarantined = run_validation(all_files)

    # Build summary with row counts
    alert_msg = f"Pre-validation completed. {len(all_files)} file(s) scanned.\n"
    alert_msg += f"Passed: {len(valid_entries)} file(s)\n"
    alert_msg += f"Quarantined: {len(quarantined)} file(s)"

    if valid_entries:
        alert_msg += "\n\nPassed Files:\n"
        for entry in valid_entries:
            alert_msg += f"- {os.path.basename(entry['path'])} ({entry['rows']} rows)\n"

    if quarantined:
        alert_msg += "\nQuarantined Files:\n"
        for name in quarantined:
            alert_msg += f"- {name}\n"

    send_alert("PRE-VALIDATION COMPLETE", alert_msg)


if __name__ == "__main__":
    main()
