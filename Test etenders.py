import requests
from bs4 import BeautifulSoup
import re

URL = "https://etenders.gov.in/eprocure/app"

print("Fetching etenders...")
resp = requests.get(
    URL,
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    timeout=60
)
print(f"Status: {resp.status_code}")

soup = BeautifulSoup(resp.text, "html.parser")
text = soup.get_text("\n", strip=True)

# Extract tender section
lines = [l.strip() for l in text.splitlines() if l.strip()]

print("\n=== ALL TENDER TITLES ===")
in_tenders = False
count = 0
for i, line in enumerate(lines):
    if "Latest Tenders" in line and "Corrigendum" not in line:
        in_tenders = True
    if in_tenders and "Latest Tenders updates every 15 mins" in line:
        break
    if in_tenders and re.match(r'^\d+\.', line):
        print(f"{line[:100]}")
        count += 1

print(f"\nTotal tenders found: {count}")

# Show closing dates to confirm freshness
print("\n=== CLOSING DATES ===")
date_pattern = re.compile(r'\d{2}-\w{3}-\d{4}')
dates_found = date_pattern.findall(text[:5000])
for d in set(dates_found):
    print(d)
