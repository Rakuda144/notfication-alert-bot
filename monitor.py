import requests

url = "https://assamtenders.gov.in/nicgep/app"

r = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30
)

print("Status:", r.status_code)

keywords = [
    "Sivasagar",
    "Jorhat",
    "Charaideo",
    "Nazira",
    "Sonari",
    "Amguri",
    "Demow"
]

for keyword in keywords:
    if keyword.lower() in r.text.lower():
        print("FOUND:", keyword)
