```python
import os
import json
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

URL = "https://assamtenders.gov.in/nicgep/app"
SEEN_FILE = "seen_tenders.json"


def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        return

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": msg
        },
        timeout=30
    )


def load_seen():
    try:
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def fetch_latest_tenders():

    r = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )

    soup = BeautifulSoup(r.text, "html.parser")

    tables = soup.find_all("table")

    target_text = ""

    for table in tables:

        text = table.get_text(" ", strip=True)

        if (
            "Tender Title" in text
            and "Reference No" in text
            and "Closing Date" in text
        ):
            target_text = text
            break

    if not target_text:
        print("Tender table not found")
        return []

    lines = target_text.split()

    tenders = []

    current = ""

    for token in lines:

        if token.endswith(".") and token[:-1].isdigit():

            if current:
                tenders.append(current.strip())

            current = token

        else:
            current += " " + token

    if current:
        tenders.append(current.strip())

    return tenders[:10]


def main():

    print("Checking Assam homepage tenders...")

    tenders = fetch_latest_tenders()

    print("Found", len(tenders), "tenders")

    seen = load_seen()

    updated = False

    for tender in tenders:

        tender_id = tender[:150]

        if tender_id in seen:
            continue

        send_telegram(
            "🚨 NEW ASSAM TENDER\n\n"
            + tender
        )

        seen.add(tender_id)

        updated = True

    if updated:
        save_seen(seen)

    print("Done")


if __name__ == "__main__":
    main()
```
