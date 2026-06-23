"""Browser Launch & Context Utilities"""

import os
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from utils.logger import get_logger

logger = get_logger(__name__)
_playwright_instance = None


def launch_browser(headless=False, user_data_dir=None):
    global _playwright_instance
    if user_data_dir is None:
        user_data_dir = os.getenv("BROWSER_DATA_DIR", "./browser_data")
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)
    logger.info(f"Launching browser (headless={headless}, profile={user_data_dir})")
    try:
        _playwright_instance = sync_playwright().start()
        context = _playwright_instance.chromium.launch_persistent_context(
            user_data_dir=user_data_dir, headless=headless,
            viewport={"width": 1280, "height": 720}, locale="en-US",
            timezone_id="Asia/Karachi",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        logger.info("Browser launched successfully with persistent session")
        return _playwright_instance, context, page
    except Exception as e:
        if _playwright_instance: _playwright_instance.stop()
        raise RuntimeError(f"Browser launch failed: {e}")


def close_browser(playwright_instance=None, context=None):
    global _playwright_instance
    pw = playwright_instance or _playwright_instance
    try:
        if context: context.close()
        if pw: pw.stop(); _playwright_instance = None
    except Exception as e:
        logger.warning(f"Browser cleanup error: {e}")
