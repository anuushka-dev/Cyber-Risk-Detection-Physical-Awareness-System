AI Intrusion Detection System with Human Context Awareness

Setup Instructions
1. Clone or unzip project

Navigate to project folder:

cd Cyber_Risk_Detection_System

2. Create virtual environment

Windows:

python -m venv venv
venv\Scripts\activate

Mac/Linux:

python3 -m venv venv
source venv/bin/activate

3. Install dependencies
pip install -r requirements.txt

4. Configure Telegram Alerts (optional)

Create file:

.env

Example:

TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_COOLDOWN_SECONDS=120

If Telegram not needed, leave file empty.

5. Run Backend API

python -m uvicorn api.app:app --reload


6. Run Frontend Dashboard


Navigate to frontend folder:

cd frontend
npm install
npm run dev

7. Run RealTime Monitoring

python -m monitoring.realtime_monitor

Requirements

Python 3.9 – 3.11 recommended.

Webcam required for human detection module.


# Telegram Alerts Setup 

### Step 1 — Create Bot

1. Open Telegram
2. Search **BotFather**
3. Send:

```
/start
```

4. Send:

```
/newbot
```

5. Enter bot name (example):

```
AI IDS Alerts
```

6. Enter username (must end with `bot`):

```
ainids_alerts_bot
```

7. Copy the **BOT TOKEN** provided.

---

### Step 2 — Get Chat ID

1. Open your bot in Telegram
2. Click **Start**
3. Send message:

```
hello
```

4. Open browser:

```
https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
```

Example:

```
https://api.telegram.org/bot123456:ABC/getUpdates
```

5. Copy the number:

```
"chat":{"id":5279301197}
```

That number is your **CHAT ID**.

---

### Step 3 — Create .env file

In project root create file:

```
.env
```

Add:

```
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_COOLDOWN_SECONDS=120
```

Example:

```
TELEGRAM_BOT_TOKEN=123456:ABCxyz
TELEGRAM_CHAT_ID=5279301197
TELEGRAM_COOLDOWN_SECONDS=120
```

---

### Step 4 — Run system

```
python -m uvicorn api.app:app --reload
```

Telegram will send alerts automatically when:

• attack detected
• severity ≥ MEDIUM
• more than 2 people detected

---

Done ✅
