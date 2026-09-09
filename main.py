"""
AI Job Application Agent -- Main Orchestrator
================================================
Supports two modes:
  1. Single URL mode:  python main.py --url "https://..."
  2. Batch feed mode:  python main.py --mode feed --max-apply 20

Single URL mode applies to one specific job listing.
Batch feed mode crawls Indeed's job feed and auto-applies to all eligible jobs.

Usage:
    python main.py --url "https://pk.indeed.com/viewjob?jk=abc123"
    python main.py --url "https://pk.indeed.com/viewjob?jk=abc123" --dry-run
    python main.py --mode feed --max-apply 20
    python main.py --mode feed --search "AI Engineer" --max-apply 10
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from config.candidate_profile import CANDIDATE
from modules.scraper import scrape_job_page, is_page_blocked
from modules.llm_brain import analyze_job
from modules.form_filler import fill_application_form
from modules.human_loop import check_for_intervention, _is_cloudflare_blocked
from modules.sheets_logger import log_application, get_applied_urls
from modules.feed_crawler import crawl_feed
from modules.apply_flow import (
    click_apply_button,
    detect_apply_form,
    get_apply_page,
    handle_multi_step_form,
    click_submit,
    is_application_complete,
)
from utils.browser import launch_browser, close_browser, wait_for_cloudflare
from utils.cv_parser import parse_cv
from utils.delays import long_delay, medium_delay
from utils.logger import get_logger

logger = get_logger("main")

# Default CV path
DEFAULT_CV_PATH = "./assets/updated_cv.pdf"


def _print_banner():
    """Print the agent startup banner."""
    banner = """
