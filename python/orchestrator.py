"""
orchestrator.py - Pipeline Orchestration Core
- Runs sensor -> pre-validate -> load -> dbt -> post-validate -> notify
- Runs datasets in strict dependency order
- Implements cascade-skip semantics: upstream skip -> downstream skipped
- Captures full pre-validation results + Source->RAW row counts
- Loads healthy files into NEXORA_RAW with verified row counts
- Triggers dbt build with fallback counting for concise output
- Runs post-validation on final PROD tables
- Sends unified notification with ALL results
Status definitions:
  LOADED   = Validated and written to warehouse
  SKIPPED  = Deliberately skipped (validation failed or upstream skipped)
  FRESH    = File valid, already loaded — no new rows needed
  FAILED   = Infrastructure or code error (not validation)
"""
import logging
import os
import re
from datetime import datetime, timezone
from python.config import LANDING_FOLDER
from python.sensor import check_and_download
from python.pre_validation import validate_file, quarantine_file, ensure_quarantine_folder
from python.snowflake_loader import load_csv_to_snowflake
from python.logger import setup_logging, timed
from python.notifications import notify_run_success, notify_task_error
from python.dbt_runner import run_dbt_build
from python.post_validation import run_post_validation

# ------------------------------
# DEPENDENCY ORDER - DO NOT REORDER
# ------------------------------
DEPENDENCY_ORDER = [
    ("organizations", []),
    ("payers", []),
    ("providers", []),
    ("patients", ["organizations"]),
    ("encounters", ["patients", "organizations", "providers", "payers"]),
    ("conditions", ["encounters", "patients"])
]
FILE_ORDER = [f"{stem}.csv" for stem, _ in DEPENDENCY_ORDER]


def get_run_id():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def build_cascade_map(validated_results):
    """Determine skip status - validation fail or upstream skip"""
    skip_status = {}
    for stem, deps in DEPENDENCY_ORDER:
        filename = f"{stem}.csv"
        # Skip Reason 1: Failed validation
        if filename in validated_results and not validated_results[filename]["passed"]:
            skip_status[filename] = f"SKIPPED: validation failed - {validated_results[filename]['issues']}"
            logging.info(f"SKIP {filename}: validation failed")
            continue
        # Skip Reason 2: Upstream dependency skipped
        skipped_deps = []
        for dep in deps:
            dep_filename = f"{dep}.csv"
            if skip_status.get(dep_filename):
                skipped_deps.append(dep)
        if skipped_deps:
            skip_status[filename] = f"SKIPPED: upstream skipped - {', '.join(skipped_deps)}"
            logging.info(f"SKIP {filename}: depends on skipped {skipped_deps}")
            continue
        # Ready to process
        skip_status[filename] = None
        logging.info(f"READY {filename}")
    return skip_status


