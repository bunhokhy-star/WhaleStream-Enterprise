r"""
close_all_positions.py — WHALE-STREAM
======================================
Closes ALL open Bybit Demo positions at market and cancels ALL pending orders.
Use this to reset before a fresh trading cycle.

USAGE (run on server via SSH):
  cd /opt/whalestream

  # Step 1 — Dry run (shows what would be closed, makes NO trades):
  python3 close_all_positions.py

  # Step 2 — Actually close everything:
  python3 close_all_positions.py --execute
"""

import sys
import os
import hmac
import hashlib
import time
import json
from urllib.parse import urlencode

import requests

# ── Config ────────────────────────────────────────────────────────────────────
BYBIT_BASE_URL = "https://api-demo.bybit.com"   # Demo — change to api.bybit.com for live
DRY_RUN = "--execute" not in sys.argv

# ── Load credentials ──────────────────────────────────────────────────────────
try:
    from local_config import BYBIT_API_KEY, BYBIT_API_SECRET
except ImportError:
    BYBIT_API_KEY    = os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")

if not BYBIT_API_KEY or not BYBIT_API_SECRET:
    print("ERROR: No API keys. Add local_config.py or set BYBIT_API_KEY/BYBIT_API_SECRET env vars.")
    sys.exit(1)


# ── Auth helpers ──────────────────────────────────────────────────────────────
def _make_headers(params=None, body=None, method="GET"):
    """Build HMAC-SHA256 signed headers for Bybit V5 API."""
    timestamp   = str(int(time.time() * 1000) - 3000)   # -3000ms clock-skew fix
    recv_window = "20000"
    if method == "GET":
        qs       = urlencode(params) if params else ""
        sign_str = f"{timestamp}{BYBIT_API_KEY}{recv_window}{qs}"
    else:
        bs       = json.dumps(body, separators=(",", ":")) if body else ""
        sign_str = f"{timestamp}{BYBIT_API_KEY}{recv_window}{bs}"
    sig = hmac.new(
        BYBIT_API_SECRET.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-BAPI-API-KEY":      BYBIT_API_KEY,
        "X-BAPI-SIGN":         sig,
        "X-BAPI-TIMESTAMP":    timestamp,
        "X-BAPI-RECV-WINDOW":  recv_window,
        "X-BAPI-DEMO-TRADING": "1",          # Required for Demo Trading endpoint
        "Content-Type":        "application/json",
    }


def bybit_get(path, params=None):
    params = params or {}
    url    = f"{BYBIT_BASE_URL}{path}"
    r      = requests.get(url, params=params, headers=_make_headers(params=params, method="GET"), timeout=15)
    return r.json()


def bybit_post(path, body):
    url     = f"{BYBIT_BASE_URL}{path}"
    payload = json.dumps(body, separators=(",", ":"))
    r       = requests.post(url, data=payload, headers=_make_headers(body=body, method="POST"), timeout=15)
    return r.json()


# ── Banner ────────────────────────────────────────────────────────────────────
print()
print("=" * 65)
print("  WHALE-STREAM — Close All Positions & Cancel All Orders")
print(f"  Mode : {'DRY RUN  (no trades placed — add --execute to run live)' if DRY_RUN else '⚠  LIVE EXECUTE'}")
print(f"  URL  : {BYBIT_BASE_URL}")
print("=" * 65)
print()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Fetch & close all open positions
# ══════════════════════════════════════════════════════════════════════════════
print("[ STEP 1 ]  Fetching open positions...")
resp = bybit_get("/v5/position/list", {"category": "linear", "settleCoin": "USDT"})

if resp.get("retCode") != 0:
    print(f"  ✗ ERROR fetching positions: retCode={resp.get('retCode')}  msg='{resp.get('retMsg')}'")
    sys.exit(1)

all_positions = resp.get("result", {}).get("list", [])
open_positions = [p for p in all_positions if float(p.get("size", 0)) > 0]

print(f"  Found {len(open_positions)} open position(s) (of {len(all_positions)} total).\n")

closed_ok  = []
closed_err = []

