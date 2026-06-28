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

import io
import sys
import os
import json
import re
import subprocess
import requests
from datetime import datetime, timezone, timedelta

# ── Force UTF-8 output (prevents UnicodeEncodeError on Windows CP1252 / Task Scheduler) ──
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


# ── Self-tick helper (writes completion to daily_status.json) ────
def _mark_done(agent_name, details=None):
    """Mark this agent done for the current cycle in daily_status.json."""
    import json, datetime
    _path  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_status.json")
    _today = datetime.date.today().isoformat()
    _h     = datetime.datetime.now().hour
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
        _jspath = _path.replace("daily_status.json", "daily_status.js")
        with open(_jspath, "w", encoding="utf-8") as _f:
            _f.write("window.WHALE_STATUS=" + json.dumps(_data) + ";")
        import re as _re
        _html_path = os.path.join(os.path.dirname(_path), "To do list", "Daily Checklist.html")
        with open(_html_path, encoding="utf-8") as _hf:
            _html = _hf.read()
        _inject = "var WS_EMBEDDED=" + json.dumps(_data, separators=(',', ':')) + ";"
        _html = _re.sub(r'var WS_EMBEDDED=\{[^;]*\};', _inject, _html)
        with open(_html_path, "w", encoding="utf-8") as _hf:
            _hf.write(_html)
    except Exception:
        pass


# ── Credentials ───────────────────────────────────────────────
try:
    from local_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    import os as _os
    TELEGRAM_BOT_TOKEN = _os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = _os.getenv("TELEGRAM_CHAT_ID", "")

# ── Google Sheets ─────────────────────────────────────────────
GOOGLE_SHEET_ID       = "1R21mkduSpbki2HmlNJMHM95-LkGS0q-AKHE1HVIfMmI"
GOOGLE_CREDENTIALS_FILE = "google_credentials.json"
# Column indices (0-based) — must match whale_stream_tracker.py
_COL_STATUS      = 11
_COL_PNL         = 15
_COL_RESOLVED_AT = 16

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
# MARKET REGIME FETCH (BTC 4h SMA)
# ─────────────────────────────────────────────────────────────

def get_btc_market_bias():
    """
    Fetch BTC market bias from Bybit V5 kline API (no API key needed).
    Returns (bias, current_price, sma20, pct_from_sma).
    bias = "BEARISH" / "BULLISH" / "NEUTRAL"

    GOLDEN RULE: trade WITH the trend.
      BEARISH → SHORT only.  BULLISH → LONG only.  NEUTRAL → both.
    """
    try:
        r = requests.get(
            "https://api.bybit.com/v5/market/kline",
            params={"category": "linear", "symbol": "BTCUSDT", "interval": "240", "limit": "21"},
            timeout=10,
        )
        data = r.json()
        if data.get("retCode") != 0:
            return "NEUTRAL", None, None, None
        candles = data["result"]["list"]
        if len(candles) < 21:
            return "NEUTRAL", None, None, None
        closes  = [float(c[4]) for c in candles[1:21]]
        sma20   = sum(closes) / 20
        current = float(candles[0][4])
        pct     = (current - sma20) / sma20 * 100
        bias    = "BEARISH" if pct < -2.0 else ("BULLISH" if pct > 2.0 else "NEUTRAL")
        return bias, current, sma20, pct
    except Exception:
        return "NEUTRAL", None, None, None


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

    # Estimate next run (~4h interval is typical for the scheduler)
    next_run_str = "unknown"
    if last_run_dt:
        next_dt = last_run_dt + timedelta(hours=4)
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
# 6. YESTERDAY'S P&L  (from Google Sheets resolved_at column)
# ─────────────────────────────────────────────────────────────

