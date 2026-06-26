"""
╔══════════════════════════════════════════════════════════════╗
║       WHALE-STREAM WATCHDOG                                  ║
║                                                              ║
║  Runs at :30 of each 4h cycle (00:30, 04:30, 08:30 …)       ║
║  Checks if Bot (:00), Strategist (:10), Trader (:20)         ║
║  all ran in the current cycle. Sends Telegram alert if any   ║
║  agent missed its slot.                                      ║
║                                                              ║
║  Also alerts if circuit breaker is active or balance is      ║
║  stale (not updated in 6h+).                                 ║
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

# How many minutes after cycle start before we flag an agent as missed
# Bot runs at :00 → we check at :30 → 30 min window
# Strategist at :10 → 20 min window
# Trader at :20 → 10 min window (generous: give it 15)
BOT_DEADLINE_MIN        = 28   # flag if no bot run in last 28 min at check time
STRATEGIST_DEADLINE_MIN = 22   # flag if no strategist run in last 22 min
TRADER_DEADLINE_MIN     = 16   # flag if no trader run in last 16 min


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def last_log_timestamp(path, pattern):
    """
    Scan log file for all occurrences of `pattern` (a regex with one
    datetime group in format YYYY-MM-DD HH:MM) and return the most
    recent as a timezone-aware datetime (BKK), or None.
    """
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
    """Return how many minutes ago `dt` was, relative to now (BKK)."""
    if dt is None:
        return None
    return int((datetime.now(BKK) - dt).total_seconds() / 60)


# ─────────────────────────────────────────────────────────────
# AGENT CHECKS
# ─────────────────────────────────────────────────────────────

def check_bot():
    """
    Bot logs: [2026-06-26 08:00 BKK] === Bot run started
    Returns (ok: bool, last_run_str: str, mins_ago: int|None)
    """
    dt = last_log_timestamp(
        BOT_LOG,
        r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\].*?Bot run started"
    )
    if dt is None:
        # Also try the banner line as fallback
        dt = last_log_timestamp(
            BOT_LOG,
            r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\]"
        )
    ago = minutes_ago(dt)
    last_str = dt.strftime("%H:%M BKK") if dt else "never"
    ok = (ago is not None and ago <= BOT_DEADLINE_MIN)
    return ok, last_str, ago


def check_strategist():
    """
    Strategist logs: [2026-06-26 08:10 BKK] === Strategist run started
    """
    dt = last_log_timestamp(
        STRATEGIST_LOG,
        r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\].*?Strategist run started"
    )
    if dt is None:
        dt = last_log_timestamp(
            STRATEGIST_LOG,
            r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\]"
        )
    ago = minutes_ago(dt)
    last_str = dt.strftime("%H:%M BKK") if dt else "never"
    ok = (ago is not None and ago <= STRATEGIST_DEADLINE_MIN)
    return ok, last_str, ago


def check_trader():
    """
    Trader logs: [2026-06-26 08:20 BKK] RUN COMPLETE
    """
    dt = last_log_timestamp(
        TRADER_LOG,
        r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\] RUN COMPLETE"
    )
    if dt is None:
        dt = last_log_timestamp(
            TRADER_LOG,
            r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\]"
        )
    ago = minutes_ago(dt)
    last_str = dt.strftime("%H:%M BKK") if dt else "never"
    ok = (ago is not None and ago <= TRADER_DEADLINE_MIN)
    return ok, last_str, ago


def check_balance_staleness():
    """
    Returns (stale: bool, hours_old: float, updated_at: str)
    Stale = not updated in 6h+ (should update every 4h via trader)
    """
    try:
        with open(BALANCE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        updated_at = data.get("updated_at", "")
        # Parse "2026-06-25 22:20 BKK"
        dt = datetime.strptime(updated_at, "%Y-%m-%d %H:%M BKK").replace(tzinfo=BKK)
        hours_old = (datetime.now(BKK) - dt).total_seconds() / 3600
        stale = hours_old >= 6.0
        return stale, round(hours_old, 1), updated_at
    except Exception:
        return True, None, "unknown"


# ─────────────────────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────────────────────

def send_telegram(text):
    url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": ""}
    try:
        resp = requests.post(url, data=data, timeout=15)
        if resp.status_code == 200 and resp.json().get("ok"):
            print("✅ Watchdog alert sent to Telegram.")
        else:
            print(f"❌ Telegram error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"❌ Telegram request failed: {e}")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    now_bkk  = datetime.now(BKK)
    now_str  = now_bkk.strftime("%Y-%m-%d %H:%M BKK")
    print(f"[{now_str}] === Watchdog run started ===")

    # ── Run all checks ────────────────────────────────────────
    bot_ok,   bot_last,   bot_ago   = check_bot()
    strat_ok, strat_last, strat_ago = check_strategist()
    trade_ok, trade_last, trade_ago = check_trader()
    paused    = os.path.exists(PAUSED_FLAG)
    bal_stale, bal_hours, bal_updated = check_balance_staleness()

    # ── Build status lines ────────────────────────────────────
    def fmt_ago(ago):
        if ago is None:
            return "never"
        if ago < 60:
            return f"{ago}m ago"
        return f"{ago // 60}h {ago % 60}m ago"

    bot_line   = f"{'✅' if bot_ok   else '🚨'} Bot        last: {bot_last}  ({fmt_ago(bot_ago)})"
    strat_line = f"{'✅' if strat_ok else '🚨'} Strategist last: {strat_last}  ({fmt_ago(strat_ago)})"
    trade_line = f"{'✅' if trade_ok else '🚨'} Trader     last: {trade_last}  ({fmt_ago(trade_ago)})"

    print(bot_line)
    print(strat_line)
    print(trade_line)

    # ── Determine if anything needs alerting ──────────────────
    issues = []
    if not bot_ok:
        issues.append(f"🚨 BOT missed its :00 slot! Last run: {bot_last} ({fmt_ago(bot_ago)})")
    if not strat_ok:
        issues.append(f"🚨 STRATEGIST missed its :10 slot! Last run: {strat_last} ({fmt_ago(strat_ago)})")
    if not trade_ok:
        issues.append(f"🚨 TRADER missed its :20 slot! Last run: {trade_last} ({fmt_ago(trade_ago)})")
    if paused:
        issues.append("🚨 CIRCUIT BREAKER ACTIVE — system is paused! Run CLEAR_PAUSE.bat to resume.")
    if bal_stale:
        hours_str = f"{bal_hours}h" if bal_hours is not None else "unknown"
        issues.append(f"⚠️ BALANCE STALE — last updated {hours_str} ago ({bal_updated}). Trader may be down.")

    # ── Send alert if any issues ──────────────────────────────
    if issues:
        msg_lines = [
            f"🐋 WHALE-STREAM WATCHDOG ALERT",
            f"{now_str}",
            "",
            "─── ISSUES DETECTED ───",
        ]
        for issue in issues:
            msg_lines.append(f"  {issue}")
        msg_lines += [
            "",
            "─── AGENT STATUS ───",
            f"  {bot_line}",
            f"  {strat_line}",
            f"  {trade_line}",
            "",
            "Action: Check logs or re-run the affected agent manually.",
        ]
        msg = "\n".join(msg_lines)
        print("\n" + msg)
        send_telegram(msg)
    else:
        print(f"[{now_str}] ✅ All agents healthy — no alert sent.")

    print("Done.")
