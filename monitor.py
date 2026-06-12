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
    if not BOT_TOKEN or not CHAT_ID:
        print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return False

    # Telegram max message length is ~4096
    if len(message) > 4000:
        message = message[:3900] + "\n\n...(truncated)"

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=30
        )
        response.raise_for_status()
        return True

    except requests.RequestException as e:
        print(f"Telegram Error: {e}")
        return False


def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_page_text():
    try:
        response = requests.get(
            URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/137.0 Safari/537.36"
                )
            },
            timeout=30
        )

        response.raise_for_status()

        print(f"Website Status: {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")
        return soup.get_text("\n")

    except requests.RequestException as e:
        print(f"Website Error: {e}")
        return None


def check_corrigendums(text):
    corr_lines = []

    print("===== CORRIGENDUM CHECK =====")

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        lower = line.lower()

        if (
            "date extension" in lower
            or "closing date" in lower
            or "corrigendum" in lower
        ):
            corr_lines.append(line)
            print(line)

    old_corr = load_json(CORR_FILE, [])

    if len(corr_lines) > len(old_corr):
        send_telegram(
            "📢 ASSAM CORRIGENDUM UPDATE\n\n"
            "One or more new Corrigendums / Date Extensions detected.\n\n"
            f"{URL}"
        )
        print("NEW CORRIGENDUM DETECTED")

    if corr_lines != old_corr:
        save_json(CORR_FILE, corr_lines)


def check_tenders(text):
    seen = set(load_json(SEEN_FILE, []))
    updated = False

    print("===== TENDER CHECK =====")

    for line in text.splitlines():

        line = " ".join(line.split())

        if len(line) < 30:
            continue

        matched_place = None

        for place in WATCHLIST:
            if place.lower() in line.lower():
                matched_place = place
                break

        if not matched_place:
            continue

        tender_id = line.lower().strip()

        if tender_id in seen:
            continue

        message = (
            "🚨 NEW ASSAM TENDER\n\n"
            f"📍 Location Match: {matched_place}\n\n"
            f"{line[:1000]}\n\n"
            "Source: Assam eProcurement"
        )

        send_telegram(message)

        print(f"NEW TENDER FOUND: {matched_place}")

        seen.add(tender_id)
        updated = True

    if updated:
        save_json(SEEN_FILE, list(seen))


def main():
    text = get_page_text()

    if not text:
        print("No page text found.")
        return

    check_corrigendums(text)
    check_tenders(text)

    print("Completed successfully.")


if __name__ == "__main__":
    main()
