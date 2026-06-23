# WHALE-STREAM — Demo → Live Switch Runbook
*Version: v46.34 | Prepared: 2026-06-22*
*⚠ READ THIS ENTIRE DOCUMENT BEFORE TOUCHING ANYTHING*

---

## What You Are About To Do

You are switching all three trading scripts (trader, monitor, tracker) from Bybit's
paper-money demo environment to real-money live trading. This means:

- Real USDT will be used for every order
- Losses are permanent
- There is no undo once an order is placed

This document lists every line to change in every file. Do them all in one sitting.
Do not run any scheduler until all changes are complete and verified.

---

## Pre-Flight Checklist (complete ALL before touching any file)

- [ ] All Task Scheduler tasks are STOPPED: whale_stream_trader, whale_stream_tracker, whale_stream_monitor
- [ ] No open positions on the Demo account (log in to bybit.com → Demo → Derivatives → Positions)
- [ ] Real Bybit API keys generated with: **Futures trading ENABLED**, **Withdrawal DISABLED**
      → bybit.com → Account & Security → API Management → Create New Key
      → Permissions: "Contract" read + write; "Unified Trading" read; NO withdrawal
- [ ] Starting capital deposited to Bybit Unified Trading account (suggested: $200–$500 USDT)
- [ ] paused.flag does NOT exist in C:\Users\MAX\WhaleStream\ (if it exists, delete it first)
- [ ] Telegram bot is still receiving messages — send a test message now to confirm
- [ ] You have a plain text editor open ready to paste new key values (do NOT store keys in cloud notes)
- [ ] You have noted your real account balance so you can verify it appears in the log after switch

---

## Exact File Changes Required

### 1. whale_stream_trader.py

**Line 52 — API Key**
```
# BEFORE:
BYBIT_API_KEY    = "uJbW2tKiexXXDhoucb"

# AFTER:
BYBIT_API_KEY    = "YOUR_REAL_LIVE_KEY_HERE"
```

**Line 53 — API Secret**
```
# BEFORE:
BYBIT_API_SECRET = "c8ce3oTWMvGW7incCe3ECsMJf7BnMZaCMpqP"

# AFTER:
BYBIT_API_SECRET = "YOUR_REAL_LIVE_SECRET_HERE"
```

**Line 65 — Base URL**
```
# BEFORE:
BYBIT_BASE_URL   = "https://api-demo.bybit.com"

# AFTER:
BYBIT_BASE_URL   = "https://api.bybit.com"
```

**Line 246 — Demo Trading Header (inside bybit_request function)**
```
# BEFORE:
        "X-BAPI-DEMO-TRADING":  "1",        # ← demo account flag

# AFTER: (delete the entire line — do not leave it as "0", delete it completely)
        # X-BAPI-DEMO-TRADING header removed — LIVE TRADING
```
The header must be REMOVED, not set to "0". Bybit's live API ignores the header when
absent, but leaving it set to "1" on the live URL will cause authentication errors.

**Line 56 — TRADE_MARGIN_USDT (STRONGLY RECOMMENDED CHANGE)**
```
# BEFORE:
TRADE_MARGIN_USDT = 20      # USDT margin per trade ($20)

# AFTER (strongly recommended for first month on live):
TRADE_MARGIN_USDT = 5       # USDT margin per trade ($5) — live cautious start
```
At 10x leverage, $5 margin = $50 position. At $20 margin = $200 position on real money.
Start at $5 for at least the first month. You can increase it after confirming the system
works correctly on live. The leverage line (line 57, LEVERAGE = 10) can stay as-is.

**Line 93 — BYBIT_START_BALANCE (update to match your real deposit)**
```
# BEFORE:
BYBIT_START_BALANCE = 500.00   # initial demo deposit

# AFTER (set to whatever you actually deposited):
BYBIT_START_BALANCE = 300.00   # initial live deposit — UPDATE THIS TO YOUR ACTUAL AMOUNT
```
This controls the P&L% display in the dashboard. It does not affect trading.

