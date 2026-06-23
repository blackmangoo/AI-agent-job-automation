"""
Centralized Logging Setup
==========================
Provides a configured logger with colored console output and file handlers.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path


class _Colors:
    RESET = "\033[0m"
    GREY = "\033[90m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD_RED = "\033[1;91m"
    CYAN = "\033[96m"


class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: _Colors.GREY,
        logging.INFO: _Colors.GREEN,
        logging.WARNING: _Colors.YELLOW,
        logging.ERROR: _Colors.RED,
        logging.CRITICAL: _Colors.BOLD_RED,
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, _Colors.RESET)
        record.levelname = f"{color}{record.levelname:<8}{_Colors.RESET}"
        record.msg = f"{_Colors.CYAN}{record.msg}{_Colors.RESET}"
        return super().format(record)


def get_logger(name, level=logging.DEBUG):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColoredFormatter(
        fmt="%(asctime)s \u2502 %(levelname)s \u2502 %(name)s \u2502 %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(console_handler)
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s \u2502 %(levelname)-8s \u2502 %(name)s \u2502 %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(file_handler)
    return logger
