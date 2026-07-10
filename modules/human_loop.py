"""
Human-in-the-Loop Intervention Handler
========================================
Module 4: Detects situations that require human intervention (CAPTCHAs,
file uploads, login walls, OTP prompts, custom essays) and pauses the
browser via Playwright Inspector to let the user take control.

After the user completes the intervention and clicks Resume in the
Playwright Inspector, the agent continues automatically.
"""

from playwright.sync_api import Page

from utils.logger import get_logger

logger = get_logger(__name__)

# Detection configuration
# NOTE: Order matters — CAPTCHA/Cloudflare is checked first so it takes
#       priority over other patterns that may also appear on the same page.
INTERVENTION_CHECKS = [
    {
        "name": "CAPTCHA / CLOUDFLARE VERIFICATION",
        "phase": "any",  # Check in any phase (navigation or form)
        "selectors": [
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            "iframe[src*='captcha']",
            "iframe[src*='challenges.cloudflare.com']",
            "iframe[src*='turnstile']",
            "iframe[title*='cloudflare']",
            "div[class*='captcha']",
            "div[class*='CAPTCHA']",
            "div#captcha",
            "div#challenge-running",
            "div.cf-turnstile",
            "div#turnstile-wrapper",
        ],
        "text_patterns": [
            "additional verification required",
            "troubleshooting cloudflare errors",
            "verify you are human",
            "i'm not a robot",
            "prove you're not a robot",
            "complete the security check",
            "verify you are not a robot",
            "just a moment...",
            "ray id for this request",
            "attention required!",
        ],
    },
    {
        "name": "LOGIN WALL",
        "phase": "any",
        "selectors": [
            "form[action*='login']",
            "form[action*='signin']",
            "form[action*='sign-in']",
            "input[name='password']",
            "div[class*='login-form']",
            "div[class*='signin']",
        ],
        "text_patterns": [
            "sign in to continue",
            "log in to apply",
            "please sign in",
            "create an account",
            "sign in to your account",
        ],
        "url_filter": True,  # Only trigger if URL contains login/signin
    },
    {
        "name": "OTP / 2FA VERIFICATION",
        "phase": "any",
        "selectors": [
            "input[name*='otp']",
            "input[name*='verification']",
            "input[aria-label*='verification code']",
        ],
        "text_patterns": [
            "enter otp",
            "verification code",
            "enter the code",
            "two-factor",
            "2fa",
            "we sent a code",
        ],
    },
    {
        "name": "FILE UPLOAD REQUIRED",
        "phase": "form",  # Only check during form filling
        "selectors": [
            "input[type='file']",
            "button[class*='upload']",
            "div[class*='file-upload']",
            "label[class*='upload']",
        ],
        "text_patterns": [
            "upload your resume",
            "upload cv",
            "attach resume",
            "upload file",
            "drag and drop",
        ],
    },
    {
        "name": "CUSTOM ESSAY / COVER LETTER",
        "phase": "form",  # Only check during form filling
        "selectors": [],  # Handled specially — detects unmatched textareas
        "text_patterns": [
            "why do you want to work",
            "tell us about yourself",
            "write a cover letter",
            "describe your experience",
            "additional information",
        ],
    },
]


def _print_intervention_banner(reason: str) -> None:
    """Print a visible console banner alerting the user to take action.

    Args:
        reason: The reason human intervention is required.
    """
    banner = f"""
+----------------------------------------------------------+
|   HUMAN INTERVENTION REQUIRED                            |
|                                                          |
|   Reason: {reason:<46} |
|                                                          |
|   -> Complete the action in the browser window           |
|   -> Then click Resume in the Playwright Inspector       |
+----------------------------------------------------------+
"""
    # Using print() intentionally here — banners should always be visible
    print(banner)


def _is_cloudflare_blocked(page: Page) -> bool:
    """Quick check if the current page is a Cloudflare challenge page.

    Args:
        page: The current Playwright Page object.

    Returns:
        True if Cloudflare verification is detected.
    """
    try:
        page_text = page.inner_text("body").lower()
        cloudflare_indicators = [
            "additional verification required",
            "verify you are human",
            "just a moment...",
            "troubleshooting cloudflare errors",
            "ray id for this request",
            "attention required!",
        ]
        return any(indicator in page_text for indicator in cloudflare_indicators)
    except Exception:
        return False


