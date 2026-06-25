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
    "assamtenders": "Assamtenders",
    "etenders": "Etenders",
    "pmgsy": "PMGSY Assam",
    "ongc": "ONGC",
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
    if not BOT_TOKEN:
        print("Telegram credentials missing")
        return
    for target in [CHAT_ID, GROUP_ID]:
        if not target:
            continue
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": target,
                    "text": message,
                    "parse_mode": "HTML"
                },
                timeout=30
            )
        except Exception as e:
            print(f"Telegram error for {target}: {e}")


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
    msg = f"🌆 <b>DAILY SUMMARY</b> | {today.strftime('%d %b %Y')}\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"

    # Today's tenders
    if today_rows:
        msg += f"📬 <b>{len(today_rows)} new tender{'s' if len(today_rows) > 1 else ''} today</b>\n\n"
        for idx, row in enumerate(today_rows, 1):
            display = SITES.get(row[3], row[3])
            msg += f"{idx}️⃣ {row[0]}\n"
            msg += f"   📎 {row[1]} | ⏰ {row[2].split()[0] if row[2] else 'N/A'}\n"
            msg += f"   🏢 {display}\n\n"
    else:
        msg += "📭 <b>No new tenders today</b>\n\n"

    # Closing soon
    if closing_soon:
        msg += "━━━━━━━━━━━━━━━━━━\n"
        msg += f"⚠️ <b>Closing soon ({len(closing_soon)})</b>\n\n"
        for row, days_left in closing_soon:
            display = SITES.get(row[3], row[3])
            if days_left == 0:
                label = "TODAY ‼️"
            elif days_left == 1:
                label = "Tomorrow ⚠️"
            else:
                label = f"in {days_left} days"
            msg += f"🔴 {row[0]}\n"
            msg += f"   📎 {row[1]} | ⏰ {label}\n"
            msg += f"   🏢 {display}\n\n"

    # Stats footer
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"📊 Total: {total} | This week: {this_week}"

    send_telegram(msg)
    print("Daily summary sent!")


if __name__ == "__main__":
    send_summary()
