# WHALE-STREAM — July 1 Go-Live Checklist
### Demo → Live switch ops runbook

---

## PRE-FLIGHT (do the night before, June 30)

- [ ] Run `analyze_shorts.py` — confirm LONG WR ≥ 50% and SHORT WR ≥ 50% (Gate 3 threshold; target ≥70% for mature SHORT scaling)
- [ ] Verify `gate4_breach.flag` does NOT exist in WhaleStream folder (Gate 4 = >15% drawdown — must be clear before going live)
- [ ] Verify `paused.flag` does NOT exist (circuit breaker must be inactive)
- [ ] Open Bybit Dashboard → check demo balance is healthy (not in drawdown >15%)
- [ ] Confirm all 4 daily agents ran cleanly today (Daily Checklist.html all green)
- [ ] Verify 6 Recheck/Reactive tasks are registered in Task Scheduler — if not, run `ADD_RECHECK_TASKS.bat` as Administrator
- [ ] Verify `WhaleStream-StatusCheck` task is registered — if not, run `ADD_STATUS_CHECK_TASK.bat` as Administrator
- [ ] Verify `WhaleStream-StatusServer` task is registered and running — open `http://127.0.0.1:8765/daily_status.json` in browser to confirm
- [ ] Close any demo positions you don't want carrying into live (or accept they stay demo)
- [ ] Confirm live Bybit account has been funded (suggest $500 minimum)
- [ ] Generate Live API keys in Bybit → API Management:
  - Enable: **Read**, **Trade** (Unified Trading)
  - IP whitelist: leave blank (or add your PC's IP)
  - Copy API Key + Secret — you'll need them in step 3 below

---

## SWITCH DAY — July 1 Morning (BKK time, before 08:00)

### Step 1 — Pause the system first
```
Run: CLEAR_PAUSE.bat   ← confirm it's NOT paused
```
Then manually pause it while you edit:
- Create an empty file called `paused.flag` in `C:\Users\MAX\WhaleStream\`
- This stops Trader from placing orders while you're mid-edit

### Step 2 — Open Task Scheduler
- Temporarily **disable** all WhaleStream tasks so nothing fires mid-switch:
  - WhaleStream-Bot, WhaleStreamStrategist, WhaleStream-Trader, WhaleStreamWatchdog
  - WhaleStream-Tracker, WhaleStream-Monitor, WhaleStream-Briefing
  - WhaleStream-OrphanCheck, WhaleStream-LogAnalyzer, WhaleStream-StatusCheck, WhaleStream-StatusServer
  - WhaleStream-Recheck-A/B/C, WhaleStream-Reactive-A/B/C

### Step 3 — Edit local_config.py (THE ONLY FILE YOU TOUCH)
```
Notepad C:\Users\MAX\WhaleStream\local_config.py
```
Change these three lines:
```python
BYBIT_API_KEY    = "your_LIVE_key_here"
BYBIT_API_SECRET = "your_LIVE_secret_here"
BYBIT_BASE_URL   = "https://api.bybit.com"
```
⚠️ Do NOT change anything else. Telegram keys, Google keys — leave them.

> **Why `BYBIT_BASE_URL` matters:** Without it, the default is `https://api-demo.bybit.com`.
> Live API keys pointed at the demo URL will authenticate but place all orders on the demo exchange.
> Real money will never move. **This line is mandatory for go-live.**
Save and close.

### Step 4 — Verify connection (before re-enabling tasks)
```
Run: DIAGNOSE_BYBIT.bat
```
You should see: `retCode: 0` and your **live** balance printed.
If it shows demo balance or error → stop, re-check the keys.

### Step 5 — Set live trade size
Add or update `TRADE_MARGIN_USDT` in **`local_config.py`** (THE ONLY FILE YOU TOUCH):
```python
TRADE_MARGIN_USDT = 25   # ← set your live size here
```
If `TRADE_MARGIN_USDT` is not already in `local_config.py`, add it as a new line.
The system reads it via `try: from local_config import TRADE_MARGIN_USDT except ImportError: ...`

Also update `BYBIT_START_BALANCE` in both `whale_stream_trader.py` and `whale_stream_tracker.py`
to match your actual funded live balance (default: 500.0). Search for `BYBIT_START_BALANCE = 500.0`
in both files and update it. *(v47.9 goal: move this to local_config.py so only one file needs editing)*

Recommended for go-live: **$10–$25 per trade** (you can scale up after Gate 1).

### Step 6 — Delete paused.flag
```
Run: CLEAR_PAUSE.bat
```

### Step 7 — Re-enable Task Scheduler tasks
Re-enable all WhaleStream tasks you disabled in Step 2 (all 15 main + StatusCheck + StatusServer).

### Step 8 — Force a manual first cycle to verify
Run in this order (wait 30s between each):
```
1. run_bot.bat          ← generates live signals
2. run_strategist.bat   ← approves / vetoes
3. run_trader.bat       ← places LIVE orders  ← WATCH THIS ONE
4. run_tracker.bat      ← updates sheet
```
After Trader runs → go to Bybit Live → check **Open Orders** tab.
You should see real orders there.

---

## FIRST CYCLE VERIFICATION

| Check | Where | Expected |
|-------|-------|----------|
| Orders visible on Bybit Live | Bybit → Open Orders | 1–3 new orders |
| Bybit IDs written to sheet | Google Sheets → Column R | Non-empty for new rows |
| Balance deducted correctly | Bybit → Assets | ~$TRADE_MARGIN per order |
| Telegram alert received | Ops channel | "✅ Order placed: COIN LONG/SHORT" |
| Daily Checklist green | Daily Checklist.html | All 4 agents ✅ |

---

## IF SOMETHING GOES WRONG

| Problem | Fix |
|---------|-----|
| Trader places no orders | Check `trader_log.txt` for skip reason |
| "10003 API key invalid" | Re-generate keys, re-paste in local_config.py |
| Orders placed but no sheet ID | Sheets API auth issue — check google_credentials.json |
| Wrong balance shown | You're still on demo keys — re-check Step 3 |
| Circuit breaker fires | Check drawdown — if genuine, let it pause and investigate |
| Panic — want to stop everything | Create `paused.flag` in WhaleStream folder |

---

## FIRST WEEK RULES

1. **Don't change trade size** for 7 days — let the system stabilise
2. **Check Telegram morning briefing** every day at 07:00 BKK
3. **Don't manually interfere** with positions — trust the Tracker/SL system
4. **Review analyze_shorts.py** after the first Sunday auto-run
5. **Scale up** only after 20 resolved live trades with WR ≥ 55%

---

## ROLLBACK PLAN (if live is going badly)

Switch back to demo keys in `local_config.py` at any time.
The system is identical — just the API endpoint changes.
No code changes needed to roll back.

---

*Generated: 2026-06-28 | Updated: 2026-06-29 | WHALE-STREAM v47.8*
