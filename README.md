# 🤖 AI Job Application Agent

> Autonomous AI agent that scrapes job & internship listings, analyzes eligibility using Groq's LLM, fills application forms with human-like behavior, and tracks all applications in Google Sheets.

**Built by [Ammar Akbar](https://ammar.works) | [GitHub](https://github.com/blackmangoo) | [LinkedIn](https://linkedin.com/in/ammar-akbar2002)**

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py (Orchestrator)                  │
│                                                                 │
│  1. Load config & CV  →  2. Launch browser  →  3. Navigate      │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ human_loop   │  │  scraper     │  │  llm_brain           │   │
│  │ (Module 4)   │←→│  (Module 1)  │→ │  (Module 2)          │   │
│  │              │  │              │  │  Groq LLaMA 3 70B    │   │
│  │ • CAPTCHA    │  │ • BS4 parse  │  │  • JSON mode         │   │
│  │ • File upload│  │ • JD extract │  │  • Eligibility       │   │
│  │ • Login wall │  │ • Questions  │  │  • Screening answers │   │
│  │ • OTP/2FA   │  │              │  │  • Cover note        │   │
│  └──────┬───────┘  └──────────────┘  └───────────┬──────────┘  │
│         │                                         │              │
│         │         ┌──────────────┐                │              │
│         └────────→│ form_filler  │←───────────────┘              │
│                   │ (Module 3)   │                               │
│                   │ • Human-like │                               │
│                   │   typing     │                               │
│                   │ • Smart field│                               │
│                   │   detection  │                               │
│                   └──────┬───────┘                               │
│                          │                                       │
│                   ┌──────┴───────┐                               │
│                   │sheets_logger │                               │
│                   │ (Module 5)   │                               │
│                   │ Google Sheets│                               │
│                   └──────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✨ Features

- **🔍 Smart Scraping** — Playwright + BeautifulSoup extract job titles, company names, descriptions, and screening questions
- **🧠 LLM-Powered Analysis** — Groq's LLaMA 3 70B determines eligibility, generates tailored resume objectives, and answers screening questions
- **⌨️ Human-Like Form Filling** — Character-by-character typing with randomized delays to avoid bot detection
- **🛡️ Human-in-the-Loop** — Auto-detects CAPTCHAs, login walls, file uploads, OTP, and custom essays — pauses for you to handle
- **📊 Google Sheets Tracking** — Every application attempt is logged with company, role, status, and confidence score
- **🔐 Persistent Sessions** — Browser sessions are saved so you only need to log in once
- **🎯 Internship + Job Support** — Works for both full-time roles and internships

---

## 📋 Prerequisites

- **Python 3.11+**
- **Playwright** (Chromium browser)
- **Groq API Key** ([Get one free](https://console.groq.com))
- **Google Cloud Project** with Sheets API enabled (for application tracking)

---

## 🚀 Setup

### 1. Clone the repository

```bash
git clone https://github.com/blackmangoo/AI-agent-job-automation.git
cd AI-agent-job-automation
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright browsers

```bash
playwright install chromium
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and add your keys:
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
GOOGLE_SHEETS_ID=
GOOGLE_SHEETS_CREDENTIALS=./credentials/google_sheets_key.json
BROWSER_DATA_DIR=./browser_data
```

### 5. Place your CV

```bash
mkdir assets
# Place your resume at: assets/updated_cv.pdf
```

### 6. Set up Google Sheets (Optional but recommended)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select existing)
3. Enable the **Google Sheets API** and **Google Drive API**
4. Go to **Credentials** → **Create Credentials** → **Service Account**
5. Name it (e.g., `job-tracker`) and click **Create**
6. Skip role assignment, click **Done**
7. Click on the service account → **Keys** → **Add Key** → **Create new key** → **JSON**
8. Save the downloaded file as `./credentials/google_sheets_key.json`
9. **Share your Google Sheet** with the service account email (found in the JSON file under `client_email`)

---

## 📖 Usage

### Apply to a job listing

```bash
python main.py --url "https://pk.indeed.com/viewjob?jk=abc123"
```

### Dry run (analyze only — no form filling)

```bash
python main.py --url "https://pk.indeed.com/viewjob?jk=abc123" --dry-run
```

### Custom CV path

```bash
python main.py --url "https://pk.indeed.com/viewjob?jk=abc123" --cv "./my_resume.pdf"
```

---

## 🛡️ Human-in-the-Loop

The agent automatically detects and pauses for:

| Trigger | What Happens |
|---------|-------------|
| 🔒 **CAPTCHA** | Detects reCAPTCHA, hCaptcha iframes → Agent pauses → You solve it → Resume |
| 📎 **File Upload** | Detects `<input type="file">` → Agent pauses → You upload your CV → Resume |
| 🔑 **Login Wall** | Detects login/signin forms → Agent pauses → You log in → Resume |
| 📱 **OTP / 2FA** | Detects verification code inputs → Agent pauses → You enter code → Resume |
| ✍️ **Custom Essay** | Detects unrecognized textareas → Agent pauses → You write response → Resume |

When paused, you'll see:
```
╔══════════════════════════════════════════════════════════╗
║   🚨 HUMAN INTERVENTION REQUIRED                        ║
║   Reason: CAPTCHA                                        ║
║   → Complete the action in the browser window             ║
║   → Then click ▶ Resume in the Playwright Inspector       ║
╚══════════════════════════════════════════════════════════╝
```

---

## 📊 Google Sheets Tracker

Every application is logged with:

| Date | Time | Company | Role | URL | Eligible | Confidence | Status | Reason | Objective | Cover Note | Notes |
|------|------|---------|------|-----|----------|------------|--------|--------|-----------|------------|-------|
| 2026-06-24 | 03:15 | TechCorp | AI Engineer | ... | Yes | 85% | Applied | Strong match | ... | ... | ... |

---

## 📁 Project Structure

```
AI-agent-job-automation/
├── .env.example              # Environment template
├── .gitignore                # Protects secrets & data
├── requirements.txt          # Pinned dependencies
├── README.md                 # This file
├── main.py                   # 🎯 Orchestrator — run this
├── git_manager.py            # GitHub auto-commit/push
├── assets/                   # Your CV (gitignored)
├── credentials/              # Google Sheets key (gitignored)
├── config/
│   └── candidate_profile.py  # Your professional profile
├── modules/
│   ├── scraper.py            # Job page scraping engine
│   ├── llm_brain.py          # Groq LLM decision brain
│   ├── form_filler.py        # Smart form filling
│   ├── human_loop.py         # Human-in-the-loop handler
│   └── sheets_logger.py      # Google Sheets tracker
├── utils/
│   ├── browser.py            # Playwright browser manager
│   ├── delays.py             # Human-like delay utilities
│   ├── logger.py             # Colored logging setup
│   └── cv_parser.py          # PDF/DOCX CV parser
└── logs/                     # Application run logs (gitignored)
```

---

## ⚠️ Important Notes

- **This agent does NOT auto-submit** — It fills the form and pauses for your review before submission
- **Use responsibly** — This tool is for legitimate job applications by its owner
- **Rate limiting** — Random delays between actions prevent bot detection
- **Secrets are safe** — `.env`, CV files, and credentials are never committed to git

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Browser Automation | Playwright (sync API) |
| HTML Parsing | BeautifulSoup4 |
| LLM | Groq — LLaMA 3 70B (JSON mode) |
| Config | python-dotenv |
| CV Parsing | PyPDF2 / python-docx |
| Tracking | Google Sheets (gspread) |
| Logging | Python logging (colored) |

---

## 👤 Author

**Mian Muhammad Ammar (Ammar Akbar)**
- 🎓 BS Artificial Intelligence — FAST-NUCES (2026)
- 🌐 [ammar.works](https://ammar.works)
- 💼 [LinkedIn](https://linkedin.com/in/ammar-akbar2002)
- 🐙 [GitHub](https://github.com/blackmangoo)
- 📧 ammar.akbar2002@gmail.com

---

## 📄 License

This project is for personal use by its owner. All rights reserved.
