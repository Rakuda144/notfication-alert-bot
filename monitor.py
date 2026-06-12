import os
import json
import requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SEEN_FILE = "seen_tenders.json"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text
    })

def load_seen():
    try:
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(data):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(data), f)

def main():
    seen = load_seen()

    test_id = "TEST001"

    if test_id not in seen:
        send_telegram(
            "🚨 Test Alert\n\nYour GitHub tender bot is working!"
        )

        seen.add(test_id)
        save_seen(seen)

if __name__ == "__main__":
    main()
