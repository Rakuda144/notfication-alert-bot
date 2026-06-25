import json
import os
import re
import requests
import psycopg2
import urllib.parse
import socket
from bs4 import BeautifulSoup
from datetime import date

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GROUP_ID = os.getenv("TELEGRAM_GROUP_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

WATCHLIST = [
    "Jorhat", "Sivasagar", "Charaideo", "Nazira",
    "Sonari", "Amguri", "Demow", "Lakwa",
    "Simaluguri", "Moran", "Duliajan", "Tinsukia",
    "Dibrugarh", "Golaghat", "Mariani", "Bhojo",
    "Assam"
]

# PMGSY uses Location field from detail page — filter by these
PMGSY_WATCHLIST = [
    "Sivasagar", "Charaideo", "Moran", "Sonari", "Sepon",
    "Nazira", "Jorhat", "Golaghat", "Dibrugarh", "Tinsukia",
    "Duliajan", "Lakwa", "Amguri", "Demow", "Simaluguri",
    "Mariani", "Sibsagar"
]

SITES = [
    {
        "name": "assamtenders",
        "display": "Assamtenders",
        "url": "https://assamtenders.gov.in/nicgep/app",
    },
    {
        "name": "etenders",
        "display": "Etenders",
        "url": "https://etenders.gov.in/eprocure/app",
    },
]

PMGSY_URL = "https://pmgsytendersasm.gov.in/nicgep/app?page=Home&service=page"
ONGC_URL = "https://tenders.ongc.co.in/web/tendersweb"

ONGC_WATCHLIST = [
    "Sivasagar", "Jorhat", "Nazira", "Moran", "Duliajan",
    "Tinsukia", "Dibrugarh", "Golaghat", "Charaideo",
    "Sonari", "Lakwa", "Assam", "Geleki", "Naharkatia",
    "Sibsagar", "Amguri"
]

TENDER_FILE = "seen_tenders.json"


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


def save_to_db(title, ref, closing, opening, source):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO alerts (type, title, ref, closing, opening, date_found, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ref, title) DO NOTHING
        """, ("tender", title, ref, closing, opening, date.today(), source))
        conn.commit()
        cur.close()
        conn.close()
        print(f"Saved to DB: {title[:50]}")
    except Exception as e:
        print(f"DB save error: {type(e).__name__}: {e}")


# ── JSON ──────────────────────────────────────────────────────────────────────

def load_json(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except:
        return []


def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)


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
        except requests.RequestException as e:
            print(f"Telegram error for {target}: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def strip_number(title):
    return re.sub(r'^\d+\.\s*', '', title).strip()


def in_watchlist(title):
    return any(place.lower() in title.lower() for place in WATCHLIST)


def in_pmgsy_watchlist(location):
    return any(place.lower() in location.lower() for place in PMGSY_WATCHLIST)


def in_ongc_watchlist(location):
    return any(place.lower() in location.lower() for place in ONGC_WATCHLIST)


def extract_section(text, start_marker, end_marker):
    start = text.find(start_marker)
    if start == -1:
        return []
    end = text.find(end_marker, start)
    if end == -1:
        return []
    return [l.strip() for l in text[start:end].splitlines() if l.strip()]


def parse_entries(lines):
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
            "title":   chunk[0],
            "ref":     chunk[1],
            "closing": chunk[2],
            "opening": chunk[3]
        })
    return entries


# ── Process NIC sites ─────────────────────────────────────────────────────────

def process_site(site, seen_tenders):
    name = site["name"]
    display = site["display"]
    url = site["url"]

    print(f"\n--- Processing {name} ---")

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=60
        )
        response.raise_for_status()
        html = response.text
    except requests.RequestException as e:
        msg = f"⚠️ Monitor error: could not reach {url}\n\n{e}"
        print(msg)
        send_telegram(msg)
        return False

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    tender_lines = extract_section(
        text,
        "Tender Title",
        "Latest Tenders updates every 15 mins."
    )

    tenders = parse_entries(tender_lines)
    print(f"Tenders found: {len(tenders)}")

    updated = False

    for tender in tenders:
        title = strip_number(tender["title"])

        if not in_watchlist(title):
            continue

        unique_ref = f"{name}|{tender['ref']}"

        if unique_ref in seen_tenders:
            continue

        save_to_db(title, tender["ref"], tender["closing"], tender["opening"], name)

        msg = (
            f"🚨 <b>NEW TENDER</b>\n"
            f"📍 <b>Source:</b> {display}\n\n"
            f"📌 <b>Title:</b>\n{title}\n\n"
            f"📎 <b>Reference:</b>\n{tender['ref']}\n\n"
            f"⏰ <b>Closing:</b>\n{tender['closing']}\n\n"
            f"🔗 {url}"
        )
        send_telegram(msg)
        seen_tenders.append(unique_ref)
        updated = True
        print(f"NEW TENDER: {title}")

    return updated


# ── PMGSY Scraper ─────────────────────────────────────────────────────────────

def fetch_pmgsy_tenders():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })

    print("\n--- Processing pmgsy ---")
    try:
        resp = session.get(PMGSY_URL, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"PMGSY: Homepage fetch failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract tender links
    tender_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.text.strip()
        if "component=%24DirectLink&" in href and "DirectLink_" not in href and text:
            full_url = href if href.startswith("http") else "https://pmgsytendersasm.gov.in" + href
            tender_links.append((text, full_url))

    print(f"PMGSY: Found {len(tender_links)} tender links")

    # Parse homepage for ref/closing/opening
    text_lines = [l.strip() for l in soup.get_text("\n", strip=True).splitlines() if l.strip()]
    homepage_entries = {}
    try:
        idx = text_lines.index("Bid Opening Date") + 1
        data = text_lines[idx:]
        for i in range(0, len(data), 4):
            chunk = data[i:i+4]
            if len(chunk) < 4:
                continue
            title, ref, closing, opening = chunk
            clean = re.sub(r'^\d+\.\s*', '', title).strip()
            homepage_entries[clean] = {"ref": ref, "closing": closing, "opening": opening}
    except ValueError:
        pass

    # Fetch detail pages using same session
    results = []
    for raw_title, link in tender_links:
        clean_title = re.sub(r'^\d+\.\s*', '', raw_title).strip()
        entry = homepage_entries.get(clean_title, {})

        detail_title = clean_title
        location = ""
        pincode = ""

        try:
            detail_resp = session.get(link, timeout=30)
            if detail_resp.status_code == 200 and "Stale Session" not in detail_resp.text:
                dsoup = BeautifulSoup(detail_resp.text, "html.parser")
                dtext = dsoup.get_text("\n", strip=True)

                # Extract Work Description
                wd_match = re.search(r"Work Description\s*\n(.+)", dtext)
                if wd_match:
                    detail_title = wd_match.group(1).strip()

                # Extract Location
                loc_match = re.search(r"Location\s*\n(.+)", dtext)
                if loc_match:
                    location = loc_match.group(1).strip()

                # Extract Pincode
                pin_match = re.search(r"Pincode\s*\n(\d+)", dtext)
                if pin_match:
                    pincode = pin_match.group(1).strip()

                print(f"PMGSY: {clean_title} → Location: {location} Pincode: {pincode}")

        except requests.RequestException as e:
            print(f"PMGSY: Detail fetch failed for {clean_title}: {e}")

        results.append({
            "title": detail_title,
            "road_code": clean_title,
            "ref": entry.get("ref", ""),
            "closing": entry.get("closing", ""),
            "opening": entry.get("opening", ""),
            "location": location,
            "pincode": pincode,
        })

    return results


def process_pmgsy(seen_tenders):
    tenders = fetch_pmgsy_tenders()
    if not tenders:
        return False

    updated = False

    for tender in tenders:
        # Filter by PMGSY watchlist using Location field
        if not in_pmgsy_watchlist(tender["location"]):
            print(f"PMGSY: Skipping {tender['road_code']} — Location: {tender['location']} not in watchlist")
            continue

        unique_ref = f"pmgsy|{tender['road_code']}"

        if unique_ref in seen_tenders:
            continue

        save_to_db(tender["title"], tender["road_code"], tender["closing"], tender["opening"], "pmgsy")

        msg = (
            f"🚨 <b>NEW TENDER</b>\n"
            f"📍 <b>Source:</b> PMGSY Assam\n\n"
            f"📌 <b>Title:</b>\n{tender['title']}\n\n"
            f"🛣 <b>Road Code:</b>\n{tender['road_code']}\n\n"
            f"📎 <b>Reference:</b>\n{tender['ref']}\n\n"
            f"📍 <b>Location:</b> {tender['location']}\n"
            f"📮 <b>Pincode:</b> {tender['pincode']}\n\n"
            f"⏰ <b>Closing:</b>\n{tender['closing']}\n\n"
            f"🔗 {PMGSY_URL}"
        )
        send_telegram(msg)
        seen_tenders.append(unique_ref)
        updated = True
        print(f"NEW PMGSY TENDER: {tender['title'][:60]} [{tender['location']}]")

    return updated


# ── ONGC Scraper ─────────────────────────────────────────────────────────────

def fetch_ongc_tenders():
    resp = None
    for attempt in range(3):
        try:
            print(f"ONGC: Attempt {attempt + 1}/3...")
            resp = requests.get(
                ONGC_URL,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=90
            )
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            print(f"ONGC: Attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                print("ONGC: All attempts failed, skipping")
                return []

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    results = []
    tender_id_pattern = re.compile(r'^[A-Z0-9]{3,}[0-9]{2,}', re.IGNORECASE)
    uploaded_pattern = re.compile(r'^Uploaded on (\d{4}-\d{2}-\d{2})')

    i = 0
    while i < len(lines):
        line = lines[i]
        if tender_id_pattern.match(line) and i + 3 < len(lines):
            next_line = lines[i + 1]
            uploaded_match = uploaded_pattern.match(next_line)
            if uploaded_match:
                tender_id = line.strip()
                upload_date = uploaded_match.group(1)
                title = lines[i + 2] if i + 2 < len(lines) else ""
                meta = lines[i + 3] if i + 3 < len(lines) else ""
                loc_match = re.findall(r'\[([^\]]+)\]', meta)
                location = loc_match[0] if loc_match else ""
                category = loc_match[1] if len(loc_match) > 1 else ""
                print(f"ONGC: {tender_id} → [{location}] {title[:50]}")
                if in_ongc_watchlist(location):
                    results.append({
                        "tender_id": tender_id,
                        "title": title,
                        "location": location,
                        "category": category,
                        "upload_date": upload_date,
                        "ref": tender_id,
                    })
                i += 4
                continue
        i += 1

    print(f"ONGC: Found {len(results)} watchlist tenders")
    return results


def process_ongc(seen_tenders):
    print("\n--- Processing ONGC ---")
    tenders = fetch_ongc_tenders()
    if not tenders:
        return False

    updated = False

    for tender in tenders:
        unique_ref = f"ongc|{tender['ref']}"

        if unique_ref in seen_tenders:
            continue

        save_to_db(tender["title"], tender["ref"], "", "", "ongc")

        msg = (
            f"🚨 <b>NEW TENDER</b>\n"
            f"📍 <b>Source:</b> ONGC\n\n"
            f"📌 <b>Title:</b>\n{tender['title']}\n\n"
            f"📎 <b>Tender ID:</b>\n{tender['ref']}\n\n"
            f"📍 <b>Location:</b> {tender['location']}\n"
            f"🏭 <b>Category:</b> {tender['category']}\n"
            f"📅 <b>Uploaded:</b> {tender['upload_date']}\n\n"
            f"🔗 {ONGC_URL}"
        )
        send_telegram(msg)
        seen_tenders.append(unique_ref)
        updated = True
        print(f"NEW ONGC TENDER: {tender['title'][:60]} [{tender['location']}]")

    return updated


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    seen_tenders = load_json(TENDER_FILE)
    print(f"Seen tenders loaded: {len(seen_tenders)}")

    any_update = False

    for site in SITES:
        updated = process_site(site, seen_tenders)
        if updated:
            any_update = True

    # PMGSY uses session-based scraping with location filter
    if process_pmgsy(seen_tenders):
        any_update = True

    # ONGC uses custom scraper with location filter
    if process_ongc(seen_tenders):
        any_update = True

    print(f"\nSaving tenders: {len(seen_tenders)}")

    if any_update:
        save_json(TENDER_FILE, seen_tenders)

    print("Done")


if __name__ == "__main__":
    main()
