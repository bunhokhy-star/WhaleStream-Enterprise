"""
╔══════════════════════════════════════════════════════════════╗
║       WHALE-STREAM — RETROFIT QUAD-TP                        ║
║                                                              ║
║  One-shot script: cancels existing TP reduce-only orders     ║
║  on all open Bybit positions, then places 4×25% quad-TP      ║
║  reduce-only closes using TP1/TP2/TP3/TP4 from Google Sheets ║
║                                                              ║
║  HOW TO RUN:                                                 ║
║    python retrofit_quad_tp.py --dry-run   ← preview only     ║
║    python retrofit_quad_tp.py             ← live             ║
╚══════════════════════════════════════════════════════════════╝
"""

import re, os, sys, io, hmac, json, math, time, hashlib, requests, subprocess
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

# Force UTF-8
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

DRY_RUN = "--dry-run" in sys.argv

# ── Config ─────────────────────────────────────────────────────────────────
try:
    from local_config import BYBIT_API_KEY, BYBIT_API_SECRET
except ImportError:
    BYBIT_API_KEY    = os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")

try:
    from local_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

BYBIT_BASE_URL          = "https://api-demo.bybit.com"
BYBIT_CATEGORY          = "linear"
GOOGLE_SHEET_ID         = "1R21mkduSpbki2HmlNJMHM95-LkGS0q-AKHE1HVIfMmI"
GOOGLE_CREDENTIALS_FILE = "google_credentials.json"
SCRIPT_DIR              = os.path.dirname(os.path.abspath(__file__))

# Sheet columns (0-based) — must match whale_stream_trader.py
COL_COIN   = 0
COL_STATUS = 11
COL_TP1    = 5
COL_TP2    = 6
COL_TP3    = 7
COL_TP4    = 8

# ── Bybit auth ──────────────────────────────────────────────────────────────
_CLOCK_OFFSET_MS = 3000