**Line 8 (banner comment) — update so you know this is live**
```
# BEFORE:
║  Reads latest OPEN signals from Google Sheets and places     ║
║  limit orders on your Bybit DEMO account automatically.      ║

# AFTER:
║  Reads latest OPEN signals from Google Sheets and places     ║
║  limit orders on your Bybit LIVE account automatically.      ║
```
Also update line 4 banner: change "BYBIT DEMO" to "BYBIT LIVE".

---

### 2. whale_stream_monitor.py

**Line 42 — API Key**
```
# BEFORE:
BYBIT_API_KEY    = "uJbW2tKiexXXDhoucb"

# AFTER:
BYBIT_API_KEY    = "YOUR_REAL_LIVE_KEY_HERE"
```
(Same key as trader.py — they share one API key pair.)

**Line 43 — API Secret**
```
# BEFORE:
BYBIT_API_SECRET = "c8ce3oTWMvGW7incCe3ECsMJf7BnMZaCMpqP"

# AFTER:
BYBIT_API_SECRET = "YOUR_REAL_LIVE_SECRET_HERE"
```

**Line 44 — Base URL**
```
# BEFORE:
BYBIT_BASE_URL   = "https://api-demo.bybit.com"

# AFTER:
BYBIT_BASE_URL   = "https://api.bybit.com"
```

**Line 98 — Demo Trading Header (inside bybit_request function)**
```
# BEFORE:
        "X-BAPI-DEMO-TRADING": "1",

# AFTER: (delete the entire line)
        # X-BAPI-DEMO-TRADING header removed — LIVE TRADING
```

---

### 3. whale_stream_tracker.py

**Line 62 — API Key**
```
# BEFORE:
BYBIT_API_KEY    = "uJbW2tKiexXXDhoucb"

# AFTER:
BYBIT_API_KEY    = "YOUR_REAL_LIVE_KEY_HERE"
```

**Line 63 — API Secret**
```
# BEFORE:
BYBIT_API_SECRET = "c8ce3oTWMvGW7incCe3ECsMJf7BnMZaCMpqP"

# AFTER:
BYBIT_API_SECRET = "YOUR_REAL_LIVE_SECRET_HERE"
```

**Line 64 — Base URL**
```
# BEFORE:
BYBIT_BASE_URL   = "https://api-demo.bybit.com"

# AFTER:
BYBIT_BASE_URL   = "https://api.bybit.com"
```

**Line 199 — Demo Trading Header (inside bybit_request_auth function)**
```
# BEFORE:
        "X-BAPI-DEMO-TRADING": "1",

# AFTER: (delete the entire line)
        # X-BAPI-DEMO-TRADING header removed — LIVE TRADING
```

**Line 58 — BYBIT_START_BALANCE (update to match your real deposit)**
```
# BEFORE:
BYBIT_START_BALANCE = 500.00   # initial demo deposit

# AFTER:
BYBIT_START_BALANCE = 300.00   # initial live deposit — UPDATE THIS TO YOUR ACTUAL AMOUNT
```

---

### 4. whale_stream_bot.py

**No Bybit API changes required.** The bot connects only to CoinGecko, Claude API, and
Google Sheets. It has no Bybit connection and no demo headers. The bot does NOT need to
be changed for the live switch.

The bot's Telegram and Google Sheets credentials remain unchanged.

---

## Complete Change Summary (Quick Reference)

