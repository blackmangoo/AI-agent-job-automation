"""
Browser Launch & Context Utilities
====================================
Manages Playwright browser lifecycle with persistent context for
maintaining login sessions between runs.

Includes anti-detection stealth techniques to avoid Cloudflare and
bot-detection systems from flagging the automated browser.

Usage:
    from utils.browser import launch_browser, close_browser
    browser, context, page = launch_browser()
    # ... do work ...
    close_browser(browser)
"""

import os
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from utils.logger import get_logger

logger = get_logger(__name__)

# Module-level playwright instance for cleanup
_playwright_instance = None

# JavaScript to inject on every page to hide automation indicators
_STEALTH_JS = """
() => {
    // Remove webdriver flag
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // Override the chrome.runtime to look like a real Chrome browser
    if (!window.chrome) { window.chrome = {}; }
    if (!window.chrome.runtime) { window.chrome.runtime = {}; }

    // Override permissions query
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters);

    // Override plugins to have realistic length
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });

    // Override languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });
}
"""


def launch_browser(
    headless: bool = False,
    user_data_dir: str = None,
) -> tuple:
    """Launch Google Chrome with a persistent local profile.

    Due to security changes in Chrome 136+, Chrome completely blocks remote
    debugging and automation on the default profile folder to prevent cookie theft.
    Therefore, we must use a dedicated local profile directory (./browser_data).

    You only need to log into Indeed once in this browser window, and it will
    remain logged in for all future runs.

    Args:
        headless: If False (default), shows the browser window.
        user_data_dir: Directory for the persistent profile. Defaults to ./browser_data.

    Returns:
        A tuple of (playwright, browser_context, page).

    Raises:
        RuntimeError: If browser launch fails.
    """
    global _playwright_instance
    import os

    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    executable_path = next((p for p in chrome_candidates if os.path.exists(p)), None)

    if user_data_dir is None or user_data_dir == "C:\\Users\\ammar\\AppData\\Local\\Google\\Chrome\\User Data":
        user_data_dir = "./browser_data"

    # Ensure the browser data directory exists
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    logger.info(f"Launching Chrome (headless={headless}, profile={user_data_dir}, exe={executable_path})")

    try:
        _playwright_instance = sync_playwright().start()

        launch_kwargs = {
            "user_data_dir": user_data_dir,
            "headless": headless,
            "viewport": {"width": 1280, "height": 720},
            "locale": "en-US",
            "timezone_id": "Asia/Karachi",
            "args": [],
            "ignore_default_args": ["--enable-automation", "--no-sandbox"],
        }
        if executable_path:
            launch_kwargs["executable_path"] = executable_path

        # Launch persistent context using clean profile
        context = _playwright_instance.chromium.launch_persistent_context(**launch_kwargs)

        # Inject stealth anti-detection script into all pages and frames
        context.add_init_script(_STEALTH_JS)

        # Use existing page if available, otherwise create one
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()

        logger.info("Browser launched successfully with clean persistent profile")
        return _playwright_instance, context, page

    except Exception as e:
        logger.error(f"Failed to launch browser: {e}")
        if _playwright_instance:
            _playwright_instance.stop()
        raise RuntimeError(f"Browser launch failed: {e}")


def wait_for_cloudflare(page: Page, timeout: int = 30000) -> bool:
    """Wait for a Cloudflare challenge to resolve on the current page.

    Polls the page for up to `timeout` ms. Returns True once the
    Cloudflare verification page is no longer detected, or False if
    the timeout expires.

    Args:
        page: The current Playwright Page object.
        timeout: Maximum time to wait in milliseconds.

    Returns:
        True if the page cleared Cloudflare, False if still blocked.
    """
    import time

    CLOUDFLARE_INDICATORS = [
        "additional verification required",
        "verify you are human",
        "just a moment...",
        "attention required!",
        "ray id for this request",
        "troubleshooting cloudflare errors",
    ]

    deadline = time.time() + (timeout / 1000)
    check_interval = 2  # seconds

    while time.time() < deadline:
        try:
            page_text = page.inner_text("body").lower()
            is_blocked = any(indicator in page_text for indicator in CLOUDFLARE_INDICATORS)
            if not is_blocked:
                logger.info("Cloudflare challenge cleared — page is ready")
                return True
                
            # Attempt to auto-click the Turnstile/Cloudflare checkbox
            try:
                # First try the main page
                cb = page.locator('.cb-i, input[type="checkbox"], #challenge-stage').first
                if cb.is_visible(timeout=100):
                    logger.info("Auto-clicking Cloudflare verification checkbox (main page)...")
                    cb.click()
                    page.wait_for_timeout(2000)
                else:
                    # Look for the Cloudflare iframe
                    for frame in page.frames:
                        if "challenges.cloudflare.com" in frame.url or "turnstile" in frame.url:
                            logger.info("Auto-clicking Cloudflare verification (iframe body)...")
                            try:
                                frame.locator('body').click(force=True)
                            except Exception as e:
                                logger.debug(f"Click failed: {e}")
                            page.wait_for_timeout(3000)
            except Exception as e:
                logger.debug(f"Could not auto-click CAPTCHA: {e}")
                
        except Exception:
            pass  # Page may be navigating

        time.sleep(check_interval)

    logger.warning("Cloudflare challenge did not clear within timeout")
    return False


def close_browser(playwright_instance=None, context: BrowserContext = None) -> None:
    """Safely close the browser and stop the Playwright instance.

    Args:
        playwright_instance: The Playwright instance to stop.
            If None, uses the module-level instance.
        context: The BrowserContext to close. If provided, closes it first.
    """
    global _playwright_instance

    pw = playwright_instance or _playwright_instance

    try:
        if context:
            context.close()
            logger.info("Browser context closed")
        if pw:
            pw.stop()
            logger.info("Playwright instance stopped")
            _playwright_instance = None
    except Exception as e:
        logger.warning(f"Error during browser cleanup: {e}")
