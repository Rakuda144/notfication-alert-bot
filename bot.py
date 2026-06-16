import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
URL = "https://assamtenders.gov.in/nicgep/app"

WATCHLIST = [
    "Jorhat", "Sivasagar", "Charaideo", "Nazira",
    "Sonari", "Amguri", "Demow", "Lakwa",
    "Simaluguri", "Moran", "Duliajan", "Tinsukia",
    "Dibrugarh", "Golaghat", "Mariani", "Bhojo"
]


# ── Fetch & Parse ─────────────────────────────────────────────────────────────

def fetch_tenders():
    try:
        html = requests.get(
            URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30
        ).text
    except requests.RequestException as e:
        print(f"Fetch error: {e}")
        return [], []

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    def extract_section(text, start, end):
        s = text.find(start)
        e = text.find(end, s)
        if s == -1 or e == -1:
            return []
        return [l.strip() for l in text[s:e].splitlines() if l.strip()]

    def parse(lines):
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
                "title": re.sub(r'^\d+\.\s*', '', chunk[0]),
                "ref":     chunk[1],
                "closing": chunk[2],
                "opening": chunk[3]
            })
        return entries

    tenders = parse(extract_section(
        text, "Tender Title", "Latest Tenders updates every 15 mins."
    ))
    corrigendums = parse(extract_section(
        text, "Corrigendum Title", "Latest Corrigendum updates every 15 mins."
    ))
    return tenders, corrigendums


# ── Formatting ────────────────────────────────────────────────────────────────

def format_entry(entry, emoji="📋"):
    return (
        f"{emoji} {entry['title']}\n"
        f"📎 {entry['ref']}\n"
        f"⏰ Closes: {entry['closing']}\n"
    )


# ── Telegram ──────────────────────────────────────────────────────────────────

def send(chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=30
        )
    except requests.RequestException as e:
        print(f"Send error: {e}")


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_latest(chat_id, tenders, _corrigendums):
    recent = tenders[:5]
    if not recent:
        send(chat_id, "No tenders found on the site right now.")
        return
    reply = "🔴 LATEST 5 TENDERS\n\n"
    reply += "\n".join(format_entry(t) for t in recent)
    reply += f"\n🔗 {URL}"
    send(chat_id, reply)


def cmd_today(chat_id, tenders, _corrigendums):
    today_str = datetime.now().strftime("%d-%b-%Y").upper()
    results = [t for t in tenders if today_str in t["closing"].upper()]
    if not results:
        send(chat_id, f"No tenders closing today ({today_str}).")
        return
    reply = f"📅 TENDERS CLOSING TODAY\n\n"
    reply += "\n".join(format_entry(t) for t in results)
    reply += f"\n🔗 {URL}"
    send(chat_id, reply)


def cmd_week(chat_id, tenders, _corrigendums):
    now = datetime.now()
    results = []
    for t in tenders:
        try:
            closing = datetime.strptime(t["closing"].split()[0], "%d-%b-%Y")
            if now <= closing <= now + timedelta(days=7):
                results.append(t)
        except Exception:
            pass
    if not results:
        send(chat_id, "No tenders closing within the next 7 days.")
        return
    reply = "📆 TENDERS CLOSING THIS WEEK\n\n"
    reply += "\n".join(format_entry(t) for t in results)
    reply += f"\n🔗 {URL}"
    send(chat_id, reply)


def cmd_corrigendums(chat_id, _tenders, corrigendums):
    if not corrigendums:
        send(chat_id, "No corrigendums found on the site right now.")
        return
    reply = "📢 LATEST CORRIGENDUMS\n\n"
    reply += "\n".join(format_entry(c, "📢") for c in corrigendums)
    reply += f"\n🔗 {URL}"
    send(chat_id, reply)


def cmd_watchlist(chat_id, tenders, _corrigendums):
    results = [
        t for t in tenders
        if any(p.lower() in t["title"].lower() for p in WATCHLIST)
    ]
    if not results:
        send(chat_id, "No tenders matching your watchlist locations right now.")
        return
    reply = "📍 WATCHLIST TENDERS\n\n"
    reply += "\n".join(format_entry(t) for t in results)
    reply += f"\n🔗 {URL}"
    send(chat_id, reply)


def cmd_search(chat_id, tenders, _corrigendums, keyword):
    if not keyword:
        send(chat_id, "Please provide a keyword.\nExample: /search roads")
        return
    results = [t for t in tenders if keyword.lower() in t["title"].lower()]
    if not results:
        send(chat_id, f"No tenders found for '{keyword}'.")
        return
    reply = f"🔍 RESULTS FOR '{keyword}'\n\n"
    reply += "\n".join(format_entry(t) for t in results)
    reply += f"\n🔗 {URL}"
    send(chat_id, reply)


def cmd_help(chat_id):
    reply = (
        "🤖 TENDER MONITOR BOT\n\n"
        "Available commands:\n\n"
        "/latest — Last 5 tenders\n"
        "/today — Tenders closing today\n"
        "/week — Tenders closing this week\n"
        "/corrigendums — Latest corrigendums\n"
        "/watchlist — Tenders in your locations\n"
        "/search [keyword] — Search by keyword\n"
        "   e.g. /search roads\n"
        "   e.g. /search bridge\n"
        "/help — Show this message\n\n"
        f"🔗 {URL}"
    )
    send(chat_id, reply)


# ── Update Handler ────────────────────────────────────────────────────────────

def handle(update):
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "").strip()

    if not chat_id or not text:
        return

    print(f"Command received: {text}")

    # Fetch site data fresh for every command
    tenders, corrigendums = fetch_tenders()

    if text.startswith("/latest"):
        cmd_latest(chat_id, tenders, corrigendums)

    elif text.startswith("/today"):
        cmd_today(chat_id, tenders, corrigendums)

    elif text.startswith("/week"):
        cmd_week(chat_id, tenders, corrigendums)

    elif text.startswith("/corrigendums"):
        cmd_corrigendums(chat_id, tenders, corrigendums)

    elif text.startswith("/watchlist"):
        cmd_watchlist(chat_id, tenders, corrigendums)

    elif text.startswith("/search"):
        keyword = text.replace("/search", "").strip()
        cmd_search(chat_id, tenders, corrigendums, keyword)

    elif text.startswith("/help") or text.startswith("/start"):
        cmd_help(chat_id)

    else:
        send(chat_id, "Unknown command. Type /help to see available commands.")


# ── Main Loop ─────────────────────────────────────────────────────────────────

def main():
    print("Bot started, listening for commands...")
    offset = 0
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"timeout": 30, "offset": offset},
                timeout=35
            )
            updates = resp.json().get("result", [])
            for update in updates:
                handle(update)
                offset = update["update_id"] + 1
        except Exception as e:
            print(f"Polling error: {e}")


if __name__ == "__main__":
    main()
