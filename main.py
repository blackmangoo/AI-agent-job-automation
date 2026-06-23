"""
AI Job Application Agent \u2014 Main Orchestrator
================================================
Wires all modules together into a single automated pipeline.

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
DEFAULT_CV_PATH = "./assets/updated_cv.pdf"


def _print_banner():
    print("""
\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557
\u2551                                                              \u2551
\u2551   \ud83e\udd16 AI Job Application Agent                               \u2551
\u2551   Built for: Ammar Akbar                                     \u2551
\u2551   Target: Jobs & Internships                                 \u2551
\u2551                                                              \u2551
\u2551   github.com/blackmangoo/AI-agent-job-automation             \u2551
\u2551                                                              \u2551
\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d
""")


def _save_local_log(job_data, llm_response, status):
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    company = job_data.get("company", "unknown").replace(" ", "_").lower()[:30]
    role = job_data.get("job_title", "unknown").replace(" ", "_").lower()[:30]
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_data = {"timestamp": datetime.now().isoformat(), "status": status,
                "job_data": job_data, "llm_response": llm_response}
    log_path = log_dir / f"{timestamp}_{company}_{role}.json"
    log_path.write_text(json.dumps(log_data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Local log saved: {log_path}")
    return str(log_path)


def run(job_url, dry_run=False):
    _print_banner()
    load_dotenv()
    if not os.getenv("GROQ_API_KEY"):
        logger.error("GROQ_API_KEY not found"); sys.exit(1)

    try:
        cv_text = parse_cv(DEFAULT_CV_PATH)
    except FileNotFoundError:
        logger.error(f"CV not found at {DEFAULT_CV_PATH}"); sys.exit(1)

    playwright_instance = context = page = None
    try:
        playwright_instance, context, page = launch_browser()
        long_delay()

        page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
        long_delay()

        intervention = check_for_intervention(page)
        if intervention != "clear":
            long_delay()

        job_data = scrape_job_page(page, job_url)
        logger.info(f"JOB: {job_data['job_title']} at {job_data['company']}")

        llm_response = analyze_job(job_data, cv_text)
        eligible_emoji = "\u2705" if llm_response["eligible"] else "\u274c"
        logger.info(f"{eligible_emoji} Eligible: {llm_response['eligible']} ({llm_response['confidence_score']:.0%})")

        status = "analyzed"
        if dry_run:
            status = "dry_run"
        elif llm_response.get("eligible", False):
            long_delay()
            check_for_intervention(page, [a.get("question", "") for a in llm_response.get("screening_answers", [])])
            success = fill_application_form(page, llm_response, CANDIDATE)
            if success:
                print("\n\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557")
                print("\u2551   \ud83d\udccb FORM FILLED \u2014 REVIEW REQUIRED                      \u2551")
                print("\u2551   Review all fields, then submit manually.                \u2551")
                print("\u2551   Click \u25b6 Resume in Playwright Inspector to continue.     \u2551")
                print("\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d\n")
                page.pause()
                status = "applied"
            else:
                status = "form_fill_failed"
        else:
            status = "skipped"

        log_path = _save_local_log(job_data, llm_response, status)
        try:
            log_application(job_data, llm_response, status)
        except Exception as e:
            logger.warning(f"Sheets logging failed: {e}")

        logger.info(f"\u2728 Run complete \u2014 Status: {status.upper()}")
        return {"status": status, "job_data": job_data, "llm_response": llm_response}

    except KeyboardInterrupt:
        return {"status": "interrupted"}
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
    finally:
        if playwright_instance:
            close_browser(playwright_instance, context)


def main():
    parser = argparse.ArgumentParser(description="\ud83e\udd16 AI Job Application Agent")
    parser.add_argument("--url", "-u", required=True, help="Job listing URL")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Analyze only")
    parser.add_argument("--cv", default=DEFAULT_CV_PATH, help="CV file path")
    args = parser.parse_args()
    global DEFAULT_CV_PATH
    if args.cv != DEFAULT_CV_PATH: DEFAULT_CV_PATH = args.cv
    result = run(args.url, dry_run=args.dry_run)
    sys.exit(0 if result["status"] in ("applied", "form_filled", "dry_run", "skipped", "analyzed") else 1)


if __name__ == "__main__":
    main()
