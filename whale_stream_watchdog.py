"""
╔══════════════════════════════════════════════════════════════╗
║   WHALE-STREAM WATCHDOG v2.0                                 ║
║                                                              ║
║  ROLE (Principle 1): System health guardian.                 ║
║  Runs at :30 of every 4h cycle. Confirms all agents ran.     ║
║  Sends GREEN confirmation when healthy.                      ║
║  Sends AMBER alert with EXACT fix steps when something fails.║
║  Sends RED CRITICAL when Trader has been down 8h+.           ║
║                                                              ║
║  Schedule: 00:30 04:30 08:30 12:30 16:30 20:30 BKK          ║
║                                                              ║
║  ── WHALE-STREAM CONSTITUTION (7 Principles) ──              ║
║  1. Every agent has one clear isolated role                  ║
║  2. Run on continuous 4h automated schedule                  ║
║  3. After each cycle: report what works and what does not    ║
║  4. Run 24/7, proactively report — never wait to be asked    ║
║  5. Multi-agent consensus before final debrief               ║
║  6. High-risk trading: discipline is not optional            ║
║  7. Every action serves our mission — to help others         ║
╚══════════════════════════════════════════════════════════════╝
"""

import io
import sys
import os
import json
import re
import requests
from datetime import datetime, timezone, timedelta

# ── UTF-8 fix (prevents crash in Task Scheduler CP1252) ───────
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# ── Credentials ───────────────────────────────────────────────
try:
    from local_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Paths ──────────────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
BOT_LOG         = os.path.join(BASE_DIR, "bot_log.txt")
STRATEGIST_LOG  = os.path.join(BASE_DIR, "strategist_task_log.txt")
TRADER_LOG      = os.path.join(BASE_DIR, "trader_log.txt")
BALANCE_FILE    = os.path.join(BASE_DIR, "bybit_balance.json")
PAUSED_FLAG     = os.path.join(BASE_DIR, "paused.flag")

BKK = timezone(timedelta(hours=7))


