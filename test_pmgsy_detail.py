import requests
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
})

print("Fetching homepage...")
resp = session.get(
    "https://pmgsytendersasm.gov.in/nicgep/app?page=Home&service=page",
    timeout=60
)
print(f"Status: {resp.status_code}")

soup = BeautifulSoup(resp.text, "html.parser")

links = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    text = a.text.strip()
    if "component=%24DirectLink&" in href and "DirectLink_" not in href and text:
        full_url = href if href.startswith("http") else "https://pmgsytendersasm.gov.in" + href
        links.append((text, full_url))

print(f"Tender links found: {len(links)}")

# Open ALL detail pages and print full content
for i, (title, link) in enumerate(links):
    print(f"\n{'='*60}")
    print(f"TENDER {i+1}: {title}")
    print(f"{'='*60}")
    
    detail = session.get(link, timeout=30)
    print(f"Status: {detail.status_code}")
    
    if "Stale Session" in detail.text:
        print("STALE SESSION!")
        continue
    
    dsoup = BeautifulSoup(detail.text, "html.parser")
    full_text = dsoup.get_text("\n", strip=True)
    
    # Print everything
    print(full_text[:8000])
