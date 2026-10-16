"""
Post-validation module - verifies final reporting layer meets business requirements
- Runs after dbt build completes successfully
- Checks that tables exist, are populated, and row counts align with expectations
- Runs reconciliation checks across all layers
- Answers: "Does this reporting layer satisfy the business requirements?"
- Sends dedicated alerts for any failures
"""
import logging
from python.snowflake_loader import get_connection
from python.notifications import notify_post_validation_failure, notify_post_validation_summary
from python.logger import setup_logging, section

# Schema names for staging and production layers
STAGING_SCHEMA = "DBT_YISMAIL_HL7_HL7"
PROD_SCHEMA = "DBT_YISMAIL_HL7_HL7"

EXPECTED_TABLES = {
    # Staging tables
    f"{STAGING_SCHEMA}.STG_HL7__CONDITIONS": {
        "min_rows": 1,
        "label": "Staging Conditions"
    },
    f"{STAGING_SCHEMA}.STG_HL7__ENCOUNTERS": {
        "min_rows": 1,
        "label": "Staging Encounters"
    },
    f"{STAGING_SCHEMA}.STG_HL7__ORGANIZATIONS": {
        "min_rows": 1,
        "label": "Staging Organizations"
    },
    f"{STAGING_SCHEMA}.STG_HL7__PATIENTS": {
        "min_rows": 1,
        "label": "Staging Patients"
    },
    f"{STAGING_SCHEMA}.STG_HL7__PAYERS": {
        "min_rows": 1,
        "label": "Staging Payers"
    },
    f"{STAGING_SCHEMA}.STG_HL7__PROVIDERS": {
        "min_rows": 1,
        "label": "Staging Providers"
    },
    # Dimension tables
    f"NEXORA_PROD.{PROD_SCHEMA}.DIM_ORGANIZATIONS": {
        "min_rows": 1,
        "label": "Dimension Organizations"
    },
    f"NEXORA_PROD.{PROD_SCHEMA}.DIM_PATIENTS": {
        "min_rows": 100,
        "label": "Dimension Patients"
    },
    f"NEXORA_PROD.{PROD_SCHEMA}.DIM_PAYERS": {
        "min_rows": 1,
        "label": "Dimension Payers"
    },
    f"NEXORA_PROD.{PROD_SCHEMA}.DIM_PROVIDERS": {
        "min_rows": 100,
        "label": "Dimension Providers"
    },
    # Fact tables
    f"NEXORA_PROD.{PROD_SCHEMA}.FCT_APPOINTMENTS": {
        "min_rows": 100,
        "label": "Fact Appointments"
    },
    f"NEXORA_PROD.{PROD_SCHEMA}.FCT_CONDITIONS": {
        "min_rows": 1000,
        "label": "Fact Conditions"
    }
}

# Business and reconciliation checks
EXTRA_CHECKS = [
    {
        "name": "Encounter reconciliation - STAGING = FACT",
        "query": f"""
            SELECT 
              (SELECT COUNT(*) FROM NEXORA_STAGING.{STAGING_SCHEMA}.STG_HL7__ENCOUNTERS) 
            = (SELECT COUNT(*) FROM NEXORA_PROD.{PROD_SCHEMA}.FCT_APPOINTMENTS) AS reconciled
        """
    },
    {
        "name": "No future encounters",
        "query": f"""
            SELECT COUNT(*) = 0 AS no_future
            FROM NEXORA_PROD.{PROD_SCHEMA}.FCT_APPOINTMENTS 
            WHERE ENCOUNTER_START > CURRENT_DATE
        """
    },
    {
        "name": "Patient count matches through all layers",
        "query": f"""
            SELECT 
              (SELECT COUNT(*) FROM NEXORA_STAGING.{STAGING_SCHEMA}.STG_HL7__PATIENTS)
            = (SELECT COUNT(*) FROM NEXORA_PROD.{PROD_SCHEMA}.DIM_PATIENTS) AS reconciled
        """
    }
]