# ── Self-tick helper (writes completion to daily_status.json) ────
def _mark_done(agent_name):
    """Mark this agent done for the current cycle in daily_status.json."""
    _path  = os.path.join(BASE_DIR, "daily_status.json")
    _today = __import__("datetime").date.today().isoformat()
    _h     = __import__("datetime").datetime.now().hour
    _cycle = str((_h // 4) * 4).zfill(2)
    _key   = f"{agent_name}_{_cycle}" if agent_name not in ("tracker", "monitor", "briefing") else agent_name
    try:
        with open(_path, encoding="utf-8") as _f:
            _data = json.load(_f)
        if _data.get("date") != _today:
            _data = {"date": _today}
    except Exception:
        _data = {"date": _today}
    _data[_key] = True
    with open(_path, "w", encoding="utf-8") as _f:
        json.dump(_data, _f, indent=2)
    print(f"   ✓ Status logged → {_key}")


# Deadline windows (minutes after cycle start before we flag as missed)
BOT_DEADLINE_MIN        = 32   # Bot at :00, Watchdog at :30 = 30 min
STRATEGIST_DEADLINE_MIN = 22   # Strategist at :10
TRADER_DEADLINE_MIN     = 16   # Trader at :20
TRADER_CRITICAL_HOURS   = 8    # Escalate to CRITICAL if Trader down this long


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def last_log_timestamp(path, pattern):
    """Scan log for pattern, return most recent datetime match (BKK tz)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return None
    matches = re.findall(pattern, text)
    if not matches:
        return None
    latest = None
    for m in matches:
        try:
            dt = datetime.strptime(m, "%Y-%m-%d %H:%M").replace(tzinfo=BKK)
            if latest is None or dt > latest:
                latest = dt
        except Exception:
            continue
    return latest


def minutes_ago(dt):
    if dt is None:
        return None
    return int((datetime.now(BKK) - dt).total_seconds() / 60)


def fmt_ago(ago):
    if ago is None:
        return "never"
    if ago < 60:
        return f"{ago}m ago"
    h, m = divmod(ago, 60)
    return f"{h}h {m}m ago"


def load_balance():
    try:
        with open(BALANCE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────
# AGENT CHECKS
# ─────────────────────────────────────────────────────────────

def check_bot():
    # v46.64+: bot writes "[YYYY-MM-DD HH:MM BKK] Bot run complete"
    dt = last_log_timestamp(BOT_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\].*?Bot run complete")
    if dt is None:
        # Fallback: any BKK timestamp in bot log
        dt = last_log_timestamp(BOT_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\]")
    ago = minutes_ago(dt)
    last_str = dt.strftime("%H:%M BKK") if dt else "never"
    ok = (ago is not None and ago <= BOT_DEADLINE_MIN)
    return ok, last_str, ago


def check_strategist():
    dt = last_log_timestamp(STRATEGIST_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\].*?Strategist run started")
    if dt is None:
        dt = last_log_timestamp(STRATEGIST_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\]")
    ago = minutes_ago(dt)
    last_str = dt.strftime("%H:%M BKK") if dt else "never"
    ok = (ago is not None and ago <= STRATEGIST_DEADLINE_MIN)
    return ok, last_str, ago


def check_trader():
    # Primary: RUN COMPLETE (successful trade cycle)
    dt = last_log_timestamp(TRADER_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\] RUN COMPLETE")
    # Fallback: any BKK timestamp (catches PAUSED runs)
    dt_any = last_log_timestamp(TRADER_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\]")
    # Use most recent of the two
    if dt is None or (dt_any and dt_any > dt):
        dt = dt_any
    ago = minutes_ago(dt)
    last_str = dt.strftime("%H:%M BKK") if dt else "never"
    ok = (ago is not None and ago <= TRADER_DEADLINE_MIN)
    return ok, last_str, ago


def check_balance():
    """Returns (stale, hours_old, balance_str, updated_at)"""
    data = load_balance()
    try:
        updated_at = data.get("updated_at", "")
        dt = datetime.strptime(updated_at, "%Y-%m-%d %H:%M BKK").replace(tzinfo=BKK)
        hours_old = (datetime.now(BKK) - dt).total_seconds() / 3600
        bal = data.get("balance", 0)
        bal_str = f"${bal:,.2f}"
        return hours_old >= 6.0, round(hours_old, 1), bal_str, updated_at
    except Exception:
        return True, None, "unknown", "unknown"


# ─────────────────────────────────────────────────────────────
# EXACT FIX STEPS PER AGENT FAILURE (Principle 3 + 4)
# ─────────────────────────────────────────────────────────────

FIX_BOT = (
    "→ FIX: Open Task Scheduler → find 'WhaleStream-Bot' → right-click → Run\n"
    "→ Or double-click run_bot.bat in C:\\Users\\MAX\\WhaleStream\\\n"
    "→ Check bot_log.txt last 20 lines for the error"
)
FIX_STRATEGIST = (
    "→ FIX: Open Task Scheduler → find 'WhaleStreamStrategist' → right-click → Run\n"
    "→ Or double-click run_strategist.bat\n"
    "→ Check strategist_task_log.txt for the error"
)
FIX_TRADER = (
    "→ FIX STEP 1: Run DIAGNOSE_BYBIT.bat — see the exact error code\n"
    "→ If retCode=10002: right-click clock → Adjust date/time → Sync now\n"
    "→ If retCode=10003/33004: regenerate API keys in Bybit Demo → API Management\n"
    "   Then update BYBIT_API_KEY + BYBIT_API_SECRET in local_config.py\n"
    "→ FIX STEP 2: Double-click run_trader.bat to test manually\n"
    "→ Check trader_log.txt for the exact error message"
)
FIX_PAUSED = (
    "→ FIX: Double-click CLEAR_PAUSE.bat to resume trading\n"
    "→ Or delete the file: C:\\Users\\MAX\\WhaleStream\\paused.flag\n"
    "→ Review trader_log.txt to understand WHY the circuit breaker fired"
)


# ─────────────────────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────────────────────

def send_telegram(text, parse_mode="HTML"):
    url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}
    try:
        resp = requests.post(url, data=data, timeout=15)
        if resp.status_code == 200 and resp.json().get("ok"):
            print("✅ Watchdog alert sent to Telegram.")
        else:
            print(f"❌ Telegram error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"❌ Telegram request failed: {e}")


# ─────────────────────────────────────────────────────────────
# REPORT BUILDERS
# ─────────────────────────────────────────────────────────────

def build_green_report(now_str, bot_last, strat_last, trade_last, bal_str, bal_updated, paused):
    """All-clear: full team healthy — sent every cycle (Principle 3)."""
    pause_note = "\n⚠️ NOTE: Circuit breaker ACTIVE — orders paused." if paused else ""
    return (
        f"🟢 <b>WHALE-STREAM — 4h Cycle Complete</b>\n"
        f"🕐 {now_str}\n"
        f"\n"
        f"<b>Agent Status:</b>\n"
        f"  ✅ SigBot       — last run {bot_last}\n"
        f"  ✅ Strategist   — last run {strat_last}\n"
        f"  ✅ Trader       — last run {trade_last}\n"
        f"  ✅ Tracker      — every 30 min\n"
        f"  ✅ Monitor      — every 2 min\n"
        f"\n"
        f"💰 Balance: {bal_str}  (updated {bal_updated})\n"
        f"{pause_note}\n"
        f"🐋 All systems running. Next cycle in ~4h."
    )


def build_amber_alert(now_str, issues_with_fixes, bot_line, strat_line, trade_line, bal_str):
    """One or more agents failed — include exact fix steps (Principle 3+4)."""
    issue_block = "\n\n".join(issues_with_fixes)
    return (
        f"🟡 <b>WHALE-STREAM WATCHDOG — Issues Detected</b>\n"
        f"🕐 {now_str}\n"
        f"\n"
        f"<b>⚠️ Problems found this cycle:</b>\n"
        f"{issue_block}\n"
        f"\n"
        f"<b>Agent Status:</b>\n"
        f"  {bot_line}\n"
        f"  {strat_line}\n"
        f"  {trade_line}\n"
        f"\n"
        f"💰 Balance: {bal_str}"
    )


def build_critical_alert(now_str, trade_last, trade_ago, bal_str):
    """CRITICAL: Trader has been down >8h — maximum urgency (Principle 4+6)."""
    return (
        f"🔴🔴🔴 <b>CRITICAL — TRADER HAS BEEN OFFLINE {trade_ago//60}h {trade_ago%60}m</b> 🔴🔴🔴\n"
        f"🕐 {now_str}\n"
        f"\n"
        f"<b>NO TRADES HAVE BEEN PLACED SINCE: {trade_last}</b>\n"
        f"Every hour offline = missed profit opportunities.\n"
        f"Balance stale: {bal_str}\n"
        f"\n"
        f"<b>IMMEDIATE ACTION REQUIRED:</b>\n"
        f"1️⃣ Run DIAGNOSE_BYBIT.bat — see the exact error\n"
        f"2️⃣ If retCode=10002 → right-click clock → Sync now\n"
        f"3️⃣ If retCode=10003/33004 → regenerate API keys in Bybit Demo\n"
        f"4️⃣ Update local_config.py with new BYBIT_API_KEY + BYBIT_API_SECRET\n"
        f"5️⃣ Run run_trader.bat to confirm connection works\n"
        f"\n"
        f"🐋 This system exists to help others. Act now."
    )


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        from mission import print_mission_banner
        print_mission_banner()
    except ImportError:
        pass

    now_bkk = datetime.now(BKK)
    now_str = now_bkk.strftime("%Y-%m-%d %H:%M BKK")
    print(f"[{now_str}] === Watchdog run started ===")

    # ── Run all checks ────────────────────────────────────────
    bot_ok,   bot_last,   bot_ago   = check_bot()
    strat_ok, strat_last, strat_ago = check_strategist()
    trade_ok, trade_last, trade_ago = check_trader()
    paused    = os.path.exists(PAUSED_FLAG)
    bal_stale, bal_hours, bal_str, bal_updated = check_balance()

    # ── Build status lines ────────────────────────────────────
    bot_line   = f"{'✅' if bot_ok   else '🚨'} SigBot       last: {bot_last}  ({fmt_ago(bot_ago)})"
    strat_line = f"{'✅' if strat_ok else '🚨'} Strategist   last: {strat_last}  ({fmt_ago(strat_ago)})"
    trade_line = f"{'✅' if trade_ok else '🚨'} Trader       last: {trade_last}  ({fmt_ago(trade_ago)})"

    print(bot_line)
    print(strat_line)
    print(trade_line)

    # ── Check CRITICAL: Trader down >8h ──────────────────────
    trader_critical = (
        not trade_ok
        and trade_ago is not None
        and trade_ago >= TRADER_CRITICAL_HOURS * 60
    )

    # ── Collect issues with exact fix steps ──────────────────
    issues_with_fixes = []
    if not bot_ok:
        issues_with_fixes.append(
            f"🚨 <b>SigBot missed :00 slot</b>  (last: {bot_last}, {fmt_ago(bot_ago)})\n{FIX_BOT}"
        )
    if not strat_ok:
        issues_with_fixes.append(
            f"🚨 <b>Strategist missed :10 slot</b>  (last: {strat_last}, {fmt_ago(strat_ago)})\n{FIX_STRATEGIST}"
        )
    if not trade_ok:
        issues_with_fixes.append(
            f"🚨 <b>Trader missed :20 slot</b>  (last: {trade_last}, {fmt_ago(trade_ago)})\n{FIX_TRADER}"
        )
    if paused:
        issues_with_fixes.append(
            f"🚨 <b>CIRCUIT BREAKER ACTIVE</b> — all orders are paused\n{FIX_PAUSED}"
        )
    if bal_stale:
        hrs = f"{bal_hours}h" if bal_hours is not None else "unknown"
        issues_with_fixes.append(
            f"⚠️ <b>Balance stale</b> — last updated {hrs} ago ({bal_updated})\n"
            f"→ This is normal if Trader is down. Fix Trader first."
        )

    # ── Send appropriate Telegram message ────────────────────
    if trader_critical:
        # Highest priority: CRITICAL alert for long Trader outage
        msg = build_critical_alert(now_str, trade_last, trade_ago, bal_str)
        print(f"\n🔴 CRITICAL ESCALATION: Trader down {trade_ago//60}h {trade_ago%60}m")
        send_telegram(msg)
        # Also send amber for the other issues (if any beyond trader)
        other_issues = [i for i in issues_with_fixes if "Trader" not in i and "Balance" not in i]
        if other_issues:
            amber = build_amber_alert(now_str, other_issues, bot_line, strat_line, trade_line, bal_str)
            send_telegram(amber)

    elif issues_with_fixes:
        # Normal amber alert
        msg = build_amber_alert(now_str, issues_with_fixes, bot_line, strat_line, trade_line, bal_str)
        print("\n" + "="*50)
        print("AMBER ALERT:")
        print(msg)
        send_telegram(msg)

    else:
        # ALL GREEN — send positive confirmation (Principle 3)
        msg = build_green_report(now_str, bot_last, strat_last, trade_last, bal_str, bal_updated, paused)
        print(f"\n✅ All agents healthy.")
        print(msg)
        send_telegram(msg)

    _mark_done("watchdog")
    print(f"\n[{now_str}] Watchdog complete.")
