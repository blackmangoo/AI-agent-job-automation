"""
Centralized Logging Setup
==========================
Provides a configured logger with both colored console output and
rotating file handlers. All modules should use:

    from utils.logger import get_logger
    logger = get_logger(__name__)
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path


# ANSI color codes for console output
class _Colors:
    """ANSI escape codes for colored terminal output."""
    RESET = "\033[0m"
    GREY = "\033[90m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD_RED = "\033[1;91m"
    CYAN = "\033[96m"


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds ANSI colors based on log level.

    Attributes:
        LEVEL_COLORS: Mapping of log levels to their ANSI color codes.
    """

    LEVEL_COLORS = {
        logging.DEBUG: _Colors.GREY,
        logging.INFO: _Colors.GREEN,
        logging.WARNING: _Colors.YELLOW,
        logging.ERROR: _Colors.RED,
        logging.CRITICAL: _Colors.BOLD_RED,
    }

    def __init__(self, fmt: str = None, datefmt: str = None):
        super().__init__(fmt=fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with ANSI color codes.

        Args:
            record: The log record to format.

        Returns:
            Colored formatted string for console output.
        """
        color = self.LEVEL_COLORS.get(record.levelno, _Colors.RESET)
        record.levelname = f"{color}{record.levelname:<8}{_Colors.RESET}"
        record.msg = f"{_Colors.CYAN}{record.msg}{_Colors.RESET}"
        return super().format(record)


def get_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """Create and configure a logger with console and file handlers.

    Args:
        name: The logger name (typically __name__ of the calling module).
        level: Minimum log level. Defaults to DEBUG.

    Returns:
        A configured logging.Logger instance with:
        - Colored console handler (INFO level)
        - File handler writing to logs/YYYY-MM-DD.log (DEBUG level)
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if logger already configured
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Reconfigure stdout/stderr encoding to UTF-8 to prevent encoding errors on Windows
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    # --- Console handler (colored, INFO+) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_fmt = ColoredFormatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # --- File handler (plain text, DEBUG+) ---
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    return logger