def count_rows_in_table(full_table_path):
    """Return row count for a given fully-qualified table path"""
    try:
        parts = full_table_path.split(".")
        if len(parts) == 3:
            db_name, schema_name, table_name = parts
        elif len(parts) == 2:
            if full_table_path.startswith("NEXORA_PROD"):
                db_name = "NEXORA_PROD"
            else:
                db_name = "NEXORA_STAGING"
            schema_name, table_name = parts
        else:
            return None, f"Invalid table reference format: {full_table_path}"
    except ValueError:
        return None, f"Invalid table reference format: {full_table_path}"

    try:
        conn = get_connection(database=db_name, schema=schema_name)
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM {db_name}.{schema_name}.{table_name}")
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result[0], None
    except Exception as e:
        return None, str(e)


def run_extra_checks():
    """Execute business and reconciliation checks"""
    extra_results = {}
    for check in EXTRA_CHECKS:
        name = check["name"]
        sql = check["query"]
        logging.info(f"Running check: {name}")
        try:
            conn = get_connection(
                database="NEXORA_STAGING", schema=STAGING_SCHEMA)
            cur = conn.cursor()
            cur.execute(sql)
            result = cur.fetchone()
            cur.close()
            conn.close()
            passed = bool(result[0])
            extra_results[name] = {
                "status": "PASSED" if passed else "FAILED",
                "detail": "Requirement satisfied" if passed else "Requirement NOT met"
            }
            logging.info(f"  -> {extra_results[name]['status']}")
        except Exception as e:
            extra_results[name] = {
                "status": "FAILED",
                "detail": f"Check error: {str(e)[:200]}"
            }
            logging.warning(f"  -> FAILED: {str(e)[:200]}")
    return extra_results


def run_post_validation():
    """Execute all post-validation checks"""
    section("STARTING POST-VALIDATION")
    results = {}
    all_passed = True

    # Table existence and row count checks
    for table_path, rules in EXPECTED_TABLES.items():
        label = rules["label"]
        min_rows = rules["min_rows"]
        logging.info(f"Checking: {label} ({table_path})")

        row_count, error = count_rows_in_table(table_path)

        if error:
            results[table_path] = {
                "status": "FAILED",
                "label": label,
                "detail": f"Access error: {error[:150]}",
                "count": 0
            }
            all_passed = False
            logging.error(f"FAILED: {label} - {error[:150]}")
            notify_post_validation_failure(
                check_name=label,
                table_reference=table_path,
                issue_description=f"Could not verify table: {error[:200]}"
            )
            continue

        if row_count < min_rows:
            results[table_path] = {
                "status": "FAILED",
                "label": label,
                "detail": f"Row count {row_count} below minimum {min_rows}",
                "count": row_count
            }
            all_passed = False
            logging.warning(
                f"FAILED: {label} - {row_count} rows (min {min_rows})")
            notify_post_validation_failure(
                check_name=label,
                table_reference=table_path,
                issue_description=f"Insufficient data: {row_count} rows, expected at least {min_rows}"
            )
        else:
            results[table_path] = {
                "status": "PASSED",
                "label": label,
                "detail": f"{row_count} rows verified",
                "count": row_count
            }
            logging.info(f"PASSED: {label} - {row_count} rows")

    # Run reconciliation checks
    section("BUSINESS AND RECONCILIATION CHECKS")
    extra_results = run_extra_checks()
    for name, outcome in extra_results.items():
        if outcome["status"] != "PASSED":
            all_passed = False
    results.update(extra_results)

    overall_status = "PASSED" if all_passed else "FAILED"
    logging.info(f"POST-VALIDATION COMPLETE: {overall_status}")

    passed_list = []
    failed_list = []
    for key, outcome in results.items():
        if outcome["status"] == "PASSED":
            passed_list.append(
                f"{outcome.get('label', key)}: {outcome['detail']}")
        else:
            failed_list.append(
                f"{outcome.get('label', key)}: {outcome['detail']}")

    notify_post_validation_summary(
        total_checked=len(results),
        count_passed=len(passed_list),
        count_failed=len(failed_list),
        passed_checks=passed_list,
        failed_checks=failed_list
    )

    return overall_status, results


def main():
    setup_logging()
    status, results = run_post_validation()
    return status, results


if __name__ == "__main__":
    main()