for pos in open_positions:
    symbol      = pos["symbol"]
    size        = pos["size"]
    side        = pos["side"]            # "Buy" (long) or "Sell" (short)
    pos_idx     = int(pos.get("positionIdx", 0))
    close_side  = "Sell" if side == "Buy" else "Buy"
    entry_price = pos.get("avgPrice", "?")
    unreal_pnl  = pos.get("unrealisedPnl", "?")

    direction = "LONG" if side == "Buy" else "SHORT"
    print(f"  [{direction}] {symbol}  size={size}  entry={entry_price}  unrealPnL={unreal_pnl}")
    print(f"       → Placing {close_side} Market reduceOnly  (positionIdx={pos_idx})")

    if DRY_RUN:
        closed_ok.append(f"{direction} {size} {symbol}")
        print(f"       → [DRY RUN] skipped\n")
        continue

    body = {
        "category":    "linear",
        "symbol":      symbol,
        "side":        close_side,
        "orderType":   "Market",
        "qty":         size,
        "reduceOnly":  True,
        "positionIdx": pos_idx,      # 0 = one-way, 1 = buy-side hedge, 2 = sell-side hedge
        "timeInForce": "IOC",        # Immediate Or Cancel — ensures no partial hangs
    }
    result = bybit_post("/v5/order/create", body)
    code   = result.get("retCode")
    msg    = result.get("retMsg", "")

    if code == 0:
        oid = result.get("result", {}).get("orderId", "?")
        print(f"       ✓ Closed — orderId: {oid}\n")
        closed_ok.append(f"{direction} {size} {symbol}")
    else:
        print(f"       ✗ FAILED — retCode={code}  retMsg='{msg}'\n")
        closed_err.append(f"{symbol}: {msg}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Cancel all pending orders
# ══════════════════════════════════════════════════════════════════════════════
print("[ STEP 2 ]  Cancelling all pending orders...")

cancelled_count = 0
cancel_err      = None

if DRY_RUN:
    # Peek at what orders exist
    resp2  = bybit_get("/v5/order/realtime", {"category": "linear", "limit": "50"})
    orders = resp2.get("result", {}).get("list", [])
    print(f"  Found {len(orders)} pending order(s) — would cancel all (dry run)")
    for o in orders:
        sym   = o.get("symbol", "?")
        oside = o.get("side", "?")
        qty   = o.get("qty", "?")
        px    = o.get("price", "Market")
        otype = o.get("orderType", "?")
        oid   = o.get("orderId", "?")
        print(f"    {oside} {qty} {sym} @ {px} [{otype}] orderId={oid}")
else:
    # Cancel-all in one shot (linear, USDT-settled)
    body2   = {"category": "linear", "settleCoin": "USDT"}
    result2 = bybit_post("/v5/order/cancel-all", body2)
    code2   = result2.get("retCode")
    if code2 == 0:
        cancelled_list  = result2.get("result", {}).get("list", [])
        cancelled_count = len(cancelled_list)
        print(f"  ✓ Cancelled {cancelled_count} pending order(s)")
    else:
        cancel_err = f"retCode={code2}  retMsg='{result2.get('retMsg')}'"
        print(f"  ✗ cancel-all FAILED — {cancel_err}")


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 65)
if DRY_RUN:
    print("  DRY RUN complete — no trades placed.")
    print()
    print("  To actually close everything, run:")
    print("    python3 close_all_positions.py --execute")
else:
    status = "✓ ALL CLEAR" if not closed_err and not cancel_err else "⚠ COMPLETED WITH ERRORS"
    print(f"  {status}")
    print(f"  Positions closed OK : {len(closed_ok)}")
    print(f"  Positions FAILED    : {len(closed_err)}")
    print(f"  Orders cancelled    : {cancelled_count}")
    if closed_err:
        print()
        print("  Failed positions:")
        for e in closed_err:
            print(f"    • {e}")
    if cancel_err:
        print(f"  Order cancel error: {cancel_err}")
    if not closed_err and not cancel_err:
        print()
        print("  NEXT STEPS (run on server):")
        print("    rm -f /opt/whalestream/paused.flag")
        print("    rm -f /opt/whalestream/cb_grace.txt")
        print("    rm -f /opt/whalestream/daily_status.json")
        print("    rm -f /opt/whalestream/trader_skips.json")
        print()
        print("  Then mark stale OPEN rows in Google Sheets as EXPIRED.")
print("=" * 65)
print()
