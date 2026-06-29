"""
╔══════════════════════════════════════════════════════════════════╗
║  WHALE-STREAM STATUS GAP CHECKER                                 ║
║                                                                  ║
║  Runs every 4h at :45 BKK (5 min after Watchdog finishes)       ║
║  Reads daily_status.json and checks every agent that should      ║
║  have completed by now.                                          ║
║                                                                  ║
║  Sends Telegram:                                                 ║
║    ✅ All green — all expected completions confirmed              ║
║    ⚠️  Gap alert — lists exactly which agents didn't tick         ║
║                                                                  ║
║  Also pings 127.0.0.1:8765 to verify status server is alive.    ║
║                                                                  ║
║  Schedule: ADD_STATUS_CHECK_TASK.bat (every 4h at :45)           ║
╚══════════════════════════════════════════════════════════════════╝
"""

# ══════════════════════════════════════════════════════════════════
# WHALE-STREAM CONSTITUTION — 7 PRINCIPLES (applies to every agent)
# ══════════════════════════════════════════════════════════════════
# P1  Clear isolated roles — each agent owns one job, never another's
# P2  Continuous 4h schedule — Bot:00 Strategist:10 Trader:20 Watchdog:30
#     Tracker every 30m | Monitor every 2m | Briefing 07:00 daily
# P3  Report after every cycle — state what worked and what didn't
# P4  24/7 proactive Telegram — never wait for the human to ask
# P5  Multi-agent consensus — Debrief cross-checks Strategist vs actual outcome
# P6  High-risk discipline — no vague signals; plan every entry precisely
# P7  Mission — every trade generates capital to help those in need
# ══════════════════════════════════════════════════════════════════

import os
import io
import sys
import json
import requests
from datetime import datetime, timezone, timedelta

# Force UTF-8 output
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# ── Config ─────────────────────────────────────────────────────────
try:
    from local_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    import os as _os
    TELEGRAM_BOT_TOKEN = _os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = _os.getenv("TELEGRAM_CHAT_ID", "")

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(BASE_DIR, "daily_status.json")
STATUS_URL  = "http://127.0.0.1:8765/daily_status.json"  # explicit IPv4 — matches server bind (v47.7 fix)

BKK = timezone(timedelta(hours=7))

# Agent definitions
CYCLE_AGENTS  = ["sigbot", "strategist", "trader", "watchdog"]
STATIC_AGENTS = ["tracker", "monitor", "briefing"]

# Human-readable labels (for alert messages)
AGENT_LABEL = {
    "sigbot":      "SigBot     (scans coins :00)",
    "strategist":  "Strategist (approves    :10)",
    "trader":      "Trader     (executes    :20)",
    "watchdog":    "Watchdog   (health chk  :30)",
    "tracker":     "Tracker    (30-min resolver)",
    "monitor":     "Monitor    (2-min watcher)",
    "briefing":    "Briefing   (07:00 daily)",
}

# Task Scheduler task names (for fix instructions)
AGENT_TASK = {
    "sigbot":      "WhaleStream-Bot",
    "strategist":  "WhaleStreamStrategist",
    "trader":      "WhaleStream-Trader",
    "watchdog":    "WhaleStreamWatchdog",
    "tracker":     "WhaleStream-Tracker",
    "monitor":     "WhaleStream-Monitor",
    "briefing":    "WhaleStream-Briefing",
}


# ── Telegram ───────────────────────────────────────────────────────
def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"   ⚠ Telegram failed: {e}")


# ── Status server health ───────────────────────────────────────────
def check_status_server():
    """Returns True if status_server.py is alive on 127.0.0.1:8765."""
    try:
        r = requests.get(STATUS_URL + "?ping=1", timeout=3)
        return r.status_code < 500
    except Exception:
        return False


# ── Load daily_status.json ─────────────────────────────────────────
def load_status():
    """Load today's status JSON. Returns empty dict if missing or stale."""
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        today = datetime.now(BKK).date().isoformat()
        if data.get("date") != today:
            return {}   # file is from a previous day — fresh slate
        return data
    except Exception:
        return {}


