"""
Form-Filling Execution Engine
================================
Module 3: Uses Playwright to fill job application forms with data from
the LLM Brain's analysis and the candidate's profile. Implements
human-like typing delays and smart field location strategies.
"""

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from config.candidate_profile import CANDIDATE, CandidateProfile
from modules.human_loop import check_for_intervention
from utils.delays import short_delay, medium_delay, long_delay
from utils.logger import get_logger

logger = get_logger(__name__)

# Standard form field mappings — maps common label patterns to candidate data
STANDARD_FIELDS = {
    # Name fields
    "full name": lambda c: c.full_name,
    "first name": lambda c: c.full_name.split()[0],
    "last name": lambda c: c.full_name.split()[-1],
    "name": lambda c: c.full_name,

    # Contact fields
    "email": lambda c: c.email,
    "e-mail": lambda c: c.email,
    "email address": lambda c: c.email,
    "phone": lambda c: c.phone,
    "phone number": lambda c: c.phone,
    "mobile": lambda c: c.phone,
    "contact number": lambda c: c.phone,

    # Professional links
    "linkedin": lambda c: c.linkedin,
    "linkedin url": lambda c: c.linkedin,
    "linkedin profile": lambda c: c.linkedin,
    "github": lambda c: c.github,
    "github url": lambda c: c.github,
    "github profile": lambda c: c.github,
    "portfolio": lambda c: c.portfolio,
    "portfolio url": lambda c: c.portfolio,
    "website": lambda c: c.portfolio,
    "personal website": lambda c: c.portfolio,

    # Location
    "city": lambda c: "Islamabad",
    "location": lambda c: c.location,
    "address": lambda c: "Islamabad, Pakistan",
    "country": lambda c: "Pakistan",

    # Education
    "university": lambda c: c.university,
    "school": lambda c: c.university,
    "degree": lambda c: c.degree,
    "graduation year": lambda c: "2026",
    "gpa": lambda c: "N/A",
}


def fill_application_form(
    page: Page,
    llm_response: dict,
    candidate: CandidateProfile = None,
) -> bool:
    """Fill a job application form using LLM analysis and candidate data.

    Only proceeds if the LLM determined the candidate is eligible.
    Uses a multi-strategy approach to locate form fields:
    1. Exact label text match
    2. Placeholder attribute match
    3. name/id attribute match
    4. field_hint from LLM response

    Args:
        page: The Playwright Page with the application form loaded.
        llm_response: Dict from llm_brain.analyze_job() containing:
            - eligible (bool)
            - eligibility_reason (str)
            - screening_answers (list of dicts)
            - resume_objective (str)
        candidate: CandidateProfile instance. Defaults to CANDIDATE singleton.

    Returns:
        True if form was filled successfully, False if not eligible or on error.
    """
    if candidate is None:
        candidate = CANDIDATE

    # Gate: only proceed if eligible
    if not llm_response.get("eligible", False):
        logger.info(
            f"⏭️ Skipping — not eligible: {llm_response.get('eligibility_reason', 'No reason given')}"
        )
        return False

    logger.info("Starting form fill — candidate is eligible")

    try:
        # Phase 1: Fill standard fields (name, email, phone, links)
        _fill_standard_fields(page, candidate)
        medium_delay()

        # Check for intervention after standard fields
        check_for_intervention(page, _get_known_questions(llm_response))

        # Phase 2: Fill screening question answers from LLM
        _fill_screening_answers(page, llm_response)
        medium_delay()

        # Check for intervention after screening answers
        check_for_intervention(page, _get_known_questions(llm_response))

        # Phase 3: Fill resume objective / cover note if fields exist
        _fill_optional_text_fields(page, llm_response)

        logger.info("✅ Form fill completed successfully")
        return True

    except Exception as e:
        logger.error(f"Form fill failed: {e}")
        return False


