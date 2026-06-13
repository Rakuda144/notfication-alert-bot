
import requests
from bs4 import BeautifulSoup

URL = "https://assamtenders.gov.in/nicgep/app"

html = requests.get(
    URL,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30
).text

soup = BeautifulSoup(html, "html.parser")

tables = soup.find_all("table")

print("TOTAL TABLES:", len(tables))

for tnum, table in enumerate(tables):

    text = table.get_text(" ", strip=True)

    if "Tender Title" in text and "Reference No" in text:

        print("\n==============================")
        print("POSSIBLE TENDER TABLE:", tnum)
        print("==============================")

        rows = table.find_all("tr")

        print("ROW COUNT:", len(rows))

        for i, row in enumerate(rows[:30]):

            cols = [
                c.get_text(" ", strip=True)
                for c in row.find_all(["td", "th"])
            ]

            print(f"\nROW {i}")
            print(cols)

        break
```
