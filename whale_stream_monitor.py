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

import os
import io
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

# ─────────────────────────────────────────────────────────────
# CONFIGURATION  (must match whale_stream_trader.py)
# ─────────────────────────────────────────────────────────────
# Bybit Demo API keys — loaded from local_config.py (gitignored). Fallback: env vars.
try:
    from local_config import BYBIT_API_KEY, BYBIT_API_SECRET
except ImportError:
    import os as _os
    BYBIT_API_KEY    = _os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET = _os.getenv("BYBIT_API_SECRET", "")
BYBIT_BASE_URL   = "https://api-demo.bybit.com"
BYBIT_CATEGORY   = "linear"

try:
    from local_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    import os as _os
    TELEGRAM_BOT_TOKEN = _os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = _os.getenv("TELEGRAM_CHAT_ID", "")

SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
STATE_FILE      = os.path.join(SCRIPT_DIR, "monitor_state.json")
LOG_FILE        = os.path.join(SCRIPT_DIR, "monitor_log.txt")

# Threshold: if remaining size / previous size <= this, treat as partial close (TP1)
PARTIAL_CLOSE_RATIO = 0.60   # 50% close → ratio ~0.50, allow up to 0.60 for rounding

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
    timestamp   = str(int(time.time() * 1000) - 1000)
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
        "X-BAPI-DEMO-TRADING": "1",
    }

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
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log(f"   ⚠ Telegram send failed: {e}")


# ─────────────────────────────────────────────────────────────
# BYBIT POSITION HELPERS
# ─────────────────────────────────────────────────────────────
def get_all_positions():
    """Return dict of symbol → position dict for all open positions (size > 0)."""
    result = bybit_request("GET", "/v5/position/list",
                           {"category": BYBIT_CATEGORY, "settleCoin": "USDT"})
    positions = {}
    if result.get("retCode") == 0:
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
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
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
                be_needed = False
                if prev_side == "Buy"  and (curr_sl <= 0 or curr_sl < prev_avg):
                    be_needed = True
                elif prev_side == "Sell" and (curr_sl <= 0 or curr_sl > prev_avg):
                    be_needed = True

                if be_needed:
                    ok, result = move_sl_to_breakeven(symbol, prev_side, prev_avg)
                    if ok:
                        sl_note = (
                            f"\n  🛡 SL moved to breakeven: {result:.6g}"
                            f" (was: {curr_sl:.6g if curr_sl else 'none'})"
                        )
                        log(f"   🛡 SL moved to BE for {symbol}: {result}")
                    else:
                        sl_note = f"\n  ⚠ SL-to-BE failed: {result}"
                        log(f"   ⚠ SL-to-BE failed for {symbol}: {result}")
                else:
                    sl_note = f"\n  ✓ SL already at/above breakeven ({curr_sl:.6g})"

                msg = (
                    f"🎯 <b>TP1 PARTIAL CLOSE — {symbol}</b>\n"
                    f"  {direction}  |  {reduction_pct:.0f}% closed\n"
                    f"  Size: {prev_size} → {curr_size}\n"
                    f"  Entry (avg): {prev_avg:.6g}"
                    f"{sl_note}\n"
                    f"  Remaining 50% riding to TP2/TP3\n"
                    f"  🕐 {bkk.strftime('%H:%M BKK')}"
                )
                send_alert(msg)
                alerts_fired += 1

                # Update stored size to current
                state["positions"][symbol] = {**curr, "sl": curr["sl"]}

            elif curr_size > prev_size * 1.20:
                # Size grew significantly — position was added to; update state silently
                log(f"   ℹ {symbol}: position size grew {prev_size} → {curr_size} (position added or avg'd down)")
                state["positions"][symbol] = curr

            else:
                # Normal — just update sl/unrealised fields
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

    log("✅ Monitor run complete\n")


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
        send_alert(
            f"❌ <b>WHALE-STREAM MONITOR CRASHED</b>\n"
            f"Error: {str(e)[:300]}\n"
            f"Check monitor_log.txt for details."
        )
        raise
