"""
AI Job Application Agent -- Local HTTP Backend
==============================================
Exposes a lightweight, zero-dependency JSON API on http://localhost:8000
to interface with the Chrome Extension.
"""

import http.server
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Add project root to python path to allow importing modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from config.candidate_profile import CANDIDATE
from modules.llm_brain import analyze_job, answer_screening_questions
from modules.sheets_logger import log_application, get_applied_urls
from utils.cv_parser import parse_cv
from utils.logger import get_logger

logger = get_logger("server")

DEFAULT_CV_PATH = "./assets/updated_cv.pdf"
cv_text = ""

# Load and parse CV on startup
try:
    if os.path.exists(DEFAULT_CV_PATH):
        logger.info(f"Parsing CV: {DEFAULT_CV_PATH}")
        cv_text = parse_cv(DEFAULT_CV_PATH)
        logger.info(f"CV parsed successfully: {len(cv_text)} characters")
    else:
        logger.error(f"CV not found at {DEFAULT_CV_PATH}!")
except Exception as e:
    logger.error(f"Failed to parse CV: {e}")


def save_local_log(job_data: dict, llm_response: dict, status: str) -> str:
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


class APIRequestHandler(http.server.BaseHTTPRequestHandler):
    def _set_headers(self, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        # CORS Headers to allow requests from any Chrome extension
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        # Handle CORS preflight request
        self._set_headers(200)

    def do_GET(self):
        if self.path == "/status":
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "status": "online",
                "cv_loaded": len(cv_text) > 0,
                "candidate": CANDIDATE.full_name
            }).encode("utf-8"))
        elif self.path == "/candidate":
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "full_name": CANDIDATE.full_name,
                "email": CANDIDATE.email,
                "phone": CANDIDATE.phone,
                "linkedin": CANDIDATE.linkedin,
                "github": CANDIDATE.github,
                "portfolio": CANDIDATE.portfolio,
                "university": CANDIDATE.university,
                "degree": CANDIDATE.degree,
                "location": CANDIDATE.location,
            }).encode("utf-8"))
        elif self.path == "/applied-urls":
            try:
                urls = get_applied_urls()
                self._set_headers(200)
                self.wfile.write(json.dumps({"urls": urls}).encode("utf-8"))
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode("utf-8"))
        except Exception as e:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": f"Invalid JSON: {e}"}).encode("utf-8"))
            return

        if self.path == "/analyze":
            try:
                # Expecting format: { "job_title", "company", "description", "url", "questions" }
                job_data = {
                    "job_title": data.get("job_title", "Unknown Role"),
                    "company": data.get("company", "Unknown Company"),
                    "description": data.get("description", ""),
                    "url": data.get("url", ""),
                    "questions": data.get("questions", [])
                }
                
                logger.info(f"Analyzing job: {job_data['job_title']} at {job_data['company']}")
                llm_response = analyze_job(job_data, cv_text)
                
                self._set_headers(200)
                self.wfile.write(json.dumps(llm_response).encode("utf-8"))
            except Exception as e:
                logger.error(f"Error during job analysis: {e}\n{traceback.format_exc()}")
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

        elif self.path == "/ask-brain":
            try:
                # Expecting format: { "questions": [...] }
                questions = data.get("questions", [])
                logger.info(f"Asking brain to answer {len(questions)} screening questions dynamically...")
                
                answers = answer_screening_questions(questions, cv_text)
                
                self._set_headers(200)
                self.wfile.write(json.dumps({"answers": answers}).encode("utf-8"))
            except Exception as e:
                logger.error(f"Error during dynamic question answering: {e}\n{traceback.format_exc()}")
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

        elif self.path == "/log":
            try:
                # Expecting format: { "job_data", "llm_response", "status" }
                job_data = data.get("job_data", {})
                llm_response = data.get("llm_response", {})
                status = data.get("status", "applied")
                
                logger.info(f"Logging application for: {job_data.get('job_title')} at {job_data.get('company')}")
                
                # Log to Google Sheets
                try:
                    log_application(job_data, llm_response, status)
                except Exception as sheets_err:
                    logger.error(f"Failed to log to Google Sheets: {sheets_err}")
                
                # Save local JSON log
                save_local_log(job_data, llm_response, status)
                
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
            except Exception as e:
                logger.error(f"Error during application logging: {e}\n{traceback.format_exc()}")
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))


def run_server(port=8000):
    server_address = ("", port)
    httpd = http.server.HTTPServer(server_address, APIRequestHandler)
    logger.info(f"Starting Local API Server on http://localhost:{port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping Local API Server...")
        httpd.server_close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    run_server(port)
