import requests

URL = "https://assamtenders.gov.in/nicgep/app"

print("BOT STARTED")

try:
    response = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30
    )

    print("HTTP STATUS:", response.status_code)
    print("PAGE LENGTH:", len(response.text))

except Exception as e:
    print("ERROR:", e)
