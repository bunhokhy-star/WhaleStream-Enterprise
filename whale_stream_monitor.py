"""
╔══════════════════════════════════════════════════════════════╗
║       WHALE-STREAM NEAR-REAL-TIME MONITOR                    ║
║                                                              ║
║  Polls Bybit every 2 minutes to detect position changes      ║
║  and fires immediate Telegram alerts.                        ║
║                                                              ║
║  Detects:                                                    ║
║    • ~50% size drop  → TP1 partial close + move SL to BE     ║
║    • Position gone   → Full close alert (WIN/LOSS pending)   ║
║    • New position    → Logs to state (no alert)               ║
║                                                              ║
║  HOW TO RUN:                                                 ║
║    py whale_stream_monitor.py                                ║
║    (Scheduled every 2 min via ADD_MONITOR_TASK.bat)          ║
║                                                              ║
║  State: monitor_state.json (position sizes at last check)    ║
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

import os
import io
import re
import sys
import hmac
import json
import math
import time
import hashlib
import requests
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

# Force UTF-8 — prevents UnicodeEncodeError in Task Scheduler on Windows CP1252.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


# ── Self-tick helper (writes completion to daily_status.json) ────
BKK = timezone(timedelta(hours=7))


def _mark_done(agent_name, details=None):
    """Mark this agent done for the current cycle in daily_status.json."""
    _path  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_status.json")
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
        _jspath = _path.replace("daily_status.json", "daily_status.js")
        with open(_jspath, "w", encoding="utf-8") as _f:
            _f.write("window.WHALE_STATUS=" + json.dumps(_data) + ";")
        _html_path = os.path.join(os.path.dirname(_path), "To do list", "Daily Checklist.html")
        with open(_html_path, encoding="utf-8") as _hf:
            _html = _hf.read()
        _inject = "var WS_EMBEDDED=" + json.dumps(_data, separators=(',', ':')) + ";"
        _html = re.sub(r'var WS_EMBEDDED=\{[\s\S]*?\};', _inject, _html)
        with open(_html_path, "w", encoding="utf-8") as _hf:
            _hf.write(_html)
    except Exception as _me:
        print(f"   ⚠ Status write failed: {_me}")


# ─────────────────────────────────────────────────────────────
# CONFIGURATION  (must match whale_stream_trader.py)
# ─────────────────────────────────────────────────────────────
# Bybit Demo API keys — loaded from local_config.py (gitignored). Fallback: env vars.
try:
    from local_config import BYBIT_API_KEY, BYBIT_API_SECRET
except ImportError:
    BYBIT_API_KEY    = os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
try:
    from local_config import BYBIT_BASE_URL             # noqa — set "https://api.bybit.com" for live
except ImportError:
    BYBIT_BASE_URL = "https://api-demo.bybit.com"       # default: demo; override in local_config.py for live
BYBIT_CATEGORY   = "linear"

try:
    from local_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
STATE_FILE      = os.path.join(SCRIPT_DIR, "monitor_state.json")
LOG_FILE        = os.path.join(SCRIPT_DIR, "monitor_log.txt")

# Threshold: if remaining size / previous size <= this, treat as partial close (TP1)
# Quad-TP: 25% close leaves 75% remaining.  Need ratio > 0.75 to detect it.
# 0.85 fires on any ≥15% position reduction — catches TP1 (25%), TP2 (33%), TP3 (50%).
PARTIAL_CLOSE_RATIO = 0.85   # Quad-TP 25% close leaves 75%; fire on any ≥15% reduction

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────
def log(msg):
    bkk = datetime.now(timezone(timedelta(hours=7)))
    ts  = bkk.strftime("%Y-%m-%d %H:%M:%S BKK")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# BYBIT API AUTH
# ─────────────────────────────────────────────────────────────
def bybit_request(method, endpoint, params=None, body=None):
    """Authenticated Bybit V5 API request (Demo account)."""
    timestamp   = str(int(time.time() * 1000))
    recv_window = "20000"

    if method == "GET":
        query_str = urlencode(params or {})
        sign_str  = timestamp + BYBIT_API_KEY + recv_window + query_str
    else:
        body_str = json.dumps(body or {})
        sign_str = timestamp + BYBIT_API_KEY + recv_window + body_str

    signature = hmac.new(
        BYBIT_API_SECRET.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "X-BAPI-API-KEY":     BYBIT_API_KEY,
        "X-BAPI-TIMESTAMP":   timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "X-BAPI-SIGN":        signature,
    }
    if "demo" in BYBIT_BASE_URL:           # Only send demo header on demo endpoint
        headers["X-BAPI-DEMO-TRADING"] = "1"

    url = BYBIT_BASE_URL + endpoint
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, params=params or {}, timeout=10)
        else:
            headers["Content-Type"] = "application/json"
            r = requests.post(url, headers=headers, json=body or {}, timeout=10)
        return r.json()
    except Exception as e:
        return {"retCode": -1, "retMsg": str(e)}


# ─────────────────────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────────────────────
def send_alert(msg):
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        if not (resp.status_code == 200 and resp.json().get("ok")):
            log(f"   ⚠ Telegram send failed: {resp.status_code} {resp.text[:100]}")
    except Exception as e:
        log(f"   ⚠ Telegram send failed: {e}")


# ─────────────────────────────────────────────────────────────
# BYBIT POSITION HELPERS
# ─────────────────────────────────────────────────────────────
def get_all_positions():
    """Return dict of symbol → position dict for all open positions (size > 0).
    Returns None on API failure — caller must handle to avoid false close alerts."""
    result = bybit_request("GET", "/v5/position/list",
                           {"category": BYBIT_CATEGORY, "settleCoin": "USDT"})
    if result.get("retCode") != 0:
        return None   # API failure — do NOT treat as "no positions open"
    positions = {}
    for p in result["result"].get("list", []):
        sz = float(p.get("size", 0) or 0)
        if sz > 0:
            positions[p["symbol"]] = {
                "size":     sz,
                "side":     p.get("side", ""),          # "Buy" / "Sell"
                "avgPrice": float(p.get("avgPrice", 0) or 0),
                "sl":       float(p.get("stopLoss", 0) or 0),
                "tp":       float(p.get("takeProfit", 0) or 0),
                "liqPrice": float(p.get("liqPrice", 0) or 0),
                "unrealisedPnl": float(p.get("unrealisedPnl", 0) or 0),
            }
    return positions


def get_instrument_tick(symbol):
    """Return tick size for a symbol (needed to round SL price for Bybit)."""
    r = bybit_request("GET", "/v5/market/instruments-info",
                      {"category": BYBIT_CATEGORY, "symbol": symbol})
    if r.get("retCode") == 0:
        items = r["result"].get("list", [])
        if items:
            return float(items[0]["priceFilter"]["tickSize"])
    return None


def round_price(price, tick):
    if tick is None or tick <= 0:
        return price
    decimals = max(0, -int(math.floor(math.log10(tick))))
    return round(round(price / tick) * tick, decimals)


def fmt_price(price, tick):
    if tick is None or tick <= 0:
        return str(price)
    decimals = max(0, -int(math.floor(math.log10(tick))))
    return f"{price:.{decimals}f}"


def move_sl_to_breakeven(symbol, side, avg_price):
    """Move stop loss to avgPrice (breakeven) using /v5/position/trading-stop."""
    tick = get_instrument_tick(symbol)
    if tick is None:
        log(f"   ⚠ Could not get tick size for {symbol} — SL-to-BE skipped")
        return False, "tick_size_unavailable"

    sl_price = round_price(avg_price, tick)
    body = {
        "category":   BYBIT_CATEGORY,
        "symbol":     symbol,
        "stopLoss":   fmt_price(sl_price, tick),
        "slTriggerBy": "MarkPrice",
        "positionIdx": 0,
    }
    result = bybit_request("POST", "/v5/position/trading-stop", body=body)
    if result.get("retCode") == 0:
        return True, sl_price
    return False, result.get("retMsg", "unknown")


# ─────────────────────────────────────────────────────────────
# STATE MANAGEMENT
# ─────────────────────────────────────────────────────────────
def load_state():
    """Load monitor_state.json. Returns dict with 'positions' key."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"positions": {}}


