import os
import requests
import psycopg2
import urllib.parse
import socket
from datetime import datetime, timedelta, date
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8080))
OWNER_ID = 700080578  # Only this user can use owner-only commands

SITES = {
    "assamtenders": {
        "display": "Assamtenders",
        "url": "https://assamtenders.gov.in/nicgep/app"
    },
    "etenders": {
        "display": "Etenders",
        "url": "https://etenders.gov.in/eprocure/app"
    },
    "pmgsy": {
        "display": "PMGSY Assam",
        "url": "https://pmgsytendersasm.gov.in/nicgep/app?page=Home&service=page"
    },
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
        print(f"DB query error: {type(e).__name__}: {e}")
        return []


# ── Telegram ──────────────────────────────────────────────────────────────────

def send(chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML"
            },
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

WATCHLIST = [
    "Jorhat", "Sivasagar", "Charaideo", "Nazira",
    "Sonari", "Amguri", "Demow", "Lakwa",
    "Simaluguri", "Moran", "Duliajan", "Tinsukia",
    "Dibrugarh", "Golaghat", "Mariani", "Bhojo",
    "Assam"
]


def truncate(text, length=75):
    return text if len(text) <= length else text[:length].rstrip() + "..."


def get_matched_location(title):
    for place in WATCHLIST:
        if place.lower() in title.lower():
            return place
    return ""


def format_row(row, idx=None):
    _, title, ref, closing, opening, date_found, source = row
    site = SITES.get(source, {})
    display = site.get("display", source)
    prefix = f"{idx}. " if idx else "🔹 "
    closing_date = closing.split()[0] if closing else "N/A"
    location = get_matched_location(title)
    result = f"{prefix}<b>{truncate(title)}</b>\n"
    if location:
        result += f"📍 {location}\n"
    result += f"📎 {ref}\n"
    result += f"📅 {closing_date}\n"
    result += f"🏢 {display}\n"
    return result


def send_results(chat_id, rows, header):
    if not rows:
        send(chat_id, f"No results found for: {header}")
        return
    reply = f"<b>{header}</b>\n({len(rows)} found)\n\n"
    for idx, row in enumerate(rows, 1):
        reply += format_row(row, idx) + "\n"

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
        send(chat_id, "Unknown source. Use:\n/source assamtenders\n/source etenders")
        return
    rows = query_db(
        "SELECT type, title, ref, closing, opening, date_found, source FROM alerts WHERE source = %s ORDER BY id DESC LIMIT 10",
        (source,)
    )
    display = SITES[source]["display"]
    send_results(chat_id, rows, f"📍 LATEST FROM {display}")


def cmd_stats(chat_id):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    total = query_db("SELECT COUNT(*) FROM alerts")[0][0] if query_db("SELECT COUNT(*) FROM alerts") else 0
    today_count = query_db("SELECT COUNT(*) FROM alerts WHERE date_found = %s", (today,))[0][0]
    week_count = query_db("SELECT COUNT(*) FROM alerts WHERE date_found >= %s", (week_start,))[0][0]
    month_count = query_db("SELECT COUNT(*) FROM alerts WHERE date_found >= %s", (month_start,))[0][0]

    assam_count = query_db("SELECT COUNT(*) FROM alerts WHERE source = 'assamtenders'")[0][0]
    etenders_count = query_db("SELECT COUNT(*) FROM alerts WHERE source = 'etenders'")[0][0]

    # Most recent tender
    latest = query_db("SELECT title, date_found FROM alerts ORDER BY id DESC LIMIT 1")

    msg = (
        "📊 <b>BOT STATISTICS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 <b>Total tenders tracked:</b> {total}\n"
        f"📅 <b>Today:</b> {today_count}\n"
        f"📆 <b>This week:</b> {week_count}\n"
        f"🗓 <b>This month:</b> {month_count}\n\n"
        f"📍 <b>By source:</b>\n"
        f"  • Assamtenders: {assam_count}\n"
        f"  • Etenders: {etenders_count}\n"
    )

    if latest:
        msg += f"\n🕐 <b>Last found:</b>\n{latest[0][0][:50]}...\n({latest[0][1]})"

    send(chat_id, msg)


def cmd_ping(chat_id):
    from datetime import datetime, timezone, timedelta, date
    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")

    # Get last monitor run time
    last_run_row = query_db("SELECT value FROM bot_meta WHERE key = 'last_run'")
    last_run = last_run_row[0][0] if last_run_row else "Unknown"

    # Get today's count and total
    today = date.today()
    today_count_row = query_db("SELECT COUNT(*) FROM alerts WHERE date_found = %s", (today,))
    today_count = today_count_row[0][0] if today_count_row else 0
    total_row = query_db("SELECT COUNT(*) FROM alerts")
    total = total_row[0][0] if total_row else 0

    send(chat_id,
        f"🟢 <b>BOT STATUS</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕐 <b>Current time:</b> {now}\n"
        f"📡 <b>Monitor last run:</b> {last_run}\n"
        f"🗄 <b>New today:</b> {today_count}\n"
        f"📊 <b>Total tracked:</b> {total}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ Everything running fine"
    )


def cmd_status(chat_id):
    from datetime import datetime
    today = __import__('datetime').date.today()

    # Check each source's last entry
    sources = ["assamtenders", "etenders", "pmgsy", "ongc"]
    status_lines = ""

    for source in sources:
        rows = query_db(
            "SELECT date_found FROM alerts WHERE source = %s ORDER BY id DESC LIMIT 1",
            (source,)
        )
        if rows:
            last_seen = rows[0][0]
            days_ago = (today - last_seen).days
            if days_ago == 0:
                label = "today ✅"
            elif days_ago == 1:
                label = "yesterday ⚠️"
            else:
                label = f"{days_ago} days ago ❌"
            status_lines += f"  • {source}: last entry {label}\n"
        else:
            status_lines += f"  • {source}: no data yet\n"

    total = query_db("SELECT COUNT(*) FROM alerts")[0][0]
    week_start = today - __import__('datetime').timedelta(days=today.weekday())
    this_week = query_db(
        "SELECT COUNT(*) FROM alerts WHERE date_found >= %s", (week_start,)
    )[0][0]

    send(chat_id,
        f"📡 <b>BOT STATUS</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🗄 <b>Database:</b>\n"
        f"  • Total tenders: {total}\n"
        f"  • This week: {this_week}\n\n"
        f"🌐 <b>Sources:</b>\n"
        f"{status_lines}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ Bot is running normally"
    )


def cmd_help(chat_id):
    reply = (
        "🤖 <b>TENDER MONITOR BOT</b>\n\n"
        "📋 <b>LISTING COMMANDS:</b>\n"
        "/today — Tenders listed today\n"
        "/week — Tenders listed this week\n"
        "/latest — Last 5 tenders\n\n"
        "⏰ <b>CLOSING COMMANDS:</b>\n"
        "/closing_today — Closing today\n"
        "/closing_week — Closing this week\n\n"
        "🔍 <b>FILTER COMMANDS:</b>\n"
        "/search [keyword] — Search by keyword\n"
        "   e.g. /search roads\n"
        "/source [name] — Filter by site\n"
        "   /source assamtenders\n"
        "   /source etenders\n\n"
        "📊 <b>OTHER:</b>\n"
        "/stats — Bot statistics\n"
        "/help — Show this message"
    )
    send(chat_id, reply)


# ── Update Handler ────────────────────────────────────────────────────────────

def handle(update):
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    user_id = msg.get("from", {}).get("id")
    text = msg.get("text", "").strip()

    if not chat_id or not text:
        return

    print(f"Command: {text} from user_id: {user_id}")

    # Owner-only commands
    if text.startswith("/ping") or text.startswith("/status"):
        if user_id == OWNER_ID:
            if text.startswith("/ping"):
                cmd_ping(chat_id)
            else:
                cmd_status(chat_id)
        return  # Silently ignore for non-owners

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
    elif text.startswith("/stats"):
        cmd_stats(chat_id)
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
