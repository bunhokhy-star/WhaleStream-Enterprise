# WHALE-STREAM Cloud Migration Guide
# Windows PC → DigitalOcean VPS

**Why we're doing this:** Windows Task Scheduler crashes, encoding bugs, and
PC-must-be-on requirements cause daily failures. Moving to a Linux VPS on
DigitalOcean gives us a stable, 24/7 server that runs exactly the same code
without those problems. Cost: ~$6/month.

**Time needed:** About 1–2 hours total. I'll do most of it with you.

---

## BEFORE YOU START — What You Need

1. A credit card (for DigitalOcean — $6/month)
2. Your GitHub repo URL (where the code is pushed)
3. Your `google_credentials.json` file (already in C:\Users\MAX\WhaleStream\)
4. All your API keys (Anthropic, Telegram, Bybit) — already in `local_config.py`

---

## STEP 1: Create Your Server on DigitalOcean

**1.1 — Sign up**
- Go to: https://www.digitalocean.com
- Click "Sign Up" → use your email
- They'll ask for a credit card (you get $200 free credit for 60 days as a new user)

**1.2 — Create a Droplet (this is their word for "server")**
- Click the green **"Create"** button at the top → "Droplets"
- Choose these settings:

| Setting | Choose |
|---------|--------|
| Region | Singapore (closest to Bangkok) |
| OS | Ubuntu 22.04 LTS |
| Plan | Basic → Regular → **$6/month** (1 GB RAM, 1 CPU) |
| Authentication | Password (easier for beginners) |
| Password | Create a strong password — SAVE IT |
| Hostname | whalestream |

- Click **"Create Droplet"**
- Wait ~30 seconds — you'll see an IP address appear (looks like `134.122.xx.xx`)
- **Copy that IP address** — you'll need it for everything

---

## STEP 2: Connect to Your Server

Open **PowerShell** on your Windows PC (search "PowerShell" in Start menu).

Type this (replace `134.122.xx.xx` with your real IP):
```
ssh root@134.122.xx.xx
```

- It will say "Are you sure you want to continue? (yes/no)" → type `yes`
- It will ask for your password → type the password you created in Step 1.2
- You're now INSIDE the server. You'll see: `root@whalestream:~#`

> **Tip:** If you close PowerShell, just open it again and type the same `ssh` command to reconnect.

---

## STEP 3: Run the Setup Script

The setup script installs Python, clones your code, and configures everything.
But first, we need to update it with your GitHub repo URL.

**3.1 — Find your GitHub repo URL**
- Go to https://github.com and find your WhaleStream repo
- Click the green "Code" button → copy the HTTPS URL
- It looks like: `https://github.com/yourusername/WhaleStream.git`

**3.2 — Download and edit the setup script on the server**

In your SSH window (PowerShell connected to server), type:
```bash
curl -o setup.sh https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/setup_server.sh
```

Or simpler — copy the script content manually:
```bash
nano setup_server.sh
```
This opens a text editor. Paste the contents of `setup_server.sh` from your WhaleStream folder.
- Change `YOUR_GITHUB_USERNAME/YOUR_REPO_NAME` on line 8 to your real GitHub URL
- Press `Ctrl+X` → `Y` → `Enter` to save

**3.3 — Run it**
```bash
bash setup_server.sh
```

This takes about 2–3 minutes. You'll see progress messages. Wait until it says "Setup complete!"

---

## STEP 4: Upload google_credentials.json

This file lets the system access Google Sheets. You need to upload it from your PC to the server.

Open a **NEW PowerShell window** on your PC (keep the SSH one open too). Type:
```powershell
scp "C:\Users\MAX\WhaleStream\google_credentials.json" root@134.122.xx.xx:/opt/whalestream/
```

Replace `134.122.xx.xx` with your server IP. It will ask for your password again.

You should see: `google_credentials.json   100%  ...`  ← means it worked.

---

## STEP 5: Create local_config.py on the Server

This file holds all your secret API keys. We create it directly ON the server (never in GitHub).

In your SSH window, type:
```bash
nano /opt/whalestream/local_config.py
```

This opens the text editor. Type or paste your keys (look at C:\Users\MAX\WhaleStream\local_config.py on your PC for the values):

```python
# WHALE-STREAM Server Config — NEVER commit this file
ANTHROPIC_API_KEY    = "sk-ant-api03-YOUR-KEY-HERE"
TELEGRAM_BOT_TOKEN   = "YOUR-BOT-TOKEN"
TELEGRAM_CHAT_ID     = "YOUR-CHAT-ID"
TELEGRAM_OPS_CHAT_ID = "YOUR-OPS-CHAT-ID"  # if different
BYBIT_API_KEY        = "YOUR-BYBIT-KEY"
BYBIT_API_SECRET     = "YOUR-BYBIT-SECRET"
BYBIT_BASE_URL       = "https://api-demo.bybit.com"  # change to api.bybit.com for live
GOOGLE_CREDS_FILE    = "/opt/whalestream/google_credentials.json"
GOOGLE_SHEET_NAME    = "YOUR-SHEET-NAME"
BYBIT_START_BALANCE  = 500.0
```

Press `Ctrl+X` → `Y` → `Enter` to save.

> **Security:** This file stays only on the server, same as it stays only on your PC now.

---

## STEP 6: Test the System Manually

Before setting up the schedule, test each agent once to confirm everything connects.

