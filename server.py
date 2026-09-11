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

DEFAULT_CV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "updated_cv.pdf")
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
        # CORS Headers to allow requests from Chrome extension and web pages
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_OPTIONS(self):
        # Handle CORS preflight request
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

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
                self.wfile.write(json.dumps({"urls": list(urls)}).encode("utf-8"))
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
                # Expecting format: { "questions": [...], "job_context": { ... } }
                questions = data.get("questions", [])
                job_context = data.get("job_context", None)
                company = job_context.get("company", "Employer") if job_context else "Employer"
                logger.info(f"AI Brain reasoning over {len(questions)} application questions for {company}...")

                answers = answer_screening_questions(questions, cv_text, job_context=job_context)

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

                # Run Google Sheets and local log in a background thread for zero-latency response
                def _do_log(jd, lr, st):
                    try:
                        log_application(jd, lr, st)
                    except Exception as s_err:
                        logger.warning(f"Google Sheets log failed: {s_err}")
                    try:
                        save_local_log(jd, lr, st)
                    except Exception as f_err:
                        logger.warning(f"Local file log failed: {f_err}")

                import threading
                threading.Thread(target=_do_log, args=(job_data, llm_response, status), daemon=True).start()

                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
            except Exception as e:
                logger.error(f"Error during application logging: {e}\n{traceback.format_exc()}")
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))


def run_server(port=8005):
    # Try preferred port; if occupied, fallback to alternative port
    server_address = ("0.0.0.0", port)
    httpd = None
    actual_port = port

    try:
        http.server.ThreadingHTTPServer.allow_reuse_address = True
        httpd = http.server.ThreadingHTTPServer(server_address, APIRequestHandler)
    except OSError as e:
        alt_port = 8006 if port == 8005 else 8005
        logger.warning(f"Port {port} not available ({e}). Falling back to port {alt_port}...")
        server_address = ("0.0.0.0", alt_port)
        httpd = http.server.ThreadingHTTPServer(server_address, APIRequestHandler)
        actual_port = alt_port

    logger.info(f"Starting Multi-Threaded Local API Server on http://localhost:{actual_port} (and http://127.0.0.1:{actual_port})...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping Local API Server...")
        httpd.server_close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8005))
    run_server(port)
