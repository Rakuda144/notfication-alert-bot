import os
import json
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SEEN_FILE = "seen_tenders.json"
CORR_FILE = "seen_corrigendums.json"

WATCHLIST = [
    "Jorhat", "Sivasagar", "Charaideo", "Nazira", "Sonari",
    "Amguri", "Demow", "Lakwa", "Simaluguri", "Moran",
    "Duliajan", "Tinsukia", "Dibrugarh", "Golaghat",
    "Mariani", "Bhojo", "Assam Asset"
]

BASE_URL = "https://assamtenders.gov.in/nicgep/app"

ACTIVE_URL = "https://assamtenders.gov.in/nicgep/app"

CLOSED_KEYWORDS = [
    "tender evaluation",
    "work order",
    "contract awarded",
    "bid opened",
    "under evaluation",
    "cancelled",
    "withdrawn",
    "work awarded",
    "nit cancelled",
    "finalized",
    "closed",
    "expired",
    "award of contract",
    "awarded",
    "completed",
    "technical evaluation",
    "financial evaluation",
]

CORR_KEYWORDS = [
    "corrigendum",
    "date extension",
    "amendment",
    "cancellation",
    "technical",
    "financial",
]

DATE_FORMATS = [
    "%d-%b-%Y %I:%M %p",
    "%d-%b-%Y %H:%M",
    "%d/%m/%Y %I:%M %p",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M",
    "%d-%b-%Y",
    "%d/%m/%Y",
]


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("WARNING: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.")
        return

    if len(message) > 4000:
        message = message[:3900] + "\n\n...(truncated)"

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Telegram send failed: {e}")


def load_seen():
    try:
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def load_corr():
    try:
        with open(CORR_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_corr(data):
    with open(CORR_FILE, "w") as f:
        json.dump(data, f)


def parse_date(date_str):
    date_str = date_str.strip()

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None


def is_bid_deadline_passed(row_text):
    now = datetime.now()

    date_patterns = [
        r"\d{2}-[A-Za-z]{3}-\d{4}\s+\d{1,2}:\d{2}\s*[APap][Mm]",
        r"\d{2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}",
        r"\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}\s*[APap][Mm]",
        r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}",
        r"\d{2}-[A-Za-z]{3}-\d{4}",
        r"\d{2}/\d{2}/\d{4}",
    ]

    found_dates = []

    for pattern in date_patterns:
        for match in re.findall(pattern, row_text):
            dt = parse_date(match)
            if dt:
                found_dates.append(dt)

    if not found_dates:
        return False

    latest = max(found_dates)
    return latest < now


def is_closed_by_keyword(row_text):
    lower = row_text.lower()
    return any(keyword in lower for keyword in CLOSED_KEYWORDS)


def is_active_tender(row_text):
    if is_closed_by_keyword(row_text):
        return False

    if is_bid_deadline_passed(row_text):
        return False

    return True


def fetch_tenders():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for url in [ACTIVE_URL, BASE_URL]:
        try:
            resp = session.get(url, timeout=30)

            print(f"Fetched {url}")
            print(f"HTTP Status: {resp.status_code}")

            if resp.status_code == 200:
                return resp.text

        except requests.RequestException as e:
            print(f"Request failed: {e}")

    return None


def parse_tender_rows(html):
    soup = BeautifulSoup(html, "html.parser")

    table = (
        soup.find("table", {"class": re.compile(r"list|tender|table", re.I)})
        or soup.find("table", id=re.compile(r"tender|list", re.I))
        or soup.find("table")
    )

    if not table:
        print("ERROR: No tender table found.")
        return []

    tenders = []

    rows = table.find_all("tr")

    for row in rows:

        cells = [
            td.get_text(" ", strip=True)
            for td in row.find_all(["td", "th"])
        ]

        if len(cells) < 2:
            continue

        row_text = " | ".join(cells)

        if len(row_text) < 20:
            continue

        first = cells[0].lower()

        if first in ["sl", "sl.", "s.no", "sno", "#"]:
            continue

        tenders.append({
            "id": row_text,
            "text": row_text,
            "cells": cells
        })

    print(f"Parsed {len(tenders)} rows from table.")
    return tenders


def main():

    send_telegram("✅ TEST MESSAGE FROM BOT")

    html = fetch_tenders()

    if not html:
        print("Failed to fetch page.")
        return

    soup = BeautifulSoup(html, "html.parser")

    print("\n===== HOMEPAGE TABLES =====")

    tables = soup.find_all("table")

    for i, table in enumerate(tables):
        text = table.get_text(" ", strip=True)

        if len(text) > 100:
            print(f"\nTABLE {i}")
            print(text[:2000])

    all_rows = parse_tender_rows(html)

    print(f"Total rows fetched: {len(all_rows)}")

    # CORRIGENDUMS
    corr_lines = []

    print("\n===== CORRIGENDUM CHECK =====")

    for row in all_rows:
        text = row["text"]

        if any(k in text.lower() for k in CORR_KEYWORDS):
            print("CORR:", text)
            corr_lines.append(text)

    old_corr = load_corr()

    new_corr = [c for c in corr_lines if c not in old_corr]

    if new_corr:
        send_telegram(
            f"📢 ASSAM CORRIGENDUM UPDATE\n\n"
            f"{len(new_corr)} new corrigendum(s) detected.\n\n"
            f"{BASE_URL}"
        )

    save_corr(corr_lines)

    # ACTIVE TENDERS
    seen = load_seen()

    print(f"Seen tenders: {len(seen)}")

    updated = False

    active_count = 0
    skipped_count = 0

    print("\n===== ACTIVE TENDER SCAN =====")

    for row in all_rows:

        text = row["text"]

        print("ROW:", text[:300])

        if not is_active_tender(text):
            skipped_count += 1
            continue

        active_count += 1

        matched_place = None

        for place in WATCHLIST:
            if place.lower() in text.lower():
                matched_place = place
                break

        if not matched_place:
            continue

        tender_id = row["id"]

        if tender_id in seen:
            continue

        msg = (
            "🚨 NEW ACTIVE ASSAM TENDER\n\n"
            f"📍 Location Match: {matched_place}\n\n"
            f"{text[:1500]}\n\n"
            f"🔗 {BASE_URL}"
        )

        send_telegram(msg)

        print(f"NEW TENDER: {matched_place}")

        seen.add(tender_id)
        updated = True

    print(
        f"\nSummary → Active: {active_count} | "
        f"Skipped: {skipped_count}"
    )

    if updated:
        save_seen(seen)
