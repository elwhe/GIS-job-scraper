import requests
import os
import html
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# ENV
# ─────────────────────────────────────────────
RAPIDAPI_KEY     = os.environ["RAPIDAPI_KEY"]
TELEGRAM_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SEEN_FILE = Path("seen_jobs.txt")

MAX_JOBS = 10

# ─────────────────────────────────────────────
# SEARCH (PhD focused)
# ─────────────────────────────────────────────
SEARCH_QUERIES = [
    "fully funded PhD GIS",
    "PhD Geospatial Data Science",
    "PhD Urban Analytics",
    "PhD Smart Cities",
    "PhD Transportation Engineering",
    "PhD Spatial Data Science",
    "Research Assistant GIS",
    "Research Fellow Urban Analytics",
]

# ─────────────────────────────────────────────
# LOAD / SAVE
# ─────────────────────────────────────────────
def load_seen():
    if SEEN_FILE.exists():
        return set(SEEN_FILE.read_text().splitlines())
    return set()

def save_seen(seen):
    SEEN_FILE.write_text("\n".join(list(seen)[-3000:]))

# ─────────────────────────────────────────────
# JOB API
# ─────────────────────────────────────────────
def search_jobs(query):
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query": query,
        "num_pages": "1",
        "date_posted": "7days",
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if r.status_code != 200:
            return []
        return r.json().get("data", [])
    except:
        return []

# ─────────────────────────────────────────────
# SCORE (PhD PRIORITY ENGINE)
# ─────────────────────────────────────────────
def score(job):
    text = ((job.get("job_title") or "") + " " + (job.get("job_description") or "")).lower()

    s = 0

    # 🎓 PhD core
    if "phd" in text: s += 12
    if "fully funded" in text: s += 10
    if "funded" in text: s += 6
    if "stipend" in text: s += 6
    if "scholarship" in text: s += 6

    # 🧠 field fit
    if "geospatial" in text: s += 6
    if "spatial" in text: s += 5
    if "gis" in text: s += 5
    if "urban" in text: s += 4
    if "smart city" in text: s += 6
    if "transportation" in text: s += 5
    if "mobility" in text: s += 5

    # 🧪 research signals
    if "research assistant" in text: s += 8
    if "research fellow" in text: s += 8
    if "university" in text: s += 4
    if "lab" in text: s += 3

    # ❌ noise filter
    if "seo" in text: s -= 20
    if "marketing" in text: s -= 10
    if "content" in text: s -= 10
    if "sales" in text: s -= 8
    if "senior" in text: s -= 3

    return s

# ─────────────────────────────────────────────
# GOOGLE SCHOLAR (Supervisor Finder)
# ─────────────────────────────────────────────
def scholar_link(name, university):
    q = f"{name} {university} GIS OR geospatial OR urban analytics"
    return f"https://scholar.google.com/scholar?q={q.replace(' ', '+')}"

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    })

# ─────────────────────────────────────────────
# FORMAT
# ─────────────────────────────────────────────
def format_job(job, s):
    title = html.escape(job.get("job_title") or "")
    company = html.escape(job.get("employer_name") or "")
    country = job.get("job_country") or ""
    link = job.get("job_apply_link") or ""

    # attempt supervisor hint
    uni = company
    scholar = scholar_link(company, uni)

    return f"""
🎓 <b>PhD Opportunity Score: {s}</b>

💼 <b>{title}</b>
🏫 {company}
📍 {country}

🔗 Apply: {link}

📚 Potential Supervisor Search:
{scholar}
"""

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    seen = load_seen()
    jobs = []

    for q in SEARCH_QUERIES:
        results = search_jobs(q)

        for j in results:
            jid = j.get("job_id") or j.get("job_apply_link")
            if not jid or jid in seen:
                continue

            seen.add(jid)

            sc = score(j)
            if sc >= 10:   # فقط high quality PhD
                jobs.append((j, sc))

        time.sleep(1)

    jobs.sort(key=lambda x: x[1], reverse=True)

    if not jobs:
        send("🔍 No strong PhD / Research opportunities found today.")
        save_seen(seen)
        return

    send(f"🚀 <b>Top PhD / Research Opportunities</b>\nFound: {len(jobs)}")

    for job, sc in jobs[:MAX_JOBS]:
        send(format_job(job, sc))
        time.sleep(1)

    save_seen(seen)
    log.info("done")


if __name__ == "__main__":
    main()
