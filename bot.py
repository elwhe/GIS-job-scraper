import requests
import os
import html
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
RAPIDAPI_KEY     = os.environ["RAPIDAPI_KEY"]
TELEGRAM_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SEEN_FILE = Path("seen_phd.txt")
MAX_SEND = 10

# ─────────────────────────────────────────────
# 🎓 REAL PhD SEARCH QUERIES (UNIVERSITY STYLE)
# ─────────────────────────────────────────────
SEARCH_QUERIES = [
    "fully funded PhD GIS studentship",
    "PhD Geoinformatics studentship",
    "PhD Geospatial Analytics university",
    "PhD GeoAI studentship",
    "PhD Urban Informatics funded",
    "doctoral studentship GIS UK",
    "research assistant GIS university",
    "PhD Transportation modelling studentship",
    "PhD Smart Cities university",
    "PhD Spatial Data Science Europe",
]

# ─────────────────────────────────────────────
def load_seen():
    if SEEN_FILE.exists():
        return set(SEEN_FILE.read_text().splitlines())
    return set()

def save_seen(seen):
    SEEN_FILE.write_text("\n".join(list(seen)[-5000:]))

# ─────────────────────────────────────────────
def search(query):
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
# 🎯 PhD SCORING ENGINE (IMPORTANT)
# ─────────────────────────────────────────────
def score(job):
    text = ((job.get("job_title") or "") + " " + (job.get("job_description") or "")).lower()

    s = 0

    # 🎓 FUNDING SIGNALS (MOST IMPORTANT)
    if "fully funded" in text: s += 12
    if "funded phd" in text: s += 10
    if "phd" in text: s += 8
    if "studentship" in text: s += 10
    if "stipend" in text: s += 7
    if "scholarship" in text: s += 7
    if "assistantship" in text: s += 8

    # 🏫 UNIVERSITY RESEARCH SIGNALS
    if "university" in text: s += 5
    if "lab" in text: s += 4
    if "research group" in text: s += 4
    if "department" in text: s += 3

    # 🌍 YOUR FIELD MATCH
    if "geospatial" in text: s += 6
    if "gis" in text: s += 6
    if "spatial" in text: s += 5
    if "geoai" in text: s += 6
    if "urban" in text: s += 4
    if "smart city" in text: s += 6
    if "transportation" in text: s += 5
    if "mobility" in text: s += 5

    # 🧠 TECH
    if "python" in text: s += 3
    if "machine learning" in text: s += 5
    if "deep learning" in text: s += 5

    # ❌ REMOVE NOISE
    if "seo" in text: s -= 20
    if "marketing" in text: s -= 15
    if "sales" in text: s -= 10
    if "wordpress" in text: s -= 10

    return s

# ─────────────────────────────────────────────
# 📚 Supervisor (Google Scholar fallback)
# ─────────────────────────────────────────────
def scholar(name, uni):
    q = f"{name} {uni} GIS geospatial urban analytics"
    return f"https://scholar.google.com/scholar?q={q.replace(' ', '+')}"

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
def format(job, score):
    title = html.escape(job.get("job_title") or "")
    uni = html.escape(job.get("employer_name") or "")
    country = job.get("job_country") or ""
    link = job.get("job_apply_link") or ""

    return f"""
🎓 <b>PhD Score: {score}</b>

💼 {title}
🏫 {uni}
📍 {country}

🔗 Apply: {link}

📚 Supervisor search:
{scholar(uni, uni)}
"""

# ─────────────────────────────────────────────
def main():
    seen = load_seen()
    results = []

    for q in SEARCH_QUERIES:
        jobs = search(q)

        for j in jobs:
            jid = j.get("job_id") or j.get("job_apply_link")
            if not jid or jid in seen:
                continue

            seen.add(jid)

            sc = score(j)

            # 🎯 threshold for PhD quality
            if sc >= 12:
                results.append((j, sc))

        time.sleep(1)

    results.sort(key=lambda x: x[1], reverse=True)

    if not results:
        send("🔍 No strong PhD / funded research positions found today.")
        save_seen(seen)
        return

    send(f"🚀 <b>Top PhD Opportunities (GIS / Spatial AI)</b>\nFound: {len(results)}")

    for job, sc in results[:MAX_SEND]:
        send(format(job, sc))
        time.sleep(1)

    save_seen(seen)
    log.info("done")

# ─────────────────────────────────────────────
if __name__ == "__main__":
    main()
