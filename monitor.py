import requests
from bs4 import BeautifulSoup

url = "https://assamtenders.gov.in/nicgep/app"

r = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30
)

print("Status:", r.status_code)

soup = BeautifulSoup(r.text, "html.parser")

# Print all links on the page
for a in soup.find_all("a"):
    text = a.get_text(" ", strip=True)

    if len(text) > 5:
        print(text)
