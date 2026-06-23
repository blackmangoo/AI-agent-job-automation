"""
Job Page Scraping Engine
=========================
Module 1: Navigates to a job listing URL, extracts the page HTML,
and parses it with BeautifulSoup to extract structured job data.

Supports Indeed Pakistan (pk.indeed.com) as the primary platform,
with generic fallbacks for other job boards.
"""

from bs4 import BeautifulSoup
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from utils.logger import get_logger
from utils.delays import long_delay

logger = get_logger(__name__)

NOISE_TAGS = ["script", "style", "nav", "footer", "header", "noscript", "svg", "iframe"]


def scrape_job_page(page: Page, url: str) -> dict:
    """Scrape a job listing page and extract structured job data."""
    logger.info(f"Scraping job page: {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_selector(
                "div.jobsearch-JobComponent, div.job-details, article, main, #job-details",
                timeout=10000,
            )
        except PlaywrightTimeout:
            logger.warning("Primary content selector not found, proceeding with full page")
        page.wait_for_timeout(2000)
        html = page.content()
        logger.debug(f"Page HTML retrieved: {len(html)} characters")
    except PlaywrightTimeout as e:
        raise RuntimeError(f"Page load timed out for {url}: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to navigate to {url}: {e}")

    soup = BeautifulSoup(html, "html.parser")
    for tag_name in NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    job_title = _extract_job_title(soup, page)
    company = _extract_company(soup, page)
    description = _extract_description(soup)
    questions = _extract_questions(soup)

    result = {
        "job_title": job_title, "company": company,
        "description": description, "questions": questions, "url": url,
    }
    logger.info(f"Scraped: '{job_title}' at '{company}' \u2014 {len(questions)} screening questions found")
    return result


def _extract_job_title(soup, page):
    for selector in ["h1.jobsearch-JobInfoHeader-title", "h1[data-testid='jobsearch-JobInfoHeader-title']",
                     "div.jobsearch-JobInfoHeader-title-container h1", "h1.icl-u-xs-mb--xs"]:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True): return el.get_text(strip=True)
    for selector in ["h1.job-title", "h1[class*='title']", "h1[class*='job']", "h1"]:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True):
            title = el.get_text(strip=True)
            if len(title) < 200: return title
    logger.warning("Could not extract job title")
    return "Unknown Title"


def _extract_company(soup, page):
    for selector in ["div[data-testid='inlineHeader-companyName'] a",
                     "div[data-testid='inlineHeader-companyName']",
                     "div.jobsearch-InlineCompanyRating a", "span.companyName"]:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True): return el.get_text(strip=True)
    for selector in ["a[class*='company']", "span[class*='company']", "div[class*='company']"]:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True): return el.get_text(strip=True)
    logger.warning("Could not extract company name")
    return "Unknown Company"


def _extract_description(soup):
    for selector in ["div#jobDescriptionText", "div.jobsearch-jobDescriptionText",
                     "div[data-testid='jobDescriptionText']", "div.job-description",
                     "div[class*='description']", "article", "main"]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 100: return text
    paragraphs = soup.find_all("p")
    text = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
    if text: return text
    return soup.get_text(separator="\n", strip=True)[:5000]


def _extract_questions(soup):
    questions = []
    for selector in ["div[class*='question'] label", "div[class*='Question'] label",
                     "fieldset legend", "label[class*='question']",
                     "div.ia-Questions label", "div[data-testid*='question'] label"]:
        for el in soup.select(selector):
            text = el.get_text(strip=True)
            if text and len(text) > 5 and text not in questions:
                questions.append(text)
    if not questions:
        for label in soup.find_all("label"):
            text = label.get_text(strip=True)
            if text and len(text) > 10 and "?" in text and text not in questions:
                questions.append(text)
    logger.info(f"Found {len(questions)} screening questions")
    return questions
