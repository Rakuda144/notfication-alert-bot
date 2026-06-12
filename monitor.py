import requests

url = "https://tenders.ongc.co.in/web/tendersweb/home?p_p_id=com_ongc_tender_OngcTenderWebPortlet_INSTANCE_oajq&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view&_com_ongc_tender_OngcTenderWebPortlet_INSTANCE_oajq_javax.portlet.action=tender-currentNIT"

r = requests.get(
    url,
    headers={
        "User-Agent": "Mozilla/5.0"
    }
)

print("Status:", r.status_code)

with open("response.html", "w", encoding="utf-8") as f:
    f.write(r.text)

print(r.text[:2000])
