"""
Human-Like Delay Utilities
============================
Randomized delays to simulate human typing and browsing behavior.
"""

import time
import random
from utils.logger import get_logger

logger = get_logger(__name__)


def short_delay():
    delay = random.uniform(0.3, 0.9)
    logger.debug(f"Short delay: {delay:.2f}s")
    time.sleep(delay)


def medium_delay():
    delay = random.uniform(1.2, 2.8)
    logger.debug(f"Medium delay: {delay:.2f}s")
    time.sleep(delay)


def long_delay():
    delay = random.uniform(3.0, 6.5)
    logger.debug(f"Long delay: {delay:.2f}s")
    time.sleep(delay)
