"""
╔══════════════════════════════════════════════════════════════╗
║       WHALE-STREAM AUTO TRADER — BYBIT DEMO                  ║
║                                                              ║
║  Reads latest OPEN signals from Google Sheets and places     ║
║  limit orders on your Bybit DEMO account automatically.      ║
║                                                              ║
║  Settings: $20 margin × 10x leverage = $200 position         ║
║  Market:   USDT Perpetual (Linear)                           ║
║                                                              ║
║  HOW TO RUN:                                                 ║
║    py whale_stream_trader.py                                 ║
║                                                              ║
║  ⚠ DEMO ONLY — uses fake money on Bybit demo account         ║
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

import re
import os
import sys
import io
import hmac
import json
import math
import time
import hashlib
import requests
import subprocess
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

BKK = timezone(timedelta(hours=7))   # Bangkok timezone (UTC+7) — used everywhere

# Force UTF-8 output — prevents UnicodeEncodeError on Windows CP1252 consoles / Task Scheduler.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


# ── Self-tick helper (writes completion to daily_status.json) ────
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
        # NOTE: HTML write intentionally omitted — Watchdog is sole HTML writer (:30 cycle end)
    except Exception as _me:
        print(f"   ⚠ _mark_done write failed: {_me}")


# ── Auto-install missing libraries ────────────────────────────
REQUIRED = {"gspread": "gspread", "google.oauth2": "google-auth"}
for mod, pkg in REQUIRED.items():
    try:
        __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

from gspread.utils import rowcol_to_a1   # safe: gspread guaranteed installed by REQUIRED loop above

# ─────────────────────────────────────────────────────────────
# SECTION 1: CONFIGURATION  ← Fill in your keys here
# ─────────────────────────────────────────────────────────────

# Bybit Demo API keys — loaded from local_config.py (gitignored). Fallback: env vars.
# → Login bybit.com → Switch to Demo mode → Account → API Management → Create Key
try:
    from local_config import BYBIT_API_KEY, BYBIT_API_SECRET
except ImportError:
    import os as _os
    BYBIT_API_KEY    = _os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET = _os.getenv("BYBIT_API_SECRET", "")

# Trade settings
try:
    from local_config import TRADE_MARGIN_USDT        # noqa — set in local_config.py to override
except ImportError:
    TRADE_MARGIN_USDT = 20  # default: $20/trade; set TRADE_MARGIN_USDT in local_config.py for live
LEVERAGE          = 10      # 10x leverage → $200 position per trade
MAX_OPEN_TRADES   = 6       # max 6 simultaneous positions (3 long + 3 short)

# Google Sheets (same as whale_stream_bot.py)
GOOGLE_SHEET_ID         = "1R21mkduSpbki2HmlNJMHM95-LkGS0q-AKHE1HVIfMmI"
GOOGLE_CREDENTIALS_FILE = "google_credentials.json"

# Bybit API
try:
    from local_config import BYBIT_BASE_URL             # noqa — set "https://api.bybit.com" for live
except ImportError:
    BYBIT_BASE_URL = "https://api-demo.bybit.com"       # default: demo; override in local_config.py for live
BYBIT_PUBLIC_URL = "https://api.bybit.com"   # public market data (no auth)
BYBIT_CATEGORY   = "linear"   # USDT Perpetual

# Max distance between signal entry and Bybit mark price.
# Bybit rejects limit orders > ~10% from mark price.
# We use 8% as our cutoff (buffer for mark vs last-price divergence).
MAX_ENTRY_DISTANCE_PCT = 8.0

# Bybit's real per-instrument price band is often tighter than our 8% guard —
# many coins (especially low-cap alts) are rejected at 3-5% from mark.
# If the signal price falls outside this tighter band, we clamp it to
# mark ± BYBIT_PRICE_CLAMP_PCT instead of rejecting outright.
# This recovers trades like OP, TRX, SEI, XLM, FF that pass our 8% check
# but still hit retCode=10001 because Bybit's band is ~3%.
BYBIT_PRICE_CLAMP_PCT = 2.5   # clamp radius: mark ± 2.5%

# Risk cap: never deploy more than this fraction of total balance
MAX_DEPLOYED_FRACTION = 0.50   # 50%

# Telegram (same group as bot and tracker)
try:
    from local_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    import os as _os
    TELEGRAM_BOT_TOKEN = _os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = _os.getenv("TELEGRAM_CHAT_ID", "")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Balance file (read by whale_stream_tracker.py for dashboard)
BYBIT_BALANCE_FILE  = os.path.join(SCRIPT_DIR, "bybit_balance.json")
BYBIT_START_BALANCE = 500.00   # initial deposit — MUST match BYBIT_START_BALANCE in whale_stream_tracker.py
LOG_FILE   = os.path.join(SCRIPT_DIR, "trader_log.txt")

# Skip-counter: after this many consecutive mark-price skips, mark signal UNREACHABLE
SKIP_FILE      = os.path.join(SCRIPT_DIR, "trader_skips.json")
MAX_MARK_SKIPS = 3

# Circuit breaker: after this many consecutive LOSSes, write PAUSED flag and halt
PAUSED_FILE    = os.path.join(SCRIPT_DIR, "paused.flag")  # must match tracker's PAUSED_FILE
CIRCUIT_LOSSES = 3

# Gate 4 breach sentinel — written on first entry, deleted on recovery.
# Prevents the Telegram alert from firing every 4-hour run while breach persists.
GATE4_BREACH_FILE = os.path.join(SCRIPT_DIR, "gate4_breach.flag")

SHORT_REPAIR_FILE    = os.path.join(SCRIPT_DIR, "short_repair.flag")
SHORT_RECOVERY_COINS = {"H", "FF"}  # approved recovery coins (bypass SHORT REPAIR MODE)
# Note: CHZ removed — it's in MALFORMED_COIN_BLOCKLIST in bot.py (SL always invalid)

# Cancel-on-reversal: stores BTC price at time each entry order is placed
ORDER_CONTEXT_FILE   = os.path.join(SCRIPT_DIR, "order_context.json")

# Coins with poor historical LONG win rate — skip LONG signals for these
LONG_COIN_AVOID_LIST = ["COMP", "HYPE", "ZRO", "QNT", "WIF", "WLD"]   # must match LONG_COIN_BLOCKLIST in bot.py

def log(msg):
    """Write to console and trader_log.txt with timestamp."""
    bkk = datetime.now(BKK).strftime("%Y-%m-%d %H:%M BKK")
    line = f"[{bkk}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def load_skip_counts():
    """Load per-signal mark-price skip counts from disk."""
    if os.path.exists(SKIP_FILE):
        try:
            with open(SKIP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_skip_counts(counts):
    """Persist skip counts to disk."""
    try:
        with open(SKIP_FILE, "w", encoding="utf-8") as f:
            json.dump(counts, f)
    except Exception:
        pass


def check_circuit_breaker(data_rows, threshold=None):
    """
    Scan all resolved trades and check if the last `threshold` are all LOSS.
    Returns True if the circuit breaker should fire (auto-pause triggered).
    Sorts by COL_RESOLVED_AT (col 16) — format 'YYYY-MM-DD HH:MM BKK' sorts correctly as string.
    threshold defaults to CIRCUIT_LOSSES (3) but callers can override.
    """
    _threshold = threshold if threshold is not None else CIRCUIT_LOSSES
    resolved = []
    for row in data_rows:
        while len(row) < 18:
            row.append("")
        status      = row[COL_STATUS].strip()
        resolved_at = row[COL_RESOLVED_AT].strip()
        # Only count bot-placed trades (COL_BYBIT_ID must be set) to exclude manual rows
        if status in ("WIN", "LOSS") and row[COL_BYBIT_ID].strip():
            resolved.append((resolved_at, status))

    # Sort chronologically (YYYY-MM-DD HH:MM prefix sorts lexicographically)
    resolved.sort(key=lambda x: x[0])

    if len(resolved) < _threshold:
        return False

    last_n = resolved[-_threshold:]
    return all(s == "LOSS" for _, s in last_n)


def send_telegram_alert(msg):
    """Send a message to the Whale-Stream Telegram group."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def write_balance_file(balance, open_positions=0):
    """Write Bybit Demo balance to JSON for the dashboard to display."""
    # ── Gate 4 recovery detection — read old balance before overwriting ────────
    _GATE4_RECOVERY_THRESHOLD = BYBIT_START_BALANCE * 0.85
    _old_balance = None
    try:
        if os.path.exists(BYBIT_BALANCE_FILE):
            with open(BYBIT_BALANCE_FILE, "r", encoding="utf-8") as _rf:
                _old_data = json.load(_rf)
                _old_balance = float(_old_data.get("balance", balance))
    except Exception:
        pass
    # ── end Gate 4 recovery read ───────────────────────────────────────────────

    bkk = datetime.now(BKK).strftime("%Y-%m-%d %H:%M BKK")
    try:
        with open(BYBIT_BALANCE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "balance":        round(balance, 2),
                "start_balance":  BYBIT_START_BALANCE,
                "updated_at":     bkk,
                "open_positions": open_positions,
            }, f)
    except Exception:
        pass

    # ── Gate 4 recovery alert — fires when balance crosses $425 from below ─────
    if (_old_balance is not None
            and _old_balance < _GATE4_RECOVERY_THRESHOLD
            and balance >= _GATE4_RECOVERY_THRESHOLD):
        _g4_recovery_msg = (
            f"🟢 GATE 4 CLEARED!\n"
            f"Balance: ${balance:.2f} recovered above $425\n"
            f"Drawdown back below 15% ✅\n"
            f"→ Review July 1 go-live decision."
        )
        send_telegram_alert(_g4_recovery_msg)
        log(f"GATE 4 CLEARED — balance crossed $425 (was ${_old_balance:.2f}, now ${balance:.2f})")
        # Remove the breach sentinel so the entry alert can fire again if balance dips again
        try:
            if os.path.exists(GATE4_BREACH_FILE):
                os.remove(GATE4_BREACH_FILE)
        except Exception:
            pass
    # ── end Gate 4 recovery alert ──────────────────────────────────────────────


# ── Sheet column indices (0-based) ────────────────────────────
COL_COIN       = 0
COL_SIGNAL     = 1
COL_CONF       = 2
COL_ENTRY_ZONE = 3
COL_SL         = 4
COL_TP1        = 5
COL_TP2        = 6
COL_TP3        = 7
COL_TP4        = 8
COL_TIMESTAMP  = 10
COL_STATUS     = 11
# Columns 12-16: tracker columns (read by SL-to-BE and other logic)
COL_ENTRY_PRICE = 12   # tracker: actual fill price (avgPrice from Bybit)
COL_EXIT_PRICE  = 13   # tracker: actual exit price
COL_TP_HIT      = 14   # tracker: "TP1", "TP2", "TP3" or "SL"
COL_PNL         = 15   # tracker: estimated P&L %
COL_RESOLVED_AT = 16   # tracker: resolution timestamp (YYYY-MM-DD HH:MM BKK)
COL_BYBIT_ID    = 17   # Bybit Demo order ID — written here when order is placed


# ─────────────────────────────────────────────────────────────
# BYBIT AUTHENTICATION
# ─────────────────────────────────────────────────────────────

# Clock offset vs Bybit server (ms). Positive = our clock is ahead.
# Calibrated in main() via _calibrate_clock(). Default 3000ms keeps us safe
# even without calibration (handles up to 2.5s PC clock drift).
_BYBIT_CLOCK_OFFSET_MS = 3000


def _calibrate_clock():
    """
    Fetch Bybit server time and cache the clock offset.
    Prevents retCode 10002 (timestamp rejected) when PC clock drifts.
    """
    global _BYBIT_CLOCK_OFFSET_MS
    try:
        r = requests.get(f"{BYBIT_BASE_URL}/v5/market/time", timeout=5)
        d = r.json()
        if d.get("retCode") == 0:
            server_ms = int(d["result"]["timeNano"]) // 1_000_000
            local_ms  = int(time.time() * 1000)
            offset    = local_ms - server_ms
            # Use offset + 500ms safety buffer (always send timestamp slightly behind server)
            _BYBIT_CLOCK_OFFSET_MS = offset + 500
            direction = "ahead" if offset >= 0 else "behind"
            print(f"   ⏱ PC clock is {abs(offset)} ms {direction} of Bybit — offset applied")
            return True
    except Exception as e:
        print(f"   ⚠ Clock calibration skipped ({e}) — using {_BYBIT_CLOCK_OFFSET_MS} ms default offset")
    return False


