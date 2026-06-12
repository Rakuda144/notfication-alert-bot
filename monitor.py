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

text = soup.get_text("\n")

for line in text.split("\n"):
    line = line.strip()

    if len(line) > 20:
        if "corrig" in line.lower():
            print(line)
