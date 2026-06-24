import os
import requests
import psycopg2
from datetime import datetime, timedelta, date
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8080))

SITES = {
    "assamtenders": "https://assamtenders.gov.in/nicgep/app",
    "etenders": "https://etenders.gov.in/eprocure/app",
}


# ── Database ──────────────────────────────────────────────────────────────────

def get_conn():
    # Parse URL manually to force TCP connection and avoid Unix socket issues
    import urllib.parse
    url = DATABASE_URL.strip()
    parsed = urllib.parse.urlparse(url)
    return psycopg2.connect(
        host=parsed.hostname,
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
        print(f"DB query error: {type(e).__name__}: {e}")
        return []


# ── Telegram ──────────────────────────────────────────────────────────────────

def send(chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=30
        )
    except Exception as e:
        print(f"Send error: {e}")


def set_webhook():
    if not WEBHOOK_URL:
        print("WEBHOOK_URL not set — skipping")
        return
    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
        json={"url": f"{WEBHOOK_URL}/webhook"}
    )
    print(f"Webhook set: {resp.json()}")


# ── Formatting ────────────────────────────────────────────────────────────────

def format_row(row):
    _, title, ref, closing, opening, date_found, source = row
    site_url = SITES.get(source, "https://assamtenders.gov.in/nicgep/app")
    return (
        f"🚨 TENDER\n"
        f"📌 {title}\n"
        f"📎 {ref}\n"
        f"⏰ Closes: {closing}\n"
        f"📅 Listed: {date_found}\n"
        f"📍 {source}\n"
    )


def send_results(chat_id, rows, header):
    if not rows:
        send(chat_id, f"No results found for: {header}")
        return
    reply = f"{header}\n({len(rows)} found)\n\n"
    for row in rows:
        reply += format_row(row) + "\n"

    if len(reply) <= 4096:
        send(chat_id, reply)
    else:
        chunks = [reply[i:i+4096] for i in range(0, len(reply), 4096)]
        for chunk in chunks:
            send(chat_id, chunk)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_today(chat_id):
    today = date.today()
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found, source FROM alerts WHERE date_found = %s ORDER BY id DESC",
        (today,)
    )
    send_results(chat_id, rows, f"📋 TENDERS LISTED TODAY ({today})")


def cmd_week(chat_id):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found, source FROM alerts WHERE date_found >= %s ORDER BY date_found DESC, id DESC",
        (week_start,)
    )
    send_results(chat_id, rows, f"📋 TENDERS LISTED THIS WEEK ({week_start} → {today})")


def cmd_closing_today(chat_id):
    today_str = datetime.now().strftime("%d-%b-%Y").upper()
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found, source FROM alerts WHERE UPPER(closing) LIKE %s ORDER BY id DESC",
        (f"%{today_str}%",)
    )
    send_results(chat_id, rows, f"⏰ TENDERS CLOSING TODAY ({today_str})")


def cmd_closing_week(chat_id):
    results = []
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found, source FROM alerts ORDER BY id DESC"
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
    send_results(chat_id, results, "⏰ TENDERS CLOSING THIS WEEK")


def cmd_latest(chat_id):
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found, source FROM alerts ORDER BY id DESC LIMIT 5"
    )
    send_results(chat_id, rows, "🔴 LATEST 5 TENDERS")


def cmd_search(chat_id, keyword):
    if not keyword:
        send(chat_id, "Please provide a keyword.\nExample: /search roads")
        return
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found, source FROM alerts WHERE LOWER(title) LIKE %s ORDER BY id DESC",
        (f"%{keyword.lower()}%",)
    )
    send_results(chat_id, rows, f"🔍 SEARCH: '{keyword}'")


def cmd_source(chat_id, source):
    if source not in SITES:
        send(chat_id, f"Unknown source. Use:\n/source assamtenders\n/source etenders")
        return
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found, source FROM alerts WHERE source = %s ORDER BY id DESC LIMIT 10",
        (source,)
    )
    send_results(chat_id, rows, f"📍 LATEST FROM {source}")


def cmd_help(chat_id):
    reply = (
        "🤖 TENDER MONITOR BOT\n\n"
        "📋 LISTING COMMANDS:\n"
        "/today — Tenders listed today\n"
        "/week — Tenders listed this week\n"
        "/latest — Last 5 tenders\n\n"
        "⏰ CLOSING COMMANDS:\n"
        "/closing_today — Closing today\n"
        "/closing_week — Closing this week\n\n"
        "🔍 FILTER COMMANDS:\n"
        "/search [keyword] — Search by keyword\n"
        "   e.g. /search roads\n"
        "   e.g. /search bridge\n\n"
        "📍 SOURCE COMMANDS:\n"
        "/source assamtenders\n"
        "/source etenders\n\n"
        "/help — Show this message"
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
    elif text.startswith("/search"):
        keyword = text.replace("/search", "").strip()
        cmd_search(chat_id, keyword)
    elif text.startswith("/source"):
        source = text.replace("/source", "").strip()
        cmd_source(chat_id, source)
    elif text.startswith("/help") or text.startswith("/start"):
        cmd_help(chat_id)
    else:
        send(chat_id, "Unknown command. Type /help to see available commands.")


# ── Webhook Server ────────────────────────────────────────────────────────────

class WebhookHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Tender Bot is running!")

    def do_POST(self):
        if self.path == "/webhook":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                update = json.loads(body)
                handle(update)
            except Exception as e:
                print(f"Webhook error: {e}")
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Testing database connection...")
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM alerts")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        print(f"Database connected! {count} rows in alerts table.")
    except Exception as e:
        print(f"DATABASE CONNECTION FAILED: {type(e).__name__}: {e}")

    set_webhook()
    print(f"Starting webhook server on port {PORT}...")
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