def _fill_standard_fields(page: Page, candidate: CandidateProfile) -> None:
    """Fill standard application fields (name, email, phone, links).

    Args:
        page: Playwright Page object.
        candidate: CandidateProfile with contact information.
    """
    logger.info("Phase 1: Filling standard fields...")

    # Find all visible input/select/textarea elements
    inputs = page.query_selector_all(
        "input:visible, select:visible, textarea:visible"
    )

    for element in inputs:
        try:
            # Determine what this field is for
            field_identity = _identify_field(page, element)

            if not field_identity:
                continue

            # Check if we have a standard mapping for this field
            for pattern, value_fn in STANDARD_FIELDS.items():
                if pattern in field_identity.lower():
                    value = value_fn(candidate)
                    _fill_field(page, element, value)
                    logger.debug(f"Filled '{field_identity}' with standard value")
                    medium_delay()
                    break

        except Exception as e:
            logger.debug(f"Skipped field: {e}")
            continue


def _fill_screening_answers(page: Page, llm_response: dict) -> None:
    """Fill screening question answers from the LLM's analysis.

    Args:
        page: Playwright Page object.
        llm_response: Dict containing screening_answers list.
    """
    answers = llm_response.get("screening_answers", [])

    if not answers:
        logger.info("No screening answers to fill")
        return

    logger.info(f"Phase 2: Filling {len(answers)} screening answers...")

    for i, answer_data in enumerate(answers):
        question = answer_data.get("question", "")
        answer = answer_data.get("answer", "")
        hint = answer_data.get("field_hint", "")

        if not answer:
            continue

        logger.debug(f"  Q{i + 1}: {question[:60]}...")
        logger.debug(f"  A{i + 1}: {answer[:60]}...")

        # Try to find the corresponding field
        field = _find_field_for_question(page, question, hint)

        if field:
            _fill_field(page, field, answer)
            medium_delay()
        else:
            logger.warning(f"Could not locate field for: '{question[:50]}...'")


def _fill_optional_text_fields(page: Page, llm_response: dict) -> None:
    """Fill optional fields like resume objective or cover note.

    Args:
        page: Playwright Page object.
        llm_response: Dict with resume_objective and cover_note.
    """
    logger.info("Phase 3: Checking for optional text fields...")

    # Try to find and fill resume objective / summary field
    objective = llm_response.get("resume_objective", "")
    if objective:
        objective_selectors = [
            "textarea[name*='objective']",
            "textarea[name*='summary']",
            "textarea[aria-label*='objective']",
            "textarea[aria-label*='summary']",
            "textarea[placeholder*='objective']",
            "textarea[placeholder*='summary']",
        ]
        for selector in objective_selectors:
            field = page.query_selector(selector)
            if field:
                _fill_field(page, field, objective)
                logger.debug("Filled resume objective field")
                break

    # Try to find and fill cover note field
    cover_note = llm_response.get("cover_note", "")
    if cover_note:
        cover_selectors = [
            "textarea[name*='cover']",
            "textarea[name*='message']",
            "textarea[aria-label*='cover']",
            "textarea[placeholder*='cover']",
            "textarea[placeholder*='message']",
            "textarea[name*='note']",
        ]
        for selector in cover_selectors:
            field = page.query_selector(selector)
            if field:
                _fill_field(page, field, cover_note)
                logger.debug("Filled cover note field")
                break


def _identify_field(page: Page, element) -> str:
    """Determine what a form field is for by examining its attributes and label.

    Args:
        page: Playwright Page object.
        element: The form element to identify.

    Returns:
        A string representing the field's identity (label text, placeholder, etc.)
        or empty string if unidentifiable.
    """
    identifiers = []

    # Check associated label (via 'for' attribute)
    field_id = element.get_attribute("id")
    if field_id:
        label = page.query_selector(f"label[for='{field_id}']")
        if label:
            identifiers.append(label.inner_text().strip())

    # Check aria-label
    aria_label = element.get_attribute("aria-label")
    if aria_label:
        identifiers.append(aria_label.strip())

    # Check placeholder
    placeholder = element.get_attribute("placeholder")
    if placeholder:
        identifiers.append(placeholder.strip())

    # Check name attribute
    name = element.get_attribute("name")
    if name:
        identifiers.append(name.strip())

    # Check nearest label (parent traversal)
    try:
        parent_label = element.evaluate(
            """el => {
                let parent = el.closest('label');
                if (parent) return parent.innerText.trim();
                let prev = el.previousElementSibling;
                if (prev && prev.tagName === 'LABEL') return prev.innerText.trim();
                return '';
            }"""
        )
        if parent_label:
            identifiers.append(parent_label)
    except Exception:
        pass

    return " | ".join(identifiers)


