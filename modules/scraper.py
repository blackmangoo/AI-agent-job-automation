"""
Job Page Scraping Engine
=========================
Module 1: Extracts structured job data from the current browser page
using BeautifulSoup. Does NOT re-navigate — it reads whatever is
currently loaded in the Playwright page.

Supports Indeed Pakistan (pk.indeed.com) as the primary platform,
with generic fallbacks for other job boards.
"""

from bs4 import BeautifulSoup
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from utils.logger import get_logger

logger = get_logger(__name__)

# Tags to strip from the page before text extraction
NOISE_TAGS = ["script", "style", "nav", "footer", "header", "noscript", "svg", "iframe"]

# Indicators that the page is still blocked by Cloudflare
BLOCK_INDICATORS = [
    "additional verification required",
    "verify you are human",
    "just a moment...",
    "troubleshooting cloudflare errors",
    "ray id for this request",
    "attention required!",
]


def is_page_blocked(page: Page) -> bool:
    """Check if the current page is a Cloudflare/bot verification page.

    Args:
        page: A Playwright Page object.

    Returns:
        True if the page appears to be a verification/challenge page.
    """
    try:
        page_text = page.inner_text("body").lower()
        return any(indicator in page_text for indicator in BLOCK_INDICATORS)
    except Exception:
        return False


def scrape_job_page(page: Page, url: str) -> dict:
    """Scrape the currently loaded job listing page and extract structured data.

    IMPORTANT: This function does NOT call page.goto(). It reads the current
    DOM state of whatever is loaded in the browser. The caller (main.py)
    is responsible for navigating to the correct URL first.

    Args:
        page: A Playwright Page object with the job page already loaded.
        url: The original URL (used for logging and the result dict).

    Returns:
        A dict with keys:
        - job_title (str): The position title
        - company (str): The employer/company name
        - description (str): Cleaned full job description text
        - questions (list[str]): Any visible screening question labels
        - url (str): The original URL

    Raises:
        RuntimeError: If the page is a Cloudflare/bot verification page.
    """
    logger.info(f"Scraping current page content for: {url}")

    # First, check if the page is blocked
    if is_page_blocked(page):
        raise RuntimeError(
            "Page is still showing a Cloudflare/bot verification challenge. "
            "The actual job content has not loaded yet."
        )

    # Wait for main content to appear (Indeed-specific + generic)
    try:
        page.wait_for_selector(
            "div.jobsearch-JobComponent, div.job-details, article, main, #job-details",
            timeout=10000,
        )
    except PlaywrightTimeout:
        logger.warning("Primary content selector not found, proceeding with full page")

    # Give dynamic content a moment to render
    page.wait_for_timeout(2000)

    # Get the full page HTML
    html = page.content()
    logger.debug(f"Page HTML retrieved: {len(html)} characters")

    # Parse with BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # Strip noise elements
    for tag_name in NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Extract structured data
    job_title = _extract_job_title(soup, page)
    company = _extract_company(soup, page)
    description = _extract_description(soup)
    questions = _extract_questions(soup)

    # Final sanity check — did we actually get real job content?
    body_text = description.lower() if description else ""
    if any(indicator in job_title.lower() for indicator in BLOCK_INDICATORS):
        raise RuntimeError(
            "Scraped title matches a Cloudflare block page. "
            "The actual job content has not loaded yet."
        )
    if any(indicator in body_text for indicator in BLOCK_INDICATORS):
        raise RuntimeError(
            "Scraped description contains Cloudflare block indicators. "
            "The actual job content has not loaded yet."
        )

    result = {
        "job_title": job_title,
        "company": company,
        "description": description,
        "questions": questions,
        "url": url,
    }

    logger.info(f"Scraped: '{job_title}' at '{company}' -- {len(questions)} screening questions found")
    return result


