import os
import re
import requests
import psycopg2
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, date

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
URL = "https://assamtenders.gov.in/nicgep/app"

WATCHLIST = [
    "Jorhat", "Sivasagar", "Charaideo", "Nazira",
    "Sonari", "Amguri", "Demow", "Lakwa",
    "Simaluguri", "Moran", "Duliajan", "Tinsukia",
    "Dibrugarh", "Golaghat", "Mariani", "Bhojo"
]


# ── Database ──────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(DATABASE_URL)


def query_db(sql, params=()):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"DB query error: {e}")
        return []


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


# ── Formatting ────────────────────────────────────────────────────────────────

def format_row(row):
    """Format a database row into a readable message block."""
    entry_type, title, ref, closing, opening, date_found = row
    emoji = "🚨" if entry_type == "tender" else "📢"
    type_label = "TENDER" if entry_type == "tender" else "CORRIGENDUM"
    return (
        f"{emoji} {type_label}\n"
        f"📌 {title}\n"
        f"📎 {ref}\n"
        f"⏰ Closes: {closing}\n"
        f"📅 Listed: {date_found}\n"
    )


def send_results(chat_id, rows, header):
    if not rows:
        send(chat_id, f"No results found for: {header}")
        return
    reply = f"{header}\n({len(rows)} found)\n\n"
    for row in rows:
        reply += format_row(row) + "\n"
    reply += f"🔗 {URL}"

    # Telegram has 4096 char limit — split if needed
    if len(reply) <= 4096:
        send(chat_id, reply)
    else:
        chunks = [reply[i:i+4096] for i in range(0, len(reply), 4096)]
        for chunk in chunks:
            send(chat_id, chunk)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_today(chat_id):
    """All tenders and corrigendums listed today."""
    today = date.today()
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found FROM alerts WHERE date_found = %s ORDER BY type, id DESC",
        (today,)
    )
    send_results(chat_id, rows, f"📋 LISTED TODAY ({today})")


def cmd_week(chat_id):
    """All tenders and corrigendums listed this week."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found FROM alerts WHERE date_found >= %s ORDER BY date_found DESC, type",
        (week_start,)
    )
    send_results(chat_id, rows, f"📋 LISTED THIS WEEK ({week_start} → {today})")


def cmd_closing_today(chat_id):
    """All tenders and corrigendums closing today."""
    today_str = datetime.now().strftime("%d-%b-%Y").upper()
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found FROM alerts WHERE UPPER(closing) LIKE %s ORDER BY type",
        (f"%{today_str}%",)
    )
    send_results(chat_id, rows, f"⏰ CLOSING TODAY ({today_str})")


def cmd_closing_week(chat_id):
    """All tenders and corrigendums closing within 7 days."""
    results = []
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found FROM alerts ORDER BY type"
    )
    now = datetime.now()
    for row in rows:
        closing_str = row[3].split()[0] if row[3] else ""
        try:
            closing_date = datetime.strptime(closing_str, "%d-%b-%Y")
            if now <= closing_date <= now + timedelta(days=7):
                results.append(row)
        except:
            pass
    send_results(chat_id, results, "⏰ CLOSING THIS WEEK")


def cmd_latest(chat_id):
    """Last 5 entries overall."""
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found FROM alerts ORDER BY id DESC LIMIT 5"
    )
    send_results(chat_id, rows, "🔴 LATEST 5 ALERTS")


def cmd_corrigendums(chat_id):
    """All corrigendums from the database."""
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found FROM alerts WHERE type = 'corrigendum' ORDER BY id DESC LIMIT 20"
    )
    send_results(chat_id, rows, "📢 LATEST CORRIGENDUMS")


def cmd_watchlist(chat_id):
    """Tenders matching watchlist locations."""
    conditions = " OR ".join(["LOWER(title) LIKE %s"] * len(WATCHLIST))
    params = [f"%{p.lower()}%" for p in WATCHLIST]
    rows = query_db(
        f"SELECT type, title, ref, closing, opening, date_found FROM alerts WHERE type = 'tender' AND ({conditions}) ORDER BY id DESC",
        params
    )
    send_results(chat_id, rows, "📍 WATCHLIST TENDERS")


def cmd_search(chat_id, keyword):
    """Search tenders and corrigendums by keyword."""
    if not keyword:
        send(chat_id, "Please provide a keyword.\nExample: /search roads")
        return
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found FROM alerts WHERE LOWER(title) LIKE %s ORDER BY id DESC",
        (f"%{keyword.lower()}%",)
    )
    send_results(chat_id, rows, f"🔍 SEARCH: '{keyword}'")


def cmd_help(chat_id):
    reply = (
        "🤖 TENDER MONITOR BOT\n\n"
        "📋 LISTING COMMANDS:\n"
        "/today — All listed today\n"
        "/week — All listed this week\n"
        "/latest — Last 5 alerts\n\n"
        "⏰ CLOSING COMMANDS:\n"
        "/closing_today — Closing today\n"
        "/closing_week — Closing this week\n\n"
        "🔍 FILTER COMMANDS:\n"
        "/corrigendums — Latest corrigendums\n"
        "/watchlist — Your location tenders\n"
        "/search [keyword] — Search by keyword\n"
        "   e.g. /search roads\n"
        "   e.g. /search bridge\n\n"
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

    print(f"Command: {text}")

    if text.startswith("/today"):
        cmd_today(chat_id)
    elif text.startswith("/week"):
        cmd_week(chat_id)
    elif text.startswith("/closing_today"):
        cmd_closing_today(chat_id)
    elif text.startswith("/closing_week"):
        cmd_closing_week(chat_id)
    elif text.startswith("/latest"):
        cmd_latest(chat_id)
    elif text.startswith("/corrigendums"):
        cmd_corrigendums(chat_id)
    elif text.startswith("/watchlist"):
        cmd_watchlist(chat_id)
    elif text.startswith("/search"):
        keyword = text.replace("/search", "").strip()
        cmd_search(chat_id, keyword)
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
