import requests
from bs4 import BeautifulSoup

URL = "https://etenders.gov.in/eprocure/app"

print("Fetching etenders...")
for attempt in range(3):
    try:
        print(f"Attempt {attempt + 1}/3...")
        resp = requests.get(
            URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=90
        )
        print(f"Status: {resp.status_code}")
        break
    except Exception as e:
        print(f"Failed: {e}")
        if attempt == 2:
            print("All attempts failed")
            exit(1)

soup = BeautifulSoup(resp.text, "html.parser")
text = soup.get_text("\n", strip=True)
lines = [l.strip() for l in text.splitlines() if l.strip()]

# Find Tender Title marker and show 60 lines after it
print("\n=== LINES AROUND TENDER TITLE ===")
for i, line in enumerate(lines):
    if "Tender Title" in line:
        for j in range(i, min(i + 60, len(lines))):
            print(f"{j}: {lines[j][:120]}")
        break

# Also check if "Bid Opening Date" exists
print("\n=== BID OPENING DATE CHECK ===")
if "Bid Opening Date" in text:
    print("Found 'Bid Opening Date' ✅")
else:
    print("'Bid Opening Date' NOT found ❌")

# Show what markers exist
print("\n=== KEY MARKERS FOUND ===")
for marker in ["Tender Title", "Bid Opening Date", "Latest Tenders updates", "Reference No", "Closing Date"]:
    print(f"'{marker}': {'✅' if marker in text else '❌'}")