# ── Determine expected completions ────────────────────────────────
def expected_cycles(now_bkk):
    """
    Return list of HH strings for cycles fully expected to be done.
    A cycle at hour H is expected done if more than 35 min have passed
    since H:00 (Watchdog runs at H:30 and finishes by ~H:35).
    """
    h, m = now_bkk.hour, now_bkk.minute
    done = []
    for slot in [0, 4, 8, 12, 16, 20]:
        # minutes elapsed since this cycle started
        elapsed = (h - slot) * 60 + m
        if elapsed >= 35:
            done.append(str(slot).zfill(2))
    return done


# ── Main check ─────────────────────────────────────────────────────
def run_check():
    now      = datetime.now(BKK)
    now_str  = now.strftime("%Y-%m-%d %H:%M BKK")
    today    = now.date().isoformat()

    print(f"[{now_str}] Status gap check starting...")

    data   = load_status()
    cycles = expected_cycles(now)

    gaps   = []    # missing completions
    ok     = []    # confirmed completions

    # ── Check cycle agents ─────────────────────────────────────────
    for hh in cycles:
        for agent in CYCLE_AGENTS:
            key = f"{agent}_{hh}"
            if data.get(key):
                ok.append(key)
            else:
                gaps.append((key, agent, hh))

    # ── Check always-running agents ────────────────────────────────
    for agent in STATIC_AGENTS:
        # Briefing only runs at 07:00 BKK — don't flag as gap before it's scheduled
        if agent == "briefing" and now.hour < 7:
            ok.append(agent)   # treat as OK until 07:00
            continue
        if data.get(agent):
            ok.append(agent)
        else:
            gaps.append((agent, agent, None))

    server_up = check_status_server()
    total_exp = len(cycles) * len(CYCLE_AGENTS) + len(STATIC_AGENTS)
    server_badge = "🟢 LIVE" if server_up else "🔴 OFFLINE — run ADD_STATUS_SERVER_TASK.bat"

    # ── Build and send Telegram message ───────────────────────────
    if not gaps:
        # All green
        cycle_str = ", ".join(cycles) if cycles else "none yet"
        msg = (
            f"✅ <b>WHALE-STREAM — ALL AGENTS ON TRACK</b>\n"
            f"  Check time : {now_str}\n"
            f"  Cycles done: {cycle_str}\n"
            f"  Completions: {len(ok)}/{total_exp} ✓\n"
            f"  Status srv : {server_badge}"
        )
        print(f"✅ All {len(ok)}/{total_exp} completions confirmed.")
    else:
        # Build gap lines grouped by cycle
        gap_by_cycle = {}
        static_gaps  = []
        for key, agent, hh in gaps:
            if hh:
                gap_by_cycle.setdefault(hh, []).append(agent)
            else:
                static_gaps.append(agent)

        lines = []
        for hh in sorted(gap_by_cycle):
            missing = gap_by_cycle[hh]
            lines.append(f"\n  <b>{hh}:xx cycle</b> — missing:")
            for a in missing:
                lines.append(f"    ❌ {AGENT_LABEL[a]}")
                lines.append(f"       → Task Scheduler: <code>{AGENT_TASK[a]}</code> → Run")

        if static_gaps:
            lines.append("\n  <b>Always-running</b> — missing:")
            for a in static_gaps:
                lines.append(f"    ❌ {AGENT_LABEL[a]}")
                lines.append(f"       → Task Scheduler: <code>{AGENT_TASK[a]}</code> → Run")

        msg = (
            f"⚠️ <b>WHALE-STREAM — AGENT GAPS DETECTED</b>\n"
            f"  Check time : {now_str}\n"
            f"  Missing    : {len(gaps)}/{total_exp} completions\n"
            + "\n".join(lines) + "\n\n"
            f"  Status srv : {server_badge}"
        )
        print(f"⚠️ {len(gaps)} gap(s) detected: {[g[0] for g in gaps]}")

    send_telegram(msg)
    print(f"[{now_str}] Status check complete.\n")


# ── Entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        from mission import print_mission_banner
        print_mission_banner()
    except ImportError:
        pass
    run_check()