def save_state(state):
    try:
        _tmp = STATE_FILE + ".tmp"
        with open(_tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(_tmp, STATE_FILE)
    except Exception as e:
        log(f"   ⚠ Could not save state: {e}")


# ─────────────────────────────────────────────────────────────
# MAIN MONITOR LOGIC
# ─────────────────────────────────────────────────────────────
def run_monitor():
    bkk = datetime.now(timezone(timedelta(hours=7)))
    log(f"🔍 Monitor run — {bkk.strftime('%Y-%m-%d %H:%M BKK')}")

    # Load last known state
    state = load_state()
    prev_positions = state.get("positions", {})

    # Fetch current Bybit positions
    current_positions = get_all_positions()
    if current_positions is None:
        log("   ⚠ Bybit API failure — skipping cycle (cannot diff positions safely)")
        _mark_done("monitor", details={"positions": "API_ERROR", "alerts": 0,
                                       "last_run": bkk.strftime("%H:%M") + " BKK"})
        return
    log(f"   Bybit open positions: {len(current_positions)} ({', '.join(current_positions) or 'none'})")

    alerts_fired = 0

    # ── Check for changes in previously tracked positions ──────
    for symbol, prev in list(prev_positions.items()):
        prev_size = prev.get("size", 0)
        prev_side = prev.get("side", "")
        prev_avg  = prev.get("avgPrice", 0)
        prev_sl   = prev.get("sl", 0)

        if symbol not in current_positions:
            # ── FULL CLOSE DETECTED ──────────────────────────
            log(f"   📉 {symbol}: position gone (was {prev_side} {prev_size})")
            direction = "LONG" if prev_side == "Buy" else "SHORT"
            msg = (
                f"📊 <b>POSITION CLOSED — {symbol}</b>\n"
                f"  Direction: {direction}  |  Size was: {prev_size}\n"
                f"  Entry (avg): {prev_avg:.6g}\n"
                f"  ⏳ Tracker will mark WIN/LOSS at next run (within 30 min)\n"
                f"  🕐 {bkk.strftime('%H:%M BKK')}"
            )
            send_alert(msg)
            alerts_fired += 1
            # Remove from state
            del state["positions"][symbol]

        else:
            curr = current_positions[symbol]
            curr_size = curr["size"]

            # ── PARTIAL CLOSE DETECTED (~50% reduction) ───────
            if curr_size <= prev_size * PARTIAL_CLOSE_RATIO and curr_size > 0:
                reduction_pct = (1 - curr_size / prev_size) * 100
                log(f"   🎯 {symbol}: partial close detected  {prev_size} → {curr_size} ({reduction_pct:.0f}% closed)")
                direction = "LONG" if prev_side == "Buy" else "SHORT"

                # Check if SL-to-BE is needed
                sl_note = ""
                curr_sl = curr.get("sl", 0)
                # Fallback: use live avgPrice if prev_avg is 0 (e.g. state file wiped)
                _effective_avg = prev_avg if prev_avg > 0 else float(curr.get("avgPrice", 0) or 0)
                be_needed = False
                if not prev.get("be_set"):   # skip if SL-to-BE already applied this trade
                    if prev_side == "Buy"  and (curr_sl <= 0 or curr_sl < _effective_avg):
                        be_needed = True
                    elif prev_side == "Sell" and (curr_sl <= 0 or curr_sl > _effective_avg):
                        be_needed = True

                if be_needed:
                    ok, result = move_sl_to_breakeven(symbol, prev_side, curr["avgPrice"])  # use live avg, not stale prev_avg
                    if ok:
                        curr["be_set"] = True   # prevent re-firing on TP2/TP3 partial closes
                        was_str = f"{curr_sl:.6g}" if curr_sl else "none"   # pre-compute to avoid invalid f-string format spec
                        sl_note = (
                            f"\n  🛡 SL moved to breakeven: {result:.6g}"
                            f" (was: {was_str})"
                        )
                        log(f"   🛡 SL moved to BE for {symbol}: {result}")
                    else:
                        sl_note = f"\n  ⚠ SL-to-BE failed: {result}"
                        log(f"   ⚠ SL-to-BE failed for {symbol}: {result}")
                elif prev.get("be_set"):
                    sl_note = f"\n  ✓ SL-to-BE already applied (skipping)"
                else:
                    sl_note = f"\n  ✓ SL already at/above breakeven ({curr_sl:.6g})"

                msg = (
                    f"🎯 <b>TP1 PARTIAL CLOSE — {symbol}</b>\n"
                    f"  {direction}  |  {reduction_pct:.0f}% closed\n"
                    f"  Size: {prev_size} → {curr_size}\n"
                    f"  Entry (avg): {prev_avg:.6g}"
                    f"{sl_note}\n"
                    f"  Remaining 75% riding to TP2/TP3/TP4\n"
                    f"  🕐 {bkk.strftime('%H:%M BKK')}"
                )
                send_alert(msg)
                alerts_fired += 1

                # Update stored size to current
                # Always carry be_set forward — it is only set on curr when be_needed=True,
                # so TP2/TP3 partial closes would lose it without this propagation.
                if prev.get("be_set") and not curr.get("be_set"):
                    curr["be_set"] = True
                state["positions"][symbol] = curr  # curr already has updated sl/size

            elif curr_size > prev_size * 1.20:
                # Size grew significantly — position was added to; update state silently
                log(f"   ℹ {symbol}: position size grew {prev_size} → {curr_size} (position added or avg'd down)")
                if prev.get("be_set") and not curr.get("be_set"):
                    curr["be_set"] = True
                state["positions"][symbol] = curr

            else:
                # Normal — just update sl/unrealised fields
                if prev.get("be_set") and not curr.get("be_set"):
                    curr["be_set"] = True
                state["positions"][symbol] = curr

    # ── Add newly opened positions to state ───────────────────
    for symbol, curr in current_positions.items():
        if symbol not in state["positions"]:
            log(f"   ➕ New position tracked: {symbol} {curr['side']} {curr['size']} @ {curr['avgPrice']:.6g}")
            state["positions"][symbol] = curr

    save_state(state)

    if alerts_fired:
        log(f"   ✓ {alerts_fired} alert(s) sent to Telegram")
    else:
        log(f"   ✓ No position changes detected")

    _bkk_now_str = bkk.strftime("%H:%M")
    _mark_done("monitor", details={
        "positions": len(current_positions),
        "alerts":    alerts_fired,
        "last_run":  f"{_bkk_now_str} BKK"
    })
    log("✅ Monitor run complete")


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        from mission import print_mission_banner
        print_mission_banner()
    except ImportError:
        pass
    try:
        run_monitor()
    except Exception as e:
        log(f"❌ Monitor crashed: {e}")
        _mark_done("monitor", details={"error": str(e)[:200]})
        send_alert(
            f"❌ <b>WHALE-STREAM MONITOR CRASHED</b>\n"
            f"Error: {str(e)[:300]}\n"
            f"Check monitor_log.txt for details."
        )
        raise
