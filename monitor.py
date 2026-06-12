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

    if len(line) > 30:
        if any(
            x.lower() in line.lower()
            for x in [
                "jorhat",
                "sivasagar",
                "charaideo",
                "nazira",
                "sonari",
                "amguri",
                "demow",
                "lakwa"
            ]
        ):
            print(line)
