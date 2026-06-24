import re
import requests
from bs4 import BeautifulSoup

PMGSY_URL = "https://pmgsytendersasm.gov.in/nicgep/app?page=Home&service=page"


def fetch_pmgsy_tenders():
    """
    Fetch PMGSY tenders using session cookies to access detail pages.
    Returns list of dicts with title, ref, closing, opening, detail_title
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })

    # Step 1: fetch homepage to establish session
    print("PMGSY: Fetching homepage...")
    try:
        resp = session.get(PMGSY_URL, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"PMGSY: Homepage fetch failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Step 2: extract tender rows and their detail links
    # Links look like: href="...component=$DirectLink&...&sp=XXXXX"
    # Exclude DirectLink_0 (corrigendum), DirectLink_3 (STQC logo)
    tender_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.text.strip()
        if (
            "component=%24DirectLink&" in href
            and "DirectLink_" not in href
            and text
        ):
            # Make absolute URL
            if href.startswith("http"):
                full_url = href
            else:
                full_url = "https://pmgsytendersasm.gov.in" + href
            tender_links.append((text, full_url))

    print(f"PMGSY: Found {len(tender_links)} tender links")

    # Step 3: parse homepage table for ref/closing/opening
    # Table columns: Title | Ref No | Closing Date | Opening Date
    text_lines = [
        l.strip()
        for l in soup.get_text("\n", strip=True).splitlines()
        if l.strip()
    ]

    # Build basic entries from homepage
    homepage_entries = {}
    try:
        idx = text_lines.index("Bid Opening Date") + 1
        data = text_lines[idx:]
        for i in range(0, len(data), 4):
            chunk = data[i:i+4]
            if len(chunk) < 4:
                continue
            title, ref, closing, opening = chunk
            # Strip leading number
            clean_title = re.sub(r'^\d+\.\s*', '', title).strip()
            homepage_entries[clean_title] = {
                "ref": ref,
                "closing": closing,
                "opening": opening,
            }
    except ValueError:
        pass

    # Step 4: for each tender, fetch detail page using same session
    results = []
    for raw_title, link in tender_links:
        clean_title = re.sub(r'^\d+\.\s*', '', raw_title).strip()
        entry = homepage_entries.get(clean_title, {})

        print(f"PMGSY: Fetching details for {clean_title}...")
        detail_title = clean_title  # fallback to road code

        try:
            detail_resp = session.get(link, timeout=30)
            if detail_resp.status_code == 200:
                dsoup = BeautifulSoup(detail_resp.text, "html.parser")
                dtext = dsoup.get_text("\n", strip=True)

                # Look for work name/description fields
                # NIC detail pages usually have patterns like:
                # "Work Description" or "Name of Work" followed by actual text
                work_patterns = [
                    r"Work Description\s*\n(.+)",
                    r"Name of Work\s*\n(.+)",
                    r"Work Name\s*\n(.+)",
                    r"Description of Work\s*\n(.+)",
                    r"Package Name\s*\n(.+)",
                ]

                for pattern in work_patterns:
                    match = re.search(pattern, dtext)
                    if match:
                        detail_title = match.group(1).strip()
                        print(f"PMGSY: Got detail title: {detail_title[:60]}")
                        break

                # If no pattern matched, try finding text near the road code
                if detail_title == clean_title:
                    lines = [l for l in dtext.splitlines() if l.strip()]
                    for i, line in enumerate(lines):
                        if clean_title in line and i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if len(next_line) > 10 and next_line != entry.get("ref", ""):
                                detail_title = next_line
                                print(f"PMGSY: Got nearby title: {detail_title[:60]}")
                                break

            elif "Stale Session" in detail_resp.text:
                print(f"PMGSY: Stale session for {clean_title} — using road code")

        except requests.RequestException as e:
            print(f"PMGSY: Detail fetch failed for {clean_title}: {e}")

        results.append({
            "title": detail_title,
            "road_code": clean_title,
            "ref": entry.get("ref", ""),
            "closing": entry.get("closing", ""),
            "opening": entry.get("opening", ""),
        })

    return results


if __name__ == "__main__":
    tenders = fetch_pmgsy_tenders()
    print(f"\nTotal PMGSY tenders: {len(tenders)}")
    for t in tenders:
        print(f"\nRoad Code: {t['road_code']}")
        print(f"Title: {t['title']}")
        print(f"Ref: {t['ref']}")
        print(f"Closing: {t['closing']}")
