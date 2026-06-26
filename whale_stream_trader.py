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

# Force UTF-8 output — prevents UnicodeEncodeError on Windows CP1252 consoles / Task Scheduler.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# ── Auto-install missing libraries ────────────────────────────
REQUIRED = {"gspread": "gspread", "google.oauth2": "google-auth"}
for mod, pkg in REQUIRED.items():
    try:
        __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

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
TRADE_MARGIN_USDT = 20      # USDT margin per trade ($20)
LEVERAGE          = 10      # 10x leverage → $200 position per trade
MAX_OPEN_TRADES   = 6       # max 6 simultaneous positions (3 long + 3 short)

# Google Sheets (same as whale_stream_bot.py)
GOOGLE_SHEET_ID         = "1R21mkduSpbki2HmlNJMHM95-LkGS0q-AKHE1HVIfMmI"
GOOGLE_CREDENTIALS_FILE = "google_credentials.json"

# Bybit API
BYBIT_BASE_URL   = "https://api-demo.bybit.com"
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
BYBIT_START_BALANCE = 500.00   # initial demo deposit
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

# Coins with poor historical LONG win rate — skip LONG signals for these
LONG_COIN_AVOID_LIST = ["COMP", "HYPE", "ZRO"]

def log(msg):
    """Write to console and trader_log.txt with timestamp."""
    bkk = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M BKK")
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
    COL_RESOLVED_AT = 16
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
    import json

    # ── Gate 4 recovery detection — read old balance before overwriting ────────
    _GATE4_RECOVERY_THRESHOLD = 425.0
    _old_balance = None
    try:
        if os.path.exists(BYBIT_BALANCE_FILE):
            with open(BYBIT_BALANCE_FILE, "r", encoding="utf-8") as _rf:
                _old_data = json.load(_rf)
                _old_balance = float(_old_data.get("balance", balance))
    except Exception:
        pass
    # ── end Gate 4 recovery read ───────────────────────────────────────────────

    bkk = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M BKK")
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

