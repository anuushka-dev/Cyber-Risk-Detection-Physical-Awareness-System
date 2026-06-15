import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TOKEN or not CHAT_ID:
    print("FAIL  TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
    raise SystemExit(2)

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = {
    "chat_id": CHAT_ID,
    "text": "IDS TEST: Telegram path is working."
}

try:
    r = requests.post(url, json=payload, timeout=10)
    print(r.status_code)
    print(r.text)
    data = r.json()
    print("\nRESULT:", "PASS" if data.get("ok") else "FAIL")
except Exception as e:
    print("FAIL")
    print(e)
    raise SystemExit(2)