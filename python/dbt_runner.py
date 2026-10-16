"""dbt_runner.py - Handles execution of dbt build commands and logging of results."""
from python.logger import setup_logging
import logging
import subprocess
import os
import sys  # Added

# Force UTF-8 encoding
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"


def run_dbt_build():
    """Run full dbt build - returns (success: bool, message: str)"""
    logging.info("Running: dbt build")

    project_root = os.path.dirname(os.path.dirname(__file__))
    profiles_dir = os.path.join(project_root, ".dbt")

    result = subprocess.run(
        ["dbt", "build", "--profiles-dir", profiles_dir],
        capture_output=True,
        text=True,
        encoding="utf-8",  # Force UTF-8 here
        errors="replace",   # Handle any remaining bad chars gracefully
        cwd=project_root
    )

    full_output = result.stdout + result.stderr

    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                logging.info(f"dbt: {line}")
    if result.stderr:
        for line in result.stderr.strip().split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("[WARNING]"):
                logging.info(f"dbt: {stripped}")

    if result.returncode == 0:
        logging.info("dbt build SUCCESS")
        return True, "All models and tests passed"

    error_markers = ["ERROR", "FAILED", "COMPILATION ERROR", "DATABASE ERROR"]
    has_real_error = any(term in full_output.upper() for term in error_markers)

    if not has_real_error:
        ok_patterns = ["Nothing to do", "up to date",
                       "PASS", "All checks passed"]
        if any(pattern in full_output for pattern in ok_patterns):
            logging.info("dbt build SUCCESS — All models already up to date")
            return True, "Models already up to date"

    err_tail = result.stderr[-800:] if len(
        result.stderr) > 800 else result.stderr
    logging.error(f"dbt FAILED:\n{err_tail}")
    return False, err_tail


def main():
    setup_logging()
    success, message = run_dbt_build()
    if not success:
        logging.error("DBT build failed")
    else:
        logging.info("DBT build succeeded")


if __name__ == "__main__":
    main()
