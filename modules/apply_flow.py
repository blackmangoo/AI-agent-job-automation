"""
Indeed Apply Flow Handler
===========================
Handles the multi-step Indeed application process:
1. Click "Apply now" button on the job listing page
2. Detect whether it's Indeed Easy Apply or external redirect
3. Navigate multi-step forms (click Continue between steps)
4. Coordinate with form_filler for field population

This module bridges the gap between scraping a job page and
actually filling the application form.
"""

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from utils.logger import get_logger
from utils.delays import medium_delay, long_delay

logger = get_logger(__name__)

# Selectors for the "Apply now" button on Indeed
APPLY_BUTTON_SELECTORS = [
    "button#indeedApplyButton",
    "button[data-testid='indeedApplyButton']",
    "button.jobsearch-IndeedApplyButton-newDesign",
    "a.jobsearch-IndeedApplyButton-newDesign",
    "button[aria-label*='Apply now']",
    "a[aria-label*='Apply now']",
    "button:has-text('Apply now')",
    "a:has-text('Apply now')",
    "button:has-text('Apply on company site')",
    "a:has-text('Apply on company site')",
    "span:has-text('Apply now')",
]

# Selectors for the Continue/Next/Submit buttons in multi-step forms
CONTINUE_BUTTON_SELECTORS = [
    "button[data-testid='continue-button']",
    "button#continueButton",
    "button:has-text('Continue')",
    "button:has-text('Next')",
    "button:has-text('Review')",
    "button[aria-label='Continue']",
    "button[type='submit']:has-text('Continue')",
    "button.ia-continueButton",
]

SUBMIT_BUTTON_SELECTORS = [
    "button[data-testid='submit-button']",
    "button#submitButton",
    "button:has-text('Submit your application')",
    "button:has-text('Submit application')",
    "button:has-text('Submit')",
    "button[aria-label='Submit']",
    "button.ia-submitButton",
]

# Indicators that the application was submitted
SUCCESS_INDICATORS = [
    "your application has been submitted",
    "application submitted",
    "you have applied",
    "thank you for applying",
    "application sent",
    "successfully applied",
]

# Indicators that we've already applied
ALREADY_APPLIED_INDICATORS = [
    "you've already applied",
    "you already applied",
    "you have already applied",
    "previously applied",
]

# Indicators of an external apply
EXTERNAL_APPLY_INDICATORS = [
    "apply on company site",
    "continue to apply",
    "apply on employer",
]


def click_apply_button(page: Page) -> str:
    """Find and click the 'Apply now' button on a job listing page.

    Args:
        page: Playwright Page with job listing loaded.

    Returns:
        Status string:
        - "indeed_apply" -- Indeed Easy Apply form opened
        - "external" -- Redirected to external company site
        - "already_applied" -- Already applied to this job
        - "not_found" -- No apply button found
    """
    logger.info("Looking for Apply button...")

    # First check if we've already applied
    try:
        page_text = page.inner_text("body").lower()
        for indicator in ALREADY_APPLIED_INDICATORS:
            if indicator in page_text:
                logger.info("Already applied to this job -- skipping")
                return "already_applied"
    except Exception:
        pass

    # Try each apply button selector
    for selector in APPLY_BUTTON_SELECTORS:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                btn_text = btn.inner_text().strip().lower()
                logger.info(f"Found apply button: '{btn_text}'")

                # Check if it's an external apply
                is_external = any(ind in btn_text for ind in EXTERNAL_APPLY_INDICATORS)

                # Click it
                btn.click()
                logger.info("Clicked apply button")
                page.wait_for_timeout(3000)

                if is_external:
                    logger.info("External application -- redirecting to company site")
                    return "external"

                return "indeed_apply"
        except Exception as e:
            logger.debug(f"Selector '{selector}' failed: {e}")
            continue

    logger.warning("No apply button found on this page")
    return "not_found"


