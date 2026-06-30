"""
╔══════════════════════════════════════════════════════════════╗
║   WHALE-STREAM WATCHDOG v47.15                                ║
║                                                              ║
║  ROLE (Principle 1): System health guardian.                 ║
║  Runs at :30 of every 4h cycle. Confirms all agents ran.     ║
║  Sends GREEN confirmation when healthy.                      ║
║  Sends AMBER alert with EXACT fix steps when something fails.║
║  Sends RED CRITICAL when Trader has been down 4h+.           ║
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
import time
import subprocess
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
STRATEGIST_LOG  = os.path.join(BASE_DIR, "strategist_log.txt")
TRADER_LOG      = os.path.join(BASE_DIR, "trader_log.txt")
TRACKER_LOG     = os.path.join(BASE_DIR, "tracker_log.txt")
MONITOR_LOG     = os.path.join(BASE_DIR, "monitor_log.txt")
BALANCE_FILE    = os.path.join(BASE_DIR, "bybit_balance.json")
PAUSED_FLAG     = os.path.join(BASE_DIR, "paused.flag")

BKK = timezone(timedelta(hours=7))


# ── HTML snapshot writer (Watchdog is sole HTML writer — no race conditions) ──
def _write_html_snapshot():
    """Read full daily_status.json and write complete WS_EMBEDDED blob to Daily Checklist.html.
    Called once at the end of each Watchdog run (:30), after all 4 cycle agents have finished.
    This eliminates the race condition where earlier agents' HTML writes collide with monitor."""
    try:
        _status_path = os.path.join(BASE_DIR, "daily_status.json")
        _html_path   = os.path.join(BASE_DIR, "To do list", "Daily Checklist.html")
        with open(_status_path, encoding="utf-8") as _sf:
            _data = json.load(_sf)
        with open(_html_path, encoding="utf-8") as _hf:
            _html = _hf.read()
        _inject = "var WS_EMBEDDED=" + json.dumps(_data, separators=(',', ':'), ensure_ascii=False) + ";"
        # Replace existing WS_EMBEDDED assignment; DOTALL non-greedy stops at first ';' after '}'
        _new_html = re.sub(r'var WS_EMBEDDED=\{[\s\S]*?\};', _inject, _html)
        if _new_html == _html:
            # Pattern not matched (first run or HTML was reset) — inject before </script>
            _new_html = _html.replace("</script>", f"{_inject}\n</script>", 1)
            print("   ⚠ WS_EMBEDDED pattern not found — used fallback inject.")
        with open(_html_path, "w", encoding="utf-8") as _hf:
            _hf.write(_new_html)
        print("   ✓ Daily Checklist.html WS_EMBEDDED updated with full cycle snapshot.")
    except Exception as _e:
        print(f"   ⚠ HTML snapshot write failed: {_e}")


# ── Self-tick helper (writes completion to daily_status.json) ────
def _mark_done(agent_name, details=None):
    """Mark this agent done for the current cycle in daily_status.json."""
    _path  = os.path.join(BASE_DIR, "daily_status.json")
    _now   = datetime.now(BKK)
    _today = _now.date().isoformat()
    _h     = _now.hour
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
    if details:
        _data[f"{_key}_details"] = details
    try:
        with open(_path, "w", encoding="utf-8") as _f:
            json.dump(_data, _f, indent=2)
    except Exception as _we:
        print(f"   ⚠ Status write failed: {_we}")
    try:
        _jspath = _path.replace("daily_status.json", "daily_status.js")
        with open(_jspath, "w", encoding="utf-8") as _f:
            _f.write("window.WHALE_STATUS=" + json.dumps(_data) + ";")
        # HTML is written by _write_html_snapshot() at end of main — no duplicate write here
    except Exception as _we2:
        print(f"   ⚠ Status JS write failed: {_we2}")
    print(f"   ✓ Status logged → {_key}")


# Deadline windows (minutes after cycle start before we flag as missed)
BOT_DEADLINE_MIN        = 40   # Bot at :00, Watchdog at :30 = 30 min (+10 min Task Scheduler jitter buffer)
STRATEGIST_DEADLINE_MIN = 25   # Strategist at :10; Watchdog at :30 = 20 min gap (+5 min jitter buffer)
TRADER_DEADLINE_MIN     = 16   # Trader at :20
TRADER_CRITICAL_HOURS   = 4    # Escalate to CRITICAL if Trader down this long (4h = 1 missed cycle)


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
    dt = last_log_timestamp(STRATEGIST_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\].*?Strategist run complete")
    if dt is None:
        dt = last_log_timestamp(STRATEGIST_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\]")
    ago = minutes_ago(dt)
    last_str = dt.strftime("%H:%M BKK") if dt else "never"
    ok = (ago is not None and ago <= STRATEGIST_DEADLINE_MIN)
    return ok, last_str, ago


