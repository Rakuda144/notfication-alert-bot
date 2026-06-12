import os
import json
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SEEN_FILE = "seen_tenders.json"
CORR_FILE = "seen_corrigendums.json"

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
    "Bhojo",
    "Assam Asset"
]

URL = "https://assamtenders.gov.in/nicgep/app"


def send_telegram(message):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": message
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
def load_corr():
    try:
        with open(CORR_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_corr(data):
    with open(CORR_FILE, "w") as f:
        json.dump(data, f)


def main():
    response = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )

    print("Status:", response.status_code)

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text("\n")

    # CORRIGENDUM CHECK

corr_lines = []

print("===== CORRIGENDUM TABLE TEST =====")

for line in text.split("\n"):
    line = line.strip()

    if (
        "date extension" in line.lower()
        or "sbm(" in line.lower()
        or "closing date" in line.lower()
    ):
        print(line)

    if "date extension" in line.lower():
        corr_lines.append(line)

old_corr = load_corr()

    if len(corr_lines) > len(old_corr):
        send_telegram(
            "📢 ASSAM CORRIGENDUM UPDATE\n\n"
            "One or more new Date Extensions / Corrigendums detected.\n\n"
            "Check: https://assamtenders.gov.in/nicgep/app"
        )

        print("NEW CORRIGENDUM DETECTED")

    save_corr(corr_lines)

    # TENDER CHECK
    seen = load_seen()
    updated = False

    for line in text.split("\n"):
        line = line.strip()

        if len(line) < 30:
            continue

        matched = False
        matched_place = ""

        for place in WATCHLIST:
            if place.lower() in line.lower():
                matched = True
                matched_place = place
                break

        if not matched:
            continue

        tender_id = line

        if tender_id not in seen:

            msg = (
                "🚨 NEW ASSAM TENDER\n\n"
                f"Location Match: {matched_place}\n\n"
                f"{line}\n\n"
                "Source: Assam eProcurement"
            )

            send_telegram(msg)

            seen.add(tender_id)
            updated = True

            print("NEW:", line)

    if updated:
        save_seen(seen)

if __name__ == "__main__":
    main()
