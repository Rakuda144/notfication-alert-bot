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

# Assamtenders — NO "Assam" (appears in every footer/org name on this site)
WATCHLIST = [
    "Jorhat", "Sivasagar", "Charaideo", "Nazira",
    "Sonari", "Amguri", "Demow", "Lakwa",
    "Simaluguri", "Moran", "Duliajan", "Tinsukia",
    "Dibrugarh", "Golaghat", "Mariani", "Bhojo"
]

# Etenders — all-India site so include "Assam" to catch Assam tenders
ETENDERS_WATCHLIST = [
    "Jorhat", "Sivasagar", "Charaideo", "Nazira",
    "Sonari", "Amguri", "Demow", "Lakwa",
    "Simaluguri", "Moran", "Duliajan", "Tinsukia",
    "Dibrugarh", "Golaghat", "Mariani", "Bhojo",
    "Assam"
]

# PMGSY — filters by Location field from detail page
PMGSY_WATCHLIST = [
    "Sivasagar", "Charaideo", "Moran", "Sonari", "Sepon",
    "Nazira", "Jorhat", "Golaghat", "Dibrugarh", "Tinsukia",
    "Duliajan", "Lakwa", "Amguri", "Demow", "Simaluguri",
    "Mariani", "Sibsagar"
]

# ONGC — filters by Location field
ONGC_WATCHLIST = [
    "Sivasagar", "Jorhat", "Nazira", "Moran", "Duliajan",
    "Tinsukia", "Dibrugarh", "Golaghat", "Charaideo",
    "Sonari", "Lakwa", "Geleki", "Naharkatia",
    "Sibsagar", "Amguri"
]

SITES = [
    {
        "name": "assamtenders",
        "display": "Assamtenders",
        "url": "https://assamtenders.gov.in/nicgep/app",
        "watchlist": WATCHLIST,
    },
    {
        "name": "etenders",
        "display": "Etenders",
        "url": "https://etenders.gov.in/eprocure/app",
        "watchlist": ETENDERS_WATCHLIST,
    },
]

PMGSY_URL = "https://pmgsytendersasm.gov.in/nicgep/app?page=Home&service=page"
ONGC_URL = "https://tenders.ongc.co.in/web/tendersweb"
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


def save_last_run():
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bot_meta (key, value) VALUES ('last_run', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (now,))
        conn.commit()
        cur.close()
        conn.close()
        print(f"Last run saved: {now}")
    except Exception as e:
        print(f"DB meta save error: {e}")


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


def truncate(text, length=75):
    return text if len(text) <= length else text[:length].rstrip() + "..."


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


def in_pmgsy_watchlist(location):
    return any(place.lower() in location.lower() for place in PMGSY_WATCHLIST)


def in_ongc_watchlist(location):
    return any(place.lower() in location.lower() for place in ONGC_WATCHLIST)


# ── Process NIC sites ─────────────────────────────────────────────────────────

def fetch_nic_detail(session, link):
    """Fetch a NIC tender detail page using session cookies and extract
    location, pincode, tender value, product category, and tender ID.
    """
    details = {"location": "", "pincode": "", "value": "", "category": "", "tender_id": ""}
    try:
        resp = session.get(link, timeout=30)
        if resp.status_code != 200 or "Stale Session" in resp.text:
            return details

        dsoup = BeautifulSoup(resp.text, "html.parser")
        dtext = dsoup.get_text("\n", strip=True)

        # Match Location that is immediately followed by Pincode to avoid
        # grabbing an earlier unrelated "Location" link from the nav menu
        # (e.g. "Tenders by Location")
        loc_pin_match = re.search(r"Location\s*\n(.+)\s*\nPincode\s*\n(\d+)", dtext)
        if loc_pin_match:
            details["location"] = loc_pin_match.group(1).strip()
            details["pincode"] = loc_pin_match.group(2).strip()

        value_match = re.search(r"Tender Value in ₹\s*\n([\d,]+)", dtext)
        if value_match:
            details["value"] = value_match.group(1).strip()

        category_match = re.search(r"Product Category\s*\n(.+)", dtext)
        if category_match:
            details["category"] = category_match.group(1).strip()

        tid_match = re.search(r"Tender ID\s*\n(\S+)", dtext)
        if tid_match:
            details["tender_id"] = tid_match.group(1).strip()

    except requests.RequestException as e:
        print(f"Detail fetch failed: {e}")

    return details