def check_trader():
    # Primary: RUN COMPLETE (successful trade cycle)
    dt = last_log_timestamp(TRADER_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\] RUN COMPLETE")
    # Fallback: any BKK timestamp that is NOT a PAUSED line.
    # Bug fix: if PAUSED is logged AFTER a RUN COMPLETE, scanning all timestamps
    # would pick up the PAUSED timestamp and overwrite the valid RUN COMPLETE dt,
    # making a paused run appear as a successful one.
    dt_any = None
    try:
        with open(TRADER_LOG, "r", encoding="utf-8", errors="replace") as _tf:
            for _line in _tf:
                if "PAUSED" in _line or "paused" in _line:
                    continue  # skip PAUSED lines — they must not overwrite RUN COMPLETE
                _m = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\]", _line)
                if _m:
                    try:
                        _dt = datetime.strptime(_m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=BKK)
                        if dt_any is None or _dt > dt_any:
                            dt_any = _dt
                    except Exception:
                        pass
    except Exception:
        pass
    # Use most recent of RUN COMPLETE and non-PAUSED fallback
    if dt is None or (dt_any and dt_any > dt):
        dt = dt_any
    ago = minutes_ago(dt)
    last_str = dt.strftime("%H:%M BKK") if dt else "never"
    ok = (ago is not None and ago <= TRADER_DEADLINE_MIN)
    return ok, last_str, ago


def check_tracker():
    """Tracker runs every 30 min — flag if last log > 45 min ago.
    Primary: look for BKK-bracketed completion line (requires tracker to emit it).
    Fallback: use daily_status.json 'tracker' key + log mtime."""
    dt = last_log_timestamp(TRACKER_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\].*?Tracker run complete")
    if dt is None:
        dt = last_log_timestamp(TRACKER_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\]")
    # Fallback: tracker uses _mark_done("tracker") → check daily_status.json + log mtime
    if dt is None:
        try:
            _sp = os.path.join(BASE_DIR, "daily_status.json")
            with open(_sp, encoding="utf-8") as _sf:
                _sd = json.load(_sf)
            if _sd.get("tracker") and _sd.get("date") == datetime.now(BKK).date().isoformat():
                # Use tracker_log.txt mtime as proxy for last run time
                _mt = os.path.getmtime(TRACKER_LOG)
                dt = datetime.fromtimestamp(_mt, tz=BKK)
        except Exception:
            pass
    ago = minutes_ago(dt)
    last_str = dt.strftime("%H:%M BKK") if dt else "never"
    ok = (ago is not None and ago <= 45)
    return ok, last_str, ago


def check_monitor():
    """Monitor runs every 2 min — flag if last log > 10 min ago.
    Monitor logs timestamps as [YYYY-MM-DD HH:MM:SS BKK] (with seconds)."""
    # Primary: completion marker with seconds format
    dt = last_log_timestamp(MONITOR_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}):\d{2} BKK\].*?Monitor run complete")
    if dt is None:
        # Fallback: any BKK timestamp (HH:MM:SS format — capture HH:MM only)
        dt = last_log_timestamp(MONITOR_LOG, r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}):\d{2} BKK\]")
    ago = minutes_ago(dt)
    last_str = dt.strftime("%H:%M BKK") if dt else "never"
    ok = (ago is not None and ago <= 10)
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

