import json
import os
import re
import requests
import psycopg2
import urllib.parse
import socket
from bs4 import BeautifulSoup
from datetime import date

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

WATCHLIST = [
    "Jorhat", "Sivasagar", "Charaideo", "Nazira",
    "Sonari", "Amguri", "Demow", "Lakwa",
    "Simaluguri", "Moran", "Duliajan", "Tinsukia",
    "Dibrugarh", "Golaghat", "Mariani", "Bhojo",
    "Assam"
]

SITES = [
    {
        "name": "assamtenders",
        "display": "Assamtenders",
        "url": "https://assamtenders.gov.in/nicgep/app",
    },
    {
        "name": "etenders",
        "display": "Etenders",
        "url": "https://etenders.gov.in/eprocure/app",
    },
]

TENDER_FILE = "seen_tenders.json"


# ── Database ──────────────────────────────────────────────────────────────────

def get_conn():
    url = DATABASE_URL.strip()
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    ipv4 = socket.getaddrinfo(hostname, parsed.port or 5432, socket.AF_INET)[0][4][0]
    return psycopg2.connect(
        host=ipv4,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
        sslmode="require",
        connect_timeout=10
    )


def save_to_db(title, ref, closing, opening, source):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO alerts (type, title, ref, closing, opening, date_found, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ref, title) DO NOTHING
        """, ("tender", title, ref, closing, opening, date.today(), source))
        conn.commit()
        cur.close()
        conn.close()
        print(f"Saved to DB: {title[:50]}")
    except Exception as e:
        print(f"DB save error: {type(e).__name__}: {e}")


# ── JSON ──────────────────────────────────────────────────────────────────────

def load_json(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except:
        return []


def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=30
        )
    except requests.RequestException as e:
        print(f"Telegram error: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def strip_number(title):
    return re.sub(r'^\d+\.\s*', '', title).strip()


def in_watchlist(title):
    return any(place.lower() in title.lower() for place in WATCHLIST)


def extract_section(text, start_marker, end_marker):
    start = text.find(start_marker)
    if start == -1:
        return []
    end = text.find(end_marker, start)
    if end == -1:
        return []
    return [l.strip() for l in text[start:end].splitlines() if l.strip()]


def parse_entries(lines):
    entries = []
    try:
        idx = lines.index("Bid Opening Date") + 1
    except ValueError:
        return entries
    data = lines[idx:]
    for i in range(0, len(data), 4):
        chunk = data[i:i + 4]
        if len(chunk) < 4:
            continue
        entries.append({
            "title":   chunk[0],
            "ref":     chunk[1],
            "closing": chunk[2],
            "opening": chunk[3]
        })
    return entries


# ── Process one site ──────────────────────────────────────────────────────────

def process_site(site, seen_tenders):
    name = site["name"]
    display = site["display"]
    url = site["url"]

    print(f"\n--- Processing {name} ---")

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=60
        )
        response.raise_for_status()
        html = response.text
    except requests.RequestException as e:
        msg = f"⚠️ Monitor error: could not reach {url}\n\n{e}"
        print(msg)
        send_telegram(msg)
        return False

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    tender_lines = extract_section(
        text,
        "Tender Title",
        "Latest Tenders updates every 15 mins."
    )

    tenders = parse_entries(tender_lines)
    print(f"Tenders found: {len(tenders)}")

    updated = False

    for tender in tenders:
        title = strip_number(tender["title"])

        if not in_watchlist(title):
            continue

        unique_ref = f"{name}|{tender['ref']}"

        if unique_ref in seen_tenders:
            continue

        save_to_db(title, tender["ref"], tender["closing"], tender["opening"], name)

        msg = (
            f"🚨 <b>NEW TENDER</b>\n"
            f"📍 <b>Source:</b> {display}\n\n"
            f"📌 <b>Title:</b>\n{title}\n\n"
            f"📎 <b>Reference:</b>\n{tender['ref']}\n\n"
            f"⏰ <b>Closing:</b>\n{tender['closing']}\n\n"
            f"🔗 {url}"
        )
        send_telegram(msg)
        seen_tenders.append(unique_ref)
        updated = True
        print(f"NEW TENDER: {title}")

    return updated


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    seen_tenders = load_json(TENDER_FILE)
    print(f"Seen tenders loaded: {len(seen_tenders)}")

    any_update = False

    for site in SITES:
        updated = process_site(site, seen_tenders)
        if updated:
            any_update = True

    print(f"\nSaving tenders: {len(seen_tenders)}")

    if any_update:
        save_json(TENDER_FILE, seen_tenders)

    print("Done")


if __name__ == "__main__":
    main()