+--------------------------------------------------------------+
|                                                              |
|   AI Job Application Agent                                   |
|   Built for: Ammar Akbar                                     |
|   Target: Jobs & Internships                                 |
|                                                              |
|   github.com/blackmangoo/AI-agent-job-automation             |
|                                                              |
+--------------------------------------------------------------+
"""
    print(banner)


def _save_local_log(job_data: dict, llm_response: dict, status: str) -> str:
    """Save application results to a local JSON log file."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    company = job_data.get("company", "unknown").replace(" ", "_").lower()[:30]
    role = job_data.get("job_title", "unknown").replace(" ", "_").lower()[:30]
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"{timestamp}_{company}_{role}.json"

    log_data = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "job_data": job_data,
        "llm_response": llm_response,
        "candidate": CANDIDATE.full_name,
    }

    log_path = log_dir / filename
    log_path.write_text(json.dumps(log_data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Local log saved: {log_path}")
    return str(log_path)


def _wait_for_real_page(page, job_url: str, max_attempts: int = 3) -> None:
    """Navigate to a job URL and wait until Cloudflare clears."""
    logger.info(f"Navigating to: {job_url}")
    page.goto(job_url, wait_until="domcontentloaded", timeout=30000)

    for attempt in range(max_attempts):
        logger.info("Waiting for page to stabilize...")
        page.wait_for_timeout(3000)

        if not _is_cloudflare_blocked(page):
            logger.info("Page loaded successfully")
            return

        logger.warning(f"Cloudflare challenge detected (attempt {attempt + 1}/{max_attempts})")
        logger.info("Waiting up to 15 seconds for auto-resolve...")
        if wait_for_cloudflare(page, timeout=15000):
            logger.info("Cloudflare auto-resolved!")
            return

        if attempt < max_attempts - 1:
            logger.warning("Requesting human intervention for Cloudflare...")
            check_for_intervention(page)
            page.wait_for_timeout(3000)
        else:
            raise RuntimeError(
                f"Could not clear Cloudflare after {max_attempts} attempts."
            )


def _process_single_job(
    page, job_url: str, cv_text: str, dry_run: bool = False, auto_submit: bool = False
) -> dict:
    """Process a single job listing through the full pipeline.

    Args:
        page: Playwright Page object.
        job_url: URL of the job listing.
        cv_text: Parsed CV text.
        dry_run: If True, analyze only -- don't fill forms.
        auto_submit: If True, auto-submit without pausing.

    Returns:
        Dict with status, job_data, llm_response.
    """
    # -- Scrape the job page --
    logger.info("Scraping job listing...")
    job_data = None
    for attempt in range(3):
        try:
            job_data = scrape_job_page(page, job_url)
            break
        except RuntimeError as e:
            if ("cloudflare" in str(e).lower() or "verification" in str(e).lower()) and attempt < 2:
                logger.warning(f"Page blocked (attempt {attempt + 1}/3). Requesting intervention...")
                check_for_intervention(page)
                page.wait_for_timeout(5000)
            else:
                raise

    if job_data is None:
        raise RuntimeError("Failed to scrape job data")

    logger.info(f"{'=' * 50}")
    logger.info(f"JOB: {job_data['job_title']}")
    logger.info(f"COMPANY: {job_data['company']}")
    logger.info(f"QUESTIONS: {len(job_data['questions'])}")
    logger.info(f"{'=' * 50}")

    # -- LLM Analysis --
    logger.info("Analyzing with LLM...")
    llm_response = analyze_job(job_data, cv_text)

    eligible_str = "YES" if llm_response["eligible"] else "NO"
    logger.info(f"ELIGIBLE: {eligible_str} | CONFIDENCE: {llm_response['confidence_score']:.0%}")
    logger.info(f"REASON: {llm_response['eligibility_reason']}")

    # -- Form filling --
    status = "analyzed"

    if dry_run:
        logger.info("DRY RUN -- skipping form fill")
        status = "dry_run"

    elif llm_response.get("eligible", False):
        logger.info("Proceeding to apply...")
        long_delay()

        # Check for interventions (login walls, etc.)
        intervention = check_for_intervention(page)
        if intervention != "clear":
            logger.info(f"Intervention resolved: {intervention}")

        # Click "Apply Now" button
        apply_result = click_apply_button(page)

        if apply_result == "already_applied":
            status = "already_applied"
            logger.info("Already applied to this job")

        elif apply_result == "not_found":
            # No apply button -- try filling any visible form
            logger.info("No apply button found. Trying to fill visible form fields...")
            success = fill_application_form(page, llm_response, CANDIDATE)
            status = "form_filled" if success else "form_fill_failed"

        elif apply_result in ("indeed_apply", "external"):
            # Apply form should now be visible
            medium_delay()

            # Get the correct page/frame for the form
            form_page = get_apply_page(page)

            # Check for intervention on the form page
            check_for_intervention(form_page, is_form=True)

            # Fill the form (may be multi-step)
            def fill_step(p):
                fill_application_form(p, llm_response, CANDIDATE)

            form_status = handle_multi_step_form(form_page, fill_step)

            if form_status == "ready_to_submit":
                if auto_submit:
                    logger.info("Auto-submitting application...")
                    if click_submit(form_page):
                        page.wait_for_timeout(3000)
                        if is_application_complete(page):
                            status = "applied"
                            logger.info("Application submitted successfully!")
                        else:
                            status = "submit_uncertain"
                            logger.warning("Clicked submit but could not confirm success")
                    else:
                        status = "form_filled"
                        logger.info("Could not find submit button")
                else:
                    status = "form_filled"
                    logger.info("Form filled -- pausing for manual review and submit")
                    print(
                        "\n+----------------------------------------------------------+\n"
                        "|   FORM FILLED -- REVIEW REQUIRED                         |\n"
                        "|   Review the form in the browser, then submit manually.  |\n"
                        "|   Click Resume in Playwright Inspector to continue.      |\n"
                        "+----------------------------------------------------------+\n"
                    )
                    page.pause()
                    status = "applied"

            elif form_status == "submitted":
                status = "applied"
                logger.info("Application submitted!")
            else:
                status = "form_fill_failed"
                logger.warning(f"Form handling result: {form_status}")

    else:
        logger.info(f"Not eligible -- skipping: {llm_response['eligibility_reason']}")
        status = "skipped"

    # -- Log results --
    log_path = _save_local_log(job_data, llm_response, status)

    try:
        sheets_ok = log_application(job_data, llm_response, status)
        if sheets_ok:
            logger.info("Logged to Google Sheets")
    except Exception as e:
        logger.warning(f"Google Sheets logging failed: {e}")

    return {
        "status": status,
        "job_data": job_data,
        "llm_response": llm_response,
        "log_path": log_path,
    }


# =====================================================================
# SINGLE URL MODE
# =====================================================================

def run_single(job_url: str, dry_run: bool = False, auto_submit: bool = False) -> dict:
    """Run the pipeline for a single job URL."""
    _print_banner()
    load_dotenv()

    if not os.getenv("GROQ_API_KEY"):
        logger.error("GROQ_API_KEY not found in .env")
        sys.exit(1)

    cv_text = parse_cv(DEFAULT_CV_PATH)
    logger.info(f"CV loaded ({len(cv_text)} chars)")

    playwright_instance = None
    context = None

    try:
        playwright_instance, context, page = launch_browser()
        long_delay()

        _wait_for_real_page(page, job_url)
        long_delay()

        result = _process_single_job(page, job_url, cv_text, dry_run=dry_run, auto_submit=auto_submit)

        logger.info(f"{'=' * 50}")
        logger.info(f"Run complete -- Status: {result['status'].upper()}")
        logger.info(f"{'=' * 50}")
        return result

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return {"status": "interrupted"}
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
    finally:
        if playwright_instance:
            close_browser(playwright_instance, context)


# =====================================================================
# BATCH FEED MODE
# =====================================================================

def run_batch(
    max_apply: int = 20,
    search_query: str = None,
    dry_run: bool = False,
    auto_submit: bool = False,
    delay_min: int = 60,
    delay_max: int = 180,
) -> dict:
    """Run the batch pipeline: crawl feed, then apply to each eligible job.

    Args:
        max_apply: Maximum number of applications to submit.
        search_query: Optional Indeed search query. If None, uses 'Jobs for you'.
        dry_run: If True, analyze only -- don't fill forms.
        auto_submit: If True, auto-submit forms without pausing.
        delay_min: Minimum seconds between applications.
        delay_max: Maximum seconds between applications.

    Returns:
        Summary dict with stats.
    """
    _print_banner()
    load_dotenv()
    logger.info(f"BATCH MODE -- max_apply={max_apply}, dry_run={dry_run}")

    if not os.getenv("GROQ_API_KEY"):
        logger.error("GROQ_API_KEY not found in .env")
        sys.exit(1)

    cv_text = parse_cv(DEFAULT_CV_PATH)
    logger.info(f"CV loaded ({len(cv_text)} chars)")

    # Get already-applied URLs for dedup
    applied_urls = set()
    try:
        applied_urls = get_applied_urls()
        logger.info(f"Loaded {len(applied_urls)} already-applied URLs for dedup")
    except Exception as e:
        logger.warning(f"Could not load applied URLs: {e}")

    playwright_instance = None
    context = None
    stats = {
        "total_found": 0,
        "skipped_dedup": 0,
        "applied": 0,
        "skipped_ineligible": 0,
        "errors": 0,
        "dry_runs": 0,
        "details": [],
    }

    try:
        playwright_instance, context, page = launch_browser()
        long_delay()

        # Handle Cloudflare on Indeed home
        logger.info("Navigating to Indeed...")
        if search_query:
            target_url = f"https://pk.indeed.com/jobs?q={search_query.replace(' ', '+')}&l=Pakistan"
        else:
            target_url = "https://pk.indeed.com"

        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Handle Cloudflare on the feed page
        while _is_cloudflare_blocked(page):
            logger.warning("Cloudflare detected. Waiting for resolution...")
            if not wait_for_cloudflare(page, timeout=15000):
                check_for_intervention(page)
                page.wait_for_timeout(3000)
            else:
                break

        # Check if login is needed
        try:
            page_text = page.inner_text("body").lower()
            if "sign in" in page_text and not any(
                ind in page_text for ind in ["jobs for you", "job results", "jobs in"]
            ):
                logger.warning("Indeed login required. Please log in manually.")
                print(
                    "\n+----------------------------------------------------------+\n"
                    "|   LOGIN REQUIRED                                         |\n"
                    "|   Please log in to Indeed in the browser window.         |\n"
                    "|   Then click Resume in Playwright Inspector.             |\n"
                    "+----------------------------------------------------------+\n"
                )
                page.pause()
                page.wait_for_timeout(3000)
        except Exception:
            pass

        # Crawl the feed for job URLs
        logger.info("Crawling job feed...")
        jobs = crawl_feed(page, max_jobs=max_apply * 2, search_query=search_query)
        stats["total_found"] = len(jobs)
        logger.info(f"Found {len(jobs)} jobs in feed")

        if not jobs:
            logger.warning("No jobs found in feed. Try logging in or using --search.")
            return stats

        # Filter out already-applied jobs
        new_jobs = []
        for job in jobs:
            url = job["url"]
            # Normalize URL for comparison
            job_key = job.get("job_key", "")
            is_dup = url in applied_urls
            if not is_dup and job_key:
                # Also check by job key in URLs
                is_dup = any(job_key in u for u in applied_urls)
            if is_dup:
                stats["skipped_dedup"] += 1
                logger.info(f"Skipping (already applied): {job.get('title', url)[:60]}")
            else:
                new_jobs.append(job)

        logger.info(f"After dedup: {len(new_jobs)} new jobs to process")

        # Process each job
        applications_done = 0
        for i, job in enumerate(new_jobs):
            if applications_done >= max_apply:
                logger.info(f"Reached max_apply limit ({max_apply})")
                break

            job_url = job["url"]
            job_title = job.get("title", "Unknown")[:60]

            logger.info(f"\n{'=' * 60}")
            logger.info(f"JOB {i + 1}/{len(new_jobs)}: {job_title}")
            logger.info(f"URL: {job_url}")
            logger.info(f"{'=' * 60}")

            try:
                # Navigate to the job page
                _wait_for_real_page(page, job_url)
                long_delay()

                # Check for intervention triggers
                intervention = check_for_intervention(page)
                if intervention != "clear":
                    logger.info(f"Intervention resolved: {intervention}")
                    long_delay()

                # Process the job
                result = _process_single_job(
                    page, job_url, cv_text,
                    dry_run=dry_run,
                    auto_submit=auto_submit,
                )

                result_status = result["status"]
                stats["details"].append({
                    "url": job_url,
                    "title": result.get("job_data", {}).get("job_title", job_title),
                    "company": result.get("job_data", {}).get("company", "Unknown"),
                    "status": result_status,
                })

                if result_status in ("applied", "form_filled", "submit_uncertain"):
                    stats["applied"] += 1
                    applications_done += 1
                elif result_status == "dry_run":
                    stats["dry_runs"] += 1
                    applications_done += 1
                elif result_status in ("skipped", "already_applied"):
                    stats["skipped_ineligible"] += 1
                else:
                    stats["errors"] += 1

                logger.info(f"Result: {result_status} | Applied so far: {applications_done}/{max_apply}")

            except Exception as e:
                logger.error(f"Error processing job {job_url}: {e}")
                stats["errors"] += 1
                stats["details"].append({
                    "url": job_url,
                    "title": job_title,
                    "status": "error",
                    "error": str(e),
                })

            # Rate limiting delay between applications
            if i < len(new_jobs) - 1 and applications_done < max_apply:
                delay = random.randint(delay_min, delay_max)
                logger.info(f"Rate limit: waiting {delay} seconds before next job...")
                time.sleep(delay)

        # Print summary
        _print_summary(stats)
        return stats

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        _print_summary(stats)
        return stats
    except Exception as e:
        logger.error(f"Batch pipeline failed: {e}", exc_info=True)
        return stats
    finally:
        if playwright_instance:
            close_browser(playwright_instance, context)


def _print_summary(stats: dict):
    """Print a summary of the batch run."""
    print(f"\n{'=' * 60}")
    print("BATCH RUN SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Jobs found in feed:      {stats['total_found']}")
    print(f"  Skipped (already applied): {stats['skipped_dedup']}")
    print(f"  Applied:                   {stats['applied']}")
    print(f"  Skipped (not eligible):    {stats['skipped_ineligible']}")
    print(f"  Dry runs:                  {stats['dry_runs']}")
    print(f"  Errors:                    {stats['errors']}")
    print(f"{'=' * 60}\n")

    if stats.get("details"):
        print("Details:")
        for d in stats["details"]:
            status_icon = "[OK]" if d["status"] in ("applied", "form_filled", "dry_run") else "[--]"
            title = d.get("title", "Unknown")[:50]
            print(f"  {status_icon} {title} -- {d['status']}")
        print()


# =====================================================================
# CLI ENTRY POINT
# =====================================================================

def main():
    """CLI entry point -- parse arguments and run the agent."""
    global DEFAULT_CV_PATH

    parser = argparse.ArgumentParser(
        description="AI Job Application Agent -- Automated job applications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  Single URL:   python main.py --url "https://pk.indeed.com/viewjob?jk=abc123"
  Batch feed:   python main.py --mode feed --max-apply 20
  Batch search: python main.py --mode feed --search "AI Engineer" --max-apply 10
  Dry run:      python main.py --mode feed --dry-run --max-apply 5
  Continuous:   python main.py --mode feed --max-apply 50 --auto-submit
        """,
    )

    parser.add_argument(
        "--url", "-u",
        help="URL of a specific job listing to apply to (single mode)",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["single", "feed"],
        default="single",
        help="Mode: 'single' for one URL, 'feed' for batch auto-apply (default: single)",
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        default=False,
        help="Analyze only -- don't fill application forms",
    )
    parser.add_argument(
        "--max-apply",
        type=int,
        default=20,
        help="Max number of applications in feed mode (default: 20)",
    )
    parser.add_argument(
        "--search", "-s",
        type=str,
        default=None,
        help="Indeed search query for feed mode (e.g., 'AI Engineer')",
    )
    parser.add_argument(
        "--auto-submit",
        action="store_true",
        default=False,
        help="Auto-submit applications without pausing for review",
    )
    parser.add_argument(
        "--delay-min",
        type=int,
        default=60,
        help="Min seconds between applications in feed mode (default: 60)",
    )
    parser.add_argument(
        "--delay-max",
        type=int,
        default=180,
        help="Max seconds between applications in feed mode (default: 180)",
    )
    parser.add_argument(
        "--cv",
        default=DEFAULT_CV_PATH,
        help=f"Path to CV file (default: {DEFAULT_CV_PATH})",
    )

    args = parser.parse_args()

    if args.cv != DEFAULT_CV_PATH:
        DEFAULT_CV_PATH = args.cv

    # Determine mode
    if args.url:
        # Single URL mode
        result = run_single(args.url, dry_run=args.dry_run, auto_submit=args.auto_submit)
        status = result.get("status", "error")
        sys.exit(0 if status in ("applied", "form_filled", "dry_run", "skipped", "analyzed") else 1)

    elif args.mode == "feed":
        # Batch feed mode
        stats = run_batch(
            max_apply=args.max_apply,
            search_query=args.search,
            dry_run=args.dry_run,
            auto_submit=args.auto_submit,
            delay_min=args.delay_min,
            delay_max=args.delay_max,
        )
        sys.exit(0 if stats.get("applied", 0) > 0 or stats.get("dry_runs", 0) > 0 else 1)

    else:
        parser.error("Either --url or --mode feed is required")


if __name__ == "__main__":
    main()
