import requests

url = "https://tenders.ongc.co.in/web/tendersweb/home?p_p_id=com_ongc_tender_OngcTenderWebPortlet_INSTANCE_oajq&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view&_com_ongc_tender_OngcTenderWebPortlet_INSTANCE_oajq_javax.portlet.action=tender-currentNIT"

response = requests.get(
    url,
    headers={
        "User-Agent": "Mozilla/5.0"
    },
    timeout=30
)

print("Status:", response.status_code)
print("Length:", len(response.text))
print(response.text[:500])
