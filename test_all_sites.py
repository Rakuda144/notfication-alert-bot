import requests
import re
from bs4 import BeautifulSoup

WATCHLIST = [
    "Jorhat", "Sivasagar", "Charaideo", "Nazira",
    "Sonari", "Amguri", "Demow", "Lakwa",
    "Simaluguri", "Moran", "Duliajan", "Tinsukia",
    "Dibrugarh", "Golaghat", "Mariani", "Bhojo",
    "Assam"
]

ONGC_WATCHLIST = [
    "Sivasagar", "Jorhat", "Nazira", "Moran", "Duliajan",
    "Tinsukia", "Dibrugarh", "Golaghat", "Charaideo",
    "Sonari", "Lakwa", "Assam", "Geleki", "Naharkatia",
    "Sibsagar", "Amguri"
]

PMGSY_WATCHLIST = [
    "Sivasagar", "Charaideo", "Moran", "Sonari", "Sepon",
    "Nazira", "Jorhat", "Golaghat", "Dibrugarh", "Tinsukia",
    "Duliajan", "Lakwa", "Amguri", "Demow", "Simaluguri",
    "Mariani", "Sibsagar"
]

def in_list(title, lst):
    return any(p.lower() in title.lower() for p in lst)

def strip_number(title):
    return re.sub(r'^\d+\.\s*', '', title).strip()

def fetch_nic(url, name):
    print(f"\n{'='*50}")
    print(f"SITE: {name}")
    print(f"{'='*50}")
    for attempt in range(3):
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=90)
            resp.raise_for_status()
            break
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            if attempt == 2:
                print("All attempts failed!")
                return
    
    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    
    # Find tenders
    try:
        idx = lines.index("Bid Opening Date") + 1
    except ValueError:
        print("Could not find Bid Opening Date marker!")
        return
    
    data = lines[idx:]
    matches = []
    all_tenders = []
    
    for i in range(0, len(data), 4):
        chunk = data[i:i+4]
        if len(chunk) < 4:
            continue
        title = strip_number(chunk[0])
        ref = chunk[1]
        closing = chunk[2]
        all_tenders.append(title)
        if in_list(title, WATCHLIST):
            matches.append((title, ref, closing))
    
    print(f"Total tenders found: {len(all_tenders)}")
    print(f"\nAll tenders:")
    for t in all_tenders:
        print(f"  {'✅' if in_list(t, WATCHLIST) else '❌'} {t[:80]}")
    
    if matches:
        print(f"\n🎯 WATCHLIST MATCHES ({len(matches)}):")
        for title, ref, closing in matches:
            print(f"  ✅ {title}")
            print(f"     Ref: {ref}")
            print(f"     Closing: {closing}")
    else:
        print(f"\n❌ No watchlist matches")


def fetch_ongc():
    print(f"\n{'='*50}")
    print(f"SITE: ONGC")
    print(f"{'='*50}")
    for attempt in range(3):
        try:
            resp = requests.get(
                "https://tenders.ongc.co.in/web/tendersweb",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=90
            )
            resp.raise_for_status()
            break
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            if attempt == 2:
                print("All attempts failed!")
                return

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    tender_id_pattern = re.compile(r'^[A-Z0-9]{3,}[0-9]{2,}', re.IGNORECASE)
    uploaded_pattern = re.compile(r'^Uploaded on (\d{4}-\d{2}-\d{2})')

    matches = []
    all_tenders = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if tender_id_pattern.match(line) and i + 3 < len(lines):
            next_line = lines[i + 1]
            uploaded_match = uploaded_pattern.match(next_line)
            if uploaded_match:
                tender_id = line.strip()
                title = lines[i + 2]
                meta = lines[i + 3]
                loc_match = re.findall(r'\[([^\]]+)\]', meta)
                location = loc_match[0] if loc_match else ""
                all_tenders.append((tender_id, title, location))
                if in_list(location, ONGC_WATCHLIST):
                    matches.append((tender_id, title, location))
                i += 4
                continue
        i += 1

    print(f"Total tenders found: {len(all_tenders)}")
    print(f"\nAll tenders:")
    for tid, title, loc in all_tenders:
        print(f"  {'✅' if in_list(loc, ONGC_WATCHLIST) else '❌'} [{loc}] {title[:60]}")

    if matches:
        print(f"\n🎯 WATCHLIST MATCHES ({len(matches)}):")
        for tid, title, loc in matches:
            print(f"  ✅ {tid} [{loc}] {title[:60]}")
    else:
        print(f"\n❌ No watchlist matches")


def fetch_pmgsy():
    print(f"\n{'='*50}")
    print(f"SITE: PMGSY Assam")
    print(f"{'='*50}")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    for attempt in range(3):
        try:
            resp = session.get(
                "https://pmgsytendersasm.gov.in/nicgep/app?page=Home&service=page",
                timeout=60
            )
            resp.raise_for_status()
            break
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            if attempt == 2:
                print("All attempts failed!")
                return

    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.text.strip()
        if "component=%24DirectLink&" in href and "DirectLink_" not in href and text:
            full_url = href if href.startswith("http") else "https://pmgsytendersasm.gov.in" + href
            links.append((text, full_url))

    print(f"Total tenders found: {len(links)}")
    matches = []

    for raw_title, link in links:
        clean = re.sub(r'^\d+\.\s*', '', raw_title).strip()
        try:
            detail = session.get(link, timeout=30)
            dtext = BeautifulSoup(detail.text, "html.parser").get_text("\n", strip=True)
            loc_match = re.search(r"Location\s*\n(.+)", dtext)
            location = loc_match.group(1).strip() if loc_match else ""
            wd_match = re.search(r"Work Description\s*\n(.+)", dtext)
            work_desc = wd_match.group(1).strip() if wd_match else clean
        except:
            location = ""
            work_desc = clean

        is_match = in_list(location, PMGSY_WATCHLIST)
        print(f"  {'✅' if is_match else '❌'} {clean} → [{location}] {work_desc[:50]}")
        if is_match:
            matches.append((clean, location, work_desc))

    if matches:
        print(f"\n🎯 WATCHLIST MATCHES ({len(matches)}):")
        for code, loc, desc in matches:
            print(f"  ✅ {code} [{loc}] {desc[:60]}")
    else:
        print(f"\n❌ No watchlist matches")


# Run all checks
fetch_nic("https://assamtenders.gov.in/nicgep/app", "Assamtenders")
fetch_nic("https://etenders.gov.in/eprocure/app", "Etenders")
fetch_pmgsy()
fetch_ongc()

print(f"\n{'='*50}")
print("SCAN COMPLETE")
print(f"{'='*50}")
