import requests
from bs4 import BeautifulSoup

html = requests.get(
    "https://assamtenders.gov.in/nicgep/app",
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30
).text

soup = BeautifulSoup(html, "html.parser")

text = soup.get_text("\n", strip=True)

start = text.find("Tender Title")

print(text[start:start+8000])
