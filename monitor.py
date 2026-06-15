import json
import os
import re
import requests
from bs4 import BeautifulSoup

URL = "https://assamtenders.gov.in/nicgep/app"
HOMEPAGE = "https://assamtenders.gov.in/nicgep/app"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

WATCHLIST = [
    "Jorhat",
    "Sivasagar",
    "Charaideo",
    "Nazira",
    "Sonari",
    "Amguri",
    "Demow",
    "Lakwa",
    "Simaluguri",
    "Moran",
    "Duliajan",
    "Tinsukia",
    "Dibrugarh",
    "Golaghat",
    "Mariani",
    "Bhojo"
]

TENDER_FILE = "seen_tenders.json"
CORR_FILE = "seen_corrigendums.json"


def load_json(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except:
        return []


def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=30
    )


def strip_number(title):
    """Remove leading number like '1. ', '2. ' from title."""
    return re.sub(r'^\d+\.\s*', '', title).strip()


def extract_section(text, start_marker, end_marker):
    start = text.find(start_marker)
    if start == -1:
        return []
    end = text.find(end_marker, start)
    if end == -1:
        return []
    section = text[start:end]
    lines = [
        line.strip()
        for line in section.splitlines()
        if line.strip()
    ]
    return lines


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
        title, ref_no, closing, opening = chunk
        entries.append({
            "title": title,
            "ref": ref_no,
            "closing": closing,
            "opening": opening
        })
    return entries


def migrate_seen_corr(seen_corr):
    """Strip leading numbers from old entries in seen_corrigendums.json."""
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


def main():
    print("Downloading homepage...")

    html = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    ).text

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    tender_lines = extract_section(
        text,
        "Tender Title",
        "Latest Tenders updates every 15 mins."
    )
    corr_lines = extract_section(
        text,
        "Corrigendum Title",
        "Latest Corrigendum updates every 15 mins."
    )

    tenders = parse_tenders(tender_lines)
    corrigendums = parse_tenders(corr_lines)

    print("Tenders found:", len(tenders))
    print("Corrigendums found:", len(corrigendums))

    seen_tenders = load_json(TENDER_FILE)
    seen_corr = load_json(CORR_FILE)

    # Migrate old numbered entries to new format
    seen_corr, migrated = migrate_seen_corr(seen_corr)
    if migrated:
        print("Migrated seen_corrigendums.json to strip numbering")

    updated_tenders = False
    updated_corr = False

    # TENDERS
    for tender in tenders:
        title = tender["title"]

        if not any(place.lower() in title.lower() for place in WATCHLIST):
            continue

        if tender["ref"] in seen_tenders:
            continue

        msg = (
            "🚨 NEW TENDER\n\n"
            f"Title:\n{title}\n\n"
            f"Reference:\n{tender['ref']}\n\n"
            f"Closing:\n{tender['closing']}\n\n"
            f"🔗 {HOMEPAGE}"
        )
        send_telegram(msg)
        seen_tenders.append(tender["ref"])
        updated_tenders = True
        print("NEW TENDER:", title)

    # CORRIGENDUMS
    for corr in corrigendums:
        clean_title = strip_number(corr["title"])
        unique_id = f"{clean_title}|{corr['ref']}"

        if unique_id in seen_corr:
            continue

        msg = (
            "📢 NEW CORRIGENDUM\n\n"
            f"Title:\n{clean_title}\n\n"
            f"Reference:\n{corr['ref']}\n\n"
            f"Closing:\n{corr['closing']}\n\n"
            f"🔗 {HOMEPAGE}"
        )
        send_telegram(msg)
        seen_corr.append(unique_id)
        updated_corr = True
        print("NEW CORRIGENDUM:", clean_title)

    print("Saving tenders:", len(seen_tenders))
    print("Saving corrigendums:", len(seen_corr))

    if updated_tenders or migrated:
        save_json(TENDER_FILE, seen_tenders)
    if updated_corr or migrated:
        save_json(CORR_FILE, seen_corr)

    print("Done")


if __name__ == "__main__":
    main()
                  
