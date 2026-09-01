"""
orchestrator.py - Pipeline Orchestration Core
- Runs datasets in strict dependency order
- Implements cascade-skip semantics: upstream skip → downstream skip
- Loads healthy datasets into NEXORA_RAW
- Records full run summary per dataset
Status definitions:
  LOADED   = Validated and written to warehouse
  SKIPPED  = Deliberately skipped (validation failed or upstream skipped)
  FAILED   = Infrastructure or code error (not validation)
"""
import logging
import os
from datetime import datetime, timezone
from python.config import LANDING_FOLDER
from python.pre_validation import validate_file
from python.snowflake_loader import load_csv_to_snowflake
from python.logger import setup_logging
from python.notifications import send_alert


# ------------------------------
# DEPENDENCY ORDER - DO NOT REORDER
# ------------------------------
# Format: (file_stem_name, [list_of_dependencies])
DEPENDENCY_ORDER = [
    ("organizations", []),
    ("payers", []),
    ("providers", []),
    ("patients", ["organizations"]),
    ("encounters", ["patients", "organizations", "providers", "payers"]),
    ("conditions", ["encounters", "patients"])
]

# Converting dependency order to file order
FILE_ORDER = [f"{stem}.csv" for stem, _ in DEPENDENCY_ORDER]


# Generate a unique run identifier for this orchestration session
def get_run_id():
    """Generate consistent run identifier"""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


# Read the list of files that passed pre-validation
def read_valid_files_list():
    """Read list of files that passed pre-validation"""
    valid_list_path = os.path.join(LANDING_FOLDER, ".valid_files.txt")
    if not os.path.exists(valid_list_path):
        return set()
    with open(valid_list_path, "r") as f:
        return {os.path.basename(line.strip()) for line in f if line.strip()}


def build_cascade_map(valid_files):
    """
    Determine skip status for every file:
      - Not in valid_files → SKIPPED (validation failed)
      - Depends on skipped file → SKIPPED (cascade)
    Returns: dict[filename, skip_reason or None]
    """
    skip_status = {}

    for stem, deps in DEPENDENCY_ORDER:
        filename = f"{stem}.csv"

        # Skip Reason 1: Failed pre-validation
        if filename not in valid_files:
            skip_status[filename] = "SKIPPED: validation failed"
            logging.info(f"SKIP {filename}: failed pre-validation")
            continue

        # Skip Reason 2: Upstream dependency skipped
        skipped_deps = [d for d in deps if skip_status.get(f"{d}.csv")]
        if skipped_deps:
            skip_status[filename] = f"SKIPPED: upstream skipped: {', '.join(skipped_deps)}"
            logging.info(f"SKIP {filename}: depends on skipped {skipped_deps}")
            continue

        # Ready to process
        skip_status[filename] = None
        logging.info(f"READY {filename}")

    return skip_status


def orchestrate():
    """Main orchestration loop: decide → load → summarize"""
    run_id = get_run_id()
    logging.info("=" * 60)
    logging.info(f"ORCHESTRATION STARTED: Run {run_id}")
    logging.info("=" * 60)

    valid_files = read_valid_files_list()
    logging.info(f"Files passed pre-validation: {len(valid_files)}")

    skip_reason_map = build_cascade_map(valid_files)

    summary = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "datasets": {}
    }

    for filename in FILE_ORDER:
        stem = filename.replace(".csv", "")
        source_path = os.path.join(LANDING_FOLDER, filename)

        entry = {
            "status": "PENDING",
            "rows_read": 0,
            "rows_validated": 0,
            "rows_loaded": 0,
            "rows_skipped": 0,
            "quarantined": False,
            "skip_reason": None,
            "error": None
        }

        reason = skip_reason_map.get(filename)
        if reason:
            entry["status"] = "SKIPPED"
            entry["skip_reason"] = reason
            summary["datasets"][filename] = entry
            logging.info(f"RESULT {filename}: SKIPPED | {reason}")
            continue

        try:
            if not os.path.exists(source_path):
                entry["status"] = "SKIPPED"
                entry["skip_reason"] = "File missing from landing folder"
                summary["datasets"][filename] = entry
                continue

            passed, issues, row_count = validate_file(source_path)
            entry["rows_read"] = row_count
            entry["rows_validated"] = row_count if passed else 0

            if not passed:
                entry["status"] = "SKIPPED"
                entry["skip_reason"] = f"Validation failed: {'; '.join(issues)}"
                entry["quarantined"] = True
                entry["rows_skipped"] = row_count
                summary["datasets"][filename] = entry
                continue

            logging.info(f"LOADING {filename} → NEXORA_RAW.HL7.{stem.upper()}")
            rows_written = load_csv_to_snowflake(
                file_path=source_path,
                table_name=stem.upper(),
                schema="HL7",
                database="NEXORA_RAW"
            )
            entry["status"] = "LOADED"
            entry["rows_loaded"] = rows_written
            logging.info(f"LOADED {filename}: {rows_written} rows written")

        except Exception as e:
            entry["status"] = "FAILED"
            entry["error"] = str(e)[:200]
            logging.error(f"FAILED {filename}: {e}")

        summary["datasets"][filename] = entry

    summary["completed_at"] = datetime.now(
        timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    emit_summary(summary)
    return summary


def emit_summary(summary):
    """Print and send final run summary"""
    run_id = summary["run_id"]
    lines = [
        f"ORCHESTRATION COMPLETE: Run {run_id}",
        f"Started: {summary['started_at']}",
        "",
        "DATASET SUMMARY:"
    ]

    loaded_count = 0
    skipped_count = 0
    failed_count = 0

    for filename, entry in summary["datasets"].items():
        status = entry["status"]
        if status == "LOADED":
            loaded_count += 1
            lines.append(
                f"  {filename:25s}: LOADED:     {entry['rows_loaded']:>8} rows\n")
        elif status == "SKIPPED":
            skipped_count += 1
            lines.append(
                f"  {filename:25s}: SKIPPED:    {entry['skip_reason']}\n")
        else:
            failed_count += 1
            lines.append(f"  {filename:25s}: FAILED     {entry['error']}\n")

    lines.extend([
        "",
        f"Total: {len(summary['datasets'])}  |  Loaded: {loaded_count}  |  Skipped: {skipped_count}  |  Failed: {failed_count}"
    ])

    report_text = "\n".join(lines)
    logging.info("\n" + report_text)
    send_alert(
        f"PIPELINE RUN {run_id} - Loaded: {loaded_count}  Skipped: {skipped_count}  Failed: {failed_count}",
        report_text
    )


def main():
    setup_logging()
    orchestrate()


if __name__ == "__main__":
    main()
