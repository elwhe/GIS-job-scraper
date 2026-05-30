import requests
import os
import html
import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

# ─── Optional: Google Sheets ──────────────────────────────────────────────────
try:
    import gspread
    from google.oauth2.service_account import Credentials
    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
RAPIDAPI_KEY       = os.environ["RAPIDAPI_KEY"]
TELEGRAM_TOKEN     = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
GSHEET_CREDENTIALS = os.environ.get("GSHEET_CREDENTIALS", "")
GSHEET_ID          = os.environ.get("GSHEET_ID", "")
GSHEET_SHEET_NAME  = "Jobs"

SEEN_JOBS_FILE    = Path("seen_jobs.txt")
MAX_SEEN_JOBS     = 2000
MAX_JOBS_PER_RUN  = 15

# ─── کلمات جستجو شخصی سازی شده ─────────────────────────────────────────────────
SEARCH_QUERIES = [

    # Spatial Data Science
    "Spatial Data Scientist",
    "Geospatial Data Scientist",
    "GIS Data Scientist",
    "Geospatial Machine Learning",

    # Urban Analytics
    "Urban Data Scientist",
    "Urban Analytics",
    "Urban Informatics",
    "Smart City Data Analyst",

    # Transportation
    "Transportation Data Scientist",
    "Mobility Data Scientist",
    "Transit Data Analyst",
    "Transportation GIS",

    # GIS + Python
    "GIS Analyst Python",
    "Geospatial Developer",
    "GIS Specialist Python",

    # Research
    "Research Assistant GIS",
    "Research Associate Transportation",
    "Research Assistant Urban Analytics",
    "PhD Geospatial",
]

# ─── کلمات ممنوعه اصلاح شده ─────────────────────────────────────────────────────
BLACKLIST_KEYWORDS = [
    "senior",
    "staff",
    "principal",
    "director",
    "vp",
    "vice president",
    "manager",
    "15+ years",
    "10+ years",
    "12+ years",
]

# ─── مهارت‌های مورد نیاز ──────────────────────────────────────────────────────
REQUIRED_KEYWORDS = [
    "python",
    "gis",
    "geospatial",
    "spatial",
    "geopandas",
    "arcgis",
    "qgis",
    "machine learning",
    "data science",
    "sql",
    "transportation",
    "mobility",
    "urban",
]

# ══════════════════════════════════════════════════════════════════════════════

def load_seen_jobs() -> set:
    if SEEN_JOBS_FILE.exists():
        ids = set(line.strip() for line in SEEN_JOBS_FILE.read_text().splitlines() if line.strip())
        log.info(f"Loaded {len(ids)} seen job IDs from cache")
        return ids
    log.info("No cache file found — starting fresh")
    return set()


def save_seen_jobs(seen: set) -> None:
    ids_list = list(seen)
    if len(ids_list) > MAX_SEEN_JOBS:
        ids_list = ids_list[-MAX_SEEN_JOBS:]
    SEEN_JOBS_FILE.write_text("\n".join(ids_list))
    log.info(f"Saved {len(ids_list)} job IDs to cache")


# ══════════════════════════════════════════════════════════════════════════════
# JSearch API
# ══════════════════════════════════════════════════════════════════════════════

def search_jobs(query: str, retries: int = 3) -> list:
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-key":  RAPIDAPI_KEY,
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query":          query,
        "num_pages":      "1",
        "date_posted":    "3days",
        # حذف work_from_home برای پیدا کردن شغل‌های مهاجرتی واقعی
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=20)

            if resp.status_code == 429:
                log.warning("Rate limit hit — waiting 60s before retry...")
                time.sleep(60)
                continue

            if resp.status_code == 403:
                log.error("API key invalid or not subscribed (403)")
                return []

            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "OK":
                log.warning(f"API non-OK for '{query}': {data.get('error')}")
                return []

            return data.get("data", [])

        except requests.exceptions.Timeout:
            log.warning(f"Timeout on attempt {attempt}/{retries} for '{query}'")
        except requests.exceptions.JSONDecodeError:
            log.error(f"Invalid JSON response for '{query}'")
            return []
        except requests.exceptions.RequestException as e:
            log.error(f"Request error (attempt {attempt}/{retries}): {e}")

        if attempt < retries:
            wait = 5 * attempt
            log.info(f"Waiting {wait}s before retry...")
            time.sleep(wait)

    log.error(f"All {retries} attempts failed for '{query}'")
    return []


# ══════════════════════════════════════════════════════════════════════════════
# فیلترها
# ══════════════════════════════════════════════════════════════════════════════

def is_blacklisted(job: dict) -> bool:
    description = (job.get("job_description") or "").lower()
    title       = (job.get("job_title") or "").lower()
    combined    = f"{title} {description}"

    for keyword in BLACKLIST_KEYWORDS:
        if keyword.lower() in combined:
            log.info(f"  ⛔ Blacklisted '{job.get('job_title')}' — matched: '{keyword}'")
            return True
    return False


def has_required_keywords(job: dict) -> bool:
    text = (
        (job.get("job_title") or "") +
        " " +
        (job.get("job_description") or "")
    ).lower()
    return any(keyword.lower() in text for keyword in REQUIRED_KEYWORDS)


# ══════════════════════════════════════════════════════════════════════════════
# Telegram
# ══════════════════════════════════════════════════════════════════════════════

def send_telegram(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":                  TELEGRAM_CHAT_ID,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if not resp.ok:
            log.error(f"Telegram error {resp.status_code}: {resp.text[:300]}")
            return False
        return True
    except Exception as e:
        log.error(f"Telegram send exception: {e}")
        return False


def extract_salary(job: dict) -> str:
    if job.get("job_salary_string"):
        return job["job_salary_string"]
    min_s  = job.get("job_min_salary")
    max_s  = job.get("job_max_salary")
    period = (job.get("job_salary_period") or "").lower()
    period_map = {"year": "/yr", "month": "/mo", "hour": "/hr", "week": "/wk"}
    period_label = period_map.get(period, f"/{period}" if period else "")
    if min_s and max_s:
        return f"${int(min_s):,} – ${int(max_s):,}{period_label}"
    if min_s:
        return f"${int(min_s):,}+{period_label}"
    return ""


def format_job(job: dict) -> str:
    title    = html.escape(job.get("job_title")    or "بدون عنوان")
    company  = html.escape(job.get("employer_name") or "نامشخص")
    city     = html.escape(job.get("job_city")     or "")
    country  = html.escape(job.get("job_country")  or "")
    location = f"{city}, {country}".strip(", ") or "Remote"
    source   = html.escape(job.get("job_publisher") or "")
    link     = job.get("job_apply_link") or job.get("job_google_link") or ""
    salary   = extract_salary(job)

    lines = [
        f"💼 <b>{title}</b>",
        f"🏢 {company}",
        f"📍 {location}",
    ]
    if salary:
       
