import requests
from bs4 import BeautifulSoup

URL = "https://assamtenders.gov.in/nicgep/app"

print("===== BOT STARTED =====")

try:
    response = requests.get(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
        timeout=30
    )

    print("HTTP STATUS:", response.status_code)

    print("\n===== FIRST 1000 HTML CHARS =====")
    print(response.text[:1000])

    soup = BeautifulSoup(response.text, "html.parser")

    print("\n===== PAGE TITLE =====")
    print(soup.title)

    tables = soup.find_all("table")

    print(f"\n===== TABLE COUNT: {len(tables)} =====")

    for i, table in enumerate(tables[:10]):
        text = table.get_text(" ", strip=True)

        print(f"\n----- TABLE {i} -----")
        print(text[:1000])

except Exception as e:
    print("ERROR:", e)

print("\n===== SCRIPT FINISHED =====")