def parse_yesterday_pnl():
    """
    Read Google Sheets and return dict with yesterday's resolved trade stats.
    'Yesterday' = BKK date (UTC+7) for rows where resolved_at starts with that date.

    Returns:
        {
            "count": int,     # total resolved trades yesterday
            "wins":  int,
            "losses": int,
            "net_pnl": float, # sum of pnl_pct values (% at 10x leverage)
        }
    or None if Sheets is unavailable.
    """
    try:
        from google.oauth2.service_account import Credentials
        import gspread
    except ImportError:
        return None

    try:
        creds_path = os.path.join(BASE_DIR, GOOGLE_CREDENTIALS_FILE)
        if not os.path.exists(creds_path):
            return None
        # Use google.oauth2 directly — bypasses gspread.auth which fails on some Python 3.14 setups
        from google.oauth2.service_account import Credentials as _GCreds
        from gspread.client import Client as _GClient
        _SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = _GCreds.from_service_account_file(creds_path, scopes=_SCOPES)
        client = _GClient(auth=creds)
        sheet  = client.open_by_key(GOOGLE_SHEET_ID).sheet1
        rows   = sheet.get_all_values()
    except Exception:
        return None

    now_bkk   = datetime.now(BKK)
    yesterday  = (now_bkk - timedelta(days=1)).strftime("%Y-%m-%d")

    wins = 0
    losses = 0
    net_pnl = 0.0

    for row in rows[1:]:  # skip header row
        while len(row) < 17:
            row.append("")
        status      = row[_COL_STATUS].strip().upper()
        resolved_at = row[_COL_RESOLVED_AT].strip()
        pnl_raw     = row[_COL_PNL].strip()

        if status not in ("WIN", "LOSS"):
            continue
        if not resolved_at.startswith(yesterday):
            continue

        # Parse pnl_pct — stored as e.g. "+12.50%" or "-5.20%" or "12.50"
        pnl_val = 0.0
        try:
            pnl_val = float(pnl_raw.replace("%", "").replace("+", "").strip())
        except (ValueError, AttributeError):
            pnl_val = 0.0

        if status == "WIN":
            wins += 1
        else:
            losses += 1
        net_pnl += pnl_val

    return {
        "count":   wins + losses,
        "wins":    wins,
        "losses":  losses,
        "net_pnl": net_pnl,
    }


# ─────────────────────────────────────────────────────────────
# BUILD MESSAGE
# ─────────────────────────────────────────────────────────────