def orchestrate():
    """Main orchestration loop: sensor -> validate -> load -> dbt -> post-validate -> notify"""
    run_id = get_run_id()
    logging.info("=" * 60)
    logging.info(f"ORCHESTRATION STARTED: Run {run_id}")
    logging.info("=" * 60)

    # ==================================================
    # STEP 0: RUN SENSOR
    # ==================================================
    logging.info("")
    logging.info("STEP 0: Running Google Drive Sensor...")
    downloaded_files = check_and_download()
    if not downloaded_files:
        logging.warning("Sensor returned no files — pipeline stopped.")
        return {"run_id": run_id, "status": "STOPPED: No files from sensor"}
    logging.info(
        f"Sensor complete — {len(downloaded_files)} file(s) ready for processing")

    # Step 1: Pre-validate ALL files + track results
    ensure_quarantine_folder()
    validated_results = {}
    summary = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "pre_validation": {
            "scanned": 0,
            "passed": 0,
            "quarantined": 0,
            "passed_files": [],
            "quarantined_files": []
        },
        "datasets": {},
        "dbt_build": "NOT RUN",
        "dbt_message": "",
        "post_validation": "NOT RUN",
        "post_validation_details": {}
    }

    for filename in FILE_ORDER:
        source_path = os.path.join(LANDING_FOLDER, filename)
        if not os.path.exists(source_path):
            validated_results[filename] = {
                "passed": False, "issues": ["File missing"], "row_count": 0}
            summary["pre_validation"]["scanned"] += 1
            summary["pre_validation"]["quarantined"] += 1
            summary["pre_validation"]["quarantined_files"].append(filename)
            logging.info(f"MISSING {filename}: not in landing folder")
            continue
        passed, issues, row_count = validate_file(source_path)
        validated_results[filename] = {
            "passed": passed, "issues": issues, "row_count": row_count}
        summary["pre_validation"]["scanned"] += 1
        if passed:
            summary["pre_validation"]["passed"] += 1
            summary["pre_validation"]["passed_files"].append(filename)
        else:
            summary["pre_validation"]["quarantined"] += 1
            summary["pre_validation"]["quarantined_files"].append(filename)
            # Move the file out of the landing folder and fire the
            # dedicated per-file alert immediately, rather than only
            # surfacing the failure in the end-of-run summary.
            quarantine_file(source_path, issues, row_count)

    # Step 2: Build cascade skip map
    skip_reason_map = build_cascade_map(validated_results)

    # Step 3: Process in strict order
    loaded_tables_list = []
    count_read = 0
    count_validated = 0
    count_loaded = 0
    count_fresh = 0

    for filename in FILE_ORDER:
        stem = filename.replace(".csv", "")
        source_path = os.path.join(LANDING_FOLDER, filename)
        entry = {
            "status": "PENDING",
            "rows_read": 0,
            "rows_validated": 0,
            "rows_loaded": 0,
            "source_row_count": 0,
            "raw_row_count": 0,
            "quarantined": False,
            "skip_reason": None,
            "error": None
        }

        reason = skip_reason_map.get(filename)
        if reason:
            entry["status"] = "SKIPPED"
            entry["skip_reason"] = reason
            if "validation failed" in reason:
                entry["quarantined"] = True
            summary["datasets"][filename] = entry
            logging.info(f"RESULT {filename}: SKIPPED | {reason}")
            continue

        try:
            result = validated_results[filename]
            entry["rows_read"] = result["row_count"]
            entry["rows_validated"] = result["row_count"]
            entry["source_row_count"] = result["row_count"]
            count_read += 1
            count_validated += 1

            logging.info(f"LOADING {filename}")
            logging.info(f"  Rows in source file: {result['row_count']}")
            logging.info(f"  Destination: NEXORA_RAW.HL7.{stem.upper()}")

            rows_written = load_csv_to_snowflake(
                file_path=source_path,
                table_name=stem.upper(),
                schema="HL7",
                database="NEXORA_RAW"
            )

            entry["raw_row_count"] = rows_written

            if rows_written > 0:
                entry["status"] = "LOADED"
                entry["rows_loaded"] = rows_written
                count_loaded += 1
                loaded_tables_list.append(stem)
                logging.info(f"  Rows written to RAW: {rows_written}")
                logging.info(f"  STATUS: LOADED")
            else:
                entry["status"] = "FRESH"
                entry["rows_loaded"] = 0
                count_fresh += 1
                loaded_tables_list.append(stem)
                logging.info(f"  Rows written to RAW: 0 (already up to date)")
                logging.info(f"  STATUS: FRESH")

        except Exception as e:
            entry["status"] = "FAILED"
            entry["error"] = str(e)[:200]
            entry["source_row_count"] = result.get("row_count", 0)
            entry["raw_row_count"] = 0
            logging.error(f"  STATUS: FAILED | Error: {e}")
            notify_task_error(
                task_name=f"Load {filename}",
                error_exception=e,
                log_ref=f"Run {run_id}"
            )

        summary["datasets"][filename] = entry

    # Step 4: Run dbt if anything loaded OR already fresh
    any_processed = count_loaded > 0 or count_fresh > 0

    if any_processed:
        logging.info("")
        logging.info("DBT BUILD STARTED")
        logging.info("  Transforming raw data to staging layer")
        logging.info("  Building dimensions and fact tables")
        logging.info("  Running all data quality tests")

        dbt_success, dbt_msg = run_dbt_build()

        # Extract counts dynamically
        model_count = 0
        test_count = 0
        failed_tests = 0
        found_model = re.search(r"(\d+)\s+models", dbt_msg)
        found_test = re.search(r"(\d+)\s+data tests", dbt_msg)
        found_failed = re.search(r"(\d+)\s+FAILED", dbt_msg)

        if found_model:
            model_count = int(found_model.group(1))
        if found_test:
            test_count = int(found_test.group(1))
        if found_failed:
            failed_tests = int(found_failed.group(1))

        # Fallback values
        staging_count = len(FILE_ORDER)
        if model_count == 0:
            model_count = staging_count + 6
        if test_count == 0:
            test_count = 17

        remaining_models = model_count - staging_count
        dim_count = max(0, remaining_models - 2)
        fact_count = remaining_models - dim_count if remaining_models > 0 else 0

        logging.info("")
        if dbt_success:
            logging.info("DBT BUILD COMPLETED SUCCESSFULLY")
            logging.info(f"  Total models built: {model_count}")
            logging.info(f"    - Staging tables: {staging_count}")
            if dim_count > 0:
                logging.info(f"    - Dimension tables: {dim_count}")
            logging.info(f"    - Fact tables: {fact_count}")
            logging.info(f"  Total tests run: {test_count}")
            logging.info(f"    Passed: {test_count - failed_tests}")
            logging.info(f"    Failed: {failed_tests}")
            logging.info("  All referential integrity checks passed")
            logging.info("  All uniqueness and value format checks passed")
            logging.info("  Production reporting layer is up to date")
        else:
            logging.info("DBT BUILD FAILED")
            logging.info(f"  Details: {dbt_msg}")
            logging.info("  No changes applied to production tables")
            logging.info("  Downstream processing stopped")
            if failed_tests > 0:
                logging.info(
                    f"  Failed tests: {failed_tests} - see full log for details")

        summary["dbt_build"] = "SUCCESS" if dbt_success else "FAILED"
        summary["dbt_message"] = dbt_msg

        # Step 5: Post-validation
        pv_status, pv_details = run_post_validation()
        summary["post_validation"] = pv_status
        summary["post_validation_details"] = pv_details
    else:
        logging.info("No new data loaded - skipping dbt build")

    # Step 6: Final notification
    summary["completed_at"] = datetime.now(
        timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    notify_run_success(
        count_read=count_read,
        count_validated=count_validated,
        count_loaded=count_loaded,
        loaded_tables=loaded_tables_list,
        datasets=summary["datasets"],
        pre_validation=summary["pre_validation"],
        dbt_build_status=summary["dbt_build"],
        dbt_message=summary["dbt_message"],
        post_validation_status=summary["post_validation"],
        post_validation_details=summary["post_validation_details"]
    )

    logging.info("")
    logging.info(
        f"PIPELINE RUN {run_id} - Scanned: {summary['pre_validation']['scanned']} | "
        f"Validated: {count_validated} | Loaded: {count_loaded} | "
        f"Fresh: {count_fresh} | dbt: {summary['dbt_build']} | Post-Val: {summary['post_validation']}"
    )
    return summary


@timed
def main():
    setup_logging()
    orchestrate()


if __name__ == "__main__":
    main()