def _extract_job_title(soup: BeautifulSoup, page: Page) -> str:
    """Extract the job title from the page.

    Args:
        soup: Parsed BeautifulSoup object.
        page: Playwright page for fallback extraction.

    Returns:
        The job title string, or "Unknown Title" if not found.
    """
    # Indeed-specific selectors (pk.indeed.com)
    indeed_selectors = [
        "h1.jobsearch-JobInfoHeader-title",
        "h1[data-testid='jobsearch-JobInfoHeader-title']",
        "div.jobsearch-JobInfoHeader-title-container h1",
        "h1.icl-u-xs-mb--xs",
    ]

    for selector in indeed_selectors:
        element = soup.select_one(selector)
        if element and element.get_text(strip=True):
            return element.get_text(strip=True)

    # Generic fallbacks
    generic_selectors = [
        "h1.job-title",
        "h1[class*='title']",
        "h1[class*='job']",
        "h1",
    ]

    for selector in generic_selectors:
        element = soup.select_one(selector)
        if element and element.get_text(strip=True):
            title = element.get_text(strip=True)
            if len(title) < 200:  # Sanity check — not a paragraph
                return title

    logger.warning("Could not extract job title")
    return "Unknown Title"


def _extract_company(soup: BeautifulSoup, page: Page) -> str:
    """Extract the company name from the page.

    Args:
        soup: Parsed BeautifulSoup object.
        page: Playwright page for fallback extraction.

    Returns:
        The company name string, or "Unknown Company" if not found.
    """
    # Indeed-specific
    indeed_selectors = [
        "div[data-testid='inlineHeader-companyName'] a",
        "div[data-testid='inlineHeader-companyName']",
        "div.jobsearch-InlineCompanyRating a",
        "div.jobsearch-InlineCompanyRating div",
        "span.companyName",
    ]

    for selector in indeed_selectors:
        element = soup.select_one(selector)
        if element and element.get_text(strip=True):
            return element.get_text(strip=True)

    # Generic
    generic_selectors = [
        "a[class*='company']",
        "span[class*='company']",
        "div[class*='company']",
        "[data-company]",
    ]

    for selector in generic_selectors:
        element = soup.select_one(selector)
        if element and element.get_text(strip=True):
            return element.get_text(strip=True)

    logger.warning("Could not extract company name")
    return "Unknown Company"


def _extract_description(soup: BeautifulSoup) -> str:
    """Extract the full job description text.

    Args:
        soup: Parsed BeautifulSoup object.

    Returns:
        Cleaned job description text.
    """
    # Indeed-specific
    jd_selectors = [
        "div#jobDescriptionText",
        "div.jobsearch-jobDescriptionText",
        "div[data-testid='jobDescriptionText']",
        "div.job-description",
        "div[class*='description']",
        "article",
        "main",
    ]

    for selector in jd_selectors:
        element = soup.select_one(selector)
        if element:
            text = element.get_text(separator="\n", strip=True)
            if len(text) > 100:  # Must be substantial
                return text

    # Fallback: grab all paragraph text
    paragraphs = soup.find_all("p")
    text = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

    if text:
        return text

    logger.warning("Could not extract job description -- using page body text")
    return soup.get_text(separator="\n", strip=True)[:5000]


def _extract_questions(soup: BeautifulSoup) -> list:
    """Extract screening/application questions from the page.

    Looks for form labels, fieldset legends, and question-like elements
    that typically appear in job application forms.

    Args:
        soup: Parsed BeautifulSoup object.

    Returns:
        A list of question text strings.
    """
    questions = []

    # Indeed screening questions
    question_selectors = [
        "div[class*='question'] label",
        "div[class*='Question'] label",
        "fieldset legend",
        "label[class*='question']",
        "div.ia-Questions label",
        "div[data-testid*='question'] label",
    ]

    for selector in question_selectors:
        elements = soup.select(selector)
        for el in elements:
            text = el.get_text(strip=True)
            if text and len(text) > 5 and text not in questions:
                questions.append(text)

    # Also check for labels near input/select/textarea elements
    if not questions:
        for label in soup.find_all("label"):
            text = label.get_text(strip=True)
            # Filter out generic labels
            if (text and len(text) > 10 and "?" in text
                    and text not in questions):
                questions.append(text)

    logger.info(f"Found {len(questions)} screening questions")
    for i, q in enumerate(questions, 1):
        logger.debug(f"  Q{i}: {q}")

    return questions