def check_for_intervention(page: Page, known_questions: list = None, is_form: bool = False) -> str:
    """Check the current page for conditions requiring human intervention.

    Scans the page for CAPTCHAs, file uploads, login walls, OTP prompts,
    and unrecognized textareas. If any are detected, prints a console
    banner and pauses the browser via page.pause() so the user can
    handle it manually.

    After the user resolves the intervention and clicks Resume, this
    function waits for the page to stabilize before returning.

    Args:
        page: The current Playwright Page object.
        known_questions: List of screening question texts that the LLM
            has already prepared answers for. Textareas matching these
            will NOT trigger intervention.
        is_form: Boolean indicating whether we are actively filling an
            application form. File upload and essay checks are only run
            when True.

    Returns:
        Status string indicating what was detected:
        - "clear" — no intervention needed
        - "<type>_resolved" — intervention was detected and user handled it
    """
    if known_questions is None:
        known_questions = []

    current_phase = "form" if is_form else "navigation"
    logger.debug(f"Checking for intervention triggers (phase={current_phase})...")
    page_text = ""

    try:
        page_text = page.inner_text("body").lower()
    except Exception:
        logger.debug("Could not extract page text for intervention check")

    # Check each intervention type
    for check in INTERVENTION_CHECKS:
        name = check["name"]
        phase = check.get("phase", "any")

        # Skip checks that don't apply to the current phase
        if phase != "any" and phase != current_phase:
            continue

        # Check CSS selectors
        for selector in check["selectors"]:
            try:
                if page.query_selector(selector):
                    # Special handling for textareas — only flag unknown ones
                    if name == "CUSTOM ESSAY / COVER LETTER":
                        continue  # Handled below separately
                    logger.warning(f"Intervention trigger detected: {name} (selector: {selector})")
                    _print_intervention_banner(name)
                    page.pause()
                    # Wait for page to stabilize after user intervention
                    page.wait_for_timeout(3000)
                    return f"{name.lower().replace(' ', '_').replace('/', '_')}_resolved"
            except Exception:
                continue

        # Check text patterns
        for pattern in check["text_patterns"]:
            if pattern.lower() in page_text:
                # URL filter: Don't flag login text if we're on the actual job page
                if check.get("url_filter"):
                    current_url = page.url.lower()
                    if "login" not in current_url and "signin" not in current_url:
                        continue

                logger.warning(f"Intervention trigger detected: {name} (text: '{pattern}')")
                _print_intervention_banner(name)
                page.pause()
                # Wait for page to stabilize after user intervention
                page.wait_for_timeout(3000)
                return f"{name.lower().replace(' ', '_').replace('/', '_')}_resolved"

    # Special check for unmatched textareas (potential essay questions) during form filling
    if is_form:
        _check_unknown_textareas(page, known_questions)

    logger.debug("No intervention triggers detected — all clear")
    return "clear"


def _check_unknown_textareas(page: Page, known_questions: list) -> None:
    """Detect textarea fields that aren't covered by screening answers.

    If a textarea is found that doesn't match any of the known screening
    questions, it likely requires a custom response (essay, cover letter)
    that the LLM hasn't prepared for.

    Args:
        page: The current Playwright Page object.
        known_questions: Questions the LLM has prepared answers for.
    """
    try:
        textareas = page.query_selector_all("textarea")

        for textarea in textareas:
            # Try to find the label for this textarea
            textarea_id = textarea.get_attribute("id") or ""
            textarea_name = textarea.get_attribute("name") or ""
            textarea_label = textarea.get_attribute("aria-label") or ""
            textarea_placeholder = textarea.get_attribute("placeholder") or ""

            identifier = f"{textarea_id} {textarea_name} {textarea_label} {textarea_placeholder}".lower()

            # Check if this textarea is already accounted for
            is_known = False
            for q in known_questions:
                if any(word in identifier for word in q.lower().split() if len(word) > 3):
                    is_known = True
                    break

            if not is_known and identifier.strip():
                logger.warning(
                    f"Unknown textarea detected: id='{textarea_id}', "
                    f"name='{textarea_name}', placeholder='{textarea_placeholder}'"
                )
                _print_intervention_banner(
                    f"CUSTOM TEXT FIELD: {textarea_placeholder or textarea_name or textarea_id}"
                )
                page.pause()
                return

    except Exception as e:
        logger.debug(f"Error checking textareas: {e}")
