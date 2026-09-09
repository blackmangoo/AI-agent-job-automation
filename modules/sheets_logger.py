"""
Google Sheets Application Tracker
===================================
Module 5: Logs every job application attempt to a Google Sheets
spreadsheet for tracking. Records company, role, URL, eligibility
status, confidence score, and timestamps.

Setup:
    1. Create a Google Cloud project
    2. Enable the Google Sheets API
    3. Create a Service Account and download JSON key
    4. Place the key at ./credentials/google_sheets_key.json
    5. Share your spreadsheet with the service account email
"""

import os
import re
from datetime import datetime
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# Column headers for the tracking sheet
HEADERS = [
    "Date",
    "Time",
    "Company",
    "Role",
    "URL",
    "Eligible",
    "Confidence",
    "Status",
    "Eligibility Reason",
    "Resume Objective",
    "Cover Note",
    "Notes",
]


def _get_sheets_client():
    """Initialize and return a gspread client using service account credentials.

    Returns:
        An authorized gspread.Client instance.

    Raises:
        RuntimeError: If credentials file is missing or authentication fails.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise RuntimeError(
            "Required packages not installed. Run:\n"
            "  pip install gspread google-auth"
        )

    creds_path = os.getenv(
        "GOOGLE_SHEETS_CREDENTIALS",
        "./credentials/google_sheets_key.json"
    )

    if not os.path.exists(creds_path):
        raise RuntimeError(
            f"Google Sheets credentials not found at: {creds_path}\n"
            f"Please create a service account and download the JSON key.\n"
            f"See README.md for setup instructions."
        )

    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = Credentials.from_service_account_file(creds_path, scopes=scopes)
        client = gspread.authorize(credentials)
        logger.info("Google Sheets client authenticated successfully")
        return client
    except Exception as e:
        raise RuntimeError(f"Failed to authenticate with Google Sheets: {e}")


def _extract_spreadsheet_id(id_or_url: str) -> str:
    """Extract clean spreadsheet ID from a raw ID or full Google Sheets URL.

    Args:
        id_or_url: Google Sheets key ID or full URL.

    Returns:
        Clean spreadsheet key ID.
    """
    if not id_or_url:
        return ""
    id_or_url = id_or_url.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", id_or_url)
    if match:
        return match.group(1)
    return id_or_url


def _open_spreadsheet(client, id_or_url: str):
    """Open a Google Spreadsheet by key ID or full URL.

    Args:
        client: Authorized gspread client.
        id_or_url: Key ID or full URL of the spreadsheet.

    Returns:
        Opened gspread.Spreadsheet instance.
    """
    id_or_url = id_or_url.strip()
    if id_or_url.startswith("http://") or id_or_url.startswith("https://"):
        try:
            return client.open_by_url(id_or_url)
        except Exception:
            clean_id = _extract_spreadsheet_id(id_or_url)
            return client.open_by_key(clean_id)
    else:
        return client.open_by_key(id_or_url)


def _get_or_create_spreadsheet(client, spreadsheet_id: Optional[str] = None):
    """Get an existing spreadsheet or create a new one.

    Args:
        client: Authorized gspread client.
        spreadsheet_id: Optional ID or URL of an existing spreadsheet.

    Returns:
        A gspread.Spreadsheet instance.
    """
    import gspread

    if spreadsheet_id:
        try:
            spreadsheet = _open_spreadsheet(client, spreadsheet_id)
            logger.info(f"Opened existing spreadsheet: {spreadsheet.title}")
            return spreadsheet
        except gspread.SpreadsheetNotFound:
            logger.warning(f"Spreadsheet {spreadsheet_id} not found, creating new one")
        except Exception as e:
            logger.warning(f"Could not open spreadsheet {spreadsheet_id}: {e}")

    # Create a new spreadsheet
    spreadsheet = client.create("Job Applications Tracker")
    logger.info(f"Created new spreadsheet: {spreadsheet.title}")
    logger.info(f"Spreadsheet URL: {spreadsheet.url}")
    logger.info(f"Spreadsheet ID: {spreadsheet.id}")

    # Set up the header row
    worksheet = spreadsheet.sheet1
    worksheet.update("A1", [HEADERS])

    # Format header row (bold)
    worksheet.format("A1:L1", {
        "textFormat": {"bold": True},
        "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.3},
        "horizontalAlignment": "CENTER",
    })

    # Auto-resize columns
    worksheet.columns_auto_resize(0, len(HEADERS) - 1)

    print(f"\n📊 New Google Sheet created!")
    print(f"   URL: {spreadsheet.url}")
    print(f"   ID: {spreadsheet.id}")
    print(f"   Add this ID to your .env as GOOGLE_SHEETS_ID\n")

    return spreadsheet


def log_application(
    job_data: dict,
    llm_response: dict,
    status: str = "applied",
    notes: str = "",
) -> bool:
    """Log a job application attempt to Google Sheets.

    Args:
        job_data: Dict from scraper module with job_title, company, url.
        llm_response: Dict from llm_brain with eligible, confidence_score, etc.
        status: Application status — "applied", "skipped", "error", "manual".
        notes: Optional free-text notes about this application.

    Returns:
        True if logging succeeded, False on error.
    """
    try:
        client = _get_sheets_client()
        spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID", "")
        spreadsheet = _get_or_create_spreadsheet(
            client, spreadsheet_id if spreadsheet_id else None
        )
        worksheet = spreadsheet.sheet1

        # Check if headers exist, add them if not
        existing = worksheet.row_values(1)
        if not existing or existing[0] != "Date":
            worksheet.update("A1", [HEADERS])

        # Build the row data
        now = datetime.now()
        row = [
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            job_data.get("company", "Unknown"),
            job_data.get("job_title", "Unknown"),
            job_data.get("url", "N/A"),
            "Yes" if llm_response.get("eligible", False) else "No",
            f"{llm_response.get('confidence_score', 0):.0%}",
            status.capitalize(),
            llm_response.get("eligibility_reason", "N/A"),
            llm_response.get("resume_objective", "N/A"),
            llm_response.get("cover_note", "N/A"),
            notes,
        ]

        # Append the row
        worksheet.append_row(row, value_input_option="USER_ENTERED")

        logger.info(
            f"Logged to Google Sheets: {job_data.get('company')} -- "
            f"{job_data.get('job_title')} ({status})"
        )

        # Update the spreadsheet ID in memory if it was newly created
        if not spreadsheet_id:
            logger.info(
                f"New spreadsheet created with ID: {spreadsheet.id}\n"
                f"Add GOOGLE_SHEETS_ID={spreadsheet.id} to your .env file"
            )

        return True

    except RuntimeError as e:
        logger.error(f"Google Sheets logging failed: {e}")
        logger.info("Application data will be saved to local log file instead")
        return False
    except Exception as e:
        logger.error(f"Unexpected error logging to Google Sheets: {e}")
        return False


def get_applied_urls() -> set:
    """Get all job URLs that have already been logged to Google Sheets.

    Used by the batch orchestrator to skip jobs we've already applied to.

    Returns:
        Set of URL strings from the 'URL' column in the sheet.
        Returns empty set on error.
    """
    try:
        client = _get_sheets_client()
        spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID", "")
        if not spreadsheet_id:
            return set()

        spreadsheet = _open_spreadsheet(client, spreadsheet_id)
        worksheet = spreadsheet.sheet1

        # Get all values from the URL column (column 5, index 4)
        all_values = worksheet.get_all_values()
        urls = set()
        for row in all_values[1:]:  # Skip header row
            if len(row) > 4 and row[4]:  # Column E = URL
                urls.add(row[4].strip())

        logger.info(f"Found {len(urls)} previously applied URLs in Google Sheets")
        return urls

    except Exception as e:
        logger.warning(f"Could not fetch applied URLs from Sheets: {e}")
        return set()


def get_application_history() -> list:
    """Retrieve all logged applications from Google Sheets.

    Returns:
        List of dicts, each representing an application row.
        Returns empty list on error.
    """
    try:
        client = _get_sheets_client()
        spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID", "")

        if not spreadsheet_id:
            logger.warning("No GOOGLE_SHEETS_ID configured")
            return []

        spreadsheet = _open_spreadsheet(client, spreadsheet_id)
        worksheet = spreadsheet.sheet1
        records = worksheet.get_all_records()

        logger.info(f"Retrieved {len(records)} application records from Google Sheets")
        return records

    except Exception as e:
        logger.error(f"Failed to retrieve application history: {e}")
        return []
