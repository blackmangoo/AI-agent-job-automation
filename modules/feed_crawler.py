"""
Indeed Job Feed Crawler
========================
Crawls the Indeed 'Jobs for you' feed or search results page
and extracts individual job listing URLs for batch processing.
"""

from playwright.sync_api import Page
from utils.logger import get_logger
from utils.delays import medium_delay, long_delay
import time

logger = get_logger(__name__)

# Indeed Pakistan base URLs
INDEED_HOME = "https://pk.indeed.com"
INDEED_SEARCH = "https://pk.indeed.com/jobs"

# Selectors for job cards on Indeed
JOB_CARD_SELECTORS = [
    "a[data-jk]",                          # Job cards with job key
    "div.job_seen_beacon a.jcs-JobTitle",   # Job title links
    "h2.jobTitle a",                        # Job title heading links
    "a[id^='job_']",                       # Job links with id starting with job_
    "div.cardOutline a[href*='viewjob']",  # Card links to viewjob
    "a[href*='/viewjob?jk=']",             # Any viewjob links
]

# Indicators that we're on an Indeed feed/search page
FEED_INDICATORS = [
    "div.job_seen_beacon",
    "div.jobsearch-ResultsList",
    "div#mosaic-jobResults",
    "ul.jobsearch-ResultsList",
]


def is_feed_page(page: Page) -> bool:
    """Check if the current page is an Indeed job feed/search results page."""
    for selector in FEED_INDICATORS:
        try:
            if page.query_selector(selector):
                return True
        except Exception:
            continue
    return False


def crawl_feed(page: Page, max_jobs: int = 50, search_query: str = None) -> list:
    """Crawl Indeed job feed and return a list of job dicts.
    
    If already on a feed page, scrapes it directly.
    Otherwise navigates to Indeed home or search.
    
    Args:
        page: Playwright Page object (should already be logged in via persistent session).
        max_jobs: Maximum number of jobs to collect.
        search_query: Optional search query (e.g., 'AI Engineer'). If None, uses 'Jobs for you'.
    
    Returns:
        List of dicts with keys: url, title, company, job_key
    """
    # Navigate to the right page
    if search_query:
        search_url = f"{INDEED_SEARCH}?q={search_query.replace(' ', '+')}&l=Pakistan"
        logger.info(f"Navigating to Indeed search: {search_query}")
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    elif not is_feed_page(page):
        if "indeed.com" not in page.url:
            logger.info("Navigating to Indeed home page...")
            page.goto(INDEED_HOME, wait_until="domcontentloaded", timeout=30000)
        else:
            logger.info("Already on Indeed. Waiting for feed to appear...")
            page.wait_for_timeout(5000)
    
    # Wait for the page to load
    page.wait_for_timeout(3000)
    
    # Check if we need to be logged in
    page_text = ""
    try:
        page_text = page.inner_text("body").lower()
    except Exception:
        pass
    
    if "sign in" in page_text and "jobs for you" not in page_text:
        logger.warning("Not logged in to Indeed. Login may be required for personalized feed.")
    
    # Wait for job results to appear
    try:
        page.wait_for_selector(
            ", ".join(FEED_INDICATORS),
            timeout=15000
        )
        logger.info("Job feed loaded successfully")
    except Exception:
        logger.warning("Could not detect job feed elements, trying to scrape anyway...")
    
    # Collect jobs from the current page and scroll for more
    all_jobs = []
    seen_keys = set()
    pages_scraped = 0
    max_pages = 5  # Limit pagination
    
    while len(all_jobs) < max_jobs and pages_scraped < max_pages:
        # Extract job links from current page
        new_jobs = _extract_job_links(page, seen_keys)
        all_jobs.extend(new_jobs)
        pages_scraped += 1
        
        logger.info(f"Page {pages_scraped}: Found {len(new_jobs)} new jobs (total: {len(all_jobs)})")
        
        if len(all_jobs) >= max_jobs:
            break
        
        # Try to go to next page
        if not _go_to_next_page(page):
            logger.info("No more pages available")
            break
        
        page.wait_for_timeout(3000)
    
    # Trim to max_jobs
    all_jobs = all_jobs[:max_jobs]
    logger.info(f"Feed crawl complete: collected {len(all_jobs)} job URLs")
    
    return all_jobs


def _extract_job_links(page: Page, seen_keys: set) -> list:
    """Extract job URLs from the current page.
    
    Args:
        page: Playwright Page object.
        seen_keys: Set of already-seen job keys to avoid duplicates.
    
    Returns:
        List of new job dicts.
    """
    jobs = []
    
    for selector in JOB_CARD_SELECTORS:
        try:
            elements = page.query_selector_all(selector)
            for el in elements:
                href = el.get_attribute("href") or ""
                data_jk = el.get_attribute("data-jk") or ""
                
                # Extract job key
                job_key = data_jk
                if not job_key and "jk=" in href:
                    job_key = href.split("jk=")[-1].split("&")[0]
                
                if not job_key or job_key in seen_keys:
                    continue
                
                seen_keys.add(job_key)
                
                # Build full URL
                if href.startswith("/"):
                    url = f"{INDEED_HOME}{href}"
                elif href.startswith("http"):
                    url = href
                else:
                    url = f"{INDEED_HOME}/viewjob?jk={job_key}"
                
                # Make sure it's a viewjob URL
                if "viewjob" not in url and job_key:
                    url = f"{INDEED_HOME}/viewjob?jk={job_key}"
                
                # Try to extract title and company from the card
                title = ""
                company = ""
                try:
                    title = el.inner_text().strip()[:100]
                except Exception:
                    pass
                
                jobs.append({
                    "url": url,
                    "title": title,
                    "company": company,
                    "job_key": job_key,
                })
        except Exception as e:
            logger.debug(f"Selector {selector} failed: {e}")
            continue
    
    return jobs


def _go_to_next_page(page: Page) -> bool:
    """Try to navigate to the next page of results.
    
    Args:
        page: Playwright Page object.
    
    Returns:
        True if navigation succeeded, False if no next page.
    """
    next_selectors = [
        "a[data-testid='pagination-page-next']",
        "a[aria-label='Next Page']",
        "a[aria-label='Next']",
        "nav[aria-label='pagination'] a:last-child",
        "ul.pagination-list li:last-child a",
    ]
    
    for selector in next_selectors:
        try:
            next_btn = page.query_selector(selector)
            if next_btn:
                next_btn.click()
                logger.info("Navigated to next page")
                return True
        except Exception:
            continue
    
    return False
