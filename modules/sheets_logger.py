"""
Google Sheets Application Tracker
===================================
Module 5: Logs every job application attempt to a Google Sheets
spreadsheet for tracking.
"""

import os
from datetime import datetime
from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)

HEADERS = [
    "Date", "Time", "Company", "Role", "URL", "Eligible",
    "Confidence", "Status", "Eligibility Reason", "Resume Objective",
    "Cover Note", "Notes",
]


def _get_sheets_client():
    import gspread
    from google.oauth2.service_account import Credentials
    creds_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "./credentials/google_sheets_key.json")
    if not os.path.exists(creds_path):
        raise RuntimeError(f"Google Sheets credentials not found at: {creds_path}")
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_file(creds_path, scopes=scopes)
    client = gspread.authorize(credentials)
    logger.info("Google Sheets client authenticated")
    return client


def _get_or_create_spreadsheet(client, spreadsheet_id=None):
    import gspread
    if spreadsheet_id:
        try:
            return client.open_by_key(spreadsheet_id)
        except Exception as e:
            logger.warning(f"Could not open spreadsheet: {e}")
    spreadsheet = client.create("Job Applications Tracker")
    worksheet = spreadsheet.sheet1
    worksheet.update("A1", [HEADERS])
    worksheet.format("A1:L1", {"textFormat": {"bold": True},
        "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.3},
        "horizontalAlignment": "CENTER"})
    print(f"\n\ud83d\udcca New Google Sheet created!\n   URL: {spreadsheet.url}\n   ID: {spreadsheet.id}\n")
    return spreadsheet


def log_application(job_data, llm_response, status="applied", notes=""):
    try:
        client = _get_sheets_client()
        sid = os.getenv("GOOGLE_SHEETS_ID", "")
        spreadsheet = _get_or_create_spreadsheet(client, sid if sid else None)
        worksheet = spreadsheet.sheet1
        existing = worksheet.row_values(1)
        if not existing or existing[0] != "Date":
            worksheet.update("A1", [HEADERS])
        now = datetime.now()
        row = [
            now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"),
            job_data.get("company", "Unknown"), job_data.get("job_title", "Unknown"),
            job_data.get("url", "N/A"),
            "Yes" if llm_response.get("eligible", False) else "No",
            f"{llm_response.get('confidence_score', 0):.0%}", status.capitalize(),
            llm_response.get("eligibility_reason", "N/A"),
            llm_response.get("resume_objective", "N/A"),
            llm_response.get("cover_note", "N/A"), notes,
        ]
        worksheet.append_row(row, value_input_option="USER_ENTERED")
        logger.info(f"\ud83d\udcca Logged: {job_data.get('company')} \u2014 {job_data.get('job_title')} ({status})")
        return True
    except Exception as e:
        logger.error(f"Google Sheets logging failed: {e}")
        return False


def get_application_history():
    try:
        client = _get_sheets_client()
        sid = os.getenv("GOOGLE_SHEETS_ID", "")
        if not sid: return []
        spreadsheet = client.open_by_key(sid)
        return spreadsheet.sheet1.get_all_records()
    except Exception as e:
        logger.error(f"Failed to retrieve history: {e}")
        return []
