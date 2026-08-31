"""
Pre-validation module - validates downloaded files against schema rules.
Expected file structure:

- Rule: Each file must adhere to the expected schema and data quality rules (Please refer to the EXPECTED configuration in python/config.py)
- Mandatory fields must not be empty and must follow the correct format.
- UUID fields must contain valid UUIDs.
- Date fields must be valid dates and follow chronological order where applicable.
- Allowed values for categorical fields must be respected.
- Row count must match expectations where applicable.

Files that fail are moved to quarantine and skipped. Pipeline continues with passing files.
"""
import logging
import os
import re
import shutil
import pandas as pd
from datetime import datetime, timezone
from python.config import (LANDING_FOLDER, EXPECTED, QUARANTINE_FOLDER)
from python.notifications import notify_pre_validation_failure, notify_pre_validation_summary
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
    Run all validation checks.
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

    # Check 2: Mandatory Fields - NOT EMPTY + VALID FORMAT
    for col in cfg["mandatory"]:
        if col not in df.columns:
            continue

        # Strip whitespace and treat empty string as missing
        stripped = df[col].astype(str).str.strip()
        blanks = (df[col].isna()) | (stripped == "")
        if blanks.any():
            reasons.append(f"{blanks.sum()} empty in {col}")

        # If column is a DATE column, ALSO check if value is a VALID DATE
        if col in ["BIRTHDATE", "DEATHDATE", "START", "STOP"]:
            non_empty = stripped != ""
            if non_empty.any():
                parsed = pd.to_datetime(
                    df.loc[non_empty, col], errors="coerce")
                invalid_format = parsed.isna()
                if invalid_format.any():
                    reasons.append(
                        f"{invalid_format.sum()} invalid date in {col}")

    # Check 3: Valid UUID Format
    for col in cfg["uuid_cols"]:
        if col in df.columns:
            invalid = df[col].dropna().astype(str).apply(
                lambda x: not UUID_PATTERN.match(x.strip()))
            if invalid.any():
                reasons.append(f"{invalid.sum()} invalid UUID in {col}")

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


def quarantine_file(file_path, issues, row_count):
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
        file_rows=str(row_count),
        cascade_skipped=None
    )
    logging.info(f"Alert sent for quarantined file: {filename}")
    return dest_path


def run_validation(file_paths):
    """
    Validate all files. Quarantine failures individually.
    Return (list_of_valid_entries, list_of_quarantined_info).
    valid_entries = [{"path": "...", "rows": N}]
    quarantined_info = [{"name": "...", "reasons": [...]}]
    """
    section("STARTING PRE-VALIDATION")
    valid_entries = []
    quarantined_info = []

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
            quarantine_file(path, issues, rows)
            quarantined_info.append({"name": filename, "reasons": issues})

    # Save list of valid files for loader
    valid_list_path = os.path.join(LANDING_FOLDER, ".valid_files.txt")
    with open(valid_list_path, "w") as f:
        for entry in valid_entries:
            f.write(entry["path"] + "\n")

    # Format lists with row counts for summary alert
    passed_files = [
        f"{os.path.basename(e['path'])}: {e['rows']} rows"
        for e in valid_entries
    ]

    # Format quarantined files with ALL issues listed
    quarantined_files = []
    for info in quarantined_info:
        issues_text = "; ".join(info["reasons"])
        quarantined_files.append(f"{info['name']}: {issues_text}")

    # Send standardized summary alert
    notify_pre_validation_summary(
        count_scanned=len(file_paths),
        count_passed=len(valid_entries),
        count_quarantined=len(quarantined_info),
        passed_files=passed_files,
        quarantined_files=quarantined_files
    )

    if quarantined_info:
        names = [i["name"] for i in quarantined_info]
        logging.info(f"Quarantined files: {', '.join(names)}")

    return valid_entries, quarantined_info


def main():
    setup_logging()
    ensure_quarantine_folder()

    # Scan landing folder for CSV files
    all_files = [
        os.path.join(LANDING_FOLDER, f)
        for f in os.listdir(LANDING_FOLDER)
        if f.endswith(".csv")
    ]

    run_validation(all_files)


if __name__ == "__main__":
    main()
