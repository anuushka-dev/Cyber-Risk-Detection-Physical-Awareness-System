# alerts/notifier_telegram.py

import os
import requests


def send_telegram_notification(event):

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Telegram not configured")
        return False

    label = (
        event.get("attack_type")
        or event.get("label")
        or "ATTACK"
    )

    severity = (
        event.get("severity")
        or "unknown"
    )

    src_ip = event.get("src_ip") or "unknown"
    dst_ip = event.get("dst_ip") or "unknown"


    confidence = float(
        event.get("confidence")
        or event.get("score")
        or 0.0
    )

    meta = event.get("metadata", {}) or {}

    people = int(meta.get("people_detected", 0))

    motion = float(meta.get("motion_score", 0.0))


    message = f"""
🚨 IDS ALERT

Attack: {label}

Severity: {severity}

Source IP: {src_ip}

Destination IP: {dst_ip}

Confidence: {confidence:.3f}

People detected: {people}

Motion score: {motion:.2f}
"""


    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"


    payload = {

        "chat_id": chat_id,

        "text": message

    }


    try:

        r = requests.post(url, json=payload, timeout=5)

        print("telegram sent:", r.status_code)

        return True

    except Exception as e:

        print("telegram error:", e)

        return False