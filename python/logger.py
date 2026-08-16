import logging
import os
import platform
import re
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler


# Detect Windows
IS_WINDOWS = platform.system() == "Windows"


# Detect if console supports UTF‑8
def console_supports_utf8() -> bool:
    # macOS / Linux always UTF‑8
    if not IS_WINDOWS:
        return True

    # VS Code terminal
    if "VSCODE_INJECTION" in os.environ:
        return True

    # Windows Terminal
    if os.environ.get("WT_SESSION"):
        return True

    # PowerShell 7+ (UTF‑8 by default)
    if "pwsh" in os.environ.get("SHELL", "").lower():
        return True

    # Python stdout encoding
    if sys.stdout.encoding and "utf" in sys.stdout.encoding.lower():
        return True

    # Check Windows code page
    try:
        cp = subprocess.check_output("chcp", shell=True).decode()
        if "65001" in cp:  # UTF‑8 code page
            return True
    except Exception:
        pass

    return False


UTF8_SAFE = console_supports_utf8()


# Emoji stripping (only when unsafe)
def strip_emoji(text: str) -> str:
    if UTF8_SAFE:
        return text
    return re.sub(r"[^\x00-\x7F]+", "", text)


# Color Formatter (Console Only)
class ColorFormatter(logging.Formatter):
    COLORS = {
        "INFO": "\033[94m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "SUCCESS": "\033[92m",
        "DEBUG": "\033[90m",
        "RESET": "\033[0m",
    }

    def format(self, record):
        # Make a copy of the original message
        original_msg = str(record.msg)

        # Strip emojis only when terminal is unsafe
        safe_msg = strip_emoji(original_msg)

        # Replace only the message portion in the formatted output
        record.msg = safe_msg
        clean_output = super().format(record)

        # Restore original message so file handler is unaffected
        record.msg = original_msg

        # Apply color ONLY to console output
        color = self.COLORS.get(record.levelname, "")
        reset = self.COLORS["RESET"]

        # Only colorize the message portion, not the whole line
        return clean_output.replace(safe_msg, f"{color}{safe_msg}{reset}")


# Setup Logging
def setup_logging():
    os.makedirs("logs", exist_ok=True)

    # Console handler (colored)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        ColorFormatter("%(asctime)s - %(levelname)s - %(message)s")
    )

    # Rotating file handler (UTF‑8, clean text)
    file_handler = RotatingFileHandler(
        "logs/pipeline.log",
        maxBytes=2_000_000,
        backupCount=7,
        encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )

    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler],
        force=True
    )

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


# Helper utilities
def section(title: str):
    logging.info("\n" + "=" * 50)
    logging.info(f"🔷 {title}")   # emojis kept when safe
    logging.info("=" * 31 + "\n")


# logger.py — fix timed to return result
def timed(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start

        mins = int(elapsed // 60)
        secs = int(elapsed % 60)

        if mins > 0:
            logging.info(f"⏱️ Step completed in {mins}m {secs}s\n")
        else:
            logging.info(f"⏱️ Step completed in {secs}s\n")

        return result
    return wrapper