def bybit_request(method, endpoint, params=None, body=None):
    """
    Authenticated Bybit V5 API request.
    Adds X-BAPI-DEMO-TRADING: 1 header for demo account.
    """
    timestamp   = str(int(time.time() * 1000) - _BYBIT_CLOCK_OFFSET_MS)
    recv_window = "20000"

    if method == "GET":
        query_str = urlencode(params) if params else ""
        sign_str  = f"{timestamp}{BYBIT_API_KEY}{recv_window}{query_str}"
    else:
        body_str = json.dumps(body) if body else ""
        sign_str = f"{timestamp}{BYBIT_API_KEY}{recv_window}{body_str}"

    signature = hmac.new(
        BYBIT_API_SECRET.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    headers = {
        "X-BAPI-API-KEY":       BYBIT_API_KEY,
        "X-BAPI-SIGN":          signature,
        "X-BAPI-TIMESTAMP":     timestamp,
        "X-BAPI-RECV-WINDOW":   recv_window,
        "Content-Type":         "application/json",
    }
    if "demo" in BYBIT_BASE_URL:            # Only send demo header on demo endpoint (go-live blocker)
        headers["X-BAPI-DEMO-TRADING"] = "1"

    url = f"{BYBIT_BASE_URL}{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, params=params, headers=headers, timeout=15)
        else:
            resp = requests.post(url, json=body, headers=headers, timeout=15)
        return resp.json()
    except Exception as e:
        return {"retCode": -1, "retMsg": str(e)}


# ─────────────────────────────────────────────────────────────
# BYBIT HELPERS
# ─────────────────────────────────────────────────────────────

def get_wallet_balance():
    """
    Check Bybit demo USDT balance.
    Returns (available, total, err_msg) tuple.
    On success: (float, float, None)
    On failure: (None, None, str_error)
    """
    result = bybit_request("GET", "/v5/account/wallet-balance",
                           {"accountType": "UNIFIED"})
    if result.get("retCode") == 0:
        coins = result["result"]["list"][0].get("coin", [])
        for c in coins:
            if c.get("coin") == "USDT":
                avail = float(c.get("availableToWithdraw") or
                              c.get("walletBalance") or 0)
                total = float(c.get("walletBalance") or
                              c.get("equity") or avail)
                return avail, total, None
        print("   ⚠ Connected to Bybit but no USDT coin found in wallet")
        return 0.0, 0.0, None
    code = result.get("retCode", -1)
    msg  = result.get("retMsg", "unknown error")
    return None, None, f"retCode={code} | {msg}"


def get_current_price(symbol):
    """
    Fetch current last-traded price from Bybit public API (no auth needed).
    Uses main API, not demo — market prices are identical.
    Returns None if unavailable.
    """
    try:
        resp = requests.get(
            f"{BYBIT_PUBLIC_URL}/v5/market/tickers",
            params={"category": BYBIT_CATEGORY, "symbol": symbol},
            timeout=10,
        )
        data = resp.json()
        if data.get("retCode") == 0:
            items = data.get("result", {}).get("list", [])
            if items:
                # Prefer markPrice — Bybit uses mark price for its limit order
                # price-band filter (not last traded price). Using mark price
                # here lets us accurately predict whether Bybit will accept
                # our limit price before we even submit the order.
                price = (items[0].get("markPrice")
                         or items[0].get("lastPrice")
                         or items[0].get("indexPrice"))
                return float(price) if price else None
    except Exception:
        pass
    return None


def get_instrument_info(symbol):
    """Get lot size, price tick size, and static price bounds for a USDT Perpetual symbol."""
    result = bybit_request("GET", "/v5/market/instruments-info",
                           {"category": BYBIT_CATEGORY, "symbol": symbol})
    if result.get("retCode") == 0:
        items = result["result"].get("list", [])
        if items:
            item       = items[0]
            lot_f      = item["lotSizeFilter"]
            price_f    = item["priceFilter"]
            # minPrice / maxPrice are static floor/ceiling constraints Bybit
            # always enforces regardless of mark price distance.  They are
            # occasionally non-zero for low-priced coins (e.g. OP minPrice may
            # be 0.1001) and would cause retCode=10001 if violated.
            raw_min = price_f.get("minPrice", "0") or "0"
            raw_max = price_f.get("maxPrice", "0") or "0"
            return {
                "min_qty":   float(lot_f["minOrderQty"]),
                "qty_step":  float(lot_f["qtyStep"]),
                "max_qty":   float(lot_f.get("maxOrderQty", 999999)),
                "tick_size": float(price_f["tickSize"]),
                "min_price": float(raw_min),   # 0 means "no static floor"
                "max_price": float(raw_max),   # 0 means "no static ceiling"
            }
    return None


def set_leverage(symbol):
    """Set leverage to LEVERAGE value for both sides."""
    result = bybit_request("POST", "/v5/position/set-leverage", body={
        "category":     BYBIT_CATEGORY,
        "symbol":       symbol,
        "buyLeverage":  str(LEVERAGE),
        "sellLeverage": str(LEVERAGE),
    })
    code = result.get("retCode", -1)
    # 110043 = leverage already set — not an error
    return code in (0, 110043)


def get_open_positions():
    """Return set of symbols that already have an open position."""
    result = bybit_request("GET", "/v5/position/list",
                           {"category": BYBIT_CATEGORY, "settleCoin": "USDT"})
    open_syms = set()
    if result.get("retCode") == 0:
        for pos in result["result"].get("list", []):
            if float(pos.get("size", 0)) > 0:
                open_syms.add(pos["symbol"])
    return open_syms


def get_open_positions_full():
    """Return list of full position dicts for all positions with size > 0."""
    result = bybit_request("GET", "/v5/position/list",
                           {"category": BYBIT_CATEGORY, "settleCoin": "USDT"})
    if result.get("retCode") == 0:
        return [p for p in result["result"].get("list", [])
                if float(p.get("size", 0)) > 0]
    print("   ⚠ get_open_positions_full(): Bybit API failure — SL-to-BE skipped (monitor handles it)")
    return []


def get_open_orders():
    """Return set of symbols that already have an unfilled ENTRY order (reduce-only excluded)."""
    result = bybit_request("GET", "/v5/order/realtime",
                           {"category": BYBIT_CATEGORY, "settleCoin": "USDT"})
    open_syms = set()
    if result.get("retCode") == 0:
        for order in result["result"].get("list", []):
            # Skip reduce-only TP close orders — they are on existing positions, not new entries
            if order.get("reduceOnly") is True or str(order.get("reduceOnly", "")).lower() == "true":
                continue
            open_syms.add(order["symbol"])
    return open_syms


def get_stale_entry_orders(sheet_open_coins, min_age_hours=72):
    """
    Find unfilled ENTRY limit orders on Bybit that are older than min_age_hours
    AND have no matching OPEN signal in the sheet (coin already expired).
    Reduce-only orders (partial close orders) are EXCLUDED — they're supposed
    to stay open until TP is hit.
    Returns list of dicts: {symbol, orderId, side, qty, price, age_h, created_time}
    """
    result = bybit_request("GET", "/v5/order/realtime",
                           {"category": BYBIT_CATEGORY, "settleCoin": "USDT"})
    stale = []
    if result.get("retCode") != 0:
        return stale

    bkk_now = datetime.now(BKK)
    for order in result["result"].get("list", []):
        # Skip reduce-only orders — these are partial close orders, keep them alive
        if order.get("reduceOnly") is True or str(order.get("reduceOnly", "")).lower() == "true":
            continue
        sym      = order.get("symbol", "")
        coin     = sym.replace("USDT", "").replace("PERP", "").upper()
        created  = order.get("createdTime", "0")
        try:
            created_dt = datetime.fromtimestamp(int(created) / 1000, tz=timezone.utc)
            age_h = (bkk_now - created_dt).total_seconds() / 3600
        except Exception:
            age_h = 0

        if age_h >= min_age_hours and coin not in sheet_open_coins:
            stale.append({
                "symbol":       sym,
                "coin":         coin,
                "orderId":      order.get("orderId", ""),
                "side":         order.get("side", ""),
                "qty":          order.get("qty", ""),
                "price":        order.get("price", ""),
                "age_h":        age_h,
                "created_time": created,
            })
    return stale


def cancel_order(symbol, order_id, _max_retries=3):
    """
    Cancel a specific open order by orderId.
    Retries up to _max_retries times on transient failures with exponential backoff.
    Returns True on success. Returns False immediately if order is already gone (retCode 20001).
    """
    for _attempt in range(_max_retries):
        result = bybit_request("POST", "/v5/order/cancel", body={
            "category": BYBIT_CATEGORY,
            "symbol":   symbol,
            "orderId":  order_id,
        })
        ret_code = result.get("retCode", -1)
        if ret_code == 0:
            return True
        if ret_code == 20001:
            # Order no longer exists (already filled or cancelled) — don't retry
            return False
        if _attempt < _max_retries - 1:
            _sleep = 2 ** _attempt   # 1s, 2s, 4s
            log(f"cancel_order {symbol} attempt {_attempt+1} failed (retCode={ret_code}) — retrying in {_sleep}s")
            time.sleep(_sleep)
    log(f"cancel_order {symbol} failed after {_max_retries} attempts")
    return False


def get_position_for_coin(symbol):
    """
    Return the open position dict for symbol, or None if no position.
    Returns a dict with at least 'size' (str) and 'side' ('Buy'/'Sell').
    """
    result = bybit_request("GET", "/v5/position/list",
                           params={"category": BYBIT_CATEGORY, "symbol": symbol})
    if result.get("retCode") == 0:
        for pos in result.get("result", {}).get("list", []):
            try:
                if float(pos.get("size", 0)) > 0:
                    return pos
            except (ValueError, TypeError):
                pass
    return None


def close_position_at_market_for_veto(symbol, bybit_order_id):
    """
    Called when Strategist vetoes a coin whose order was already placed.

    Step 1 — Try to cancel the open order (if still unfilled).
             cancel_order() already retries 3x on transient failures.
    Step 2 — If cancel fails (order filled), retry get_position_for_coin() up to 3 times
             with 3s delay to handle Bybit fill-propagation lag (1–5s typical).
    Step 3 — Close the live position at market with reduceOnly=True.
    Step 4 — On final failure, send urgent Telegram so manual intervention can happen.

    Returns (action, success) where action is 'cancelled' | 'closed' | 'failed'.
    """
    # Step 1: attempt cancel (with built-in retries)
    cancelled = cancel_order(symbol, bybit_order_id)
    if cancelled:
        log(f"REACTIVE VETO: {symbol} order {bybit_order_id} cancelled successfully")
        print(f"   ✅ Order cancelled: {symbol} (order {bybit_order_id})")
        return "cancelled", True

    # Step 2: order may have filled — retry position check to handle API propagation lag
    log(f"REACTIVE VETO: cancel failed for {symbol} — checking for live position (up to 3 retries)")
    pos = None
    for _retry in range(3):
        pos = get_position_for_coin(symbol)
        if pos is not None:
            break
        if _retry < 2:
            log(f"REACTIVE VETO: position not yet visible for {symbol} — waiting 3s (attempt {_retry+1}/3)")
            time.sleep(3)

    if pos is None:
        # Position genuinely not found after retries — send urgent Telegram
        _msg = (f"⚠️ <b>VETO FAILED — MANUAL ACTION REQUIRED</b>\n"
                f"Symbol: {symbol}\n"
                f"Order {bybit_order_id} could not be cancelled and no open position found.\n"
                f"Please check Bybit manually and close if needed.")
        try:
            send_telegram_alert(_msg)
        except Exception:
            pass
        log(f"REACTIVE VETO FAILED: {symbol} — no position found after 3 retries, Telegram sent")
        print(f"   ✗ VETO FAILED for {symbol} — no position found. Telegram alert sent.")
        return "failed", False

    # Step 3: close position at market
    pos_size = pos.get("size", "0")
    pos_side = pos.get("side", "")      # "Buy" (LONG) or "Sell" (SHORT)
    close_side = "Sell" if pos_side == "Buy" else "Buy"

    result = bybit_request("POST", "/v5/order/create", body={
        "category":    BYBIT_CATEGORY,
        "symbol":      symbol,
        "side":        close_side,
        "orderType":   "Market",
        "qty":         pos_size,
        "reduceOnly":  True,
        "timeInForce": "IOC",
    })
    if result.get("retCode") == 0:
        log(f"REACTIVE VETO: {symbol} position closed at market (size={pos_size})")
        print(f"   ✅ Position closed at market: {symbol} {pos_size} (Strategist veto)")
        return "closed", True

    # Step 4: market close also failed — urgent Telegram
    _err_msg = result.get("retMsg", "?")
    _alert = (f"⛔ <b>VETO CLOSE FAILED — MANUAL CLOSE REQUIRED</b>\n"
              f"Symbol: {symbol}  Size: {pos_size}\n"
              f"Error: {_err_msg}\n"
              f"Go to Bybit → Positions → close {symbol} manually NOW.")
    try:
        send_telegram_alert(_alert)
    except Exception:
        pass
    log(f"REACTIVE VETO CLOSE FAILED: {symbol} size={pos_size} — {_err_msg}. Telegram sent.")
    print(f"   ✗ Failed to close {symbol}: {_err_msg} — Telegram alert sent")
    return "failed", False


def load_order_context():
    """Load order_context.json — {order_id: {symbol, side, btc_price, placed_at}}."""
    if os.path.exists(ORDER_CONTEXT_FILE):
        try:
            with open(ORDER_CONTEXT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_order_context(ctx):
    """Persist order_context.json to disk."""
    try:
        with open(ORDER_CONTEXT_FILE, "w", encoding="utf-8") as f:
            json.dump(ctx, f, indent=2)
    except Exception:
        pass


def cancel_reversed_orders(threshold_pct=3.0):
    """
    Cancel unfilled LONG entry orders where BTC has dropped >= threshold_pct%
    since the order was placed (market reversed against the direction).
    SHORTs are not cancelled — a rising BTC hurts SHORTs but we let the
    Strategist/Watchdog assess that separately.
    Reduce-only orders (partial close) are always excluded.
    Returns list of cancelled order dicts for logging/Telegram.
    """
    ctx = load_order_context()
    if not ctx:
        return []

    btc_now = get_current_price("BTCUSDT")
    if not btc_now:
        print("   ⚠ cancel_reversed_orders: could not fetch BTC price — skipping")
        return []

    result = bybit_request("GET", "/v5/order/realtime",
                           {"category": BYBIT_CATEGORY, "settleCoin": "USDT"})
    if result.get("retCode") != 0:
        return []

    open_orders = result["result"].get("list", [])
    cancelled   = []

    for order in open_orders:
        if order.get("side") != "Buy":
            continue
        if order.get("reduceOnly") is True or str(order.get("reduceOnly", "")).lower() == "true":
            continue

        order_id = order.get("orderId", "")
        symbol   = order.get("symbol", "")
        if order_id not in ctx:
            continue  # no BTC context stored for this order — skip

        btc_at_placement = ctx[order_id].get("btc_price")
        if not btc_at_placement or btc_at_placement <= 0:
            continue

        drop_pct = (btc_at_placement - btc_now) / btc_at_placement * 100
        if drop_pct >= threshold_pct:
            ok   = cancel_order(symbol, order_id)
            coin = symbol.replace("USDT", "")
            if ok:
                cancelled.append({
                    "symbol":   symbol,
                    "order_id": order_id,
                    "btc_then": btc_at_placement,
                    "btc_now":  btc_now,
                    "drop_pct": drop_pct,
                })
                print(f"   🚫 CANCELLED {coin} LONG — BTC dropped {drop_pct:.1f}% "
                      f"since placement ({btc_at_placement:.0f} → {btc_now:.0f})")
                log(f"CANCEL {coin} LONG {order_id} — BTC -{drop_pct:.1f}% "
                    f"({btc_at_placement:.0f}→{btc_now:.0f})")
                del ctx[order_id]
            else:
                print(f"   ⚠ Could not cancel {coin} LONG {order_id}")

    save_order_context(ctx)

    # Cancel any orphaned reduce-only TP close orders for symbols whose entry was cancelled.
    # place_quad_tp_closes() places 4 reduce-only orders right after the entry order.
    # If the entry never fills (or is cancelled here), those TP orders are orphaned on Bybit.
    tp_cancelled_total = 0
    if cancelled:
        _canc_syms = {c["symbol"] for c in cancelled}
        for _sym in _canc_syms:
            _tp_res = bybit_request("GET", "/v5/order/realtime", {
                "category": BYBIT_CATEGORY,
                "symbol":   _sym,
            })
            if _tp_res.get("retCode") != 0:
                continue
            for _tp_ord in _tp_res["result"].get("list", []):
                _is_ro = (_tp_ord.get("reduceOnly") is True
                          or str(_tp_ord.get("reduceOnly", "")).lower() == "true")
                if not _is_ro:
                    continue
                _tp_id = _tp_ord.get("orderId", "")
                if not _tp_id:
                    continue
                if cancel_order(_sym, _tp_id):
                    tp_cancelled_total += 1
                    _coin = _sym.replace("USDT", "")
                    print(f"   🚫 Cancelled orphaned TP close {_tp_id} for {_coin}")
                    log(f"CANCEL {_coin} TP close {_tp_id} — entry order reversed")

    if cancelled:
        lines = "\n".join(
            f"  {c['symbol'].replace('USDT','')} — BTC -{c['drop_pct']:.1f}% "
            f"({c['btc_then']:.0f}→{c['btc_now']:.0f})"
            for c in cancelled
        )
        tp_note = f"\n  🗑 {tp_cancelled_total} orphaned TP close order(s) also cancelled" if tp_cancelled_total else ""
        send_telegram_alert(
            f"🚫 <b>REVERSED ORDERS CANCELLED</b> — {len(cancelled)} LONG(s)\n"
            f"{lines}\n"
            f"  BTC dropped ≥{threshold_pct:.0f}% since placement → market reversed"
            f"{tp_note}"
        )

    return cancelled


def _count_decimals(value):
    """
    Return the number of significant decimal places for any float, safely.

    Problem: str(0.00001) = "1e-05" in Python — scientific notation has no "."
    so the old code `if "." in str(v)` returned 0 decimals, causing round() to
    collapse all sub-$1 prices to 0.0 → Bybit returns "Price invalid".

    Fix: format with %.10f first so we always get plain decimal notation,
    then strip trailing zeros to find the meaningful precision.

    Examples:
        0.001   → "0.0010000000" → "0.001"    → 3 decimals
        0.00001 → "0.0000100000" → "0.00001"  → 5 decimals
        1       → "1.0000000000" → "1."        → 0 decimals
    """
    s = f"{value:.10f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0


def round_to_step(value, step):
    """Round value DOWN to nearest step increment."""
    decimals = _count_decimals(step)
    rounded  = math.floor(value / step) * step
    return round(rounded, decimals)


def round_price(price, tick_size):
    """Round price to nearest Bybit tick size."""
    decimals = _count_decimals(tick_size)
    return round(round(price / tick_size) * tick_size, decimals)


def fmt_price(price, tick_size):
    """
    Format a price float as a string for the Bybit V5 API.

    Uses explicit decimal notation so we never send "0.0" or "0.00" when the
    real price is e.g. 0.05415 — which happens if Python's str() rounds the
    float to 0 significant decimal places after the scientific-notation bug.
    """
    decimals = _count_decimals(tick_size)
    return f"{price:.{decimals}f}"


def calc_qty(entry_price, info, size_mult=1.0):
    """
    Calculate order quantity.
    Position value = TRADE_MARGIN_USDT × LEVERAGE
    qty = position_value / entry_price, rounded to qty_step
    size_mult: drawdown-based scaling factor (0.0–1.0). Default 1.0 = full size.
    """
    position_value = TRADE_MARGIN_USDT * LEVERAGE * size_mult   # e.g. $200 × 0.75 = $150
    raw_qty        = position_value / entry_price
    qty            = round_to_step(raw_qty, info["qty_step"])
    qty            = max(qty, info["min_qty"])
    return qty


# ─────────────────────────────────────────────────────────────
# PRICE PARSING
# ─────────────────────────────────────────────────────────────

def parse_midpoint(zone_str):
    """Parse '$435-$445' → 440.0  or  '$435' → 435.0"""
    nums = re.findall(r"[\d]+\.?[\d]*", str(zone_str).replace(",", ""))
    if len(nums) >= 2:
        return (float(nums[0]) + float(nums[1])) / 2
    elif len(nums) == 1:
        return float(nums[0])
    return None


def parse_price(s):
    nums = re.findall(r"[\d]+\.?[\d]*", str(s).replace(",", ""))
    return float(nums[0]) if nums else None


# ─────────────────────────────────────────────────────────────
# PLACE ORDER
# ─────────────────────────────────────────────────────────────

def place_order(symbol, side, qty, entry_price, sl_price, tp_price, info):
    """
    Place a limit order with stop-loss and optional take-profit.
    side:     "Buy" (long) or "Sell" (short)
    tp_price: pass None to omit built-in TP (used when placing separate partial close orders)
    """
    tick    = info["tick_size"]
    entry_r = round_price(entry_price, tick)
    sl_r    = round_price(sl_price,    tick)

    body = {
        "category":      BYBIT_CATEGORY,
        "symbol":        symbol,
        "side":          side,
        "orderType":     "Limit",
        "qty":           str(qty),
        "price":         fmt_price(entry_r, tick),
        "stopLoss":      fmt_price(sl_r,    tick),
        "slTriggerBy":   "MarkPrice",
        "timeInForce":   "GTC",
        "positionIdx":   0,      # one-way mode
        "reduceOnly":    False,
        "closeOnTrigger": False,
    }
    if tp_price is not None:
        tp_r = round_price(tp_price, tick)
        body["takeProfit"]  = fmt_price(tp_r, tick)
        body["tpTriggerBy"] = "MarkPrice"

    result = bybit_request("POST", "/v5/order/create", body=body)
    if result.get("retCode") == 0:
        order_id = result["result"].get("orderId", "")
        return True, order_id
    else:
        msg  = result.get("retMsg", "Unknown error")
        code = result.get("retCode", "?")
        tp_dbg = body.get("takeProfit", "none")
        print(f"   DEBUG sent: price={body['price']}  sl={body['stopLoss']}  tp={tp_dbg}  "
              f"qty={body['qty']}  tick={tick}")
        return False, f"{msg} (retCode={code})"


def place_quad_tp_closes(symbol, entry_side, qty, tp_prices, info):
    """
    Place up to four reduce-only limit orders at 25% of qty each, targeting TP1-TP4.
    tp_prices: list of up to 4 prices [tp1, tp2, tp3, tp4] — None/0 entries are skipped.
    Each valid leg gets floor(qty / n_valid) contracts; the last leg absorbs any rounding
    remainder so the full position is always covered.
    Returns list of dicts: [{tp_label, price, qty, ok, order_id}, ...]
    """
    close_side = "Sell" if entry_side == "Buy" else "Buy"
    tick       = info["tick_size"]
    step       = info["qty_step"]
    min_q      = info["min_qty"]

    # Filter to valid (non-None, non-zero) TP prices
    valid_tps = [(f"TP{i+1}", p) for i, p in enumerate(tp_prices) if p and p > 0]
    n = len(valid_tps)
    if n == 0:
        return []

    # If position too small to split into n legs at min_q each, reduce leg count
    # (prevents last-leg overcounting when base_qty rounds below min_q)
    if qty < n * min_q:
        n = max(1, int(qty // min_q))
        valid_tps = valid_tps[:n]
    base_qty  = round_to_step(qty / n, step) if n > 0 else min_q
    base_qty  = max(base_qty, min_q)
    results   = []
    allocated = 0

    for idx, (label, tp_price) in enumerate(valid_tps):
        if idx == n - 1:
            # Last leg: use whatever quantity remains
            leg_qty = round_to_step(qty - allocated, step)
            leg_qty = max(leg_qty, min_q)
        else:
            leg_qty = base_qty

        if leg_qty < min_q:
            results.append({"tp_label": label, "price": tp_price,
                            "qty": leg_qty, "ok": False, "order_id": "qty_too_small"})
            continue

        tp_r = round_price(tp_price, tick)
        body = {
            "category":       BYBIT_CATEGORY,
            "symbol":         symbol,
            "side":           close_side,
            "orderType":      "Limit",
            "qty":            str(leg_qty),
            "price":          fmt_price(tp_r, tick),
            "timeInForce":    "GTC",
            "positionIdx":    0,
            "reduceOnly":     True,
            "closeOnTrigger": False,
        }
        r   = bybit_request("POST", "/v5/order/create", body=body)
        ok  = r.get("retCode") == 0
        oid = (r.get("result") or {}).get("orderId", "") if ok else r.get("retMsg", "?")
        results.append({"tp_label": label, "price": tp_price,
                        "qty": leg_qty, "ok": ok, "order_id": oid})
        if ok:
            allocated += leg_qty

    _fail_legs = [r for r in results if not r["ok"]]
    if _fail_legs:
        print(f"   ⚠ {len(_fail_legs)} TP leg(s) failed — position partially uncovered")

    return results


# ─────────────────────────────────────────────────────────────
# GOOGLE SHEETS
# ─────────────────────────────────────────────────────────────

def connect_sheet():
    creds_path = os.path.join(SCRIPT_DIR, GOOGLE_CREDENTIALS_FILE)
    if not os.path.exists(creds_path):
        raise FileNotFoundError(f"google_credentials.json not found in {SCRIPT_DIR}")
    # Use google.oauth2 directly — bypasses gspread.auth which fails on some Python 3.14 setups
    from google.oauth2.service_account import Credentials as _GCreds
    try:
        from gspread.client import Client as _GClient
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "gspread", "--quiet"])
        from gspread.client import Client as _GClient
    _SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = _GCreds.from_service_account_file(creds_path, scopes=_SCOPES)
    client = _GClient(auth=creds)
    return client.open_by_key(GOOGLE_SHEET_ID).sheet1


# ─────────────────────────────────────────────────────────────
# SL GUARD SWEEP
# ─────────────────────────────────────────────────────────────

def _sweep_missing_sl(data_rows):
    """
    Safety sweep — runs every trader cycle.
    Checks every open Bybit position for a missing stop-loss.

    Bybit V5 has TWO distinct SL types:
      1. Order-level SL: stopLoss in /v5/order/create body → creates a conditional stop
         order when entry fills. Does NOT populate pos["stopLoss"]. Shows as a Stop Order
         in Open Orders, NOT in the TP/SL column.
      2. Position-level SL: /v5/position/trading-stop → sets pos["stopLoss"]. Shows in
         the Bybit UI TP/SL column.

    This sweep checks BOTH types before deciding a position truly has no SL.
    Without the conditional-stop check, every order-level SL position would trigger a
    false "SL MISSING" restore every 4h cycle.
    """
    try:
        print("\n🔒 SL guard sweep — checking all open positions...")
        positions = get_open_positions_full()
        if not positions:
            print("   ✅ No open positions")
            return

        # ── Step 1: Fetch all active conditional stop orders (order-level SL) ──
        # place_order() sets stopLoss in /v5/order/create — this creates a Stop Order,
        # NOT a position-level SL. We must query order/realtime to detect it.
        cond_sl_syms = set()
        try:
            _so_result = bybit_request("GET", "/v5/order/realtime", {
                "category":    BYBIT_CATEGORY,
                "settleCoin":  "USDT",
                "orderFilter": "StopOrder",
            })
            if _so_result.get("retCode") == 0:
                for _o in _so_result["result"].get("list", []):
                    _is_ro = (_o.get("reduceOnly") is True
                              or str(_o.get("reduceOnly", "")).lower() == "true")
                    if _is_ro:
                        cond_sl_syms.add(_o.get("symbol", ""))
                        print(f"   🔍 {_o.get('symbol','')}: conditional stop order active (order-level SL)")
        except Exception as _cse:
            log(f"⚠ SL guard: could not fetch conditional stop orders: {_cse}")

        # ── Step 2: Build SL price lookup from sheet rows ───────────────────────
        # Include OPEN rows (active entries) AND WIN/TP1 rows (75% still open
        # after first partial close — SL-to-BE routine handles those separately).
        sheet_sl = {}
        for row in data_rows:
            while len(row) < 18:
                row.append("")
            status = row[COL_STATUS].strip()
            coin   = row[COL_COIN].strip().upper()
            if not coin:
                continue
            if status == "OPEN":
                sl_str = row[COL_SL].strip()
                if sl_str:
                    sheet_sl[coin] = sl_str
            elif status == "WIN" and row[COL_TP_HIT].strip() == "TP1":
                # TP1 hit: position still 75% open, SL-to-BE handles SL placement.
                # Record coin so we don't flag it as "no sheet row found".
                if coin not in sheet_sl:
                    sheet_sl[coin] = ""   # empty = SL-to-BE responsible

        restored = 0
        missing  = []

        for pos in positions:
            sym  = pos.get("symbol", "")
            coin = sym.replace("USDT", "").replace("PERP", "").upper()
            sl   = (pos.get("stopLoss", "") or "").strip()
            side = pos.get("side", "")   # "Buy" (LONG) or "Sell" (SHORT)

            # Check A: position-level SL already set
            try:
                if sl and float(sl) > 0:
                    print(f"   ✅ {sym}: position-level SL = {sl}")
                    continue
            except (ValueError, TypeError):
                pass

            # Check B: conditional stop order exists (order-level SL from place_order)
            if sym in cond_sl_syms:
                print(f"   ✅ {sym}: conditional stop order active (order-level SL) — no restore needed")
                continue

            print(f"   ⚠ {sym}: no SL found (neither position-level nor conditional) — checking sheet...")

            if coin not in sheet_sl:
                print(f"   🚨 {sym}: no OPEN/WIN sheet row — cannot auto-restore!")
                missing.append(sym)
                continue

            sl_str_from_sheet = sheet_sl[coin]
            if not sl_str_from_sheet:
                # WIN/TP1 row — SL-to-BE routine is responsible for moving SL to breakeven
                print(f"   ⚠ {sym}: WIN/TP1 row — SL-to-BE routine handles this (skipping restore)")
                continue

            try:
                sl_val = float(sl_str_from_sheet)
            except ValueError:
                print(f"   🚨 {sym}: SL in sheet not a number: {sl_str_from_sheet!r}")
                missing.append(sym)
                continue

            info     = get_instrument_info(sym)
            tick     = info["tick_size"] if info else 0.0001
            sl_fmted = fmt_price(round_price(sl_val, tick), tick)

            result = bybit_request("POST", "/v5/position/trading-stop", body={
                "category":    BYBIT_CATEGORY,
                "symbol":      sym,
                "stopLoss":    sl_fmted,
                "slTriggerBy": "MarkPrice",
                "positionIdx": 0,
            })
            if result.get("retCode") == 0:
                restored += 1
                dl = "LONG 🟢" if side == "Buy" else "SHORT 🔴"
                print(f"   🔒 {sym} {dl} — SL restored → {sl_fmted}")
                send_telegram_alert(
                    f"🔒 <b>SL RESTORED</b> — {coin} {dl}\n"
                    f"  Position had no stop-loss detected\n"
                    f"  SL now set to: <b>{sl_fmted}</b> (from sheet signal)\n"
                    f"  Position is now protected ✅"
                )
            else:
                err = result.get("retMsg", "?")
                print(f"   🚨 {sym}: SL restore failed — {err}")
                missing.append(sym)

        if missing:
            send_telegram_alert(
                f"🚨 <b>SL MISSING — MANUAL ACTION REQUIRED</b>\n"
                + "\n".join(f"  • {s}" for s in missing)
                + "\n\nThese positions have NO stop-loss and could not be auto-restored.\n"
                + "⚠️ Go to Bybit → Positions → set SL manually now!"
            )

        if restored:
            print(f"   🔒 SL guard: {restored} missing SL(s) restored")
        elif not missing:
            print(f"   ✅ All {len(positions)} position(s) have SL (position-level or conditional)")

    except Exception as _slg_e:
        log(f"⚠ SL guard sweep failed: {_slg_e}")
        print(f"   ⚠ SL guard sweep error: {_slg_e}")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    try:
        from mission import print_mission_banner
        print_mission_banner()
    except ImportError:
        pass
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║   🤖  WHALE-STREAM TRADER v47.8 — BYBIT DEMO    ║")
    print(f"║   💰  ${TRADE_MARGIN_USDT} margin × {LEVERAGE}x = ${TRADE_MARGIN_USDT*LEVERAGE} per trade        ║")
    print("╚══════════════════════════════════════════════════╝")
    print()

    # ── Validate API keys ──────────────────────────────────────
    if "YOUR_BYBIT" in BYBIT_API_KEY:
        print("✗ ERROR: Please fill in BYBIT_API_KEY and BYBIT_API_SECRET in the CONFIG section.")
        _mark_done("trader", details={"placed": [], "skipped": ["api_key_not_configured"]})
        return

    # ── Calibrate clock against Bybit server time ─────────────
    _calibrate_clock()

    # ── Detect reactive mode (--reactive flag from Strategist re-check) ──
    _is_reactive = "--reactive" in sys.argv

    # ── Cycle guard: skip if already done this 4h slot ──────────────
    _cg_path  = os.path.join(SCRIPT_DIR, "daily_status.json")
    _cg_hour  = datetime.now(BKK).hour
    _cg_cycle = str((_cg_hour // 4) * 4).zfill(2)
    _cg_key   = f"trader_{_cg_cycle}"
    if not _is_reactive:   # reactive mode always bypasses the guard
        try:
            with open(_cg_path, encoding="utf-8") as _cgf:
                _cg_data = json.load(_cgf)
            if _cg_data.get("date") == datetime.now(BKK).date().isoformat() and _cg_data.get(_cg_key):
                print(f"[CYCLE GUARD] {_cg_key} already completed today — skipping duplicate run.")
                _mark_done("trader", details={"placed": [], "skipped": ["cycle_guard"]})
                return
        except Exception:
            pass  # status missing → proceed normally
    else:
        print("⚡ REACTIVE MODE — re-checking decisions from Strategist re-check")
    # ── End cycle guard ─────────────────────────────────────────────

    # ── Check wallet balance (runs even when paused — keeps balance file fresh) ──
    print("💳 Checking Bybit demo wallet...")
    balance, total_balance, _bal_err = get_wallet_balance()
    if balance is None:
        print(f"   ✗ Could not connect to Bybit. Error: {_bal_err}")
        print("   → If retCode=10002: PC clock is out of sync — right-click clock → Adjust date/time → Sync now")
        print("   → If retCode=10003/33004: re-generate API keys in Bybit Demo > API Management")
        print("   → If 'Connection refused' or timeout: check network / Bybit status page")
        print("   → Run DIAGNOSE_BYBIT.bat for a full step-by-step connection test")
        send_telegram_alert(
            f"🚨 <b>TRADER — Bybit API Connection FAILED</b>\n"
            f"Error: <code>{_bal_err}</code>\n"
            f"No orders can be placed until connection is restored.\n"
            f"➡ Run DIAGNOSE_BYBIT.bat to identify the cause."
        )
        _mark_done("trader", details={"placed": [], "skipped": ["bybit_connection_failed"]})
        return
    print(f"   ✓ Available USDT: ${balance:,.2f}  (total: ${total_balance:,.2f})")

    # ── Fetch open positions early (needed for balance file) ──
    _early_open_positions = get_open_positions()
    _early_n_positions    = len(_early_open_positions)

    # ── Write balance file NOW — before pause check ───────────
    # This ensures bybit_balance.json always reflects current Bybit reality
    # even when the circuit breaker is holding (paused.flag present).
    write_balance_file(total_balance, open_positions=_early_n_positions)

    # ── Circuit breaker: check for PAUSED flag ────────────────
    if os.path.exists(PAUSED_FILE):
        msg = (f"🚨 <b>TRADER PAUSED — CIRCUIT BREAKER ACTIVE</b>\n"
               f"  {CIRCUIT_LOSSES} consecutive LOSSes detected on a previous run.\n"
               f"  No new orders will be placed until you manually clear the pause.\n"
               f"  To resume: delete <code>paused.flag</code> or run CLEAR_PAUSE.bat")
        print("🚨 CIRCUIT BREAKER ACTIVE — Trader is PAUSED.")
        print(f"   {CIRCUIT_LOSSES} consecutive LOSSes were detected on a previous run.")
        print("   No new orders will be placed until you clear the pause.")
        print("   → Delete 'paused.flag' or run CLEAR_PAUSE.bat to resume.")
        # NOTE: CLEAR_PAUSE.bat must also delete cb_pause_alerted.flag so the alert fires again
        # if the circuit breaker re-triggers after the next operator clear.
        _alerted_file = os.path.join(SCRIPT_DIR, "cb_pause_alerted.flag")
        if not os.path.exists(_alerted_file):
            send_telegram_alert(msg)
            try:
                open(_alerted_file, "w").close()
            except Exception:
                pass
        else:
            print("[CB] Already alerted — skipping repeat Telegram")
        log("PAUSED — circuit breaker flag present, skipping all orders")
        _mark_done("trader", details={"placed": [], "skipped": ["PAUSED — circuit breaker active"]})
        return

    # ── Low balance warning ────────────────────────────────────
    _BALANCE_GATE4_FLOOR    = BYBIT_START_BALANCE * 0.85  # Gate 4 = 15% drawdown ($500×0.85=$425)
    _BALANCE_WARN_THRESHOLD = _BALANCE_GATE4_FLOOR + 25   # warn $25 above Gate 4 floor
    if balance < _BALANCE_WARN_THRESHOLD:
        _dd_pct = (BYBIT_START_BALANCE - balance) / BYBIT_START_BALANCE * 100
        _remaining = balance - _BALANCE_GATE4_FLOOR
        _warn_level = "🚨 CRITICAL" if balance < _BALANCE_GATE4_FLOOR + 10 else "⚠️ WARNING"
        _breach_note = " ⚡ Gate 4 active now!" if balance < _BALANCE_GATE4_FLOOR else ""
        send_telegram_alert(
            f"{_warn_level} <b>BYBIT BALANCE LOW</b>\n"
            f"  Current balance : ${balance:,.2f}\n"
            f"  Drawdown        : {_dd_pct:.1f}% from ${BYBIT_START_BALANCE:.0f} start\n"
            f"  Gate 4 floor    : ${_BALANCE_GATE4_FLOOR:.0f} (15% drawdown threshold)\n"
            f"  Remaining margin: ${_remaining:,.2f} before Gate 4 breach{_breach_note}"
        )
        log(f"LOW BALANCE WARNING — ${balance:,.2f} ({_dd_pct:.1f}% drawdown)")

    if balance < TRADE_MARGIN_USDT:
        print(f"   ✗ Balance too low. Need at least ${TRADE_MARGIN_USDT} to place one trade.")
        _mark_done("trader", details={"placed": [], "skipped": ["balance_too_low"]})
        return

    # ── Load Google Sheets ─────────────────────────────────────
    print("\n📋 Loading signals from Google Sheets...")
    try:
        sheet = connect_sheet()
        log("Google Sheets connected OK")
    except Exception as e:
        log(f"Google Sheets FAILED: {e}")
        print(f"   ✗ Google Sheets error: {e}")
        _mark_done("trader", details={"placed": [], "skipped": ["sheets_failed"]})
        return

    all_rows  = sheet.get_all_values()
    data_rows = all_rows[1:] if len(all_rows) > 1 else []

    # ── SL guard: restore missing stop-losses on all open positions ──
    # Runs before any new orders — protects positions regardless of CB state.
    _sweep_missing_sl(data_rows)

    # ── Circuit breaker: check for consecutive LOSSes ─────────
    # ── Dynamic circuit breaker threshold ─────────────────────
    # In LONG-only (REPAIR MODE), raise threshold: 3→5 to avoid
    # pausing on normal single-day LONG volatility.
    _cb_threshold = CIRCUIT_LOSSES
    if os.path.exists(SHORT_REPAIR_FILE):
        _cb_threshold = 5
        log(f"REPAIR MODE active — circuit breaker threshold raised to {_cb_threshold}")
    # ──────────────────────────────────────────────────────────

    # ── CB grace period: did operator recently clear the CB? ──
    # When RUN_FULL_CYCLE_NOW.bat or CLEAR_PAUSE.bat clears paused.flag,
    # it also writes cb_grace.txt. We respect that override for 60 minutes
    # so the Trader gets ONE real run before the CB can re-arm. Without
    # this, the Trader would immediately re-create paused.flag from the
    # same stale LOSS streak, making manual clears completely ineffective.
    _cb_grace_active = False
    _grace_age_min   = 0            # default — avoids NameError if try block partially executes
    _cb_grace_file   = os.path.join(SCRIPT_DIR, "cb_grace.txt")
    try:
        if os.path.exists(_cb_grace_file):
            with open(_cb_grace_file, "r") as _cbgf:
                _grace_data = json.load(_cbgf)
            _grace_ts = datetime.fromisoformat(_grace_data.get("cleared_at", ""))
            # fromisoformat returns UTC-aware if string ends with +00:00
            _now_utc  = datetime.now(timezone.utc)
            if _grace_ts.tzinfo is None:
                _grace_ts = _grace_ts.replace(tzinfo=timezone.utc)
            _grace_age_min = (_now_utc - _grace_ts).total_seconds() / 60
            if _grace_age_min < 60:
                _cb_grace_active = True
                log(f"CB grace period active — cleared {_grace_age_min:.0f}min ago by operator")
                print(f"   ⚡ CB grace period active ({_grace_age_min:.0f}min ago) — overriding streak check")
    except Exception as _gex:
        pass  # grace file unreadable — treat as no grace

    if check_circuit_breaker(data_rows, threshold=_cb_threshold):
        if _cb_grace_active:
            # Operator cleared the CB — let this ONE run place orders
            _grace_msg = (
                f"⚡ <b>CB GRACE OVERRIDE — TRADING THIS CYCLE</b>\n"
                f"  Last {_cb_threshold} resolved trades were LOSS, but you recently cleared the CB.\n"
                f"  Placing orders this run as operator override.\n"
                f"  CB will re-arm on the NEXT cycle if the loss streak continues."
            )
            print(f"\n⚡ CB GRACE OVERRIDE — operator cleared CB recently, proceeding with trading.")
            send_telegram_alert(_grace_msg)
            log(f"CB GRACE OVERRIDE — trading despite {_cb_threshold} consecutive LOSSes (operator cleared {_grace_age_min:.0f}min ago)")
            # Fall through to normal trading below
        else:
            # Standard CB behavior — write flag and pause
            try:
                bkk_now_flag = datetime.now(BKK).strftime("%Y-%m-%d %H:%M BKK")
                with open(PAUSED_FILE, "w", encoding="utf-8") as f:
                    f.write(f"PAUSED by circuit breaker at {bkk_now_flag}\n"
                            f"Last {_cb_threshold} resolved trades were all LOSS.\n"
                            f"Delete this file or run CLEAR_PAUSE.bat to resume trading.\n")
            except Exception:
                pass
            msg = (f"🚨 <b>CIRCUIT BREAKER TRIGGERED — TRADER NOW PAUSED</b>\n"
                   f"  Last {_cb_threshold} resolved trades all resolved as LOSS.\n"
                   f"  Possible bad market regime or systematic issue.\n"
                   f"  ⛔ No new orders placed this run.\n"
                   f"  To resume: review the situation, then run CLEAR_PAUSE.bat")
            print(f"\n🚨 CIRCUIT BREAKER TRIGGERED!")
            print(f"   Last {_cb_threshold} resolved trades all LOSS — auto-pausing trader.")
            print("   Written: paused.flag")
            print("   → Run CLEAR_PAUSE.bat after reviewing the situation to resume.")
            send_telegram_alert(msg)
            log(f"CIRCUIT BREAKER — last {_cb_threshold} trades all LOSS, trader PAUSED")
            _mark_done("trader", details={"placed": [], "skipped": ["CIRCUIT BREAKER TRIGGERED — auto-paused"]})
            return

    # BKK time now (UTC+7)
    bkk_now = datetime.now(BKK)

    # Maximum signal age before the trader stops trying to fill it.
    # Both the bot AND the trader run every 4 hours.  Signals are written by
    # the bot immediately at run time, so a freshly-written signal is 0h old.
    # We allow up to 4h so the very next trader run (up to 4h later) can still
    # act on it.  Beyond 4h the entry zone is likely stale (price has moved).
    MAX_SIGNAL_AGE_HOURS = 4

    # Get FRESH OPEN trades only — signals from the last MAX_SIGNAL_AGE_HOURS hours
    # This prevents placing orders at stale entry zones from days-old signals.
    #
    # NOTE on the "984 stale skips" pattern: The sheet accumulates OPEN rows over
    # time (signals never filled by Bybit stay OPEN indefinitely until the tracker
    # marks them expired).  Each run re-counts ALL historical OPEN rows as stale,
    # so the counter grows linearly with sheet history — it does NOT mean fresh
    # signals are arriving pre-stale.  The 4h window is correct; we just need
    # better logging to separate "old accumulated rows" from "truly fresh but stale".
    open_trades   = []
    skipped_stale = 0          # OPEN rows that are older than MAX_SIGNAL_AGE_HOURS
    skipped_stale_ages = []    # collect ages for summary stats

    for i, row in enumerate(data_rows):
        while len(row) < 12:
            row.append("")
        if row[COL_STATUS].strip() != "OPEN":
            continue
        if row[COL_COIN].strip() in ("", "STAY OUT", "—"):
            continue
        # Check signal age
        ts_str = row[COL_TIMESTAMP].strip()
        if ts_str:
            try:
                sig_dt = datetime.strptime(ts_str.replace(" BKK", ""), "%Y-%m-%d %H:%M")
                sig_dt = sig_dt.replace(tzinfo=BKK)
                age_hours = (bkk_now - sig_dt).total_seconds() / 3600
                if age_hours > MAX_SIGNAL_AGE_HOURS:
                    skipped_stale += 1
                    skipped_stale_ages.append(age_hours)
                    coin_label = row[COL_COIN].strip()
                    print(f"   ⏭ Skipping {coin_label} — signal is {age_hours:.1f}h old "
                          f"(max {MAX_SIGNAL_AGE_HOURS}h)")
                    continue
            except Exception:
                print(f"   ⏭ Skipping {row[COL_COIN].strip()} — timestamp unparseable: {ts_str!r}")
                continue  # unparseable timestamp → skip rather than silently include
        open_trades.append((i + 2, row))  # (sheet row 1-indexed, data)

    if skipped_stale:
        avg_age = sum(skipped_stale_ages) / len(skipped_stale_ages)
        max_age = max(skipped_stale_ages)
        print(f"   ⏭ {skipped_stale} stale OPEN signal(s) skipped "
              f"(avg age: {avg_age:.1f}h, max age: {max_age:.1f}h)")

    # Take only the most recent MAX_OPEN_TRADES
    open_trades = open_trades[-MAX_OPEN_TRADES:]
    print(f"   ✓ Found {len(open_trades)} fresh OPEN signal(s) to trade")

    if not open_trades:
        print("\n   No OPEN signals to trade. Run whale_stream_bot.py first to generate signals.")
        _mark_done("trader", details={"placed": [], "skipped": ["no_signals"]})
        return

    # ── Check existing positions + open orders on Bybit ──────────
    print("\n📊 Checking existing Bybit positions and orders...")
    open_positions = _early_open_positions   # already fetched before pause check
    open_orders    = get_open_orders()
    already_active = open_positions | open_orders   # union of both sets
    n_positions    = _early_n_positions      # already counted before pause check
    if already_active:
        print(f"   ⚠ Already active (position or order): {', '.join(already_active)}")
    else:
        print("   ✓ No existing positions or orders")

    # balance file already written before the pause check — no second write needed

    # ── Fix 1: Hard cap — max 8 concurrent open positions ─────
    # Read bybit_balance.json to get the live open_positions count.
    # If >= 8 simultaneous trades are already active, skip ALL orders
    # this run to prevent a market turn from triggering a cascade of SLs.
    _bb_open_positions = n_positions   # fallback: use the live count we just fetched
    try:
        with open(BYBIT_BALANCE_FILE, "r", encoding="utf-8") as _bb_f:
            _bb_data = json.load(_bb_f)
            _bb_open_positions = int(_bb_data.get("open_positions", n_positions))
    except Exception:
        pass   # use live n_positions as fallback

    MAX_CONCURRENT_POSITIONS = 8
    if _bb_open_positions >= MAX_CONCURRENT_POSITIONS:
        _cap_msg = (
            f"⚠️ POSITION CAP — {_bb_open_positions} open trades already active. "
            f"Skipping this run to protect capital."
        )
        log(f"POSITION CAP — {_bb_open_positions}/{MAX_CONCURRENT_POSITIONS} positions open, skipping all orders")
        print(f"\n   ⚠ POSITION CAP: {_bb_open_positions} open trades >= {MAX_CONCURRENT_POSITIONS} limit")
        print("   No new orders placed this run to avoid cascade SL exposure.")
        send_telegram_alert(_cap_msg)
        _mark_done("trader", details={"placed": [], "skipped": [f"position_cap_{_bb_open_positions}"]})
        return

    # ── Fix 2: Drawdown-based position size scaling ────────────
    # As drawdown grows, reduce size to slow capital erosion.
    #   < 8% drawdown  → full size (1.0×)
    #   8–12% drawdown → 75% size (caution zone)
    #   ≥ 12% drawdown → 60% size (danger zone — currently here at ~13.2%)
    _bb_balance       = total_balance   # live Bybit balance
    _bb_start_balance = BYBIT_START_BALANCE
    try:
        with open(BYBIT_BALANCE_FILE, "r", encoding="utf-8") as _bb_f2:
            _bb_data2 = json.load(_bb_f2)
            _bb_balance       = float(_bb_data2.get("balance",       total_balance))
            _bb_start_balance = float(_bb_data2.get("start_balance", BYBIT_START_BALANCE))
    except Exception:
        pass   # use live values as fallback

    _drawdown_pct = max(0.0, (_bb_start_balance - _bb_balance) / _bb_start_balance * 100) if _bb_start_balance > 0 else 0.0
    if _drawdown_pct < 8:
        _size_mult = 1.0      # full size
    elif _drawdown_pct < 12:
        _size_mult = 0.75     # 75% — caution zone
    else:
        _size_mult = 0.60     # 60% — danger zone

    if _size_mult < 1.0:
        log(f"DRAWDOWN SCALING — {_drawdown_pct:.1f}% drawdown → size multiplier {_size_mult:.2f}x "
            f"(${_bb_balance:.2f} / ${_bb_start_balance:.2f})")
        print(f"\n   ⚠ DRAWDOWN SCALING: {_drawdown_pct:.1f}% drawdown → "
              f"trading at {int(_size_mult*100)}% size ({_size_mult:.2f}×)")
    else:
        log(f"DRAWDOWN OK — {_drawdown_pct:.1f}% drawdown → full size (1.0×)")
        print(f"   ✓ Drawdown {_drawdown_pct:.1f}% — full position size (1.0×)")

    # ── Gate 4 breach override — drawdown > 15% ──────────────────────────────
    _GATE4_BREACH = _drawdown_pct > 15.0
    if _GATE4_BREACH:
        _size_mult = 0.40  # ultra-conservative: below the normal 0.60 floor
        # Only fire the Telegram alert once (when first entering breach mode).
        # GATE4_BREACH_FILE is created here and deleted when balance recovers in
        # write_balance_file() — this avoids spamming the alert every 4-hour run.
        if not os.path.exists(GATE4_BREACH_FILE):
            _g4_msg = (
                f"🔴 GATE 4 BREACH MODE — {_drawdown_pct:.1f}% drawdown exceeds 15% limit.\n"
                f"  Ultra-conservative activated: 40% size, both LONG + SHORT, max 4 positions."
            )
            send_telegram_alert(_g4_msg)
            print(_g4_msg)
            try:
                bkk_g4 = datetime.now(BKK).strftime("%Y-%m-%d %H:%M BKK")
                with open(GATE4_BREACH_FILE, "w", encoding="utf-8") as _g4f:
                    _g4f.write(f"Gate 4 breach entered at {bkk_g4}\n"
                               f"Balance: ${_bb_balance:.2f}  Drawdown: {_drawdown_pct:.1f}%\n"
                               f"Deleted automatically when balance recovers above $425.\n")
            except Exception:
                pass

    # ── Risk cap: max 50% of total balance deployed ───────────
    deployed_est = len(already_active) * TRADE_MARGIN_USDT  # includes pending entry orders
    deployed_pct = (deployed_est / total_balance * 100) if total_balance > 0 else 0
    cap_usdt     = total_balance * MAX_DEPLOYED_FRACTION
    if deployed_est >= cap_usdt:
        msg = (f"🛡 <b>TRADER RISK CAP</b>\n"
               f"  ~${deployed_est} deployed ({deployed_pct:.0f}% of ${total_balance:.0f}) "
               f"≥ {MAX_DEPLOYED_FRACTION*100:.0f}% cap — no new orders this run")
        print(f"\n   🛡 Risk cap reached: ~${deployed_est} deployed ({deployed_pct:.0f}%) "
              f"≥ {MAX_DEPLOYED_FRACTION*100:.0f}% of ${total_balance:.0f} — skipping all new orders")
        send_telegram_alert(msg)
        log(f"RISK CAP — ~${deployed_est} deployed ({deployed_pct:.0f}%) ≥ {MAX_DEPLOYED_FRACTION*100:.0f}% cap")
        _mark_done("trader", details={"placed": [], "skipped": [f"risk_cap_{deployed_pct:.0f}pct"]})
        return
    else:
        print(f"   💼 Risk check OK: ~${deployed_est} deployed ({deployed_pct:.0f}%) "
              f"— cap is {MAX_DEPLOYED_FRACTION*100:.0f}% (${cap_usdt:.0f})")

    # ── Load Strategist decisions (written by whale_stream_strategist.py at :10) ──
    # If the file exists, any coin+direction marked VETO will be skipped.
    # If file doesn't exist (Strategist didn't run), we proceed normally — graceful degradation.
    DECISIONS_FILE = os.path.join(SCRIPT_DIR, "strategist_decisions.json")
    _strat_vetoes  = set()    # set of (coin, direction) pairs to skip
    _strat_reduces = set()    # set of (coin, direction) pairs to trade at 50% size
    _strat_loaded  = False
    _strat_data    = {}    # safe default — prevents NameError if outer try silently fails
    if os.path.exists(DECISIONS_FILE):
        try:
            with open(DECISIONS_FILE, "r", encoding="utf-8") as _sf:
                _strat_data = json.load(_sf)
            for _d in _strat_data.get("decisions", []):
                _key = (_d.get("coin", "").upper(), _d.get("direction", "").upper())
                if _d.get("decision") == "VETO":
                    _strat_vetoes.add(_key)
                elif _d.get("decision") == "REDUCE_SIZE":
                    _strat_reduces.add(_key)
            _strat_loaded = True
            log(f"STRATEGIST loaded — {len(_strat_vetoes)} veto(s), {len(_strat_reduces)} reduce(s)  "
                f"(run: {_strat_data.get('run_at','?')})")
            print(f"   🧠 Strategist: {len(_strat_vetoes)} VETO(s), {len(_strat_reduces)} REDUCE(s)  "
                  f"[{_strat_data.get('run_at','?')}]")
        except Exception as _se:
            log(f"STRATEGIST file unreadable: {_se} — proceeding without veto")
            print(f"   ⚠ Strategist file unreadable: {_se} — no vetoes applied")
    else:
        print("   ℹ Strategist file not found — no vetoes applied (Strategist may not have run yet)")

    # ── REACTIVE MODE: cancel/close orders Strategist has newly vetoed ──────
    if _is_reactive and _strat_loaded:
        print("\n🔄 REACTIVE MODE — scanning for newly vetoed placed orders...")
        _react_cancelled = 0
        _react_closed    = 0
        _react_failed    = 0
        # Use ALL OPEN rows (not age-filtered open_trades) so older placed orders are found too
        _all_placed_open = [(i + 2, r) for i, r in enumerate(data_rows)
                            if (len(r) > COL_STATUS and r[COL_STATUS].strip().upper() == "OPEN"
                                and len(r) > COL_BYBIT_ID and r[COL_BYBIT_ID].strip())]
        for _rr_idx, _rr_row in _all_placed_open:
            _rr_coin   = _rr_row[COL_COIN].strip().upper()
            _rr_signal = _rr_row[COL_SIGNAL].strip().upper()
            _rr_dir    = "LONG" if ("LONG" in _rr_signal or "🟢" in _rr_signal) else "SHORT"
            _rr_bybit  = _rr_row[COL_BYBIT_ID].strip() if len(_rr_row) > COL_BYBIT_ID else ""
            _rr_key    = (_rr_coin, _rr_dir)
            _rr_symbol = f"{_rr_coin}USDT"

            if not _rr_bybit:
                # Not yet placed — no cancellation needed (will be skipped in order loop below)
                continue
            if _rr_key not in _strat_vetoes:
                # Not vetoed — leave it
                continue

            # Placed AND vetoed → try to cancel / close
            print(f"   ⛔ VETO on placed order: {_rr_coin} {_rr_dir}  (order {_rr_bybit})")
            _act, _ok = close_position_at_market_for_veto(_rr_symbol, _rr_bybit)
            if _act == "cancelled":
                _react_cancelled += 1
            elif _act == "closed":
                _react_closed += 1
            else:
                _react_failed += 1

        print(f"   ✅ Reactive scan done: {_react_cancelled} cancelled, "
              f"{_react_closed} closed at market, {_react_failed} failed")
    # ── End reactive mode veto scan ──────────────────────────────────────────

    # ── Cancel-on-reversal: drop LONG orders where BTC moved ≥3% against us ──
    print("\n🔍 Checking for reversed LONG orders (BTC ≥3% drop since placement)...")
    try:
        _reversed = cancel_reversed_orders(threshold_pct=3.0)
        if not _reversed:
            print("   ✅ No reversed LONG orders detected")
    except Exception as _rev_e:
        print(f"   ⚠ cancel_reversed_orders failed: {_rev_e}")

    # ── Place orders ───────────────────────────────────────────
    print("\n🚀 Placing orders...\n")
    placed = 0
    placed_coins = []          # coin names successfully ordered this run
    sheet_order_writes = []   # (sheet_row_idx, order_id) — batch-written at end
    unreachable_rows   = []   # rows to mark UNREACHABLE in Sheets
    skip_counts = load_skip_counts()
    skipped_shorts = []       # coins skipped due to SHORT REPAIR MODE

    for sheet_row_idx, row in open_trades:
        coin       = row[COL_COIN].strip()
        signal     = row[COL_SIGNAL].strip()

        # ── Reactive mode: skip coins already placed this cycle ──────────
        if _is_reactive:
            _existing_id = row[COL_BYBIT_ID].strip() if len(row) > COL_BYBIT_ID else ""
            if _existing_id:
                continue   # already placed — handled by reactive veto scan above or leave as-is

        entry_zone = row[COL_ENTRY_ZONE].strip()
        sl_str     = row[COL_SL].strip()
        tp1_str    = row[COL_TP1].strip()
        tp2_str    = row[COL_TP2].strip() if len(row) > COL_TP2 else ""
        tp3_str    = row[COL_TP3].strip() if len(row) > COL_TP3 else ""
        tp4_str    = row[COL_TP4].strip() if len(row) > COL_TP4 else ""
        conf_str   = row[COL_CONF].strip() if len(row) > COL_CONF else ""

        symbol = f"{coin}USDT"
        side   = "Buy" if ("LONG" in signal.upper() or "🟢" in signal) else "Sell"
        dir_label = "LONG 🟢" if side == "Buy" else "SHORT 🔴"

        print(f"── {coin} {dir_label} ──────────────────────────")

        # ── SHORT REPAIR MODE — skip unless approved recovery coin ─────────────
        # SHORT_RECOVERY_COINS (H, FF) defined at module level — bypass REPAIR MODE
        if side == "Sell" and os.path.exists(SHORT_REPAIR_FILE):
            if coin.upper() in SHORT_RECOVERY_COINS:
                log(f"ALLOW {coin} SHORT — approved recovery coin (REPAIR MODE active)")
                print(f"   ✅ {coin} is an approved recovery coin — SHORT allowed in REPAIR MODE")
            else:
                log(f"SKIP {coin} SHORT — short_repair.flag present (not an approved recovery coin)")
                skipped_shorts.append(coin)
                print()
                continue
        # ── end SHORT REPAIR MODE ──────────────────────────────────────────────

        # ── Gate 4 breach mode — BOTH directions, max 4 positions, 0.40x size ──
        # NOTE: SHORTs are NO LONGER blocked in Gate 4 breach mode.
        # SHORT WR is 95% last 20 trades — they are our strongest performers.
        # In a bear market, blocking SHORTs means blocking the best money-makers.
        # Strategy: trade BOTH directions but ultra-small (0.40x) with a 4-position cap.
        if _GATE4_BREACH:
            if n_positions >= 4:
                _g4_cap_msg = (f"⛔ GATE 4 MODE — position cap reached "
                               f"({n_positions}/4) — skipping {coin}")
                print(f"   {_g4_cap_msg}")
                log(_g4_cap_msg)
                print()
                continue
        # ── end Gate 4 breach mode ─────────────────────────────────────────────

        # ── LONG_COIN_AVOID_LIST — skip LONG signals for poor-WR coins ────────
        if side == "Buy" and coin.upper() in LONG_COIN_AVOID_LIST:
            _avoid_msg = f"⏭ Skipping {coin} LONG — on LONG avoid list (poor historical WR)"
            log(_avoid_msg)
            print(f"   {_avoid_msg}")
            print()
            continue
        # ── end LONG_COIN_AVOID_LIST ───────────────────────────────────────────

        # ── Strategist VETO / REDUCE check ─────────────────────────────────────
        _strat_key = (coin.upper(), "LONG" if side == "Buy" else "SHORT")
        if _strat_key in _strat_vetoes:
            # Find the reason from the decisions file for logging
            _veto_reason = "Strategist veto"
            try:
                for _d in _strat_data.get("decisions", []):
                    if _d.get("coin","").upper() == coin.upper():
                        _veto_reason = _d.get("reason", "Strategist veto")
                        break
            except Exception:
                pass
            _veto_msg = f"⛔ STRATEGIST VETO: {coin} {_strat_key[1]} — {_veto_reason}"
            log(_veto_msg)
            print(f"   {_veto_msg}")
            print()
            continue
        if _strat_key in _strat_reduces:
            # Half-size trade — use local multiplier so other coins are unaffected
            _coin_size_mult = round(_size_mult * 0.5, 3)
            print(f"   ⚠️ STRATEGIST REDUCE: {coin} {_strat_key[1]} — trading at {_coin_size_mult:.2f}x size (was {_size_mult:.2f}x)")
            log(f"STRATEGIST REDUCE: {coin} {_strat_key[1]} — size {_size_mult:.2f}x → {_coin_size_mult:.2f}x")
        else:
            _coin_size_mult = _size_mult
        # Minimum size floor — Gate 4 (0.40×) + REDUCE_SIZE (×0.5) = 0.20×, which can
        # fall below Bybit's minimum order value. Floor at 0.25× to stay safely above.
        _MIN_SIZE_MULT = 0.25
        if _coin_size_mult < _MIN_SIZE_MULT:
            log(f"SIZE FLOOR: {coin} — {_coin_size_mult:.3f}x below minimum {_MIN_SIZE_MULT}x floor → clamped to {_MIN_SIZE_MULT}x")
            print(f"   ⚠️ SIZE FLOOR: {coin} multiplier {_coin_size_mult:.2f}x → clamped to {_MIN_SIZE_MULT}x (Bybit min order protection)")
            _coin_size_mult = _MIN_SIZE_MULT
        # ── end Strategist check ───────────────────────────────────────────────

        # Skip if already have a position OR an unfilled order
        if symbol in already_active:
            print(f"   ⚠ Already have an active position/order for {symbol} — skipping")
            continue

        # Parse prices
        entry = parse_midpoint(entry_zone)
        sl    = parse_price(sl_str)
        tp1   = parse_price(tp1_str)
        tp2   = parse_price(tp2_str) if tp2_str else None
        tp3   = parse_price(tp3_str) if tp3_str else None
        tp4   = parse_price(tp4_str) if tp4_str else None
        # Extract numeric confidence (e.g. "92%" → 92, "92" → 92)
        try:
            conf_val = float(conf_str.replace("%", "").strip())
        except (ValueError, AttributeError):
            conf_val = 0

        # ── Code-level confidence floor (belt+suspenders after Strategist) ──
        if side == "Sell" and conf_val < 95:
            print(f"   ✗ {coin} SHORT: conf {conf_val:.0f}% < 95% code floor — skipping")
            continue
        if side == "Buy" and conf_val < 88:
            print(f"   ✗ {coin} LONG: conf {conf_val:.0f}% < 88% floor — skipping")
            continue

        if entry is None or sl is None or tp1 is None:  # explicit None check — 0.0 is a valid price
            print(f"   ✗ Could not parse prices — skipping")
            print(f"     Entry: {entry_zone}  SL: {sl_str}  TP1: {tp1_str}")
            continue

        # Validate SL/TP direction
        if side == "Buy":
            if sl >= entry:
                print(f"   ✗ Invalid: SL ({sl}) >= Entry ({entry}) for LONG — skipping")
                continue
            if tp1 <= entry:
                print(f"   ✗ Invalid: TP1 ({tp1}) <= Entry ({entry}) for LONG — skipping")
                continue
        else:
            if sl <= entry:
                print(f"   ✗ Invalid: SL ({sl}) <= Entry ({entry}) for SHORT — skipping")
                continue
            if tp1 >= entry:
                print(f"   ✗ Invalid: TP1 ({tp1}) >= Entry ({entry}) for SHORT — skipping")
                continue

        # Get instrument info
        info = get_instrument_info(symbol)
        if not info:
            print(f"   ✗ {symbol} not found on Bybit perpetuals — skipping")
            continue

        # ── Pre-flight: distance from current market price ─────
        # Bybit rejects limit orders that are more than ~10% from the mark price.
        # We use 9% as our threshold to catch these before hitting the API.
        current_price = get_current_price(symbol)
        if current_price and current_price > 0:
            distance_pct = abs(entry - current_price) / current_price * 100
            if distance_pct > MAX_ENTRY_DISTANCE_PCT:
                direction = "above" if entry > current_price else "below"

                # Track consecutive mark-price skips for this row
                skip_key   = f"row_{sheet_row_idx}"
                consecutive = skip_counts.get(skip_key, 0) + 1
                skip_counts[skip_key] = consecutive

                print(f"   ⏭ Entry too far from mark: signal at {entry:.6g} vs mark {current_price:.6g} "
                      f"({distance_pct:.1f}% {direction}) — Bybit would reject")
                print(f"      Limit orders must be within {MAX_ENTRY_DISTANCE_PCT}% of mark price "
                      f"— skip {consecutive}/{MAX_MARK_SKIPS}")

                if consecutive >= MAX_MARK_SKIPS:
                    # Signal is stuck — mark UNREACHABLE so it stops blocking future runs
                    unreachable_rows.append(sheet_row_idx)
                    skip_counts.pop(skip_key)   # clear counter once actioned
                    print(f"   ☠ UNREACHABLE after {consecutive} skips — will remove from active signals")
                    send_telegram_alert(
                        f"☠ <b>SIGNAL UNREACHABLE</b> — {coin} {dir_label}\n"
                        f"  Entry {entry:.6g} vs mark {current_price:.6g} ({distance_pct:.1f}% {direction})\n"
                        f"  Skipped {consecutive} times — marking UNREACHABLE and removing"
                    )
                else:
                    send_telegram_alert(
                        f"⏭ <b>TRADER SKIPPED</b> — {coin} {dir_label} (skip {consecutive}/{MAX_MARK_SKIPS})\n"
                        f"  Entry {entry:.6g} vs mark {current_price:.6g} ({distance_pct:.1f}% {direction})\n"
                        f"  Entry zone too far from market — stale signal"
                    )
                print()
                continue
            else:
                print(f"   💹 Mark price: {current_price:.6g}  "
                      f"(entry is {distance_pct:.1f}% from mark ✓)")

                # ── Price-clamp: Bybit's real band is often tighter than 8% ──────────
                # Many coins are rejected at 3-5% from mark even though they pass our
                # MAX_ENTRY_DISTANCE_PCT guard.  Clamp to mark ± BYBIT_PRICE_CLAMP_PCT
                # so we recover these trades instead of sending a doomed order.
                # Also enforce instrument static minPrice / maxPrice bounds.
                clamp_lo = current_price * (1 - BYBIT_PRICE_CLAMP_PCT / 100)
                clamp_hi = current_price * (1 + BYBIT_PRICE_CLAMP_PCT / 100)
                # Apply static floor / ceiling from instrument info (if set)
                static_min = info.get("min_price", 0) if info else 0
                static_max = info.get("max_price", 0) if info else 0
                if static_min > 0:
                    clamp_lo = max(clamp_lo, static_min)
                if static_max > 0:
                    clamp_hi = min(clamp_hi, static_max)

                original_entry = entry
                if entry < clamp_lo:
                    entry = round_price(clamp_lo, info["tick_size"])
                    pct   = abs(original_entry - current_price) / current_price * 100
                    log(f"   ⚠ Entry price {original_entry:.6g} is {pct:.1f}% from mark {current_price:.6g} — clamping to {entry:.6g}")
                    print(f"   ⚠ Entry price {original_entry:.6g} is {pct:.1f}% from mark {current_price:.6g} — clamping to {entry:.6g}")
                elif entry > clamp_hi:
                    entry = round_price(clamp_hi, info["tick_size"])
                    pct   = abs(original_entry - current_price) / current_price * 100
                    log(f"   ⚠ Entry price {original_entry:.6g} is {pct:.1f}% from mark {current_price:.6g} — clamping to {entry:.6g}")
                    print(f"   ⚠ Entry price {original_entry:.6g} is {pct:.1f}% from mark {current_price:.6g} — clamping to {entry:.6g}")
                # ── end price-clamp ────────────────────────────────────────────────────

                # Post-clamp SL sanity check: ensure clamp didn't invert the
                # SL relative to the (possibly adjusted) entry price.
                if entry != original_entry:
                    sl_invalid = (side == "Buy"  and sl >= entry) or \
                                 (side == "Sell" and sl <= entry)
                    if sl_invalid:
                        print(f"   ✗ Post-clamp SL ({sl:.6g}) invalid vs clamped entry ({entry:.6g}) — skipping")
                        log(f"   ✗ Post-clamp SL ({sl:.6g}) invalid vs clamped entry ({entry:.6g}) for {coin} — skipping")
                        print()
                        continue
        else:
            print(f"   ⚠ Could not fetch current price for {symbol} — proceeding anyway")

        # Set leverage
        lev_ok = set_leverage(symbol)
        if not lev_ok:
            print(f"   ✗ Could not set {LEVERAGE}x leverage for {symbol}")
            continue

        # Calculate qty — apply drawdown-based size multiplier (+ Strategist REDUCE if active)
        qty = calc_qty(entry, info, size_mult=_coin_size_mult)
        if qty <= 0:
            print(f"   ✗ Position too small for {symbol} (min qty: {info['min_qty']}) — skipping")
            print(f"     Try increasing TRADE_MARGIN_USDT or reducing leverage")
            continue

        position_val = qty * entry
        tp2_display  = f"  TP2: {tp2:.6g}" if tp2 else ""
        tp3_display  = f"  TP3: {tp3:.6g}" if tp3 else ""
        tp4_display  = f"  TP4: {tp4:.6g}" if tp4 else ""
        if conf_val >= 92:
            tier_display = f" [TIER 1 ELITE — {conf_val:.0f}%]"
        elif conf_val >= 88:
            tier_display = f" [TIER 2 — {conf_val:.0f}%]"
        elif conf_val >= 85:
            tier_display = f" [TIER 3 — {conf_val:.0f}%]"
        else:
            tier_display = f" [{conf_val:.0f}%]"
        _n_tps = sum(1 for p in [tp1, tp2, tp3, tp4] if p)
        print(f"   Entry : {entry:.6g}  SL: {sl:.6g}  TP1: {tp1:.6g}{tp2_display}{tp3_display}{tp4_display}  → {_n_tps}×25% quad-TP{tier_display}")
        print(f"   Qty   : {qty} contracts  (≈${position_val:.2f} position)")

        # ── Place entry order — always NO built-in TP; quad-TP closes handle exits ──
        ok, result  = place_order(symbol, side, qty, entry, sl, None, info)

        if ok:
            order_id = result
            placed  += 1
            placed_coins.append(coin)
            n_positions += 1   # keep Gate 4 position cap accurate mid-loop
            sheet_order_writes.append((sheet_row_idx, order_id))
            skip_counts.pop(f"row_{sheet_row_idx}", None)

            # ── Store BTC price at placement for cancel-on-reversal ────────────
            _ctx = load_order_context()
            _btc_at_placement = get_current_price("BTCUSDT")
            _ctx[order_id] = {
                "symbol":    symbol,
                "side":      side,
                "btc_price": _btc_at_placement,
                "placed_at": datetime.now(BKK).strftime("%Y-%m-%d %H:%M BKK"),
            }
            save_order_context(_ctx)

            # ── Place 4×25% reduce-only TP orders ────────────────────────────
            _tp_prices    = [tp1, tp2, tp3, tp4]
            _quad_results = place_quad_tp_closes(symbol, side, qty, _tp_prices, info)
            _ok_legs      = [r for r in _quad_results if r["ok"]]
            _fail_legs    = [r for r in _quad_results if not r["ok"]]
            if _ok_legs:
                _quad_lines = "  ".join(
                    f"{r['tp_label']}@{r['price']:.6g}×{r['qty']}" for r in _ok_legs
                )
                print(f"   ✅ Quad-TP closes: {_quad_lines}")
                _partial_detail = (
                    "\n  Quad-TP: " +
                    " | ".join(f"{r['tp_label']}@{r['price']:.6g}" for r in _ok_legs)
                )
            else:
                print(f"   ⚠ No TP orders placed — position has no take-profit orders")
                _partial_detail = "\n  ⚠ No TP orders placed (no valid TP prices)"
            for _fl in _fail_legs:
                print(f"   ⚠ {_fl['tp_label']} close failed: {_fl['order_id']}")

            print(f"   ✅ Order placed!  Order ID: {order_id}")
            if conf_val >= 92:
                _tier_tag = " 🏆 TIER 1 ELITE"
            elif conf_val >= 88:
                _tier_tag = " ✅ TIER 2"
            elif conf_val >= 85:
                _tier_tag = " 🟡 TIER 3"
            else:
                _tier_tag = ""
            _scale_notice = (
                f"\n  ⚠️ Size scaled to {int(_coin_size_mult*100)}% (drawdown {_drawdown_pct:.1f}%"
                + (" + Strategist REDUCE" if _strat_key in _strat_reduces else "") + ")"
                if _coin_size_mult < 1.0 else ""
            )
            send_telegram_alert(
                f"✅ <b>DEMO ORDER PLACED</b> — {coin} {dir_label}{_tier_tag}\n"
                f"  Entry {entry:.6g} | SL {sl:.6g} | {_n_tps}×25% quad-TP{_partial_detail}\n"
                f"  Conf: {conf_val:.0f}% | Qty {qty} × ${TRADE_MARGIN_USDT} margin (${qty*entry:.0f} pos){_scale_notice}\n"
                f"  ID: {order_id}"
            )
            time.sleep(0.5)   # small delay between orders
        else:
            print(f"   ❌ Order failed: {result}")
            send_telegram_alert(
                f"❌ <b>DEMO ORDER FAILED</b> — {coin} {dir_label}\n"
                f"  {result}"
            )

        print()

    # ── SHORT REPAIR MODE — one summary Telegram if any SHORTs were skipped ──────
    if skipped_shorts:
        n = len(skipped_shorts)
        coins_str = ", ".join(skipped_shorts)
        send_telegram_alert(
            f"⏸ <b>REPAIR MODE — {n} SHORT signal(s) skipped</b>\n"
            f"  Coins: {coins_str}\n"
            f"  SHORT WR is in repair (< 50% threshold). Only H/FF allowed.\n"
            f"  To resume SHORTs: run LIFT_SHORT_REPAIR.bat (or delete short_repair.flag).\n"
            f"  Auto-resumes when analyze_shorts.py confirms WR ≥ 50% over 20+ trades."
        )
        log(f"REPAIR MODE — skipped {n} SHORT(s): {coins_str}")

    # ── Write Order IDs + UNREACHABLE status to Google Sheets ─────────────────────
    if sheet_order_writes or unreachable_rows:
        try:
            batch_data = []
            if sheet_order_writes:
                print(f"\n📝 Writing {len(sheet_order_writes)} Bybit Order ID(s) to Google Sheets...")
                batch_data += [
                    {"range": rowcol_to_a1(r, COL_BYBIT_ID + 1), "values": [[oid]]}
                    for r, oid in sheet_order_writes
                ]
            if unreachable_rows:
                print(f"\n☠ Marking {len(unreachable_rows)} signal(s) UNREACHABLE in Google Sheets...")
                batch_data += [
                    {"range": rowcol_to_a1(r, COL_STATUS + 1), "values": [["UNREACHABLE"]]}
                    for r in unreachable_rows
                ]
            sheet.batch_update(batch_data, value_input_option="USER_ENTERED")
            if sheet_order_writes:
                print("   ✓ Order IDs written to Sheets (col R)")
            if unreachable_rows:
                print("   ✓ UNREACHABLE status written to Sheets (col L)")
        except Exception as e:
            print(f"   ⚠ Could not update Google Sheets: {e}")

    # ── Prune orphaned skip counters ─────────────────────────
    # open_trades contains only OPEN signals fresher than MAX_SIGNAL_AGE_HOURS.
    # Any skip key whose row is no longer in open_trades represents a signal
    # that is stale, expired, or already resolved — clear its counter so
    # trader_skips.json doesn't accumulate zombie entries indefinitely.
    active_keys = {f"row_{idx}" for idx, _ in open_trades}
    stale_keys = [k for k in skip_counts if k not in active_keys]
    for k in stale_keys:
        del skip_counts[k]
    if stale_keys:
        print(f"   🧹 Pruned {len(stale_keys)} orphaned skip counter(s): {', '.join(stale_keys)}")

    # ── Persist skip counts ───────────────────────────────────
    save_skip_counts(skip_counts)

    # ── Refresh balance file with final position count ─────────
    # The first write (before pause check) used _early_n_positions.
    # After placing orders, n_positions reflects the actual post-run count.
    if placed > 0:
        write_balance_file(total_balance, open_positions=n_positions)

    # ── Summary ───────────────────────────────────────────────
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    _stale_summary = ""
    if skipped_stale_ages:
        _avg_age = sum(skipped_stale_ages) / len(skipped_stale_ages)
        _max_age = max(skipped_stale_ages)
        _stale_summary = (f" | {skipped_stale} stale skipped "
                          f"(avg {_avg_age:.1f}h, max {_max_age:.1f}h)")
    log(f"RUN COMPLETE — {placed}/{len(open_trades)} orders placed | "
        f"${placed * TRADE_MARGIN_USDT} margin deployed | "
        f"balance=${total_balance:,.2f}{_stale_summary}")
    print(f"📊  Check positions at: bybit.com → Demo → Derivatives → Positions")
    print(f"📝  Log: {LOG_FILE}")
    print()

    # ── Summary Telegram ──────────────────────────────────────
    bkk_now_str = datetime.now(BKK).strftime("%H:%M BKK")
    if placed > 0:
        send_telegram_alert(
            f"🤖 <b>TRADER RUN COMPLETE</b> [{bkk_now_str}]\n"
            f"  ✅ {placed}/{len(open_trades)} orders placed\n"
            f"  💰 Demo balance: ${total_balance:,.2f} | Margin in play: ~${deployed_est + placed*TRADE_MARGIN_USDT}"
        )
        print("⚡  Next steps:")
        print("   1. whale_stream_tracker.py runs every 30 min — tracks WIN/LOSS automatically")
        print("   2. Bybit auto-closes positions when TP or SL is hit")
        print("   3. Google Sheets WIN/LOSS will match Bybit balance moves")
        print()

    # ── SL-to-breakeven after TP1 (partial-close protection) ────────────────
    # When a partial-close trade resolves TP1 (STATUS=WIN, TP_HIT=TP1 in sheet),
    # the remaining 75% Bybit position still carries the original SL.
    # A reversal past entry would turn the blended P&L negative despite the TP1 win.
    # Fix: move stopLoss to avgPrice (breakeven) so the worst-case blended P&L ≥ 0%.
    # Runs every trader cycle — skips symbols already at/beyond breakeven.
    try:
        print("\n🛡 SL-to-breakeven check (TP1 partial-close positions)...")
        _slbe_positions = get_open_positions_full()

        # Build set of symbols where the sheet shows STATUS=WIN / TP_HIT=TP1
        # (TP1 partial close already confirmed by tracker)
        _slbe_tp1_syms = set()
        _slbe_all_rows = data_rows  # reuse already-fetched rows (avoid 2nd get_all_values() call)

        for _sbr in _slbe_all_rows:
            while len(_sbr) < 18:
                _sbr.append("")
            if _sbr[COL_STATUS].strip() != "WIN":
                continue
            if _sbr[COL_TP_HIT].strip() != "TP1":
                continue
            if not _sbr[COL_BYBIT_ID].strip():
                continue  # no Bybit order logged → wasn't auto-traded
            _slbe_tp1_syms.add(_sbr[COL_COIN].strip().upper() + "USDT")

        # Load idempotency record — prevents duplicate Telegram alerts every 4h cycle
        _sl_be_state_file = os.path.join(SCRIPT_DIR, "sl_be_applied.json")
        try:
            with open(_sl_be_state_file, "r", encoding="utf-8") as _f:
                _sl_be_applied = set(json.load(_f))
        except Exception:
            _sl_be_applied = set()
        # Prune symbols no longer in current TP1 set (trade closed or TP advanced)
        _sl_be_applied &= _slbe_tp1_syms

        if not _slbe_tp1_syms:
            print("   ℹ No WIN/TP1 sheet rows — nothing to tighten")
        else:
            _slbe_count = 0
            for _pos in _slbe_positions:
                _sym    = _pos.get("symbol", "")
                if _sym not in _slbe_tp1_syms:
                    continue
                _side   = _pos.get("side", "")    # "Buy" (LONG) or "Sell" (SHORT)
                _avg_px = float(_pos.get("avgPrice", 0) or 0)
                _cur_sl = float(_pos.get("stopLoss", 0) or 0)
                if _avg_px <= 0:
                    continue

                # Already applied in a previous cycle — skip to avoid duplicate alerts
                if _sym in _sl_be_applied:
                    print(f"   ✅ {_sym} — SL-to-BE already applied (idempotency guard)")
                    continue

                # Check if SL already at/better than breakeven
                if _side == "Buy" and _cur_sl >= _avg_px:    # LONG: SL ≥ entry → already BE or better
                    print(f"   ✅ {_sym} LONG — SL already ≥ entry ({_cur_sl:.8g} ≥ {_avg_px:.8g})")
                    _sl_be_applied.add(_sym)  # mark done even without API call
                    continue
                if _side == "Sell" and 0 < _cur_sl <= _avg_px:  # SHORT: SL ≤ entry → already BE or better
                    print(f"   ✅ {_sym} SHORT — SL already ≤ entry ({_cur_sl:.8g} ≤ {_avg_px:.8g})")
                    _sl_be_applied.add(_sym)  # mark done even without API call
                    continue

                # Get tick size for proper price formatting
                _slbe_info = get_instrument_info(_sym)
                _tick = _slbe_info["tick_size"] if _slbe_info else 0.0001
                _new_sl_str = fmt_price(round_price(_avg_px, _tick), _tick)

                _be_r = bybit_request("POST", "/v5/position/trading-stop", body={
                    "category":      BYBIT_CATEGORY,
                    "symbol":        _sym,
                    "stopLoss":      _new_sl_str,
                    "slTriggerBy":   "MarkPrice",   # must match entry order — prevents LastPrice wick triggers
                    "positionIdx":   0,
                })
                if _be_r.get("retCode") == 0:
                    _slbe_count += 1
                    _sl_be_applied.add(_sym)   # record — won't re-alert next cycle
                    _dl = "LONG 🟢" if _side == "Buy" else "SHORT 🔴"
                    print(f"   🛡 {_sym} {_dl} — SL → breakeven  {_cur_sl:.8g} → {_new_sl_str}")
                    send_telegram_alert(
                        f"🛡 <b>SL MOVED TO BREAKEVEN</b> — {_sym.replace('USDT', '')} {_dl}\n"
                        f"  TP1 (25%) confirmed → protecting remaining 75%\n"
                        f"  Old SL : {_cur_sl:.8g}\n"
                        f"  New SL : {_new_sl_str}  (entry / breakeven)\n"
                        f"  Worst-case blended P&L now ≥ 0%"
                    )
                else:
                    print(f"   ⚠ SL tighten failed {_sym}: {_be_r.get('retMsg', '?')}")

            if _slbe_count == 0 and _slbe_tp1_syms:
                print(f"   ✅ All {len(_slbe_tp1_syms)} TP1 position(s) already at/beyond breakeven")

        # Persist idempotency state
        try:
            with open(_sl_be_state_file, "w", encoding="utf-8") as _f:
                json.dump(list(_sl_be_applied), _f)
        except Exception as _be_save_e:
            print(f"   ⚠ Could not save sl_be_applied.json: {_be_save_e}")
    except Exception as _slbe_e:
        log(f"⚠ SL-to-breakeven check failed: {_slbe_e}")

    # ── Stale entry order check ───────────────────────────────────────────────
    # Run every trader cycle to catch unfilled entry orders whose sheet signals
    # have expired (>72h). Reduce-only orders (partial close) are excluded — they
    # should stay open until TP is hit.
    try:
        _sheet_open_coins = {row[COL_COIN].strip().upper()
                             for _, row in open_trades} if open_trades else set()
        # Also include any fresh OPEN rows we didn't trade this cycle (reuse already-fetched rows)
        _sheet_open_coins |= {r[COL_COIN].strip().upper()
                              for r in data_rows
                              if len(r) > COL_STATUS and r[COL_STATUS].strip() == "OPEN"}

        _stale = get_stale_entry_orders(_sheet_open_coins, min_age_hours=72)
        if _stale:
            print(f"\n⚠  {len(_stale)} STALE ENTRY ORDER(S) DETECTED (>72h, no sheet OPEN row) — auto-cancelling:")
            _cancelled_ok  = []
            _cancelled_fail = []
            for _s in _stale:
                print(f"   {_s['coin']:10s} {_s['side']:5s} qty={_s['qty']:8s} "
                      f"@ {_s['price']:12s}  age={_s['age_h']:.0f}h  ID={_s['orderId']}")
                _ok = cancel_order(_s["symbol"], _s["orderId"])
                if _ok:
                    _cancelled_ok.append(_s)
                    log(f"STALE ORDER AUTO-CANCELLED: {_s['coin']} {_s['side']} ID={_s['orderId']} age={_s['age_h']:.0f}h")
                    print(f"     ✅ Cancelled: {_s['coin']} ID={_s['orderId']}")
                else:
                    _cancelled_fail.append(_s)
                    log(f"STALE ORDER CANCEL FAILED: {_s['coin']} {_s['side']} ID={_s['orderId']} age={_s['age_h']:.0f}h")
                    print(f"     ✗ Cancel failed: {_s['coin']} ID={_s['orderId']}")

            # Build Telegram report
            _stale_msg = (
                f"⚠️ <b>STALE ENTRY ORDERS AUTO-CANCELLED</b> — {len(_stale)} unfilled order(s) "
                f"older than 72h with no matching sheet signal:\n"
            )
            for _s in _cancelled_ok:
                _stale_msg += f"  ✅ {_s['coin']} {_s['side']} qty={_s['qty']} @ {_s['price']}  ({_s['age_h']:.0f}h old)\n"
            for _s in _cancelled_fail:
                _stale_msg += f"  ✗ {_s['coin']} {_s['side']} qty={_s['qty']} — CANCEL FAILED — check Bybit manually\n"
            send_telegram_alert(_stale_msg)
        else:
            print("\n✅ No stale entry orders detected (all open orders have active sheet signals)")
    except Exception as _se:
        print(f"   ⚠ Stale order check failed: {_se}")
    _mark_done("trader", details={"placed": placed_coins, "skipped": skipped_shorts})


if __name__ == "__main__":
    try:
        main()
    except Exception as _e:
        print(f"💀 FATAL unhandled exception: {_e}")
        _mark_done("trader", details={"error": str(_e)})
        raise