def detect_apply_form(page: Page) -> str:
    """Detect what kind of application form is present after clicking Apply.

    Args:
        page: Playwright Page after clicking apply.

    Returns:
        Form type string:
        - "indeed_form" -- Indeed's built-in application form
        - "iframe_form" -- Form loaded in an iframe
        - "external_form" -- External company application page
        - "none" -- No form detected
    """
    # Check for Indeed Apply iframe
    try:
        frames = page.frames
        for frame in frames:
            if "indeed.com/applystart" in frame.url or "indeed.com/m/viewjob" in frame.url:
                logger.info("Detected Indeed Apply iframe")
                return "iframe_form"
    except Exception:
        pass

    # Check for Indeed form elements
    indeed_form_selectors = [
        "div[class*='ia-']",  # Indeed Apply class prefix
        "div.ia-BasePage",
        "form[action*='apply']",
        "div[data-testid='apply-form']",
        "input[name='applicant.name']",
        "input[name='applicant.email']",
    ]

    for selector in indeed_form_selectors:
        try:
            if page.query_selector(selector):
                logger.info("Detected Indeed Apply form on page")
                return "indeed_form"
        except Exception:
            continue

    # Check if we're on a new URL (external redirect)
    current_url = page.url.lower()
    if "indeed.com" not in current_url:
        logger.info(f"Redirected to external site: {current_url}")
        return "external_form"

    # Check for basic form elements
    try:
        form_elements = page.query_selector_all(
            "input:visible, select:visible, textarea:visible"
        )
        if len(form_elements) > 2:
            return "indeed_form"
    except Exception:
        pass

    return "none"


def get_apply_page(page: Page) -> Page:
    """Get the correct page/frame to interact with for the application form.

    If the form is in an iframe, returns the iframe's content frame.
    Otherwise returns the original page.

    Args:
        page: The main Playwright Page.

    Returns:
        The Page or Frame object to use for form filling.
    """
    # Check for iframes
    try:
        for frame in page.frames:
            if "indeed.com/applystart" in frame.url or "indeed.com/m/viewjob" in frame.url:
                logger.info("Using iframe for form interaction")
                return frame
    except Exception:
        pass

    return page


def click_continue(page: Page) -> bool:
    """Click the Continue/Next button in a multi-step form.

    Args:
        page: The Page or Frame with the form.

    Returns:
        True if a continue button was found and clicked.
    """
    for selector in CONTINUE_BUTTON_SELECTORS:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                logger.info("Clicking Continue button...")
                btn.click()
                page.wait_for_timeout(2000)
                return True
        except Exception:
            continue

    return False


def click_submit(page: Page) -> bool:
    """Click the Submit button to finalize the application.

    Args:
        page: The Page or Frame with the form.

    Returns:
        True if submitted successfully.
    """
    for selector in SUBMIT_BUTTON_SELECTORS:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                logger.info("Clicking Submit button...")
                btn.click()
                page.wait_for_timeout(3000)
                return True
        except Exception:
            continue

    return False


def is_application_complete(page: Page) -> bool:
    """Check if the application has been submitted successfully.

    Args:
        page: The Page after clicking submit.

    Returns:
        True if success indicators are present.
    """
    try:
        page_text = page.inner_text("body").lower()
        return any(indicator in page_text for indicator in SUCCESS_INDICATORS)
    except Exception:
        return False


def handle_multi_step_form(page: Page, fill_step_callback, max_steps: int = 5) -> str:
    """Navigate through a multi-step Indeed application form.

    Calls fill_step_callback on each step to fill visible fields,
    then clicks Continue until reaching the review/submit page.

    Args:
        page: The Page or Frame with the form.
        fill_step_callback: Function(page) that fills visible form fields.
            Called once per step.
        max_steps: Maximum number of steps before giving up.

    Returns:
        Status string:
        - "ready_to_submit" -- reached submit page
        - "submitted" -- auto-submitted
        - "stuck" -- could not progress
        - "error" -- exception occurred
    """
    for step in range(max_steps):
        logger.info(f"Processing form step {step + 1}...")

        # Fill fields on this step
        try:
            fill_step_callback(page)
        except Exception as e:
            logger.warning(f"Error filling step {step + 1}: {e}")

        medium_delay()

        # Check if we're on the submit page
        for selector in SUBMIT_BUTTON_SELECTORS:
            try:
                btn = page.query_selector(selector)
                if btn and btn.is_visible():
                    logger.info("Reached submit page")
                    return "ready_to_submit"
            except Exception:
                continue

        # Check if already submitted
        if is_application_complete(page):
            return "submitted"

        # Try to click Continue
        if not click_continue(page):
            logger.info("No Continue button found on this step")
            # Check if we're stuck or if this is a single-page form
            return "ready_to_submit"

        page.wait_for_timeout(2000)

    logger.warning(f"Exceeded max steps ({max_steps})")
    return "stuck"
