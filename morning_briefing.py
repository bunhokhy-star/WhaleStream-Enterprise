"""
╔══════════════════════════════════════════════════════════════╗
║       WHALE-STREAM MORNING BRIEFING                          ║
║                                                              ║
║  Sends a daily Telegram summary of system status every       ║
║  morning at 7:00 AM BKK time (via Task Scheduler).           ║
║                                                              ║
║  Reads:                                                      ║
║    bybit_balance.json  — wallet balance                      ║
║    monitor_state.json  — open positions                      ║
║    analysis_shorts.txt — win-rate / gate status              ║
║    monitor_log.txt     — last fill / heartbeat time          ║
║    trader_log.txt      — yesterday's order activity          ║
║                                                              ║
║  HOW TO RUN:                                                 ║
║    py morning_briefing.py                                    ║
╚══════════════════════════════════════════════════════════════╝
"""

import io
import sys
import os
import json
import re
import requests
from datetime import datetime, timezone, timedelta

# ── Force UTF-8 output (prevents UnicodeEncodeError on Windows CP1252 / Task Scheduler) ──
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# ── Credentials ───────────────────────────────────────────────
try:
    from local_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    import os as _os
    TELEGRAM_BOT_TOKEN = _os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = _os.getenv("TELEGRAM_CHAT_ID", "")

# ── Paths ─────────────────────────────────────────────────────
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
BALANCE_FILE     = os.path.join(BASE_DIR, "bybit_balance.json")
STATE_FILE       = os.path.join(BASE_DIR, "monitor_state.json")
ANALYSIS_FILE    = os.path.join(BASE_DIR, "analysis_shorts.txt")
MONITOR_LOG      = os.path.join(BASE_DIR, "monitor_log.txt")
TRADER_LOG       = os.path.join(BASE_DIR, "trader_log.txt")

# ── Go-Live target ────────────────────────────────────────────
GO_LIVE_DATE = datetime(2026, 7, 1, tzinfo=timezone(timedelta(hours=7)))

