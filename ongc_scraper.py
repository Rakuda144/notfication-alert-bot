import re
import requests
from bs4 import BeautifulSoup

ONGC_URL = "https://tenders.ongc.co.in/web/tendersweb"

ONGC_WATCHLIST = [
    "Sivasagar", "Jorhat", "Nazira", "Moran", "Duliajan",
    "Tinsukia", "Dibrugarh", "Golaghat", "Charaideo",
    "Sonari", "Lakwa", "Assam", "Geleki", "Naharkatia",
    "Sibsagar", "Amguri"
]


def in_ongc_watchlist(location):
    return any(place.lower() in location.lower() for place in ONGC_WATCHLIST)


def fetch_ongc_tenders():
    print("\n--- Processing ONGC ---")
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

    # Structure from page:
    # Line 0: Tender ID  e.g. "D16AC26010"
    # Line 1: "Uploaded on 2026-06-24 05:00 PM"
    # Line 2: Title e.g. "Two year Annual Rate Contract..."
    # Line 3: "[Location] [Category]"

    tender_id_pattern = re.compile(r'^[A-Z0-9]{3,}[0-9]{2,}', re.IGNORECASE)
    uploaded_pattern = re.compile(r'^Uploaded on (\d{4}-\d{2}-\d{2})')

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check if this line looks like a tender ID
        if tender_id_pattern.match(line) and i + 3 < len(lines):
            next_line = lines[i + 1]
            uploaded_match = uploaded_pattern.match(next_line)

            if uploaded_match:
                tender_id = line.strip()
                upload_date = uploaded_match.group(1)
                title = lines[i + 2] if i + 2 < len(lines) else ""
                meta = lines[i + 3] if i + 3 < len(lines) else ""

                # Extract location and category from "[Location] [Category]"
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
                        "closing": "",
                    })
                i += 4
                continue

        i += 1

    print(f"ONGC: Found {len(results)} watchlist tenders")
    return results


if __name__ == "__main__":
    tenders = fetch_ongc_tenders()
    print(f"\nTotal ONGC watchlist tenders: {len(tenders)}")
    for t in tenders:
        print(f"\nID: {t['tender_id']}")
        print(f"Title: {t['title']}")
        print(f"Location: {t['location']}")
        print(f"Category: {t['category']}")
        print(f"Uploaded: {t['upload_date']}")