In your SSH window:
```bash
cd /opt/whalestream

# Test 1: Strategist (fastest test — no API calls)
python3.11 whale_stream_strategist.py
```

You should see the banner:
```
╔══════════════════════════════════════╗
║   🧠  WHALE-STREAM STRATEGIST v47.14 ║
╚══════════════════════════════════════╝
```

If you see errors, check:
- `cat /opt/whalestream/local_config.py` — make sure keys are correct
- `ls /opt/whalestream/google_credentials.json` — make sure it uploaded

```bash
# Test 2: Bot (calls Claude API — takes ~30 seconds)
python3.11 whale_stream_bot.py

# Test 3: Trader (connects to Bybit — takes ~10 seconds)
python3.11 whale_stream_trader.py
```

If all 3 work without errors, you're ready for Step 7.

---

## STEP 7: Set Up Cron (Replaces Task Scheduler)

Cron is Linux's built-in scheduler. Much more reliable than Windows Task Scheduler.

In your SSH window:
```bash
crontab /opt/whalestream/whale_crontab.txt
```

Verify it installed:
```bash
crontab -l
```

You should see the schedule printed out. That's it — cron starts immediately.

The schedule runs in Bangkok time (server timezone is already set to Bangkok by the setup script):
- Bot:        00:00, 04:00, 08:00, 12:00, 16:00, 20:00 BKK
- Strategist: 00:10, 04:10, 08:10, 12:10, 16:10, 20:10 BKK
- Trader:     00:20, 04:20, 08:20, 12:20, 16:20, 20:20 BKK
- Watchdog:   00:30, 04:30, 08:30, 12:30, 16:30, 20:30 BKK
- Tracker:    Every 30 minutes
- Monitor:    Every 2 minutes
- Briefing:   07:00 BKK daily

---

## STEP 8: Start the Status Server

The Status Server needs to run continuously. Start it now:
```bash
cd /opt/whalestream
nohup python3.11 status_server.py >> logs/status_server.log 2>&1 &
echo "Status server started"
```

It will also auto-start at reboot (the crontab `@reboot` line handles this).

---

## STEP 9: Verify the First Cycle

Wait for the next :00 BKK time (or trigger manually to test):
```bash
# Manually trigger a full cycle right now:
cd /opt/whalestream
python3.11 whale_stream_bot.py && sleep 5 && python3.11 whale_stream_strategist.py
```

Watch your Telegram — you should get the bot signal alert and strategist summary.

Check the log files:
```bash
tail -50 /opt/whalestream/logs/bot.log
tail -50 /opt/whalestream/logs/strategist.log
```

---

## STEP 10: Stop the Windows Task Scheduler

Once the server is running cleanly for 24 hours, disable the Windows tasks:
- Open Task Scheduler on your PC
- Disable (don't delete): WS-Bot, WS-Strategist, WS-Trader, WS-Watchdog, WS-Tracker, WS-Monitor
- Keep them disabled as backup in case the server goes down

Your PC no longer needs to be on for the system to run.

---

## DAY-TO-DAY: How to Monitor and Fix Things

**Check if system is running:**
```bash
ssh root@134.122.xx.xx
tail -20 /opt/whalestream/logs/strategist.log
```

**View today's status:**
```bash
cat /opt/whalestream/daily_status.json
```

**Clear circuit breaker:**
```bash
rm -f /opt/whalestream/paused.flag
```

**Update code from GitHub:**
```bash
cd /opt/whalestream && git pull
```

**Restart after a code update:**
Cron picks up changes automatically — no restart needed for scheduled agents.
For the status server:
```bash
pkill -f status_server.py
nohup python3.11 status_server.py >> logs/status_server.log 2>&1 &
```

**View live logs (streaming):**
```bash
tail -f /opt/whalestream/logs/bot.log
```
Press `Ctrl+C` to stop.

---

## PROBLEMS? Common Fixes

| Problem | Fix |
|---------|-----|
| `Permission denied` when SSH | Make sure you type `yes` first time, correct password |
| `ModuleNotFoundError` | Run: `pip install -r requirements.txt` |
| `google_credentials.json not found` | Redo Step 4 |
| Telegram not sending | Check TELEGRAM_BOT_TOKEN in local_config.py |
| Bybit API error | Check BYBIT_API_KEY / BYBIT_API_SECRET in local_config.py |
| Cron not running | Run `crontab -l` to verify, check `grep CRON /var/log/syslog` |
| Server went offline | DigitalOcean panel → Droplets → Power On |

---

## COST SUMMARY

| Item | Cost |
|------|------|
| DigitalOcean Droplet (1GB/1CPU) | $6/month |
| Data transfer | Included (1TB/month — we use ~1GB) |
| **Total** | **$6/month (~200 THB)** |

New accounts get $200 free credit (enough for ~33 months free).

---

## GO-LIVE SWITCH (When Ready)

When switching from Demo to Live Bybit, only change ONE line in `local_config.py` on the server:
```bash
nano /opt/whalestream/local_config.py
```
Change:
```python
BYBIT_BASE_URL = "https://api-demo.bybit.com"   # ← before
BYBIT_BASE_URL = "https://api.bybit.com"         # ← after go-live
```
Also update `BYBIT_API_KEY` and `BYBIT_API_SECRET` to your live keys.
That's it — no code changes needed.