def bybit_request(method, endpoint, params=None, body=None):
    """
    Authenticated Bybit V5 API request.
    Adds X-BAPI-DEMO-TRADING: 1 header for demo account.
    """
    timestamp   = str(int(time.time() * 1000) - 1000)  # -1s to sync with Bybit server
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
        "X-BAPI-DEMO-TRADING":  "1",        # ← demo account flag
        "Content-Type":         "application/json",
    }

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
    Returns (available, total) tuple, or (None, None) on failure.
    """
    result = bybit_request("GET", "/v5/account/wallet-balance",
                           {"accountType": "UNIFIED"})
    if result.get("retCode") == 0:
        coins = result["result"]["list"][0].get("coin", [])
        for c in coins:
            if c.get("coin") == "USDT":
                avail = float(c.get("availableToWithdraw") or
                              c.get("availableToBorrow") or
                              c.get("walletBalance") or 0)
                total = float(c.get("walletBalance") or
                              c.get("equity") or avail)
                return avail, total
        print("   ⚠ Connected to Bybit but no USDT coin found in wallet")
        return 0.0, 0.0
    return None, None


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
    return []


def get_open_orders():
    """Return set of symbols that already have an unfilled open order."""
    result = bybit_request("GET", "/v5/order/realtime",
                           {"category": BYBIT_CATEGORY, "settleCoin": "USDT"})
    open_syms = set()
    if result.get("retCode") == 0:
        for order in result["result"].get("list", []):
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

    bkk_now = datetime.now(timezone(timedelta(hours=7)))
    for order in result["result"].get("list", []):
        # Skip reduce-only orders — these are partial close orders, keep them alive
        if order.get("reduceOnly") is True or str(order.get("reduceOnly", "")).lower() == "true":
            continue
        sym      = order.get("symbol", "")
        coin     = sym.replace("USDT", "").replace("PERP", "").upper()
        created  = order.get("createdTime", "0")
        try:
            created_dt = datetime.fromtimestamp(int(created) / 1000, tz=timezone.utc)
            age_h = (bkk_now.replace(tzinfo=timezone.utc) - created_dt.replace(tzinfo=timezone.utc)).total_seconds() / 3600
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


def place_partial_closes(symbol, entry_side, qty, tp1_price, tp_high_price, info):
    """
    Place two reduce-only limit orders to implement a partial-close strategy:
      - 50% of qty at TP1  (guaranteed profit lock-in)
      - 50% of qty at tp_high_price (TP2 or TP3 — ride the move)
    Used when the main entry order is placed WITHOUT a built-in takeProfit.
    Returns: (tp1_ok, tp1_id, tp_high_ok, tp_high_id, split_qty, rem_qty)
    If the position is too small to split (rem_qty < min_qty), returns
    (False, "qty_too_small", False, "", 0, 0) — caller should fall back.
    """
    close_side = "Sell" if entry_side == "Buy" else "Buy"
    tick       = info["tick_size"]
    step       = info["qty_step"]
    min_q      = info["min_qty"]

    split_qty = round_to_step(qty / 2, step)
    split_qty = max(split_qty, min_q)
    rem_qty   = round_to_step(qty - split_qty, step)

    if rem_qty < min_q:
        return False, "qty_too_small", False, "", split_qty, rem_qty

    tp1_r     = round_price(tp1_price,     tick)
    tp_high_r = round_price(tp_high_price, tick)

    def _reduce(price_r, close_qty):
        body = {
            "category":       BYBIT_CATEGORY,
            "symbol":         symbol,
            "side":           close_side,
            "orderType":      "Limit",
            "qty":            str(close_qty),
            "price":          fmt_price(price_r, tick),
            "timeInForce":    "GTC",
            "positionIdx":    0,
            "reduceOnly":     True,
            "closeOnTrigger": False,
        }
        r = bybit_request("POST", "/v5/order/create", body=body)
        if r.get("retCode") == 0:
            return True, r["result"].get("orderId", "")
        return False, r.get("retMsg", "?")

    tp1_ok,     tp1_id     = _reduce(tp1_r,     split_qty)
    tp_high_ok, tp_high_id = _reduce(tp_high_r, rem_qty)
    return tp1_ok, tp1_id, tp_high_ok, tp_high_id, split_qty, rem_qty


# ─────────────────────────────────────────────────────────────
# GOOGLE SHEETS
# ─────────────────────────────────────────────────────────────

def connect_sheet():
    from google.oauth2.service_account import Credentials
    import gspread
    creds_path = os.path.join(SCRIPT_DIR, GOOGLE_CREDENTIALS_FILE)
    if not os.path.exists(creds_path):
        raise FileNotFoundError(f"google_credentials.json not found in {SCRIPT_DIR}")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds  = Credentials.from_service_account_file(creds_path, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(GOOGLE_SHEET_ID).sheet1


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
    print("║   🤖  WHALE-STREAM TRADER — BYBIT DEMO          ║")
    print(f"║   💰  ${TRADE_MARGIN_USDT} margin × {LEVERAGE}x = ${TRADE_MARGIN_USDT*LEVERAGE} per trade        ║")
    print("╚══════════════════════════════════════════════════╝")
    print()

    # ── Validate API keys ──────────────────────────────────────
    if "YOUR_BYBIT" in BYBIT_API_KEY:
        print("✗ ERROR: Please fill in BYBIT_API_KEY and BYBIT_API_SECRET in the CONFIG section.")
        return

    # ── Check wallet balance (runs even when paused — keeps balance file fresh) ──
    print("💳 Checking Bybit demo wallet...")
    balance, total_balance = get_wallet_balance()
    if balance is None:
        print("   ✗ Could not connect to Bybit. Check your API keys.")
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
        send_telegram_alert(msg)
        log("PAUSED — circuit breaker flag present, skipping all orders")
        return

    # ── Low balance warning ────────────────────────────────────
    _BALANCE_WARN_THRESHOLD = 450.0   # warn when within $50 of Gate 4 floor
    _BALANCE_GATE4_FLOOR    = 400.0   # Gate 4 requires balance > $400
    if balance < _BALANCE_WARN_THRESHOLD:
        _dd_pct = (BYBIT_START_BALANCE - balance) / BYBIT_START_BALANCE * 100
        _remaining = balance - _BALANCE_GATE4_FLOOR
        _warn_level = "🚨 CRITICAL" if balance < _BALANCE_GATE4_FLOOR + 20 else "⚠️ WARNING"
        send_telegram_alert(
            f"{_warn_level} <b>BYBIT DEMO BALANCE LOW</b>\n"
            f"  Current balance : ${balance:,.2f}\n"
            f"  Drawdown        : {_dd_pct:.1f}% from ${BYBIT_START_BALANCE:.0f} start\n"
            f"  Gate 4 floor    : ${_BALANCE_GATE4_FLOOR:.0f} (real capital requires > this)\n"
            f"  Remaining margin: ${_remaining:,.2f} before Gate 4 breach\n"
            f"  ⚡ Gate 4 breach active: 40% size, max 4 positions, both LONG+SHORT allowed."
        )
        log(f"LOW BALANCE WARNING — ${balance:,.2f} ({_dd_pct:.1f}% drawdown)")

    if balance < TRADE_MARGIN_USDT:
        print(f"   ✗ Balance too low. Need at least ${TRADE_MARGIN_USDT} to place one trade.")
        return

    # ── Load Google Sheets ─────────────────────────────────────
    print("\n📋 Loading signals from Google Sheets...")
    try:
        sheet = connect_sheet()
    except Exception as e:
        print(f"   ✗ Google Sheets error: {e}")
        return

    all_rows  = sheet.get_all_values()
    data_rows = all_rows[1:] if len(all_rows) > 1 else []

    # ── Circuit breaker: check for consecutive LOSSes ─────────
    # ── Dynamic circuit breaker threshold ─────────────────────
    # In LONG-only (REPAIR MODE), raise threshold: 3→5 to avoid
    # pausing on normal single-day LONG volatility.
    _cb_threshold = CIRCUIT_LOSSES
    if os.path.exists(SHORT_REPAIR_FILE):
        _cb_threshold = 5
        log(f"REPAIR MODE active — circuit breaker threshold raised to {_cb_threshold}")
    # ──────────────────────────────────────────────────────────
    if check_circuit_breaker(data_rows, threshold=_cb_threshold):
        # Write the flag so future runs also halt until manually cleared
        try:
            bkk_now_flag = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M BKK")
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
        return

    # BKK time now (UTC+7)
    bkk_now = datetime.now(timezone(timedelta(hours=7)))

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
                sig_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M")
                sig_dt = sig_dt.replace(tzinfo=timezone(timedelta(hours=7)))
                age_hours = (bkk_now - sig_dt).total_seconds() / 3600
                if age_hours > MAX_SIGNAL_AGE_HOURS:
                    skipped_stale += 1
                    skipped_stale_ages.append(age_hours)
                    coin_label = row[COL_COIN].strip()
                    print(f"   ⏭ Skipping {coin_label} — signal is {age_hours:.1f}h old "
                          f"(max {MAX_SIGNAL_AGE_HOURS}h)")
                    continue
            except Exception:
                pass  # if timestamp unparseable, include it
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

    _drawdown_pct = (_bb_start_balance - _bb_balance) / _bb_start_balance * 100 if _bb_start_balance > 0 else 0.0
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
                bkk_g4 = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M BKK")
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

    # ── Place orders ───────────────────────────────────────────
    print("\n🚀 Placing orders...\n")
    placed = 0
    sheet_order_writes = []   # (sheet_row_idx, order_id) — batch-written at end
    unreachable_rows   = []   # rows to mark UNREACHABLE in Sheets
    skip_counts = load_skip_counts()
    skipped_shorts = []       # coins skipped due to SHORT REPAIR MODE

    for sheet_row_idx, row in open_trades:
        coin       = row[COL_COIN].strip()
        signal     = row[COL_SIGNAL].strip()
        entry_zone = row[COL_ENTRY_ZONE].strip()
        sl_str     = row[COL_SL].strip()
        tp1_str    = row[COL_TP1].strip()
        tp2_str    = row[COL_TP2].strip() if len(row) > COL_TP2 else ""
        tp3_str    = row[COL_TP3].strip() if len(row) > COL_TP3 else ""
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
        # Extract numeric confidence (e.g. "92%" → 92, "92" → 92)
        try:
            conf_val = float(conf_str.replace("%", "").strip())
        except (ValueError, AttributeError):
            conf_val = 0

        if not all([entry, sl, tp1]):
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

        # Select which TP level to use for the Bybit order.
        # Tiered strategy — higher confidence → higher TP target:
        #   TIER 1 (92%+): target TP3 if valid, else fall through to TP2, then TP1
        #   TIER 2/3 (<92%): target TP2 if valid, else fall back to TP1
        # "Valid" means the TP is on the correct side of the previous level.
        is_tier1 = conf_val >= 92
        bybit_tp = tp1
        tp_label = "TP1"
        if tp2 and tp2 > 0:
            tp2_valid = (tp2 > tp1) if side == "Buy" else (tp2 < tp1)
            if tp2_valid:
                bybit_tp = tp2
                tp_label = "TP2"
                # TIER 1: try to upgrade further to TP3
                if is_tier1 and tp3 and tp3 > 0:
                    tp3_valid = (tp3 > tp2) if side == "Buy" else (tp3 < tp2)
                    if tp3_valid:
                        bybit_tp = tp3
                        tp_label = "TP3"

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
        if conf_val >= 92:
            tier_display = f" [TIER 1 ELITE — {conf_val:.0f}%]"
        elif conf_val >= 88:
            tier_display = f" [TIER 2 — {conf_val:.0f}%]"
        elif conf_val >= 85:
            tier_display = f" [TIER 3 — {conf_val:.0f}%]"
        else:
            tier_display = f" [{conf_val:.0f}%]"
        print(f"   Entry : {entry:.6g}  SL: {sl:.6g}  TP1: {tp1:.6g}{tp2_display}{tp3_display}  → Bybit {tp_label}: {bybit_tp:.6g}{tier_display}")
        print(f"   Qty   : {qty} contracts  (≈${position_val:.2f} position)")

        # ── Place order — partial-close strategy when targeting above TP1 ─────────
        # When we target TP2 or TP3, omit the built-in TP from the entry order and
        # instead place two separate reduce-only orders: 50%@TP1 (lock profit) +
        # 50%@higher TP (ride the move).  Fallback to single order when qty too small.
        use_partial = (tp_label != "TP1")
        entry_tp    = None if use_partial else tp1   # None = no built-in TP on entry
        ok, result  = place_order(symbol, side, qty, entry, sl, entry_tp, info)

        if ok:
            order_id = result
            placed  += 1
            sheet_order_writes.append((sheet_row_idx, order_id))
            skip_counts.pop(f"row_{sheet_row_idx}", None)

            partial_detail = ""
            if use_partial:
                t1_ok, t1_id, th_ok, th_id, split_qty, rem_qty = place_partial_closes(
                    symbol, side, qty, tp1, bybit_tp, info
                )
                if t1_id == "qty_too_small":
                    # Position too small to split — place a single reduce-only close at tp1
                    # (use TP1 not TP2/TP3 so we still lock in the nearest profit target)
                    close_side = "Sell" if side == "Buy" else "Buy"
                    tick_s     = info["tick_size"]
                    fb_body    = {
                        "category": BYBIT_CATEGORY, "symbol": symbol, "side": close_side,
                        "orderType": "Limit", "qty": str(qty),
                        "price": fmt_price(round_price(tp1, tick_s), tick_s),
                        "timeInForce": "GTC", "positionIdx": 0,
                        "reduceOnly": True, "closeOnTrigger": False,
                    }
                    fb_r = bybit_request("POST", "/v5/order/create", body=fb_body)
                    if fb_r.get("retCode") == 0:
                        print(f"   ℹ Qty too small to split — single close @ TP1 placed")
                        partial_detail = f"\n  (qty too small to split — single close @TP1)"
                    else:
                        print(f"   ⚠ Fallback single close failed: {fb_r.get('retMsg')}")
                        partial_detail = f"\n  ⚠ No TP order placed — check Bybit manually"
                else:
                    if t1_ok and th_ok:
                        print(f"   ✅ Partial closes: {split_qty}×TP1 ({tp1:.6g}) + {rem_qty}×{tp_label} ({bybit_tp:.6g})")
                        partial_detail = f"\n  Partial: {split_qty}@TP1 + {rem_qty}@{tp_label}"
                    else:
                        if not t1_ok:
                            print(f"   ⚠ TP1 partial close failed: {t1_id}")
                        if not th_ok:
                            print(f"   ⚠ {tp_label} partial close failed: {th_id}")
                        partial_detail = f"\n  ⚠ Partial close order(s) failed — check Bybit"

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
                f"  Entry {entry:.6g} | SL {sl:.6g} | {tp_label} {bybit_tp:.6g}{partial_detail}\n"
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
            from gspread.utils import rowcol_to_a1
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
    bkk_now_str = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M BKK")
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
    # the remaining 50% Bybit position still carries the original SL.
    # A reversal past entry would turn the blended P&L negative despite the TP1 win.
    # Fix: move stopLoss to avgPrice (breakeven) so the worst-case blended P&L ≥ 0%.
    # Runs every trader cycle — skips symbols already at/beyond breakeven.
    try:
        print("\n🛡 SL-to-breakeven check (TP1 partial-close positions)...")
        _slbe_positions = get_open_positions_full()

        # Build set of symbols where the sheet shows STATUS=WIN / TP_HIT=TP1
        # (TP1 partial close already confirmed by tracker)
        _slbe_tp1_syms = set()
        try:
            _slbe_all_rows = sheet.get_all_values()[1:]
        except Exception:
            _slbe_all_rows = []

        _COL_TP_HIT     = 14   # not yet defined as a constant in trader.py
        _COL_ENTRY_PRICE = 12
        for _sbr in _slbe_all_rows:
            while len(_sbr) < 18:
                _sbr.append("")
            if _sbr[COL_STATUS].strip() != "WIN":
                continue
            if _sbr[_COL_TP_HIT].strip() != "TP1":
                continue
            if not _sbr[COL_BYBIT_ID].strip():
                continue  # no Bybit order logged → wasn't auto-traded
            _slbe_tp1_syms.add(_sbr[COL_COIN].strip().upper() + "USDT")

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

                # Check if SL already at/better than breakeven
                if _side == "Buy" and _cur_sl >= _avg_px:    # LONG: SL ≥ entry → already BE or better
                    print(f"   ✅ {_sym} LONG — SL already ≥ entry ({_cur_sl:.8g} ≥ {_avg_px:.8g})")
                    continue
                if _side == "Sell" and 0 < _cur_sl <= _avg_px:  # SHORT: SL ≤ entry → already BE or better
                    print(f"   ✅ {_sym} SHORT — SL already ≤ entry ({_cur_sl:.8g} ≤ {_avg_px:.8g})")
                    continue

                # Get tick size for proper price formatting
                _slbe_info = get_instrument_info(_sym)
                _tick = _slbe_info["tick_size"] if _slbe_info else 0.0001
                _new_sl_str = fmt_price(round_price(_avg_px, _tick), _tick)

                _be_r = bybit_request("POST", "/v5/position/trading-stop", body={
                    "category":    BYBIT_CATEGORY,
                    "symbol":      _sym,
                    "stopLoss":    _new_sl_str,
                    "positionIdx": 0,
                })
                if _be_r.get("retCode") == 0:
                    _slbe_count += 1
                    _dl = "LONG 🟢" if _side == "Buy" else "SHORT 🔴"
                    print(f"   🛡 {_sym} {_dl} — SL → breakeven  {_cur_sl:.8g} → {_new_sl_str}")
                    send_telegram_alert(
                        f"🛡 <b>SL MOVED TO BREAKEVEN</b> — {_sym.replace('USDT', '')} {_dl}\n"
                        f"  TP1 (50%) confirmed → protecting second half\n"
                        f"  Old SL : {_cur_sl:.8g}\n"
                        f"  New SL : {_new_sl_str}  (entry / breakeven)\n"
                        f"  Worst-case blended P&L now ≥ 0%"
                    )
                else:
                    print(f"   ⚠ SL tighten failed {_sym}: {_be_r.get('retMsg', '?')}")

            if _slbe_count == 0 and _slbe_tp1_syms:
                print(f"   ✅ All {len(_slbe_tp1_syms)} TP1 position(s) already at/beyond breakeven")
    except Exception as _slbe_e:
        print(f"   ⚠ SL-to-breakeven check failed: {_slbe_e}")

    # ── Stale entry order check ───────────────────────────────────────────────
    # Run every trader cycle to catch unfilled entry orders whose sheet signals
    # have expired (>72h). Reduce-only orders (partial close) are excluded — they
    # should stay open until TP is hit.
    try:
        _sheet_open_coins = {row[COL_COIN].strip().upper()
                             for _, row in open_trades} if open_trades else set()
        # Also include any fresh OPEN rows we didn't trade this cycle
        try:
            _all_rows  = sheet.get_all_values()[1:]
            _sheet_open_coins |= {r[COL_COIN].strip().upper()
                                  for r in _all_rows
                                  if len(r) > COL_STATUS and r[COL_STATUS].strip() == "OPEN"}
        except Exception:
            pass  # use the set we have

        _stale = get_stale_entry_orders(_sheet_open_coins, min_age_hours=72)
        if _stale:
            print(f"\n⚠  {len(_stale)} STALE ENTRY ORDER(S) DETECTED (>72h, no sheet OPEN row):")
            for _s in _stale:
                print(f"   {_s['coin']:10s} {_s['side']:5s} qty={_s['qty']:8s} "
                      f"@ {_s['price']:12s}  age={_s['age_h']:.0f}h  ID={_s['orderId']}")
            _stale_msg = (
                f"⚠️ <b>STALE ENTRY ORDERS DETECTED</b> — {len(_stale)} unfilled order(s) "
                f"older than 72h with no matching sheet signal:\n"
            )
            for _s in _stale:
                _stale_msg += (f"  {_s['coin']} {_s['side']} qty={_s['qty']} "
                               f"@ {_s['price']}  ({_s['age_h']:.0f}h old)\n")
            _stale_msg += "  ➡ Review and cancel manually in Bybit if no longer needed."
            send_telegram_alert(_stale_msg)
        else:
            print("\n✅ No stale entry orders detected (all open orders have active sheet signals)")
    except Exception as _se:
        print(f"   ⚠ Stale order check failed: {_se}")


if __name__ == "__main__":
    main()
