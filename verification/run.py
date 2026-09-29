import requests

TOKEN= "YOUR_BOT_TOKEN_HERE"
CHAT_ID=  "YOUR_CHAT_ID_HERE"

msg="TEST ALERT from IDS"

r=requests.get(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    params={"chat_id": CHAT_ID, "text": msg}
)

print(r.json())