import requests

url = "https://assamtenders.gov.in/nicgep/app"

r = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30
)

print("Status:", r.status_code)
print("Length:", len(r.text))
print(r.text[:1000])