def bybit_request(method, endpoint, params=None, body=None):
    timestamp   = str(int(time.time() * 1000) - _CLOCK_OFFSET_MS)
    recv_window = "20000"
    if method == "GET":
        query_str = urlencode(params) if params else ""
        sign_str  = f"{timestamp}{BYBIT_API_KEY}{recv_window}{query_str}"
    else:
        body_str = json.dumps(body) if body else ""
        sign_str = f"{timestamp}{BYBIT_API_KEY}{recv_window}{body_str}"
    signature = hmac.new(
        BYBIT_API_SECRET.encode(), sign_str.encode(), hashlib.sha256
    ).hexdigest()
    headers = {
        "X-BAPI-API-KEY":      BYBIT_API_KEY,
        "X-BAPI-SIGN":         signature,
        "X-BAPI-TIMESTAMP":    timestamp,
        "X-BAPI-RECV-WINDOW":  recv_window,
        "X-BAPI-DEMO-TRADING": "1",
        "Content-Type":        "application/json",
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

# ── Math helpers ────────────────────────────────────────────────────────────
def _count_decimals(value):
    s = f"{value:.10f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0

def round_to_step(value, step):
    decimals = _count_decimals(step)
    return round(math.floor(value / step) * step, decimals)

def round_price(price, tick_size):
    decimals = _count_decimals(tick_size)
    return round(round(price / tick_size) * tick_size, decimals)

def fmt_price(price, tick_size):
    return f"{price:.{_count_decimals(tick_size)}f}"

def parse_price(s):
    nums = re.findall(r"[\d]+\.?[\d]*", str(s).replace(",", ""))
    return float(nums[0]) if nums else None

# ── Bybit helpers ───────────────────────────────────────────────────────────
def get_instrument_info(symbol):
    result = bybit_request("GET", "/v5/market/instruments-info",
                           {"category": BYBIT_CATEGORY, "symbol": symbol})
    if result.get("retCode") == 0:
        items = result["result"].get("list", [])
        if items:
            lot_f   = items[0]["lotSizeFilter"]
            price_f = items[0]["priceFilter"]
            return {
                "min_qty":   float(lot_f["minOrderQty"]),
                "qty_step":  float(lot_f["qtyStep"]),
                "tick_size": float(price_f["tickSize"]),
            }
    return None

def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass

# ── Google Sheets ───────────────────────────────────────────────────────────
def get_sheet_tps():
    """
    Return dict {COIN: {tp1, tp2, tp3, tp4}} for ALL rows that have TP1.
    Includes OPEN, WIN, and any other status — we just need the TP prices.
    If the same coin appears multiple times, the OPEN row wins over others.
    """
    # Use Sheets API v4 directly — no gspread dependency
    from google.oauth2.service_account import Credentials
    import google.auth.transport.requests as _gatr

    creds_path = os.path.join(SCRIPT_DIR, GOOGLE_CREDENTIALS_FILE)
    _SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_file(creds_path, scopes=_SCOPES)
    creds.refresh(_gatr.Request())

    url = (f"https://sheets.googleapis.com/v4/spreadsheets/"
           f"{GOOGLE_SHEET_ID}/values/Sheet1")
    resp = requests.get(url, headers={"Authorization": f"Bearer {creds.token}"}, timeout=15)
    resp.raise_for_status()
    all_rows = resp.json().get("values", [])
    rows   = all_rows[1:]

    tp_map = {}
    for row in rows:
        while len(row) < 12:
            row.append("")
        coin   = row[COL_COIN].strip().upper()
        status = row[COL_STATUS].strip()
        if not coin or coin in ("STAY OUT", "—"):
            continue

        tp1_raw = row[COL_TP1].strip() if len(row) > COL_TP1 else ""
        tp1 = parse_price(tp1_raw) if tp1_raw else None
        if not tp1:
            continue  # no TP1 → skip row

        tp2 = parse_price(row[COL_TP2]) if len(row) > COL_TP2 and row[COL_TP2].strip() else None
        tp3 = parse_price(row[COL_TP3]) if len(row) > COL_TP3 and row[COL_TP3].strip() else None
        tp4 = parse_price(row[COL_TP4]) if len(row) > COL_TP4 and row[COL_TP4].strip() else None

        entry = {"tp1": tp1, "tp2": tp2, "tp3": tp3, "tp4": tp4, "status": status}

        # OPEN rows take priority; otherwise keep first found
        if coin not in tp_map or status == "OPEN":
            tp_map[coin] = entry

    return tp_map

# ── Main ────────────────────────────────────────────────────────────────────
def main():
    mode = "⚠ DRY RUN — no orders placed" if DRY_RUN else "🔴 LIVE MODE"
    print(f"\n{'═'*60}")
    print(f"  RETROFIT QUAD-TP  |  {mode}")
    print(f"{'═'*60}\n")

    # ── 1. Open positions ──────────────────────────────────────
    print("📍 Fetching open positions from Bybit...")
    pos_result = bybit_request("GET", "/v5/position/list",
                               {"category": BYBIT_CATEGORY, "settleCoin": "USDT"})
    if pos_result.get("retCode") != 0:
        print(f"❌ Cannot fetch positions: {pos_result.get('retMsg')}")
        return

    positions = [p for p in pos_result["result"].get("list", [])
                 if float(p.get("size", 0)) > 0]

    if not positions:
        print("   No open positions found — nothing to do.")
        return

    print(f"   Found {len(positions)} position(s):")
    for p in positions:
        side_lbl = "LONG 🟢" if p["side"] == "Buy" else "SHORT 🔴"
        print(f"     {p['symbol']:12s} {side_lbl}  qty={p['size']:10s}  entry={float(p.get('avgPrice',0)):.6g}")
    print()

    # ── 2. Open reduce-only orders (to cancel) ─────────────────
    print("📋 Fetching open orders...")
    ord_result = bybit_request("GET", "/v5/order/realtime",
                               {"category": BYBIT_CATEGORY, "settleCoin": "USDT"})
    reduce_by_sym = {}   # symbol → [orderId, ...]
    entry_by_sym  = {}   # symbol → [orderId, ...]  (non-reduce-only, for info only)
    if ord_result.get("retCode") == 0:
        for o in ord_result["result"].get("list", []):
            sym = o["symbol"]
            if o.get("reduceOnly") is True or str(o.get("reduceOnly","")).lower() == "true":
                reduce_by_sym.setdefault(sym, []).append(o["orderId"])
            else:
                entry_by_sym.setdefault(sym, []).append(o["orderId"])

    total_reduces = sum(len(v) for v in reduce_by_sym.values())
    print(f"   Found {total_reduces} reduce-only order(s) to cancel\n")

    # ── 3. Google Sheets TP prices ─────────────────────────────
    print("📊 Reading Google Sheets for TP1/TP2/TP3/TP4...")
    try:
        tp_map = get_sheet_tps()
        found_coins = [c for c in tp_map if any(
            p["symbol"].replace("USDT","").upper() == c for p in positions
        )]
        print(f"   TP data found for: {', '.join(found_coins) if found_coins else 'none'}\n")
    except Exception as e:
        print(f"❌ Google Sheets error: {e}")
        return

    # ── 4. Process each position ───────────────────────────────
    total_ok   = 0
    total_fail = 0
    summary    = []

    for pos in positions:
        symbol     = pos["symbol"]
        coin       = symbol.replace("USDT", "")
        side       = pos["side"]       # "Buy" or "Sell"
        qty        = float(pos["size"])
        avg_px     = float(pos.get("avgPrice", 0))
        close_side = "Sell" if side == "Buy" else "Buy"
        dir_label  = "LONG 🟢" if side == "Buy" else "SHORT 🔴"

        print(f"── {coin} {dir_label}  qty={qty}  entry={avg_px:.6g} ──────────────────")

        # TP data from sheet
        tps = tp_map.get(coin.upper())
        if not tps:
            print(f"   ⚠  No TP data in sheet for {coin} — SKIP")
            print()
            total_fail += 1
            continue

        tp1, tp2, tp3, tp4 = tps["tp1"], tps["tp2"], tps["tp3"], tps["tp4"]
        print(f"   Sheet TPs: TP1={tp1}  TP2={tp2}  TP3={tp3}  TP4={tp4}")

        # Validate direction of each TP
        valid_tps = []
        for label, price in [("TP1", tp1), ("TP2", tp2), ("TP3", tp3), ("TP4", tp4)]:
            if not price:
                continue
            if side == "Buy" and price <= avg_px:
                print(f"   ⚠  {label}={price} ≤ entry {avg_px} — skip (LONG TP must be above entry)")
                continue
            if side == "Sell" and price >= avg_px:
                print(f"   ⚠  {label}={price} ≥ entry {avg_px} — skip (SHORT TP must be below entry)")
                continue
            valid_tps.append((label, price))

        if not valid_tps:
            print(f"   ❌  No valid TP prices for {coin} — SKIP")
            print()
            total_fail += 1
            continue

        print(f"   Valid TPs ({len(valid_tps)}): " +
              "  ".join(f"{lbl}={p}" for lbl, p in valid_tps))

        # Instrument info
        info = get_instrument_info(symbol)
        if not info:
            print(f"   ❌  Cannot get instrument info for {symbol} — SKIP")
            print()
            total_fail += 1
            continue

        tick  = info["tick_size"]
        step  = info["qty_step"]
        min_q = info["min_qty"]
        n     = len(valid_tps)

        base_qty = round_to_step(qty / n, step)
        base_qty = max(base_qty, min_q)

        # Cancel existing reduce-only orders
        existing = reduce_by_sym.get(symbol, [])
        if existing:
            print(f"   🗑  Cancelling {len(existing)} existing reduce-only order(s)...")
            for oid in existing:
                if DRY_RUN:
                    print(f"       [DRY] cancel {oid}")
                else:
                    r = bybit_request("POST", "/v5/order/cancel", body={
                        "category": BYBIT_CATEGORY,
                        "symbol":   symbol,
                        "orderId":  oid,
                    })
                    status_ok = r.get("retCode") == 0
                    mark = "✅" if status_ok else "⚠"
                    print(f"       {mark} {oid}  {'' if status_ok else r.get('retMsg','?')}")
            time.sleep(0.3)
        else:
            print(f"   ℹ  No existing reduce-only orders to cancel")

        # Place 4×25% reduce-only closes
        print(f"   📤  Placing {n}×25% reduce-only closes...")
        allocated = 0
        legs_ok   = 0

        for idx, (label, tp_price) in enumerate(valid_tps):
            # Last leg gets remainder so full qty is covered
            if idx == n - 1:
                leg_qty = round_to_step(qty - allocated, step)
                leg_qty = max(leg_qty, min_q)
            else:
                leg_qty = base_qty

            tp_r      = round_price(tp_price, tick)
            price_str = fmt_price(tp_r, tick)

            if DRY_RUN:
                print(f"       [DRY] {label} @ {price_str}  qty={leg_qty}  side={close_side}")
                allocated += leg_qty
                legs_ok   += 1
                continue

            body = {
                "category":       BYBIT_CATEGORY,
                "symbol":         symbol,
                "side":           close_side,
                "orderType":      "Limit",
                "qty":            str(leg_qty),
                "price":          price_str,
                "timeInForce":    "GTC",
                "positionIdx":    0,
                "reduceOnly":     True,
                "closeOnTrigger": False,
            }
            r  = bybit_request("POST", "/v5/order/create", body=body)
            ok = r.get("retCode") == 0
            allocated += leg_qty  # always advance — keeps last-leg remainder correct even on partial failures
            if ok:
                oid = r["result"].get("orderId", "")
                print(f"       ✅ {label} @ {price_str}  qty={leg_qty}  ID={oid}")
                legs_ok += 1
            else:
                print(f"       ❌ {label} FAILED: {r.get('retMsg','?')} (retCode={r.get('retCode')})")
                total_fail += 1

            time.sleep(0.2)

        if legs_ok == n:
            result_line = f"✅ {coin} {dir_label} — {legs_ok}/{n} TP orders placed"
        elif legs_ok > 0:
            result_line = f"⚠ {coin} {dir_label} — {legs_ok}/{n} TP orders placed (partial)"
        else:
            result_line = f"❌ {coin} {dir_label} — 0/{n} TP orders placed"

        print(f"   {result_line}")
        summary.append(result_line)
        if legs_ok > 0:
            total_ok += 1
        print()

    # ── Summary ────────────────────────────────────────────────
    print(f"{'═'*60}")
    print(f"  DONE  |  {total_ok}/{len(positions)} position(s) retrofitted")
    print(f"  Mode  |  {mode}")
    print(f"{'═'*60}")
    for line in summary:
        print(f"  {line}")
    print()

    if not DRY_RUN:
        tg_lines = "\n".join(f"  {l}" for l in summary)
        send_telegram(
            f"✅ <b>QUAD-TP RETROFIT COMPLETE</b>\n"
            f"{tg_lines}\n"
            f"  {total_ok}/{len(positions)} position(s) now have 4×25% quad-TP closes"
        )

if __name__ == "__main__":
    main()
