import json
import os
import re
import requests
import psycopg2
from bs4 import BeautifulSoup
from datetime import date

URL = "https://assamtenders.gov.in/nicgep/app"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

WATCHLIST = [
    "Jorhat", "Sivasagar", "Charaideo", "Nazira",
    "Sonari", "Amguri", "Demow", "Lakwa",
    "Simaluguri", "Moran", "Duliajan", "Tinsukia",
    "Dibrugarh", "Golaghat", "Mariani", "Bhojo"
]

TENDER_FILE = "seen_tenders.json"
CORR_FILE = "seen_corrigendums.json"


# ── Database ──────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(DATABASE_URL)


def save_to_db(entry_type, title, ref, closing, opening):
    """Save a new tender or corrigendum to the database. Ignores duplicates."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO alerts (type, title, ref, closing, opening, date_found)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (ref, title) DO NOTHING
        """, (entry_type, title, ref, closing, opening, date.today()))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"DB save error: {e}")


# ── JSON (deduplication) ──────────────────────────────────────────────────────

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
            json={"chat_id": CHAT_ID, "text": message},
            timeout=30
        )
    except requests.RequestException as e:
        print(f"Telegram error: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def strip_number(title):
    return re.sub(r'^\d+\.\s*', '', title).strip()


def extract_section(text, start_marker, end_marker):
    start = text.find(start_marker)
    if start == -1:
        return []
    end = text.find(end_marker, start)
    if end == -1:
        return []
    return [l.strip() for l in text[start:end].splitlines() if l.strip()]


def parse_tenders(lines):
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


def migrate_seen_corr(seen_corr):
    migrated = []
    changed = False
    for entry in seen_corr:
        if '|' in entry:
            title_part, ref_part = entry.split('|', 1)
            clean = strip_number(title_part)
            new_entry = f"{clean}|{ref_part}"
            if new_entry != entry:
                changed = True
            migrated.append(new_entry)
        else:
            migrated.append(entry)
    return migrated, changed


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Downloading homepage...")

    try:
        response = requests.get(
            URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30
        )
        response.raise_for_status()
        html = response.text
    except requests.RequestException as e:
        msg = f"⚠️ Monitor error: could not reach assamtenders.gov.in\n\n{e}"
        print(msg)
        send_telegram(msg)
        return

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    tender_lines = extract_section(text, "Tender Title", "Latest Tenders updates every 15 mins.")
    corr_lines = extract_section(text, "Corrigendum Title", "Latest Corrigendum updates every 15 mins.")

    tenders = parse_tenders(tender_lines)
    corrigendums = parse_tenders(corr_lines)

    print(f"Tenders found: {len(tenders)}")
    print(f"Corrigendums found: {len(corrigendums)}")

    seen_tenders = load_json(TENDER_FILE)
    seen_corr = load_json(CORR_FILE)

    seen_corr, migrated = migrate_seen_corr(seen_corr)
    if migrated:
        print("Migrated seen_corrigendums.json")

    updated_tenders = False
    updated_corr = False

    # TENDERS — watchlist filtered
    for tender in tenders:
        title = tender["title"]

        if not any(p.lower() in title.lower() for p in WATCHLIST):
            continue

        if tender["ref"] in seen_tenders:
            continue

        # Save to database
        save_to_db("tender", title, tender["ref"], tender["closing"], tender["opening"])

        msg = (
            "🚨 NEW TENDER\n\n"
            f"Title:\n{title}\n\n"
            f"Reference:\n{tender['ref']}\n\n"
            f"Closing:\n{tender['closing']}\n\n"
            f"🔗 {URL}"
        )
        send_telegram(msg)
        seen_tenders.append(tender["ref"])
        updated_tenders = True
        print(f"NEW TENDER: {title}")

    # CORRIGENDUMS — all of them
    for corr in corrigendums:
        clean_title = strip_number(corr["title"])
        unique_id = f"{clean_title}|{corr['ref']}"

        if unique_id in seen_corr:
            continue

        # Save to database
        save_to_db("corrigendum", clean_title, corr["ref"], corr["closing"], corr["opening"])

        msg = (
            "📢 NEW CORRIGENDUM\n\n"
            f"Title:\n{clean_title}\n\n"
            f"Reference:\n{corr['ref']}\n\n"
            f"Closing:\n{corr['closing']}\n\n"
            f"🔗 {URL}"
        )
        send_telegram(msg)
        seen_corr.append(unique_id)
        updated_corr = True
        print(f"NEW CORRIGENDUM: {clean_title}")

    print(f"Saving tenders: {len(seen_tenders)}")
    print(f"Saving corrigendums: {len(seen_corr)}")

    if updated_tenders or migrated:
        save_json(TENDER_FILE, seen_tenders)
    if updated_corr or migrated:
        save_json(CORR_FILE, seen_corr)

    print("Done")


if __name__ == "__main__":
    main()