def process_site(site, seen_tenders):
    name = site["name"]
    display = site["display"]
    url = site["url"]
    watchlist = site["watchlist"]

    print(f"\n--- Processing {name} ---")

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

    html = None
    for attempt in range(3):
        try:
            print(f"{name}: Attempt {attempt + 1}/3...")
            response = session.get(url, timeout=60)
            response.raise_for_status()
            html = response.text
            break
        except requests.RequestException as e:
            print(f"{name}: Attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                print(f"ERROR: Could not reach {url} after 3 attempts")
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

    # Map title -> detail link from the raw homepage HTML
    title_to_link = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        link_text = a.text.strip()
        if "component=%24DirectLink&" in href and "DirectLink_" not in href and link_text:
            full_url = href if href.startswith("http") else url.split("/nicgep")[0] + href
            clean = strip_number(link_text)
            title_to_link[clean] = full_url

    updated = False

    for tender in tenders:
        title = strip_number(tender["title"])
        print(f"{name}: {title[:70]}")

        matched = next((p for p in watchlist if p.lower() in title.lower()), None)
        if not matched:
            continue

        unique_ref = f"{name}|{tender['ref']}"
        if unique_ref in seen_tenders:
            continue

        # Fetch detail page only for watchlist matches
        details = {"location": "", "pincode": "", "value": "", "category": "", "tender_id": ""}
        link = title_to_link.get(title)
        if link:
            details = fetch_nic_detail(session, link)
            print(f"{name}: Detail → Location: {details['location']} Pincode: {details['pincode']} Value: {details['value']} Category: {details['category']} TenderID: {details['tender_id']}")

        save_to_db(title, tender["ref"], tender["closing"], tender["opening"], name)

        location_display = details["location"] or matched
        msg = (
            f"🚨 <b>NEW TENDER</b> · {display}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>{truncate(title)}</b>\n\n"
            + (f"📍 <b>Location:</b> {location_display}\n" if location_display else "")
            + (f"📮 <b>Pincode:</b> {details['pincode']}\n" if details["pincode"] else "")
            + (f"💰 <b>Value:</b> ₹{details['value']}\n" if details["value"] else "")
            + (f"🏷 <b>Category:</b> {details['category']}\n" if details["category"] else "")
            + f"📎 <b>Ref:</b> {tender['ref']}\n"
            + (f"🆔 <b>Tender ID:</b> {details['tender_id']}\n" if details["tender_id"] else "")
            + f"📅 <b>Closing:</b> {tender['closing']}\n\n"
            f"🔗 <a href=\"{url}\">View on {display}</a>"
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
    resp = None
    for attempt in range(3):
        try:
            print(f"PMGSY: Attempt {attempt + 1}/3...")
            resp = session.get(PMGSY_URL, timeout=60)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            print(f"PMGSY: Attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                print("PMGSY: All attempts failed, skipping")
                return []

    soup = BeautifulSoup(resp.text, "html.parser")

    tender_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.text.strip()
        if "component=%24DirectLink&" in href and "DirectLink_" not in href and text:
            full_url = href if href.startswith("http") else "https://pmgsytendersasm.gov.in" + href
            tender_links.append((text, full_url))

    print(f"PMGSY: Found {len(tender_links)} tender links")

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

    results = []
    for raw_title, link in tender_links:
        clean_title = re.sub(r'^\d+\.\s*', '', raw_title).strip()
        entry = homepage_entries.get(clean_title, {})
        detail_title = clean_title
        location = ""
        pincode = ""
        value = ""
        category = ""
        tender_id = ""

        try:
            detail_resp = session.get(link, timeout=30)
            if detail_resp.status_code == 200 and "Stale Session" not in detail_resp.text:
                dsoup = BeautifulSoup(detail_resp.text, "html.parser")
                dtext = dsoup.get_text("\n", strip=True)

                wd_match = re.search(r"Work Description\s*\n(.+)", dtext)
                if wd_match:
                    detail_title = wd_match.group(1).strip()

                # Location and Pincode appear together in the Work Item
                # Details section — match Pincode that immediately follows
                # Location to avoid grabbing an unrelated pincode elsewhere
                loc_pin_match = re.search(
                    r"Location\s*\n(.+)\s*\nPincode\s*\n(\d+)", dtext
                )
                if loc_pin_match:
                    location = loc_pin_match.group(1).strip()
                    pincode = loc_pin_match.group(2).strip()
                else:
                    loc_match = re.search(r"Location\s*\n(.+)", dtext)
                    if loc_match:
                        location = loc_match.group(1).strip()

                value_match = re.search(r"Tender Value in ₹\s*\n([\d,]+)", dtext)
                if value_match:
                    value = value_match.group(1).strip()

                category_match = re.search(r"Product Category\s*\n(.+)", dtext)
                if category_match:
                    category = category_match.group(1).strip()

                tid_match = re.search(r"Tender ID\s*\n(\S+)", dtext)
                if tid_match:
                    tender_id = tid_match.group(1).strip()

                print(f"PMGSY: {clean_title} → Location: {location} Pincode: {pincode} Value: {value} Category: {category} TenderID: {tender_id}")

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
            "value": value,
            "category": category,
            "tender_id": tender_id,
        })

    return results


def process_pmgsy(seen_tenders):
    tenders = fetch_pmgsy_tenders()
    if not tenders:
        return False

    updated = False

    for tender in tenders:
        if not in_pmgsy_watchlist(tender["location"]):
            print(f"PMGSY: Skipping {tender['road_code']} — Location: {tender['location']} not in watchlist")
            continue

        unique_ref = f"pmgsy|{tender['road_code']}"
        if unique_ref in seen_tenders:
            continue

        save_to_db(tender["title"], tender["road_code"], tender["closing"], tender["opening"], "pmgsy")

        msg = (
            f"🚨 <b>NEW TENDER</b> · PMGSY Assam\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>{truncate(tender['title'])}</b>\n\n"
            f"📍 <b>Location:</b> {tender['location']}\n"
            + (f"📮 <b>Pincode:</b> {tender['pincode']}\n" if tender['pincode'] else "")
            + (f"💰 <b>Value:</b> ₹{tender['value']}\n" if tender['value'] else "")
            + (f"🏷 <b>Category:</b> {tender['category']}\n" if tender['category'] else "")
            + f"📎 <b>Ref:</b> {tender['ref']}\n"
            f"🛣 <b>Road Code:</b> {tender['road_code']}\n"
            + (f"🆔 <b>Tender ID:</b> {tender['tender_id']}\n" if tender['tender_id'] else "")
            + f"📅 <b>Closing:</b> {tender['closing']}\n\n"
            f"🔗 <a href=\"{PMGSY_URL}\">View on PMGSY Assam</a>"
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
            f"🚨 <b>NEW TENDER</b> · ONGC\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>{truncate(tender['title'])}</b>\n\n"
            f"📍 <b>Location:</b> {tender['location']}\n"
            f"🏷 <b>Category:</b> {tender['category']}\n"
            f"📎 <b>Ref:</b> {tender['ref']}\n"
            f"📅 <b>Uploaded:</b> {tender['upload_date']}\n\n"
            f"🔗 <a href=\"{ONGC_URL}\">View on ONGC</a>"
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

    if process_pmgsy(seen_tenders):
        any_update = True

    if process_ongc(seen_tenders):
        any_update = True

    print(f"\nSaving tenders: {len(seen_tenders)}")

    save_json(TENDER_FILE, seen_tenders)

    save_last_run()
    print("Done")


if __name__ == "__main__":
    main()