def _find_field_for_question(page: Page, question: str, hint: str):
    """Find a form field that corresponds to a screening question.

    Uses a multi-strategy approach:
    1. Look for label containing the question text
    2. Use the CSS selector hint from the LLM
    3. Search by placeholder text
    4. Search by aria-label

    Args:
        page: Playwright Page object.
        question: The screening question text.
        hint: CSS selector hint from the LLM.

    Returns:
        The matching form element, or None if not found.
    """
    # Strategy 1: Find label with matching text, then find its input
    try:
        # Get key words from the question for fuzzy matching
        key_words = [w for w in question.lower().split() if len(w) > 3][:5]

        labels = page.query_selector_all("label")
        for label in labels:
            label_text = label.inner_text().lower().strip()
            matches = sum(1 for w in key_words if w in label_text)
            if matches >= min(3, len(key_words)):  # Match at least 3 key words
                # Find the associated input
                for_attr = label.get_attribute("for")
                if for_attr:
                    field = page.query_selector(f"#{for_attr}")
                    if field:
                        return field
                # Check for input inside the label
                field = label.query_selector("input, select, textarea")
                if field:
                    return field
    except Exception as e:
        logger.debug(f"Label strategy failed: {e}")

    # Strategy 2: Use the LLM's CSS selector hint
    if hint:
        try:
            field = page.query_selector(hint)
            if field:
                return field
        except Exception:
            logger.debug(f"Hint selector failed: {hint}")

    # Strategy 3: Search by placeholder
    try:
        key_phrase = " ".join(question.split()[:4]).lower()
        field = page.query_selector(f"input[placeholder*='{key_phrase}' i]")
        if field:
            return field
    except Exception:
        pass

    # Strategy 4: Search by aria-label
    try:
        field = page.query_selector(f"[aria-label*='{question[:30]}' i]")
        if field:
            return field
    except Exception:
        pass

    return None


def _fill_field(page: Page, element, value: str) -> None:
    """Fill a form field with the given value using human-like behavior.

    Handles different field types:
    - text/email/tel/url inputs: character-by-character typing
    - select elements: option selection
    - checkboxes/radios: click-based
    - textareas: character-by-character typing

    Args:
        page: Playwright Page object.
        element: The form element to fill.
        value: The value to enter.
    """
    tag = element.evaluate("el => el.tagName.toLowerCase()")
    input_type = (element.get_attribute("type") or "text").lower()

    try:
        if tag == "select":
            # Try to select by visible text first, then by value
            try:
                element.select_option(label=value)
            except Exception:
                try:
                    element.select_option(value=value)
                except Exception:
                    # Try partial match on option text
                    options = element.query_selector_all("option")
                    for opt in options:
                        opt_text = opt.inner_text().lower()
                        if value.lower() in opt_text or opt_text in value.lower():
                            element.select_option(value=opt.get_attribute("value"))
                            break
            logger.debug(f"Selected option: {value}")

        elif input_type in ("checkbox", "radio"):
            # For checkboxes/radios, click if the answer is affirmative
            affirmative = value.lower() in ("yes", "true", "1", "agree", "accept")
            if affirmative and not element.is_checked():
                element.click()
                logger.debug("Checked checkbox/radio")
            elif not affirmative and element.is_checked():
                element.click()
                logger.debug("Unchecked checkbox/radio")

        elif tag == "textarea" or input_type in ("text", "email", "tel", "url", "number", "search"):
            # Clear existing content
            element.click()
            element.evaluate("el => el.value = ''")
            short_delay()

            # Type character by character for human-like behavior
            element.type(value, delay=50)  # 50ms between keystrokes
            logger.debug(f"Typed value ({len(value)} chars)")

        else:
            # Fallback: try fill()
            element.fill(value)
            logger.debug(f"Filled field with value ({len(value)} chars)")

    except Exception as e:
        logger.warning(f"Failed to fill field: {e}")


def _get_known_questions(llm_response: dict) -> list:
    """Extract known question texts from LLM response for intervention checking.

    Args:
        llm_response: The LLM analysis dict.

    Returns:
        List of question text strings.
    """
    return [
        ans.get("question", "")
        for ans in llm_response.get("screening_answers", [])
        if ans.get("question")
    ]
