import os
import requests
import psycopg2
import urllib.parse
import socket
from datetime import datetime, date, timedelta

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GROUP_ID = os.getenv("TELEGRAM_GROUP_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

SITES = {
    "assamtenders": "Assam Tenders",
    "etenders": "eTenders",
    "pmgsy": "PMGSY Assam",
    "ongc": "ONGC",
}

WATCHLIST = [
    "Jorhat", "Sivasagar", "Sibsagar", "Charaideo", "Nazira",
    "Sonari", "Amguri", "Demow", "Lakwa",
    "Simaluguri", "Moran", "Duliajan", "Tinsukia",
    "Dibrugarh", "Golaghat", "Mariani", "Bhojo",
    "Assam"
]


def get_matched_location(title):
    for place in WATCHLIST:
        if place.lower() in title.lower():
            return place
    return ""


# ── Database ──────────────────────────────────────────────────────────────────

def get_conn():
    url = DATABASE_URL.strip()
    parsed = urllib.parse.urlparse(url)
    ipv4 = socket.getaddrinfo(parsed.hostname, parsed.port or 5432, socket.AF_INET)[0][4][0]
    return psycopg2.connect(
        host=ipv4,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
        sslmode="require",
        connect_timeout=10
    )


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
        print(f"DB error: {e}")
        return []


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(message):
    if not BOT_TOKEN:
        print("Telegram credentials missing")
        return
    for target in [CHAT_ID, GROUP_ID]:
        if not target:
            continue
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": target,
                    "text": message,
                    "parse_mode": "HTML"
                },
                timeout=30
            )
            if not resp.ok:
                print(f"Telegram API error for {target}: {resp.status_code} {resp.text}")
            else:
                print(f"Telegram message sent successfully to {target}")
        except Exception as e:
            print(f"Telegram error for {target}: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def truncate(text, length=75):
    return text if len(text) <= length else text[:length].rstrip() + "..."


def format_closing(closing):
    if not closing:
        return "N/A"
    return closing.split()[0] if closing else "N/A"


# ── Daily Summary ─────────────────────────────────────────────────────────────

def send_summary():
    today = date.today()
    now = datetime.now()

    # Tenders listed today
    today_rows = query_db(
        "SELECT title, ref, closing, source FROM alerts WHERE date_found = %s ORDER BY id DESC",
        (today,)
    )

    # Tenders closing within 3 days
    closing_soon = []
    all_rows = query_db(
        "SELECT title, ref, closing, source FROM alerts"
    )
    for row in all_rows:
        closing_str = row[2].split()[0] if row[2] else ""
        try:
            closing_date = datetime.strptime(closing_str, "%d-%b-%Y")
            days_left = (closing_date - now).days
            if 0 <= days_left <= 3:
                closing_soon.append((row, days_left))
        except:
            pass

    # Stats
    total = query_db("SELECT COUNT(*) FROM alerts")[0][0]
    week_start = today - timedelta(days=today.weekday())
    this_week = query_db(
        "SELECT COUNT(*) FROM alerts WHERE date_found >= %s",
        (week_start,)
    )[0][0]

    # ── Build message ─────────────────────────────────────────────────────────
    msg = f"📋 <b>Daily Tender Summary • {today.strftime('%d %b %Y')}</b>\n\n"

    # Today's tenders
    if today_rows:
        msg += f"🆕 <b>New Today: {len(today_rows)}</b>\n\n"
        for idx, row in enumerate(today_rows, 1):
            display = SITES.get(row[3], row[3])
            title = truncate(row[0])
            closing = format_closing(row[2])
            location = get_matched_location(row[0])
            msg += f"{idx}. <b>{title}</b>\n"
            if location:
                msg += f"📍 {location}\n"
            msg += f"📎 {row[1]}\n"
            msg += f"📅 {closing}\n"
            msg += f"🏢 {display}\n\n"
    else:
        msg += "📭 <b>No new tenders today</b>\n\n"

    # Closing soon
    if closing_soon:
        msg += "━━━━━━━━━━━━━━━━━━\n"
        msg += f"⚠️ <b>Closing Soon</b>\n\n"
        for row, days_left in closing_soon:
            display = SITES.get(row[3], row[3])
            title = truncate(row[0])
            if days_left == 0:
                label = "Today ‼️"
            elif days_left == 1:
                label = "Tomorrow ⚠️"
            else:
                label = f"In {days_left} days"
            location = get_matched_location(row[0])
            msg += f"🔴 <b>{title}</b>\n"
            if location:
                msg += f"📍 {location}\n"
            msg += f"📎 {row[1]}\n"
            msg += f"📅 {label} — {format_closing(row[2])}\n"
            msg += f"🏢 {display}\n\n"

    # Stats footer
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"📈 Today: {len(today_rows)} • Week: {this_week} • Total: {total}"

    send_telegram(msg)
    print("Daily summary sent!")


if __name__ == "__main__":
    send_summary()
