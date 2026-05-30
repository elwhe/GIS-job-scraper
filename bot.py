import requests
import os
import html
import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# ENV
# ─────────────────────────────────────────────────────────────
RAPIDAPI_KEY     = os.environ["RAPIDAPI_KEY"]
TELEGRAM_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SEEN_JOBS_FILE   = Path("seen_jobs.txt")
MAX_JOBS_PER_RUN = 10

# ─────────────────────────────────────────────────────────────
# CORE SEARCH (Spatial Data Science Focus)
# ─────────────────────────────────────────────────────────────
SEARCH_QUERIES = [
    "Geospatial Data Scientist",
    "Spatial Data Scientist",
    "GIS Data Scientist",
    "Geospatial Machine Learning Engineer",

    "Smart City Data Scientist",
    "Urban Data Scientist",
    "Urban Informatics",
    "Smart Mobility Analyst",

    "Transportation Data Scientist",
    "Mobility Data Scientist",
    "Public Transit Analyst",

    "GIS Analyst Python",
    "Geospatial Developer",
    "GIS Engineer",

    "Research Assistant GIS",
    "Urban Analytics Researcher",
    "PhD GIS",
]

# ─────────────────────────────────────────────────────────────
# Load seen jobs
# ─────────────────────────────────────────────────────────────
def load_seen():
    if SEEN_JOBS_FILE.exists():
        return set(SEEN_JOBS_FILE.read_text().splitlines())
    return set()

def save_seen(seen):
    SEEN_JOBS_FILE.write_text("\n".join(list(seen)[-2000:]))

# ─────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────
def search_jobs(query):
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query": query,
        "num_pages": "1",
        "date_posted": "3days",
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("data", [])
    except:
        return []

# ─────────────────────────────────────────────────────────────
# Scoring System (MIGRATION INTELLIGENCE)
# ─────────────────────────────────────────────────────────────
def score_job(job):
    text = ((job.get("job_title") or "") + " " + (job.get("job_description") or "")).lower()

    score = 0

    # Core GIS / Spatial
    if "geospatial" in text: score += 5
    if "spatial" in text: score += 4
    if "gis" in text: score += 4

    # Core skills
    if "python" in text: score += 3
    if "machine learning" in text: score += 4
    if "data science" in text: score += 4
    if "sql" in text: score += 2

    # Domain relevance
    if "urban" in text: score += 3
    if "smart city" in text: score += 4
    if "transportation" in text: score += 4
    if "mobility" in text: score += 4
    if "transit" in text: score += 3

    # Research advantage
    if "research" in text: score += 2
    if "phd" in text: score += 3
    if "university" in text: score += 2

    # NEGATIVE FILTER (SEO killer)
    if "seo" in text: score -= 10
    if "marketing" in text: score -= 8
    if "content" in text: score -= 6
    if "wordpress" in text: score -= 6

    return score

# ─────────────────────────────────────────────────────────────
# Telegram
# ─────────────────────────────────────────────────────────────
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        log.error(e)

# ─────────────────────────────────────────────────────────────
# Format
# ─────────────────────────────────────────────────────────────
def format_job(job, score):
    title = html.escape(job.get("job_title") or "")
    company = html.escape(job.get("employer_name") or "")
    country = job.get("job_country") or ""
    link = job.get("job_apply_link") or ""

    return f"""
🔥 <b>Score: {score}</b>
💼 <b>{title}</b>
🏢 {company}
📍 {country}

🔗 <a href="{link}">Apply</a>
    """

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    log.info("Bot started")

    seen = load_seen()
    all_jobs = []

    for q in SEARCH_QUERIES:
        jobs = search_jobs(q)
        for job in jobs:
            jid = job.get("job_id") or job.get("job_apply_link")
            if not jid or jid in seen:
                continue

            seen.add(jid)

            sc = score_job(job)

            if sc >= 6:
                job["_score"] = sc
                all_jobs.append(job)

        time.sleep(1)

    all_jobs.sort(key=lambda x: x["_score"], reverse=True)

    if not all_jobs:
        send_telegram("🔍 No strong Spatial Data Science jobs found today.")
        save_seen(seen)
        return

    send_telegram(f"🚀 <b>Top Spatial Data Science Jobs</b>\nFound: {len(all_jobs)}")

    for job in all_jobs[:MAX_JOBS_PER_RUN]:
        send_telegram(format_job(job, job["_score"]))
        time.sleep(1)

    save_seen(seen)
    log.info("Done")

# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
