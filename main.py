"""
AI Job Application Agent -- Main Orchestrator
================================================
Wires all modules together into a single automated pipeline:
1. Load configuration and parse CV
2. Launch persistent browser
3. Navigate to job URL
4. Check for login walls / intervention triggers
5. Scrape job listing data
6. Analyze with LLM for eligibility
7. Fill application form (if eligible)
8. Log results to Google Sheets + local file
9. Commit state to GitHub

Usage:
    python main.py --url "https://pk.indeed.com/viewjob?jk=abc123"
    python main.py --url "https://pk.indeed.com/viewjob?jk=abc123" --dry-run
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from config.candidate_profile import CANDIDATE
from modules.scraper import scrape_job_page
from modules.llm_brain import analyze_job
from modules.form_filler import fill_application_form
from modules.human_loop import check_for_intervention
from modules.sheets_logger import log_application
from utils.browser import launch_browser, close_browser
from utils.cv_parser import parse_cv
from utils.delays import long_delay
from utils.logger import get_logger

logger = get_logger("main")

# Default CV path
DEFAULT_CV_PATH = "./assets/updated_cv.pdf"


def _print_banner():
    """Print the agent startup banner."""
    banner = """
+==============================================================+
|                                                              |
|   AI Job Application Agent                                   |
|   Built for: Ammar Akbar                                     |
|   Target: Jobs & Internships                                 |
|                                                              |
|   github.com/blackmangoo/AI-agent-job-automation             |
|                                                              |
+==============================================================+
"""
    print(banner)


def _save_local_log(job_data: dict, llm_response: dict, status: str) -> str:
    """Save application results to a local JSON log file.

    Args:
        job_data: Scraped job data dict.
        llm_response: LLM analysis dict.
        status: Final application status.

    Returns:
        Path to the saved log file.
    """
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


def run(job_url: str, dry_run: bool = False) -> dict:
    """Execute the full job application pipeline.

    Args:
        job_url: The URL of the job listing to apply to.
        dry_run: If True, scrapes and analyzes but does NOT fill the form.

    Returns:
        Dict with run results including status, job data, and LLM response.
    """
    _print_banner()

    # Step 1: Load environment
    load_dotenv()
    logger.info("Environment loaded from .env")

    if not os.getenv("GROQ_API_KEY"):
        logger.error("GROQ_API_KEY not found in .env -- cannot proceed")
        sys.exit(1)

    # Step 2: Parse CV
    cv_path = DEFAULT_CV_PATH
    logger.info(f"Loading CV from: {cv_path}")

    try:
        cv_text = parse_cv(cv_path)
        logger.info(f"CV loaded successfully ({len(cv_text)} characters)")
    except FileNotFoundError:
        logger.error(f"CV not found at {cv_path}. Please place your CV file there and try again.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to parse CV: {e}")
        sys.exit(1)

    # Step 3: Launch browser
    playwright_instance = None
    context = None
    page = None

    try:
        playwright_instance, context, page = launch_browser()
        long_delay()

        # Step 4: Navigate to job URL
        logger.info(f"Navigating to: {job_url}")
        page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
        long_delay()

        # Step 5: Check for login walls
        logger.info("Checking for intervention triggers (login walls, etc.)")
        intervention = check_for_intervention(page)
        if intervention != "clear":
            logger.info(f"Intervention completed: {intervention}")
            long_delay()

        # Step 6: Scrape job page
        logger.info("Scraping job listing...")
        job_data = scrape_job_page(page, job_url)

        logger.info(f"{'=' * 50}")
        logger.info(f"JOB: {job_data['job_title']}")
        logger.info(f"COMPANY: {job_data['company']}")
        logger.info(f"QUESTIONS: {len(job_data['questions'])}")
        logger.info(f"{'=' * 50}")

        # Step 7: LLM Analysis
        logger.info("Analyzing job with LLM brain...")
        llm_response = analyze_job(job_data, cv_text)

        logger.info(f"{'=' * 50}")
        eligible_str = "YES" if llm_response["eligible"] else "NO"
        logger.info(f"ELIGIBLE: {eligible_str}")
        logger.info(f"CONFIDENCE: {llm_response['confidence_score']:.0%}")
        logger.info(f"REASON: {llm_response['eligibility_reason']}")
        logger.info(f"{'=' * 50}")

        # Step 8: Form filling (if eligible and not dry run)
        status = "analyzed"

        if dry_run:
            logger.info("DRY RUN -- Skipping form fill")
            status = "dry_run"

        elif llm_response.get("eligible", False):
            logger.info("Proceeding to fill application form...")
            long_delay()

            check_for_intervention(
                page, [a.get("question", "") for a in llm_response.get("screening_answers", [])]
            )

            success = fill_application_form(page, llm_response, CANDIDATE)

            if success:
                status = "form_filled"
                logger.info("Form filled successfully!")
                logger.info(
                    "IMPORTANT: Review the form in the browser before submitting. "
                    "The agent does NOT click the submit button automatically."
                )
                print(
                    "\n+==============================================================+\n"
                    "|   FORM FILLED -- REVIEW REQUIRED                             |\n"
                    "|                                                              |\n"
                    "|   The form has been filled with your information.             |\n"
                    "|   Please review all fields in the browser window.             |\n"
                    "|   Submit the application manually when ready.                 |\n"
                    "|                                                              |\n"
                    "|   Click Resume in Playwright Inspector to continue            |\n"
                    "+==============================================================+\n"
                )
                page.pause()
                status = "applied"
            else:
                status = "form_fill_failed"

        else:
            logger.info(f"Not eligible -- skipping: {llm_response['eligibility_reason']}")
            status = "skipped"

        # Step 9: Log results
        log_path = _save_local_log(job_data, llm_response, status)

        try:
            sheets_ok = log_application(job_data, llm_response, status)
            if sheets_ok:
                logger.info("Application logged to Google Sheets")
            else:
                logger.info("Google Sheets logging skipped (check credentials)")
        except Exception as e:
            logger.warning(f"Google Sheets logging failed: {e}")

        result = {
            "status": status,
            "job_data": job_data,
            "llm_response": llm_response,
            "log_path": log_path,
        }

        logger.info(f"{'=' * 50}")
        logger.info(f"Run complete -- Status: {status.upper()}")
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
            logger.info("Browser closed")


def main():
    """CLI entry point -- parse arguments and run the agent."""
    global DEFAULT_CV_PATH

    parser = argparse.ArgumentParser(
        description="AI Job Application Agent -- Automated job/internship applications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --url "https://pk.indeed.com/viewjob?jk=abc123"
  python main.py --url "https://pk.indeed.com/viewjob?jk=abc123" --dry-run
  python main.py --url "https://linkedin.com/jobs/view/12345" --dry-run
        """,
    )

    parser.add_argument(
        "--url", "-u",
        required=True,
        help="URL of the job listing to apply to",
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        default=False,
        help="Analyze only -- don't fill the application form",
    )
    parser.add_argument(
        "--cv",
        default=DEFAULT_CV_PATH,
        help=f"Path to CV file (default: {DEFAULT_CV_PATH})",
    )

    args = parser.parse_args()

    if args.cv != DEFAULT_CV_PATH:
        DEFAULT_CV_PATH = args.cv

    result = run(args.url, dry_run=args.dry_run)

    if result["status"] in ("applied", "form_filled", "dry_run", "skipped", "analyzed"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
