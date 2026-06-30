import os
import requests
import psycopg2
import urllib.parse
import socket
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

# Alert if monitor hasn't run in this many minutes
THRESHOLD_MINUTES = 120

IST = timezone(timedelta(hours=5, minutes=30))


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


def main():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT value FROM bot_meta WHERE key = 'last_run'")
        row = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"DB error: {e}")
        send_telegram(
            "🔴 <b>DEAD-MAN'S SWITCH ALERT</b>\n\n"
            "Could not connect to the database to check monitor status.\n"
            "Please check Supabase and GitHub Actions manually."
        )
        return

    if not row:
        print("No last_run recorded yet — skipping check")
        return

    last_run_str = row[0]  # e.g. "30 Jun 2026 11:13 AM IST"

    try:
        # Parse the stored format: "%d %b %Y %I:%M %p IST"
        cleaned = last_run_str.replace(" IST", "")
        last_run_dt = datetime.strptime(cleaned, "%d %b %Y %I:%M %p")
        last_run_dt = last_run_dt.replace(tzinfo=IST)
    except Exception as e:
        print(f"Could not parse last_run timestamp: {last_run_str} — {e}")
        return

    now = datetime.now(IST)
    minutes_since = (now - last_run_dt).total_seconds() / 60

    print(f"Last run: {last_run_str}")
    print(f"Minutes since last run: {minutes_since:.1f}")

    if minutes_since > THRESHOLD_MINUTES:
        send_telegram(
            "🔴 <b>DEAD-MAN'S SWITCH ALERT</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ Monitor hasn't run in <b>{int(minutes_since)} minutes</b>!\n\n"
            f"📡 Last successful run:\n{last_run_str}\n\n"
            "Please check:\n"
            "  • cron-job.org execution history\n"
            "  • GitHub Actions tab for failed runs\n"
            "  • Repository activity status"
        )
        print("Alert sent — monitor appears stuck")
    else:
        print("Monitor is healthy, no alert needed")


if __name__ == "__main__":
    main()