| File | Line | Change |
|------|------|--------|
| trader.py | 4 | Banner: "BYBIT DEMO" → "BYBIT LIVE" |
| trader.py | 52 | BYBIT_API_KEY → real live key |
| trader.py | 53 | BYBIT_API_SECRET → real live secret |
| trader.py | 56 | TRADE_MARGIN_USDT = 20 → 5 (recommended) |
| trader.py | 65 | BASE_URL: api-demo.bybit.com → api.bybit.com |
| trader.py | 93 | BYBIT_START_BALANCE → your actual deposit |
| trader.py | 246 | DELETE the X-BAPI-DEMO-TRADING: "1" header line |
| monitor.py | 42 | BYBIT_API_KEY → real live key |
| monitor.py | 43 | BYBIT_API_SECRET → real live secret |
| monitor.py | 44 | BASE_URL: api-demo.bybit.com → api.bybit.com |
| monitor.py | 98 | DELETE the X-BAPI-DEMO-TRADING: "1" header line |
| tracker.py | 62 | BYBIT_API_KEY → real live key |
| tracker.py | 63 | BYBIT_API_SECRET → real live secret |
| tracker.py | 64 | BASE_URL: api-demo.bybit.com → api.bybit.com |
| tracker.py | 58 | BYBIT_START_BALANCE → your actual deposit |
| tracker.py | 199 | DELETE the X-BAPI-DEMO-TRADING: "1" header line |
| bot.py | — | No changes required |

---

## Post-Switch Verification (do BEFORE restarting any scheduler)

Verify each of the following manually before turning anything on:

**Step 1: Run trader manually**
```
cd C:\Users\MAX\WhaleStream
py whale_stream_trader.py
```

Look for these lines in the output:
- `✓ Available USDT: $XXX.XX` — this must match your real account balance
- If you see $0.00 or an API error, the keys are wrong or the demo header was not removed
- If it says "Could not connect to Bybit", check BASE_URL and API keys

**Step 2: Confirm it is NOT hitting the demo account**
- Log in to bybit.com and check your REAL (non-demo) Unified account balance
- The balance shown in the trader output must match what you see on bybit.com (not bybit demo)
- Do NOT rely on the log alone — visually confirm on the website

