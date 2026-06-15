import requests

TOKEN= "***REMOVED***"
CHAT_ID=  "5279301197"

msg="TEST ALERT from IDS"

r=requests.get(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    params={"chat_id": CHAT_ID, "text": msg}
)

print(r.json())