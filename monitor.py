import json
import os
import re
import requests
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────

URL = "https://assamtenders.gov.in/nicgep/app"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

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
]

# These filenames must match what the workflow commits back to the repo
TENDER_FILE = "seen_tenders.json"
CORR_FILE   = "seen_corrigendums.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(filename):
    """Load a JSON list from file. Returns [] if missing or corrupt."""
    try:
        with open(filename, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            print(f"WARNING: {filename} did not contain a list — resetting.")
            return []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_json(filename, data):
    """Always save so the workflow commit step can detect changes."""
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)


def send_telegram(message):
    """Send a message to Telegram. Logs errors instead of crashing."""
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram credentials missing — skipping send.")
        return

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=30,
        )

        if not resp.ok:
            print(f"Telegram API error: {resp.status_code} {resp.text}")

    except requests.RequestException as e:
        print(f"Failed to send Telegram message: {e}")


def in_watchlist(title):
    """Return True if the title mentions any watchlist location."""
    return any(place.lower() in title.lower() for place in WATCHLIST)

# ── Parsing ───────────────────────────────────────────────────────────────────

def extract_section(text, start_marker, end_marker):
    """Pull the block of text between two markers and return non-empty lines."""
    start = text.find(start_marker)

    if start == -1:
        print(f"WARNING: Start marker not found: {start_marker}")
        return []

    end = text.find(end_marker, start)

    if end == -1:
        print(f"WARNING: End marker not found: {end_marker}")
        return []

    return [
        line.strip()
        for line in text[start:end].splitlines()
        if line.strip()
    ]


def parse_tenders(lines):
    """
    Parse tender/corrigendum entries using reference number patterns.
    Anchors on the ref number so stray blank lines don't break parsing.
    """
    REF_PATTERN = re.compile(
        r'^(\d{4}_[A-Z]|[A-Z]{2,}/)'
    )

    entries = []

    for i, line in enumerate(lines):

        if not REF_PATTERN.match(line):
            continue

        title   = lines[i - 1] if i >= 1 else ""
        closing = lines[i + 1] if i + 1 < len(lines) else ""
        opening = lines[i + 2] if i + 2 < len(lines) else ""

        if title.lower() in ("tender title", "corrigendum title", ""):
            continue

        entries.append({
            "title":   title,
            "ref":     line,
            "closing": closing,
            "opening": opening,
        })

    return entries

# ── Main ──────────────────────────────────────────────────────────────────────

def main():

    # 1. Fetch homepage --------------------------------------------------------
    print("Fetching homepage...")

    try:
        response = requests.get(
            URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        response.raise_for_status()
        html = response.text

    except requests.RequestException as e:
        msg = (
            "⚠️ Monitor error: could not reach assamtenders.gov.in\n\n"
            f"{e}"
        )
        print(msg)
        send_telegram(msg)
        return  # Exit cleanly — don't wipe the JSON files

    # 2. Parse page ------------------------------------------------------------
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    tender_lines = extract_section(
        text,
        "Tender Title",
        "Latest Tenders updates every 15 mins."
    )
    corr_lines = extract_section(
        text,
        "Corrigendum Title",
        "Latest Corrigendum updates every 15 mins."
    )
    print("Tender lines:", len(tender_lines))
    print("Corr lines:", len(corr_lines))

    tenders      = parse_tenders(tender_lines)
    corrigendums = parse_tenders(corr_lines)

    print(f"Tenders found: {len(tenders)}")
    print(f"Corrigendums found: {len(corrigendums)}")

    print("Sample tender:", tenders[0] if tenders else "None")
    print("Sample corrigendum:", corrigendums[0] if corrigendums else "None")

    # FIX: Only alert if BOTH are empty — a much stronger signal that
    # the site structure changed, and avoids false alarms when corrigendums
    # legitimately hit zero on a quiet day.
    if len(tenders) == 0 and len(corrigendums) == 0:
        send_telegram(
            "⚠️ Tender Monitor Warning\n\n"
            "No tenders OR corrigendums were found on the homepage.\n"
            "The website structure may have changed or parsing failed.\n"
            "Please check assamtenders.gov.in manually."
        )

    # 3. Load seen state -------------------------------------------------------
    seen_tenders = load_json(TENDER_FILE)
    seen_corr    = load_json(CORR_FILE)

    print(f"Seen tenders loaded: {len(seen_tenders)}")
    print(f"Seen corrigendums loaded: {len(seen_corr)}")

    # 4. Process tenders -------------------------------------------------------
    for tender in tenders:

        title = tender["title"]

        if not in_watchlist(title):
            continue

        if tender["ref"] in seen_tenders:
            continue

        msg = (
            "🚨 NEW TENDER\n\n"
            f"Title:\n{title}\n\n"
            f"Reference:\n{tender['ref']}\n\n"
            f"Closing:\n{tender['closing']}"
        )

        send_telegram(msg)
        seen_tenders.append(tender["ref"])
        print(f"NEW TENDER: {title}")

    # 5. Process corrigendums --------------------------------------------------
    for corr in corrigendums:

        title = corr["title"]

        if not in_watchlist(title):
            continue

        # Matches the existing seen_corrigendums.json format: "title|ref"
        unique_id = f"{title}|{corr['ref']}"

        if unique_id in seen_corr:
            continue

        msg = (
            "📢 NEW CORRIGENDUM\n\n"
            f"Title:\n{title}\n\n"
            f"Reference:\n{corr['ref']}\n\n"
            f"Closing:\n{corr['closing']}"
        )

        send_telegram(msg)
        seen_corr.append(unique_id)
        print(f"NEW CORRIGENDUM: {title}")

    # 6. Always save state -----------------------------------------------------
    print(f"Saving tenders: {len(seen_tenders)}")
    print(f"Saving corrigendums: {len(seen_corr)}")

    save_json(TENDER_FILE, seen_tenders)
    save_json(CORR_FILE, seen_corr)

    print("Done.")


if __name__ == "__main__":
    main()