def _agent_coverage_section():
    """
    Read daily_status.json and return overnight agent coverage lines.
    At 07:00 BKK the 00:xx and 04:xx cycles should have all 4 agents done.
    """
    status_path = os.path.join(BASE_DIR, "daily_status.json")
    try:
        with open(status_path, encoding="utf-8") as _f:
            _data = json.load(_f)
        _today = datetime.now(BKK).date().isoformat()
        if _data.get("date") != _today:
            return "  ⏳ No data yet for today (first cycle hasn't run)"
    except Exception:
        return "  ⚠ daily_status.json missing — is status_server running?"

    _cycle_agents   = ["sigbot", "strategist", "trader", "watchdog"]
    _overnight      = ["00", "04"]   # cycles that should be done by 07:00 BKK
    _lines          = []
    _any_gap        = False

    for _hh in _overnight:
        _missing = [_a for _a in _cycle_agents if not _data.get(f"{_a}_{_hh}")]
        if not _missing:
            _lines.append(f"  ✅ {_hh}:xx — all 4 agents completed")
        else:
            _any_gap = True
            _lines.append(f"  ❌ {_hh}:xx — MISSED: {', '.join(_missing)}")
            _lines.append(f"     → Task Scheduler → find the agent → right-click → Run")

    # Always-running
    _static_gaps = [_a for _a in ["tracker", "monitor"] if not _data.get(_a)]
    if not _static_gaps:
        _lines.append("  ✅ Tracker & Monitor active")
    else:
        _any_gap = True
        _lines.append(f"  ❌ NOT seen today: {', '.join(_static_gaps)}")

    if not _any_gap:
        _lines.insert(0, "  All overnight agents confirmed ✓")

    return "\n".join(_lines)


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

    # ── Market Regime (BTC trend — the #1 filter) ──
    bias, btc_price, btc_sma, btc_pct = get_btc_market_bias()
    if bias == "BEARISH":
        bias_emoji   = "🐻"
        bias_action  = "SHORT mode — trade only SHORTs today"
        bias_detail  = f"BTC ${btc_price:,.0f} is {abs(btc_pct):.1f}% BELOW 20-period 4h SMA (${btc_sma:,.0f})"
    elif bias == "BULLISH":
        bias_emoji   = "🐂"
        bias_action  = "LONG mode — trade only LONGs today"
        bias_detail  = f"BTC ${btc_price:,.0f} is {abs(btc_pct):.1f}% ABOVE 20-period 4h SMA (${btc_sma:,.0f})"
    else:
        bias_emoji   = "😐"
        bias_action  = "NEUTRAL — both directions allowed"
        bias_detail  = (f"BTC ${btc_price:,.0f} within ±2% of 4h SMA (${btc_sma:,.0f})"
                        if btc_price else "BTC SMA unavailable (Bybit offline?)")

    # ── Data ──
    bal      = parse_balance()
    positions = parse_positions()
    analysis = parse_analysis()
    monitor_dt, monitor_ago = parse_monitor_heartbeat()
    fills_24h = parse_last_fills_24h()
    trader   = parse_trader_activity()
    yesterday_pnl = parse_yesterday_pnl()

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
        f"",
        f"{'━'*40}",
        f"{bias_emoji} MARKET TODAY: <b>{bias}</b> — {bias_action}",
        f"  {bias_detail}",
        f"{'━'*40}",
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

    # ── Yesterday's P&L from Google Sheets ──
    if yesterday_pnl is None:
        pnl_section = ["📊 Yesterday's P&L: (Sheets unavailable)"]
    elif yesterday_pnl["count"] == 0:
        pnl_section = ["📊 No trades resolved yesterday."]
    else:
        _n   = yesterday_pnl["count"]
        _w   = yesterday_pnl["wins"]
        _l   = yesterday_pnl["losses"]
        _wr  = _w / _n * 100 if _n > 0 else 0.0
        _net = yesterday_pnl["net_pnl"]
        pnl_section = [
            "📊 YESTERDAY'S RESULTS",
            f"  Resolved: {_n} trades | {_w}W / {_l}L | WR: {_wr:.0f}%",
            f"  Net P&L: {_net:+.1f}% (demo)",
        ]

    lines += [
        "",
        "⚡ YESTERDAY ACTIVITY",
        activity_summary,
    ]
    lines += [""] + pnl_section
    lines += [
        "",
        f"🔄 Monitor: {monitor_status}",
        f"🤖 Trader:  {trader_status}",
    ]

    # ── Layer 3 gap detection — overnight agent coverage ──────────
    lines += [
        "",
        "🤖 OVERNIGHT AGENT COVERAGE",
        _agent_coverage_section(),
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
    try:
        from mission import print_mission_banner
        print_mission_banner()
    except ImportError:
        pass
    now_bkk  = datetime.now(BKK)
    print(f"[{now_bkk.strftime('%Y-%m-%d %H:%M:%S BKK')}] Running morning briefing...")

    msg = build_message()

    # Also print to stdout (captured in briefing_log.txt by run_briefing.bat)
    print("\n── BRIEFING PREVIEW ────────────────────────────────────")
    print(msg)
    print("────────────────────────────────────────────────────────\n")

    send_telegram(msg)
    _mark_done("briefing")

    # ── Auto-run analyze_shorts.py on Sunday (6) and Thursday (3) ──
    _today_wd = now_bkk.weekday()  # 0=Mon … 3=Thu … 6=Sun
    if _today_wd in (3, 6):
        _day_name = "Thursday" if _today_wd == 3 else "Sunday"
        try:
            _shorts_script = os.path.join(BASE_DIR, "analyze_shorts.py")
            print(f"📊 {_day_name}: Running analyze_shorts.py for SHORT recovery check...")
            subprocess.run([sys.executable, _shorts_script], timeout=120)
            print("   ✓ analyze_shorts.py completed")
        except Exception as _e:
            print(f"   ⚠ analyze_shorts.py auto-run failed: {_e}")

    print("Done.")
