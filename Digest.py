import os
import requests
import psycopg2
import urllib.parse
import socket
from datetime import datetime, date, timedelta

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

SITES = {
    "assamtenders": "Assamtenders",
    "etenders": "Etenders",
}


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
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=30
        )
    except Exception as e:
        print(f"Telegram error: {e}")


# ── Digest ────────────────────────────────────────────────────────────────────

def send_digest():
    now = datetime.now()
    today = date.today()
    is_morning = now.hour < 12

    period = "🌅 MORNING" if is_morning else "🌆 EVENING"

    # Tenders listed today
    today_rows = query_db(
        "SELECT title, ref, closing, source FROM alerts WHERE date_found = %s ORDER BY id DESC",
        (today,)
    )

    # Tenders closing within 3 days
    closing_soon = []
    all_rows = query_db(
        "SELECT title, ref, closing, source FROM alerts ORDER BY id DESC"
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

    # Total stats
    total = query_db("SELECT COUNT(*) FROM alerts")[0][0]
    this_week_start = today - timedelta(days=today.weekday())
    this_week = query_db(
        "SELECT COUNT(*) FROM alerts WHERE date_found >= %s",
        (this_week_start,)
    )[0][0]

    # Build message
    msg = f"<b>{period} DIGEST</b> — {today.strftime('%d %b %Y')}\n"
    msg += "━━━━━━━━━━━━━━━━━━\n\n"

    # Today's tenders
    if today_rows:
        msg += f"📋 <b>NEW TODAY ({len(today_rows)})</b>\n\n"
        for row in today_rows:
            display = SITES.get(row[3], row[3])
            msg += f"📌 {row[0]}\n"
            msg += f"📎 {row[1]}\n"
            msg += f"⏰ {row[2]}\n"
            msg += f"📍 {display}\n\n"
    else:
        msg += "📋 <b>NEW TODAY</b>\nNo new tenders today.\n\n"

    # Closing soon
    if closing_soon:
        msg += f"⚠️ <b>CLOSING SOON ({len(closing_soon)})</b>\n\n"
        for row, days_left in closing_soon:
            display = SITES.get(row[3], row[3])
            label = "TODAY" if days_left == 0 else f"in {days_left} day{'s' if days_left > 1 else ''}"
            msg += f"📌 {row[0]}\n"
            msg += f"📎 {row[1]}\n"
            msg += f"⏰ Closes <b>{label}</b> — {row[2]}\n"
            msg += f"📍 {display}\n\n"

    # Stats
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"📊 <b>STATS</b>\n"
    msg += f"Total tracked: {total}\n"
    msg += f"This week: {this_week}\n"

    send_telegram(msg)
    print(f"{period} digest sent!")


if __name__ == "__main__":
    send_digest()