BKK = timezone(timedelta(hours=7))


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def safe_read(path, mode="r", encoding="utf-8"):
    """Return file contents or empty string if missing."""
    try:
        with open(path, mode, encoding=encoding, errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def read_last_lines(path, n=100):
    """Return the last n lines of a file as a list."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()[-n:]
    except Exception:
        return []


def progress_bar(filled_count, total_bars=10):
    """Return a 10-char block progress bar."""
    filled = max(0, min(total_bars, filled_count))
    return "█" * filled + "░" * (total_bars - filled)


# ─────────────────────────────────────────────────────────────
# 1. BALANCE
# ─────────────────────────────────────────────────────────────

def parse_balance():
    """Return dict with balance fields. Falls back to zeros on error."""
    defaults = {"balance": 0.0, "start_balance": 500.0, "updated_at": "unknown", "open_positions": 0}
    raw = safe_read(BALANCE_FILE)
    if not raw:
        return defaults
    try:
        data = json.loads(raw)
        defaults.update(data)
        return defaults
    except Exception:
        return defaults


# ─────────────────────────────────────────────────────────────
# 2. OPEN POSITIONS  (from monitor_state.json)
# ─────────────────────────────────────────────────────────────

def parse_positions():
    """Return list of (symbol, side, size, avgPrice, unrealisedPnl) tuples."""
    raw = safe_read(STATE_FILE)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        positions = data.get("positions", {})
        result = []
        for symbol, info in positions.items():
            result.append({
                "symbol":       symbol,
                "side":         info.get("side", "Buy"),
                "size":         info.get("size", 0.0),
                "avgPrice":     info.get("avgPrice", 0.0),
                "unrealisedPnl": info.get("unrealisedPnl", 0.0),
            })
        return result
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────
# 3. ANALYSIS  (from analysis_shorts.txt summary block)
# ─────────────────────────────────────────────────────────────

def parse_analysis():
    """
    Parse the summary block at the top of analysis_shorts.txt.

    Looks for lines like:
      Total resolved    :   51  (WIN+LOSS, excl EXPIRED)
      LONG win rate     : 51.9%  (14W/13L)
      SHORT win rate    : 25.0% ⚠️ REPAIR MODE  (6W/18L)
      Gate 1            : ❌ 51/150
      Profit Factor     : 2.16x  (need > 1.0 to be profitable)
    """
    text = safe_read(ANALYSIS_FILE)

    result = {
        "resolved":     0,
        "long_wr":      "N/A",
        "long_w":       0,
        "long_l":       0,
        "short_wr":     "N/A",
        "short_w":      0,
        "short_l":      0,
        "gate1_done":   0,
        "gate1_target": 150,
        "gate2_pass":   False,
        "gate2_pf":     None,
        "gate3_pass":   False,
        "gate3_wr":     None,
        "repair_mode":  False,
        "total_w":      0,
        "total_l":      0,
        "total_wr":     "N/A",
    }

    if not text:
        return result

    # Total resolved
    m = re.search(r"Total resolved\s*:\s*(\d+)", text)
    if m:
        result["resolved"] = int(m.group(1))

    # LONG win rate  :  51.9%  (14W/13L)
    m = re.search(r"LONG win rate\s*:\s*([\d.]+)%[^\(]*\((\d+)W/(\d+)L\)", text)
    if m:
        result["long_wr"] = m.group(1) + "%"
        result["long_w"]  = int(m.group(2))
        result["long_l"]  = int(m.group(3))

    # SHORT win rate :  25.0% ... (6W/18L)
    m = re.search(r"SHORT win rate\s*:\s*([\d.]+)%[^\(]*\((\d+)W/(\d+)L\)", text)
    if m:
        result["short_wr"] = m.group(1) + "%"
        result["short_w"]  = int(m.group(2))
        result["short_l"]  = int(m.group(3))

    # Gate 1  :  ❌ 51/150  (or ✅)
    m = re.search(r"Gate 1\s*:\s*[^\d]*(\d+)/(\d+)", text)
    if m:
        result["gate1_done"]   = int(m.group(1))
        result["gate1_target"] = int(m.group(2))

    # Profit Factor — indicates Gate 2
    m = re.search(r"Profit Factor\s*:\s*([\d.]+)x", text)
    if m:
        result["gate2_pf"] = float(m.group(1))

    # Gate 2 pass
    if "GATE 2 STATUS: PASS" in text or "✅ GATE 2" in text:
        result["gate2_pass"] = True

    # Gate 3 / SHORT WR
    # Uses the SHORT WR already parsed; pass = 50%+ and >= 20 SHORTs
    short_total = result["short_w"] + result["short_l"]
    short_wr_val = float(result["short_wr"].replace("%", "")) if result["short_wr"] != "N/A" else 0.0
    result["gate3_pass"] = (short_wr_val >= 50.0 and short_total >= 20)
    result["gate3_wr"] = result["short_wr"]

    # Repair mode
    if "REPAIR MODE" in text:
        result["repair_mode"] = True

    # Totals
    result["total_w"] = result["long_w"] + result["short_w"]
    result["total_l"] = result["long_l"] + result["short_l"]
    total = result["total_w"] + result["total_l"]
    if total > 0:
        result["total_wr"] = f"{result['total_w'] / total * 100:.1f}%"

    return result


# ─────────────────────────────────────────────────────────────
# 4. MONITOR HEARTBEAT  (last timestamp in monitor_log.txt)
# ─────────────────────────────────────────────────────────────

def parse_monitor_heartbeat():
    """
    Return (last_run_dt, minutes_ago) from the most recent timestamp
    in monitor_log.txt.  Timestamps look like:
      [2026-06-22 22:55:01 BKK]
    """
    raw = safe_read(MONITOR_LOG)
    if not raw:
        return None, None

    # Find all timestamps in the log
    pattern = r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) BKK\]"
    matches  = re.findall(pattern, raw)
    if not matches:
        return None, None

    last_str = matches[-1]
    try:
        last_dt = datetime.strptime(last_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BKK)
        now_bkk = datetime.now(BKK)
        minutes_ago = int((now_bkk - last_dt).total_seconds() / 60)
        return last_dt, minutes_ago
    except Exception:
        return None, None


def parse_last_fills_24h():
    """
    Scan monitor_log.txt for fill/close events in the last 24h.
    Lines containing "✅ Position closed" or "filled" count as fills.
    Returns count of such lines.
    """
    raw = safe_read(MONITOR_LOG)
    if not raw:
        return 0

    now_bkk   = datetime.now(BKK)
    cutoff    = now_bkk - timedelta(hours=24)
    fill_pat  = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) BKK\].*?(closed|filled|WIN|LOSS|resolved)", re.IGNORECASE)
    ts_pat    = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) BKK\]")

    fills = 0
    for line in raw.splitlines():
        m = fill_pat.search(line)
        if not m:
            continue
        ts_m = ts_pat.search(line)
        if not ts_m:
            continue
        try:
            ts = datetime.strptime(ts_m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=BKK)
        except Exception:
            continue
        if ts >= cutoff:
            fills += 1

    return fills


# ─────────────────────────────────────────────────────────────
# 5. TRADER ACTIVITY (last 100 lines of trader_log.txt)
# ─────────────────────────────────────────────────────────────

def parse_trader_activity():
    """
    Read last 100 lines of trader_log.txt.

    Counts:
      orders_placed  — lines containing '✅ Order placed!'
      orders_failed  — lines containing '❌ Order failed' or '❌ Order'
      runs_complete  — RUN COMPLETE lines (to detect last run time)
      last_run_str   — timestamp of most recent RUN COMPLETE

    Returns a dict.
    """
    lines = read_last_lines(TRADER_LOG, 100)
    now_bkk  = datetime.now(BKK)
    yesterday = (now_bkk - timedelta(days=1)).strftime("%Y-%m-%d")

    orders_placed = 0
    orders_failed = 0
    skipped       = 0
    last_run_str  = None
    last_run_dt   = None
    placed_symbols = []

    for line in lines:
        if "✅ Order placed!" in line:
            orders_placed += 1
        if "❌ Order failed" in line or ("❌" in line and "Order" in line):
            orders_failed += 1
        if "SKIP" in line and "REPAIR MODE" in line:
            skipped += 1

        # RUN COMPLETE — [2026-06-21 22:20 BKK] RUN COMPLETE
        m = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) BKK\] RUN COMPLETE", line)
        if m:
            last_run_str = m.group(1)
            try:
                last_run_dt = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M").replace(tzinfo=BKK)
            except Exception:
                pass

        # Collect symbol names from placed orders
        m2 = re.search(r"── ([A-Z0-9]+) (LONG|SHORT)", line)
        if m2 and "✅ Order placed!" in "".join(lines[max(0, lines.index(line)-3):lines.index(line)+1]):
            placed_symbols.append(m2.group(1))

    # Estimate next run (~2h interval is typical for the scheduler)
    next_run_str = "unknown"
    if last_run_dt:
        next_dt = last_run_dt + timedelta(hours=2)
        mins_until = int((next_dt - now_bkk).total_seconds() / 60)
        if mins_until > 0:
            if mins_until >= 60:
                next_run_str = f"~{mins_until // 60}h {mins_until % 60}m"
            else:
                next_run_str = f"~{mins_until}m"
        else:
            next_run_str = "due now"

    return {
        "orders_placed":   orders_placed,
        "orders_failed":   orders_failed,
        "skipped_repair":  skipped,
        "last_run_str":    last_run_str or "unknown",
        "next_run_str":    next_run_str,
    }


# ─────────────────────────────────────────────────────────────
# BUILD MESSAGE
# ─────────────────────────────────────────────────────────────

def build_message():
    now_bkk   = datetime.now(BKK)
    date_str  = now_bkk.strftime("%Y-%m-%d %H:%M BKK")

    # Days to Go-Live
    delta_days = (GO_LIVE_DATE - now_bkk).days
    if delta_days < 0:
        days_line = "🚀 GO-LIVE REACHED"
    elif delta_days == 0:
        days_line = "TODAY is Go-Live!"
    else:
        days_line = f"{delta_days} days to Go-Live"

    # ── Data ──
    bal      = parse_balance()
    positions = parse_positions()
    analysis = parse_analysis()
    monitor_dt, monitor_ago = parse_monitor_heartbeat()
    fills_24h = parse_last_fills_24h()
    trader   = parse_trader_activity()

    # ── Balance block ──
    total_bal    = bal.get("balance", 0.0)
    start_bal    = bal.get("start_balance", 500.0)
    bal_updated  = bal.get("updated_at", "unknown")
    unreal_pnl   = sum(p["unrealisedPnl"] for p in positions)
    margin_in_use = len(positions) * 20.0  # $20 margin per position at 10x
    available_bal = total_bal - margin_in_use
    pnl_sign = "+" if unreal_pnl >= 0 else ""

    # ── Capital health ──
    drawdown_pct = (start_bal - total_bal) / start_bal * 100 if start_bal > 0 else 0.0
    if drawdown_pct >= 15:
        gate4_line = f"  Gate 4: 🚨 BREACH — {drawdown_pct:.1f}% drawdown (limit 15%)"
    elif drawdown_pct >= 12:
        gate4_line = f"  Gate 4: ⚠️ WARNING — {drawdown_pct:.1f}% drawdown (limit 15%)"
    elif drawdown_pct >= 8:
        gate4_line = f"  Gate 4: 🟡 Monitoring — {drawdown_pct:.1f}% drawdown (limit 15%)"
    else:
        gate4_line = f"  Gate 4: ✅ OK — {drawdown_pct:.1f}% drawdown (limit 15%)"

    # ── Flag files ──
    paused_flag       = os.path.exists(os.path.join(BASE_DIR, "paused.flag"))
    repair_flag       = os.path.exists(os.path.join(BASE_DIR, "short_repair.flag"))
    conservative_flag = os.path.exists(os.path.join(BASE_DIR, "short_conservative.flag"))

    # ── Size scaling (v46.42) ──
    if drawdown_pct >= 12:
        size_scale_pct = 60
    elif drawdown_pct >= 8:
        size_scale_pct = 75
    else:
        size_scale_pct = 100

    # ── Critical alerts ──
    alert_lines = []
    if paused_flag:
        alert_lines.append("🚨 CIRCUIT BREAKER ACTIVE — run CLEAR_PAUSE.bat to resume!")
    if drawdown_pct >= 15:
        alert_lines.append(f"🔴 GATE 4 BREACHED — {drawdown_pct:.1f}% drawdown exceeds 15% limit!")
    elif drawdown_pct >= 12:
        alert_lines.append(f"⚠️ DRAWDOWN WARNING — {drawdown_pct:.1f}% (approaching Gate 4 limit of 15%)")
    if paused_flag:
        alert_lines.append(f"⚠️ Balance shown may be STALE (written at {bal_updated}, trader paused)")

    # ── Gate 1 bar ──
    g1_done   = analysis["gate1_done"]
    g1_target = analysis["gate1_target"]
    bar_filled = int(g1_done / g1_target * 10)
    g1_bar    = progress_bar(bar_filled)
    g1_pct    = f"{g1_done / g1_target * 100:.0f}%"

    # ── Gate 2 ──
    if analysis["gate2_pass"]:
        pf_str   = f"{analysis['gate2_pf']:.2f}×" if analysis["gate2_pf"] else "PASS"
        gate2_line = f"  Gate 2: ✅ LONG P&L PASS (PF {pf_str})"
    else:
        pf_str   = f"{analysis['gate2_pf']:.2f}×" if analysis["gate2_pf"] else "N/A"
        gate2_line = f"  Gate 2: ❌ LONG P&L (PF {pf_str})"

    # ── Gate 3 ──
    short_wr_str = analysis["short_wr"]
    if analysis["gate3_pass"]:
        gate3_line = f"  Gate 3: ✅ SHORT WR {short_wr_str}"
    else:
        mode_tag = " (REPAIR MODE)" if analysis["repair_mode"] else ""
        gate3_line = f"  Gate 3: ❌ SHORT WR {short_wr_str}{mode_tag}"

    # ── Gate 6 (profitable weeks) — placeholder; no weekly tracker file yet ──
    gate6_line = "  Gate 6: ❌ 0/3 profitable weeks"

    # ── Win rates ──
    long_label  = f"{analysis['long_wr']:>6}  ({analysis['long_w']}W / {analysis['long_l']}L)"
    short_tag   = " 🔧 REPAIR" if analysis["repair_mode"] else ""
    short_label = f"{analysis['short_wr']:>6}  ({analysis['short_w']}W / {analysis['short_l']}L){short_tag}"
    total_label = f"{analysis['total_wr']:>6}  ({analysis['total_w']}W / {analysis['total_l']}L)"

    # ── Positions block ──
    pos_count = len(positions)
    pos_lines = []
    for p in positions:
        sym   = p["symbol"].replace("USDT", "")
        side  = p["side"]
        size  = p["size"]
        price = p["avgPrice"]
        size_str  = f"{size:.0f}" if size == int(size) else f"{size:.2f}"
        price_str = f"{price:.4g}"
        pos_lines.append(f"  {sym:<10} {side:<4} {size_str:>8} @ {price_str}")

    # ── Yesterday activity ──
    orders_placed = trader["orders_placed"]
    orders_failed = trader["orders_failed"]
    skipped_rep   = trader["skipped_repair"]
    activity_summary = (
        f"  Orders placed: {orders_placed}"
        + (f" | Failed: {orders_failed}" if orders_failed else "")
        + (f" | Skipped (repair): {skipped_rep}" if skipped_rep else "")
        + f"\n  Fills in last 24h: {fills_24h}"
    )

    # ── Monitor heartbeat ──
    if monitor_ago is not None:
        if monitor_ago < 60:
            ago_str = f"{monitor_ago} min ago"
        else:
            ago_str = f"{monitor_ago // 60}h {monitor_ago % 60}m ago"
        monitor_status = f"✅ Running (last: {ago_str})"
    else:
        monitor_status = "❓ Unknown (no log)"

    # ── Trader status ──
    if paused_flag:
        trader_status = "🚨 PAUSED — circuit breaker active (run CLEAR_PAUSE.bat)"
    else:
        trader_status = f"✅ Running (next: {trader['next_run_str']})"

    # ── Assemble message ──
    lines = [
        f"🌅 WHALE-STREAM MORNING BRIEFING",
        f"{date_str} | {days_line}",
    ]

    # Critical alerts at top
    if alert_lines:
        lines.append("")
        lines.append("⚠️ ALERTS")
        for a in alert_lines:
            lines.append(f"  {a}")

    lines += [
        "",
        "💰 BYBIT BALANCE",
        f"  Total:      ${total_bal:,.2f}  (drawdown: {drawdown_pct:.1f}%)",
        f"  Available:  ${available_bal:,.2f}",
        f"  In Margin:  ${margin_in_use:,.2f}",
        f"  Unreal P&L: {pnl_sign}${unreal_pnl:,.2f}",
        f"  Size scale: {size_scale_pct}%  (v46.42 drawdown protection)",
        f"  Updated:    {bal_updated}",
        "",
        "📊 GATE PROGRESS",
        f"  Gate 1: {g1_done}/{g1_target}  {g1_bar} {g1_pct}",
        gate2_line,
        gate3_line,
        gate4_line,
        gate6_line,
        "",
        "📈 RUNNING WIN RATE",
        f"  LONG:  {long_label}",
        f"  SHORT: {short_label}",
        f"  Total: {total_label}",
        "",
        "🚩 SYSTEM FLAGS",
        f"  Circuit breaker: {'🚨 ACTIVE' if paused_flag else '✅ clear'}",
        f"  SHORT repair:    {'🔧 ACTIVE' if repair_flag else '✅ clear'}",
        f"  SHORT conserv:   {'⚠️ ACTIVE' if conservative_flag else '✅ clear'}",
        "",
        f"🏦 OPEN POSITIONS ({pos_count})",
    ]
    lines.extend(pos_lines if pos_lines else ["  (none)"])
    lines += [
        "",
        "⚡ YESTERDAY ACTIVITY",
        activity_summary,
        "",
        f"🔄 Monitor: {monitor_status}",
        f"🤖 Trader:  {trader_status}",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# SEND TELEGRAM
# ─────────────────────────────────────────────────────────────

def send_telegram(text):
    url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "",   # plain text — emojis pass through fine
    }
    try:
        resp = requests.post(url, data=data, timeout=15)
        if resp.status_code == 200 and resp.json().get("ok"):
            print("✅ Briefing sent to Telegram.")
        else:
            print(f"❌ Telegram error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"❌ Telegram request failed: {e}")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    now_bkk  = datetime.now(BKK)
    print(f"[{now_bkk.strftime('%Y-%m-%d %H:%M:%S BKK')}] Running morning briefing...")

    msg = build_message()

    # Also print to stdout (captured in briefing_log.txt by run_briefing.bat)
    print("\n── BRIEFING PREVIEW ────────────────────────────────────")
    print(msg)
    print("────────────────────────────────────────────────────────\n")

    send_telegram(msg)
    print("Done.")