def build_green_report(now_str, bot_last, strat_last, trade_last, bal_str, bal_updated, paused,
                       tracker_ok=True, tracker_last="unknown", monitor_ok=True, monitor_last="unknown"):
    """All-clear: full team healthy — sent every cycle (Principle 3)."""
    pause_note = "\n⚠️ NOTE: Circuit breaker ACTIVE — orders paused." if paused else ""
    tracker_icon = "✅" if tracker_ok else "⚠️"
    monitor_icon = "✅" if monitor_ok else "⚠️"
    return (
        f"🟢 <b>WHALE-STREAM — 4h Cycle Complete</b>\n"
        f"🕐 {now_str}\n"
        f"\n"
        f"<b>Agent Status:</b>\n"
        f"  ✅ SigBot       — last run {bot_last}\n"
        f"  ✅ Strategist   — last run {strat_last}\n"
        f"  ✅ Trader       — last run {trade_last}\n"
        f"  {tracker_icon} Tracker      — last run {tracker_last}\n"
        f"  {monitor_icon} Monitor      — last run {monitor_last}\n"
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
    """CRITICAL: Trader has been down >4h — maximum urgency (Principle 4+6)."""
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
    # ── Crash guard: Telegram alert if Watchdog dies unexpectedly ──
    import sys as _sys
    def _wdog_excepthook(_et, _ev, _etb):
        _crash_msg = (
            f"🚨 WATCHDOG CRASHED — system health unknown!\n"
            f"Error: {_ev}"
        )
        print(_crash_msg)
        try:
            _mark_done("watchdog", details={"health": "CRASHED"})
        except Exception:
            pass
        try:
            import requests as _rq
            _rq.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": _crash_msg},
                timeout=10,
            )
        except Exception:
            pass
        _sys.__excepthook__(_et, _ev, _etb)
    _sys.excepthook = _wdog_excepthook

    try:
        from mission import print_mission_banner
        print_mission_banner()
    except ImportError:
        pass

    now_bkk = datetime.now(BKK)
    now_str = now_bkk.strftime("%Y-%m-%d %H:%M BKK")
    print(f"[{now_str}] === Watchdog run started ===")

    # ── Run all checks ────────────────────────────────────────
    bot_ok,     bot_last,     bot_ago     = check_bot()
    strat_ok,   strat_last,   strat_ago   = check_strategist()
    trade_ok,   trade_last,   trade_ago   = check_trader()
    tracker_ok, tracker_last, tracker_ago = check_tracker()
    monitor_ok, monitor_last, monitor_ago = check_monitor()
    paused    = os.path.exists(PAUSED_FLAG)
    bal_stale, bal_hours, bal_str, bal_updated = check_balance()

    # ── Build status lines ────────────────────────────────────
    bot_line   = f"{'✅' if bot_ok   else '🚨'} SigBot       last: {bot_last}  ({fmt_ago(bot_ago)})"
    strat_line = f"{'✅' if strat_ok else '🚨'} Strategist   last: {strat_last}  ({fmt_ago(strat_ago)})"
    trade_line = f"{'✅' if trade_ok else '🚨'} Trader       last: {trade_last}  ({fmt_ago(trade_ago)})"

    print(bot_line)
    print(strat_line)
    print(trade_line)

    # ── Check CRITICAL: Trader down >4h (1 missed cycle) ────────
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
        # ── Self-heal: kill stuck Strategist task + relaunch ─────────────
        # Root cause: Python "lost sys.stderr" crash during interpreter shutdown
        # leaves cmd.exe hanging. Task Scheduler sees task as "Running" forever
        # and refuses to start new instances. Fix: kill the stuck process,
        # end the Task Scheduler's "running" record, then relaunch immediately.
        _healed = False
        try:
            # 1. Kill any stuck Python processes running whale_stream_strategist.py
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' "
                 "-and $_.CommandLine -like '*whale_stream_strategist*' } | "
                 "ForEach-Object { $_.Terminate() }"],
                capture_output=True, timeout=15
            )
            # 2. Force-end the stuck Task Scheduler instance record
            subprocess.run(
                ["schtasks", "/End", "/TN", "WhaleStreamStrategist"],
                capture_output=True, timeout=10
            )
            time.sleep(2)
            # 3. Relaunch the Strategist immediately to cover the missed cycle
            subprocess.Popen(
                f'start "" /B "{os.path.join(BASE_DIR, "run_strategist.bat")}"',
                shell=True, cwd=BASE_DIR
            )
            _healed = True
            print("   🔧 Self-heal: killed stuck WhaleStreamStrategist + relaunched")
        except Exception as _she:
            print(f"   ⚠ Self-heal attempt failed: {_she}")

        _heal_note = ("🔧 <b>Self-heal attempted</b> — Strategist relaunched at :30. "
                      "Check next Telegram for Strategist result.\n") if _healed else ""
        issues_with_fixes.append(
            f"🚨 <b>Strategist missed :10 slot</b>  (last: {strat_last}, {fmt_ago(strat_ago)})\n"
            f"{_heal_note}{FIX_STRATEGIST}"
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
            f"→ Normal if Trader is down. Fix Trader first."
        )
    if not tracker_ok:
        issues_with_fixes.append(
            f"⚠️ <b>Tracker may be down</b> (last: {tracker_last})\n"
            f"→ Check Task Scheduler → WhaleStream-Tracker\n"
            f"→ Check tracker_log.txt for errors"
        )
    if not monitor_ok:
        issues_with_fixes.append(
            f"⚠️ <b>Monitor may be down</b> (last: {monitor_last})\n"
            f"→ Check Task Scheduler → WhaleStream-Monitor\n"
            f"→ Check monitor_log.txt for errors"
        )

    # ── Send appropriate Telegram message ────────────────────
    if trader_critical:
        # Highest priority: CRITICAL alert for long Trader outage
        msg = build_critical_alert(now_str, trade_last, trade_ago, bal_str)
        print(f"\n🔴 CRITICAL ESCALATION: Trader down {trade_ago//60}h {trade_ago%60}m")
        send_telegram(msg)
        # Also send amber for the other issues (if any beyond trader + its side-effects)
        other_issues = [i for i in issues_with_fixes
                        if "Trader missed :20 slot" not in i and "CIRCUIT BREAKER" not in i]
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
        msg = build_green_report(now_str, bot_last, strat_last, trade_last, bal_str, bal_updated, paused,
                                 tracker_ok, tracker_last, monitor_ok, monitor_last)
        print(f"\n✅ All agents healthy.")
        print(msg)
        send_telegram(msg)

    _watchdog_health = "CRITICAL" if trader_critical else ("AMBER" if issues_with_fixes else "GREEN")

    # ── Sunday scorer health digest (v47.32) ─────────────────────────────────
    # Every Sunday :30 cycle → send weekly dim-health + score accuracy Telegram.
    if datetime.now(BKK).weekday() == 6:   # Sunday = 6
        try:
            _pm_path_wd = os.path.join(BASE_DIR, "pattern_memory.json")
            with open(_pm_path_wd, "r", encoding="utf-8") as _pmf_wd:
                _pm_wd = json.load(_pmf_wd)
            _dc_wd = _pm_wd.get("dim_correlation", {})
            _sa_wd = _pm_wd.get("score_accuracy", {})

            _dc_labels_wd = {
                "conf_high":   "Conf ≥90%  ",
                "conf_med":    "Conf 75-89%",
                "conf_low":    "Conf <75%  ",
                "mtf_ideal":   "MTF ideal  ",
                "mtf_aligned": "MTF aligned",
                "mtf_neutral": "MTF neutral",
                "mtf_counter": "MTF counter",
                "mtf_sideways":"MTF sideway",
            }
            _dim_lines_wd = []
            for _dk_wd, _dlbl_wd in _dc_labels_wd.items():
                _dv_wd  = _dc_wd.get(_dk_wd, {})
                _dw_wd  = _dv_wd.get("wins", 0)
                _dl_wd  = _dv_wd.get("losses", 0)
                _dn_wd  = _dw_wd + _dl_wd
                if _dn_wd < 10:
                    continue
                _dwr_wd = _dw_wd / _dn_wd * 100
                _dic_wd = "✅" if _dwr_wd >= 60 else ("⚠️" if _dwr_wd >= 45 else "❌")
                _dim_lines_wd.append(
                    f"  {_dic_wd} {_dlbl_wd}: {_dwr_wd:.0f}% WR ({_dn_wd} trades)"
                )

            _sa_lines_wd = []
            for _tier_wd, _rng_wd in [("ELITE","9-10"),("GOOD","7-8"),("MARGINAL","5-6"),("LOW","0-4")]:
                _tv_wd = _sa_wd.get(_tier_wd, {})
                _tc_wd = _tv_wd.get("correct", 0)
                _ti_wd = _tv_wd.get("incorrect", 0)
                _tn_wd = _tc_wd + _ti_wd
                if _tn_wd == 0:
                    continue
                _tpct_wd  = _tc_wd / _tn_wd * 100
                _ticon_wd = "✅" if _tpct_wd >= 55 else ("⚠️" if _tpct_wd >= 45 else "❌")
                _sa_lines_wd.append(
                    f"  {_ticon_wd} {_tier_wd} ({_rng_wd}): {_tpct_wd:.0f}% accuracy ({_tn_wd} trades)"
                )

            # Active scorer_tune escalations?
            _st_note_wd = ""
            try:
                _stp_wd = os.path.join(BASE_DIR, "scorer_tune.json")
                if os.path.exists(_stp_wd):
                    with open(_stp_wd, "r", encoding="utf-8") as _stf_wd:
                        _ste_wd = json.load(_stf_wd)
                    _escl_wd = []
                    if "MTF_COUNTER_PENALTY" in _ste_wd:
                        _escl_wd.append(f"MTF counter penalty → {_ste_wd['MTF_COUNTER_PENALTY']}")
                    if "MTF_SIDEWAYS_PENALTY" in _ste_wd:
                        _escl_wd.append(f"MTF sideways penalty → {_ste_wd['MTF_SIDEWAYS_PENALTY']}")
                    if _escl_wd:
                        _st_note_wd = (
                            "\n\n🔧 <b>Active scorer escalations:</b>\n"
                            + "\n".join(f"  • {e}" for e in _escl_wd)
                        )
            except Exception:
                pass

            _dim_block_wd = "\n".join(_dim_lines_wd) if _dim_lines_wd else "  (fewer than 10 trades per bucket)"
            _sa_block_wd  = "\n".join(_sa_lines_wd)  if _sa_lines_wd  else "  (no score data yet)"

            # ── P&L attribution by signal proxy (v47.33) ──────────────────────
            # Show avg P&L per trade per bucket (conf + MTF) using pnl_total/pnl_count
            # fields now stored in dim_correlation by debrief.
            _pnl_lines_wd = []
            try:
                _pnl_labels_wd = {
                    "conf_high":    "Conf ≥90%  ",
                    "conf_med":     "Conf 75-89%",
                    "conf_low":     "Conf &lt;75%  ",
                    "mtf_ideal":    "MTF ideal  ",
                    "mtf_aligned":  "MTF aligned",
                    "mtf_counter":  "MTF counter",
                    "mtf_sideways": "MTF sideway",
                }
                for _pk_wd, _plbl_wd in _pnl_labels_wd.items():
                    _pv_wd    = _dc_wd.get(_pk_wd, {})
                    _pn_cnt   = _pv_wd.get("pnl_count", 0)
                    _pn_total = _pv_wd.get("pnl_total", 0.0)
                    if _pn_cnt >= 5:   # require at least 5 trades with P&L data
                        _avg_pnl = _pn_total / _pn_cnt
                        _sign    = "+" if _avg_pnl >= 0 else ""
                        _pnl_lines_wd.append(
                            f"  {_plbl_wd}: {_sign}{_avg_pnl:.2f}% avg / trade ({_pn_cnt} trades)"
                        )
            except Exception:
                pass
            _pnl_block_wd = ("\n".join(_pnl_lines_wd)
                             if _pnl_lines_wd else "  (fewer than 5 trades with P&L data per bucket)")

            # ── Probation week-in-review (v47.34) ─────────────────────────────
            # Show coins newly blocked this week + current probation list
            _prob_block_wd = ""
            try:
                _now_wd  = datetime.now(BKK)
                _7d_ago  = _now_wd - timedelta(days=7)
                _newly_blocked_wd = []

                # Coins blocked within the last 7 days
                _bl_path_wd = os.path.join(BASE_DIR, "coin_blocklist_auto.json")
                if os.path.exists(_bl_path_wd):
                    with open(_bl_path_wd, "r", encoding="utf-8") as _blf_wd:
                        _bl_wd = json.load(_blf_wd)
                    _bs_wd = _bl_wd.get("blocked_since", {})
                    for _bk_wd, _bsince_wd in _bs_wd.items():
                        try:
                            _bdt_wd = datetime.fromisoformat(_bsince_wd).replace(tzinfo=BKK) \
                                      if _bsince_wd else None
                        except Exception:
                            _bdt_wd = None
                        if _bdt_wd and _bdt_wd >= _7d_ago:
                            _newly_blocked_wd.append(f"  🚫 {_bk_wd} (since {_bsince_wd[:10]})")

                # Current probation watchlist
                _prob_wl_wd = []
                _wlp_path_wd = os.path.join(BASE_DIR, "blocklist_watchlist.json")
                if os.path.exists(_wlp_path_wd):
                    with open(_wlp_path_wd, "r", encoding="utf-8") as _wlpf_wd:
                        _wlp_wd = json.load(_wlpf_wd)
                    for _wpentry_wd in _wlp_wd.get("watchlist", {}).values():
                        _wpc  = _wpentry_wd.get("coin", "")
                        _wpd  = _wpentry_wd.get("direction", "")
                        _wpt  = _wpentry_wd.get("probation_trades", 3)
                        _wps  = (_wpentry_wd.get("probation_started", "") or "")[:10]
                        if _wpc and _wpd:
                            _prob_wl_wd.append(
                                f"  🔶 {_wpc} {_wpd} — {_wpt} trade(s) left (since {_wps})"
                            )

                _prob_parts = []
                if _newly_blocked_wd:
                    _prob_parts.append(
                        "Newly blocked this week:\n" + "\n".join(_newly_blocked_wd)
                    )
                else:
                    _prob_parts.append("Newly blocked this week: none")
                if _prob_wl_wd:
                    _prob_parts.append(
                        "Currently on probation:\n" + "\n".join(_prob_wl_wd)
                    )
                else:
                    _prob_parts.append("Currently on probation: none")
                _prob_block_wd = "\n\n".join(_prob_parts)
            except Exception:
                _prob_block_wd = "  (probation data unavailable)"

            _sunday_msg = (
                f"📊 <b>WEEKLY SCORER HEALTH DIGEST</b>\n"
                f"🗓 {now_str}\n"
                f"\n"
                f"<b>🔬 Dim Correlation (win rate per signal proxy):</b>\n"
                f"{_dim_block_wd}\n"
                f"\n"
                f"<b>💰 P&amp;L Attribution (avg P&L per trade per proxy):</b>\n"
                f"{_pnl_block_wd}\n"
                f"\n"
                f"<b>🎯 Score Prediction Accuracy:</b>\n"
                f"{_sa_block_wd}"
                f"{_st_note_wd}\n"
                f"\n"
                f"<b>🔶 Probation Week-in-Review:</b>\n"
                f"{_prob_block_wd}\n"
                f"\n"
                f"✅ = ≥60% WR  ⚠️ = 45-59%  ❌ = &lt;45%"
            )
            send_telegram(_sunday_msg)
            print("   📊 Sunday scorer health digest sent.")
        except Exception as _sund_e:
            print(f"   ⚠ Sunday digest failed: {_sund_e}")

    # Build per-agent cycle summary for Daily Checklist hint
    try:
        _wh   = datetime.now(BKK).hour
        _whh  = str((_wh // 4) * 4).zfill(2)
        _wsp  = os.path.join(BASE_DIR, "daily_status.json")
        with open(_wsp, encoding="utf-8") as _wsf:
            _wds = json.load(_wsf)
        # SigBot: actual coin names
        _sb   = _wds.get(f"sigbot_{_whh}_details", {})
        _sb_ln = ", ".join(_sb.get("longs",  []))
        _sb_sn = ", ".join(_sb.get("shorts", []))
        if _sb_ln or _sb_sn:
            _sb_str = f"🟢{_sb_ln or '—'} | 🔴{_sb_sn or '—'}"
        elif _wds.get(f"sigbot_{_whh}"):
            _sb_str = "✓"
        else:
            _sb_str = "⚠ missed"
        # Strategist: approved / vetoed coin names (or context when queue empty)
        _st    = _wds.get(f"strategist_{_whh}_details", {})
        _st_a  = _st.get("approved", [])
        _st_v  = _st.get("vetoed",   [])
        if _st_a or _st_v:
            _st_an = ", ".join(_st_a) if _st_a else "—"
            _st_vn = ", ".join(_st_v) if _st_v else "—"
            _st_str = f"✅{_st_an} | ❌{_st_vn}"
        elif paused:
            _st_str = "⏸ CB"
        elif _wds.get(f"strategist_{_whh}"):
            _st_str = "queue empty"
        else:
            _st_str = "⚠ missed"
        # Trader: N placed / paused
        _tr    = _wds.get(f"trader_{_whh}_details", {})
        _tr_p  = len(_tr.get("placed",  []))
        _tr_cb = any("PAUSED" in s for s in _tr.get("skipped", []))
        if _tr_cb:
            _tr_str = "⏸ CB"
        elif _tr_p > 0:
            _tr_str = f"{_tr_p} placed"
        elif _tr:
            _tr_str = "— none"
        elif _wds.get(f"trader_{_whh}"):
            _tr_str = "✓"
        else:
            _tr_str = "⚠ missed"
        _cycle_summary = f"Bot:{_sb_str}  Strat:{_st_str}  Trader:{_tr_str}"
    except Exception as _wce:
        _cycle_summary = ""
        print(f"   ⚠ Watchdog cycle summary failed: {_wce}")

    _mark_done("watchdog", details={"health": _watchdog_health, "cycle_summary": _cycle_summary})
    _write_html_snapshot()   # <-- write definitive WS_EMBEDDED blob after all agents done
    print(f"\n[{now_str}] Watchdog complete.")
