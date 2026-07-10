"""
Human-Like Delay Utilities
============================
Provides randomized delay functions to simulate human typing and
browsing behavior. Used by the Form Filler to avoid bot detection.

Usage:
    from utils.delays import short_delay, medium_delay, long_delay
    short_delay()   # Between keystrokes
    medium_delay()  # Between form fields
    long_delay()    # Between page navigations
"""

import time
import random

from utils.logger import get_logger

logger = get_logger(__name__)


def short_delay() -> None:
    """Insert a short random delay (0.3–0.9 seconds).

    Used between individual keystrokes when typing into form fields
    to simulate natural human typing speed.
    """
    delay = random.uniform(0.3, 0.9)
    logger.debug(f"Short delay: {delay:.2f}s")
    time.sleep(delay)


def medium_delay() -> None:
    """Insert a medium random delay (1.2–2.8 seconds).

    Used between filling different form fields to simulate a person
    reading and thinking before moving to the next input.
    """
    delay = random.uniform(1.2, 2.8)
    logger.debug(f"Medium delay: {delay:.2f}s")
    time.sleep(delay)


def long_delay() -> None:
    """Insert a long random delay (3.0–6.5 seconds).

    Used between major page actions like navigation, page loads,
    and section transitions to simulate natural browsing behavior.
    """
    delay = random.uniform(3.0, 6.5)
    logger.debug(f"Long delay: {delay:.2f}s")
    time.sleep(delay)
