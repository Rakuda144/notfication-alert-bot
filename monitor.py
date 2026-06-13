
import os
import json
import requests
from bs4 import BeautifulSoup

# ---------------- CONFIG ----------------

URL = "https://assamtenders.gov.in/nicgep/app"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SEEN_FILE = "seen_tenders.json"

# ----------------------------------------


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=30
        )

        print("Telegram:", r.status_code)

    except Exception as e:
        print("Telegram error:", e)


def load_seen():
    try:
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f, indent=2)


def fetch_homepage():

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    r = requests.get(
        URL,
        headers=headers,
        timeout=30
    )

    print("HTTP STATUS:", r.status_code)

    r.raise_for_status()

    return r.text


def extract_latest_tenders(html):

    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")

    target_table = None

    for table in tables:

        text = table.get_text(" ", strip=True)

        if (
            "Tender Title" in text
            and "Reference No" in text
            and "Closing Date" in text
        ):
            target_table = table
            break

    if not target_table:
        print("Latest tender table not found")
        return []

    for i, row in enumerate(target_table.find_all("tr")):
    cols = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
    print(f"ROW {i}: {cols}"))

    lines = [
        line.strip()
        for line in text.split("\n")
        if line.strip()
    ]

    tenders = []

    current = []

    for line in lines:

        if line.startswith(tuple(f"{i}." for i in range(1, 30))):

            if current:
                tenders.append("\n".join(current))

            current = [line]

        else:
            current.append(line)

    if current:
        tenders.append("\n".join(current))

    print("Found tenders:", len(tenders))

    return tenders


def main():

    print("===== ASSAM TENDER CHECK =====")

    html = fetch_homepage()

    tenders = extract_latest_tenders(html)

    if not tenders:
        print("No tenders found")
        return

    seen = load_seen()

    print("Seen:", len(seen))

    updated = False

    for tender in tenders:

        tender_id = tender[:250]

        if tender_id in seen:
            continue

        print("NEW TENDER FOUND")

        msg = (
            "🚨 NEW ASSAM TENDER\n\n"
            f"{tender}\n\n"
            f"🔗 {URL}"
        )

        send_telegram(msg)

        seen.add(tender_id)

        updated = True

    if updated:
        save_seen(seen)
        print("seen_tenders.json updated")
    else:
        print("No new tenders")

    print("===== DONE =====")


if __name__ == "__main__":
    main()