**Step 3: Verify no unexpected orders were placed**
- On this first manual run there should be NO signals (bot hasn't run yet for live) OR
  if signals exist, confirm any orders placed are visible in your real Bybit account
  under Derivatives → Orders → Open Orders

**Step 4: Check Telegram received the run summary**
- The run-complete message should appear in your Telegram group
- It should show your real balance, not $500 demo balance

**Step 5: Run monitor manually**
```
py whale_stream_monitor.py
```
- Should output "No position changes detected" (or pick up any real positions)
- Check monitor_log.txt for any auth errors

**Step 6: Run tracker manually**
```
py whale_stream_tracker.py
```
- Should connect and process sheet rows
- No auth errors in output

---

## Restart Sequence

Restart schedulers in this order. Wait 30 seconds between each.

1. **whale_stream_bot.py** (signal generator) — restart FIRST
   - Reason: it writes new signals to Google Sheets; trader reads from Sheets
   - If trader runs before bot has written signals, it finds nothing and exits cleanly

2. **whale_stream_trader.py** (order placer) — restart SECOND
   - Reason: needs fresh signals from bot already in the Sheet
   - First live run may place real orders if bot has already written OPEN signals

3. **whale_stream_monitor.py** (position monitor) — restart THIRD
   - Reason: it only reads positions, never places orders; safe to start any time
   - Polls every 2 minutes via Task Scheduler

4. **whale_stream_tracker.py** (WIN/LOSS tracker) — restart FOURTH
   - Reason: needs positions to already exist before it can track them
   - Runs every 30 minutes via Task Scheduler

---

## Emergency Rollback (switch BACK to demo in under 2 minutes)

If something goes wrong after going live, do this immediately:

**Step 1 — Stop all schedulers NOW (takes 10 seconds)**
Open Task Scheduler → right-click each of the four tasks → End

**Step 2 — Create the kill switch (takes 5 seconds)**
```
echo EMERGENCY PAUSE > C:\Users\MAX\WhaleStream\paused.flag
```
This prevents the trader from placing any new orders even if it runs.

**Step 3 — Revert the three files**
In each file, make these changes:

trader.py:
- Line 52: restore `BYBIT_API_KEY    = "uJbW2tKiexXXDhoucb"`
- Line 53: restore `BYBIT_API_SECRET = "c8ce3oTWMvGW7incCe3ECsMJf7BnMZaCMpqP"`
- Line 65: restore `BYBIT_BASE_URL   = "https://api-demo.bybit.com"`
- Line 246: restore `"X-BAPI-DEMO-TRADING":  "1",`

monitor.py:
- Lines 42/43/44: restore demo keys and URL
- Line 98: restore demo header

tracker.py:
- Lines 62/63/64: restore demo keys and URL
- Line 199: restore demo header

**Step 4 — Cancel any live orders on Bybit**
Log in to bybit.com → Unified Trading → Orders → Open Orders → Cancel All

**Step 5 — Delete paused.flag when ready to resume demo**
```
del C:\Users\MAX\WhaleStream\paused.flag
```

Total rollback time if files are not yet saved: under 2 minutes.

---

## First Week Monitoring Protocol

**Every morning (takes 5 minutes):**
- Open Telegram — read any overnight alerts
- Check for circuit breaker messages ("CIRCUIT BREAKER TRIGGERED")
- Check for balance warning messages ("BALANCE LOW")

**Every day:**
- Open `C:\Users\MAX\WhaleStream\monitor_log.txt` — scan for "partial close" or "position gone" entries
- Open `C:\Users\MAX\WhaleStream\trader_log.txt` — scan for retCode errors (any line with "retCode" that is not 0)
- Log in to bybit.com and visually confirm open positions match what Telegram reported

**Kill switch — if anything looks wrong:**
```
echo PAUSE > C:\Users\MAX\WhaleStream\paused.flag
```
The trader will halt on its next scheduled run. No open positions are closed — they
stay on Bybit until TP or SL is hit. Only new orders stop.

**To resume after pausing:**
```
del C:\Users\MAX\WhaleStream\paused.flag
```

**First week risk suggestion:**
- Keep MAX_OPEN_TRADES at 6 (line 58 of trader.py) but use $5 margin — max exposure is $300
- Do not increase TRADE_MARGIN_USDT until you have seen at least 10 live trades resolve correctly
- Check bybit.com manually every 48 hours for the first two weeks to confirm positions match Google Sheets

---

## Key Settings Reference (current demo values)

| Setting | File | Line | Demo Value | Recommended Live Value |
|---------|------|------|------------|------------------------|
| TRADE_MARGIN_USDT | trader.py | 56 | $20 | $5 (first month) |
| LEVERAGE | trader.py | 57 | 10x | 10x (no change needed) |
| MAX_OPEN_TRADES | trader.py | 58 | 6 | 6 (no change needed) |
| MAX_DEPLOYED_FRACTION | trader.py | 83 | 50% | 50% (no change needed) |
| CIRCUIT_LOSSES | trader.py | — (constant) | 3 | 3 (no change needed) |
| BYBIT_START_BALANCE | trader.py | 93 | 500.00 | Your actual deposit |
| BYBIT_START_BALANCE | tracker.py | 58 | 500.00 | Your actual deposit |

---

## Important Notes

**The API key pair is shared across all three scripts.** You only need to generate ONE
set of real API keys on Bybit. Enter the same key and secret in trader.py, monitor.py,
and tracker.py.

**BYBIT_PUBLIC_URL (line 66 of trader.py) does NOT need to change.** It is already
`https://api.bybit.com` and is used only for unauthenticated market data, which is the
same endpoint for both demo and live.

**Google Sheets credentials do not change.** The same google_credentials.json and
GOOGLE_SHEET_ID work for both demo and live.

**The demo account's open trades will be orphaned.** If you have positions open on the
demo account when you switch, the tracker will no longer see them (it will be watching
your real account). Those demo positions will stay open on Bybit demo until SL/TP hit.
Close them manually on bybit.com demo before switching, or accept they will be ignored.

**Do not run demo and live simultaneously.** Using the same Google Sheet and Telegram
group for both at once will create confusion in WIN/LOSS tracking and duplicate alerts.
