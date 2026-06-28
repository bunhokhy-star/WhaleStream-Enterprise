"""
╔══════════════════════════════════════════════════════════════╗
║       WHALE-STREAM TRADE TRACKER                             ║
║                                                              ║
║  Runs every 30 minutes (via Task Scheduler).                 ║
║  Reads all OPEN trades from Google Sheets,                   ║
║  checks current Bybit price, marks WIN / LOSS / EXPIRED,     ║
║  calculates P&L%, and prints running stats.                  ║
║                                                              ║
║  HOW TO RUN MANUALLY:                                        ║
║    py whale_stream_tracker.py                                ║
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
import json
import hmac
import hashlib
import time as _btime
import requests
import subprocess
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from urllib.parse import urlencode as _burlencode

# Force UTF-8 output (prevents UnicodeEncodeError on Windows CP1252 consoles)
# reconfigure() can silently fail in Python 3.14 when output is redirected to a file —
# replacing the TextIOWrapper directly is the guaranteed fix.
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)


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
        _html_path = os.path.join(os.path.dirname(_path), "To do list", "Daily Checklist.html")
        with open(_html_path, encoding="utf-8") as _hf:
            _html = _hf.read()
        _inject = "var WS_EMBEDDED=" + json.dumps(_data, separators=(',', ':')) + ";"
        _html = re.sub(r'var WS_EMBEDDED=\{[\s\S]*?\};', _inject, _html)
        with open(_html_path, "w", encoding="utf-8") as _hf:
            _hf.write(_html)
    except Exception as _me:
        print(f"   ⚠ _mark_done write failed: {_me}")


# ── Auto-install missing libraries ────────────────────────────
REQUIRED = {"gspread": "gspread", "google.oauth2": "google-auth"}
for mod, pkg in REQUIRED.items():
    try:
        __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

import gspread
from gspread.utils import rowcol_to_a1   # safe: gspread guaranteed installed by REQUIRED loop above

BKK = timezone(timedelta(hours=7))   # Bangkok timezone (UTC+7) — used everywhere

# ─────────────────────────────────────────────────────────────
# CONFIGURATION  ← must match whale_stream_bot.py
# ─────────────────────────────────────────────────────────────
GOOGLE_SHEET_ID       = "1R21mkduSpbki2HmlNJMHM95-LkGS0q-AKHE1HVIfMmI"
GOOGLE_CREDENTIALS_FILE = "google_credentials.json"
LEVERAGE              = 10       # matches the bot's 10x setting
TRADE_TIMEOUT_HOURS   = 72       # mark EXPIRED if not resolved in 72h (3 days)
SCRIPT_DIR            = os.path.dirname(os.path.abspath(__file__))

# ── Telegram (same group as bot) ──────────────────────────────
try:
    from local_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Bybit Demo balance file (written by whale_stream_trader.py) ─
BYBIT_BALANCE_FILE = os.path.join(SCRIPT_DIR, "bybit_balance.json")
BYBIT_START_BALANCE = 500.00   # initial deposit — MUST match BYBIT_START_BALANCE in whale_stream_trader.py
PAUSED_FILE        = os.path.join(SCRIPT_DIR, "paused.flag")   # circuit-breaker flag

# ── Bybit Demo API auth (same creds as whale_stream_trader.py) ─
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

# ── Column indices (0-based) in Google Sheet ──────────────────
COL_COIN        = 0
COL_SIGNAL      = 1
COL_CONF        = 2
COL_ENTRY_ZONE  = 3
COL_SL          = 4
COL_TP1         = 5
COL_TP2         = 6
COL_TP3         = 7
COL_TP4         = 8
COL_PATTERN     = 9
COL_TIMESTAMP   = 10
COL_STATUS      = 11
COL_ENTRY_PRICE = 12
COL_EXIT_PRICE  = 13
COL_TP_HIT      = 14
COL_PNL         = 15
COL_RESOLVED_AT = 16
COL_BYBIT_ID    = 17   # Bybit entry order ID (written by whale_stream_trader.py)

# ─────────────────────────────────────────────────────────────
# HELPER: parse a price string like "$0.0485-$0.0500" → float
# ─────────────────────────────────────────────────────────────
def send_telegram_alert(msg):
    """Send a message to the Whale-Stream Telegram group."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"   ⚠ Telegram alert send failed: {e}")


def _parse_pnl(pnl_str):
    """
    Safely parse a P&L string to float.
    Handles formats: '+45.20%', '-30.00%', '+45.20% [B]' (Bybit write-back).
    Uses regex so suffixes like '[B]' don't break parsing.
    """
    if not pnl_str or str(pnl_str).strip() in ("", "#N/A", "#ERROR!", "—"):
        return None
    m = re.search(r'([+-]?\d+(?:\.\d+)?)', str(pnl_str).replace(",", ""))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _is_real_pnl(p):
    """
    Filter out old price-ratio P&L entries (stored as ~1.07 instead of ~+70%).
    Real leveraged P&L values have abs >= 1.5 (covers tight SLs <0.5% from entry at 10x).
    Old data stored raw price change ratios like 1.0714 which are near 0 after
    subtracting 1.0, so abs(p) < 1.5 reliably identifies them.
    """
    return p is not None and abs(p) >= 1.5


def parse_price(s):
    """Extract first numeric value from a string like '$435' or '$435-$445'."""
    nums = re.findall(r'[\d]+\.?[\d]*', str(s).replace(",", ""))
    return float(nums[0]) if nums else None


def parse_entry_midpoint(entry_zone):
    """Return midpoint of a range like '$435-$445', or single value."""
    nums = re.findall(r'[\d]+\.?[\d]*', str(entry_zone).replace(",", ""))
    if len(nums) >= 2:
        return (float(nums[0]) + float(nums[1])) / 2
    elif len(nums) == 1:
        return float(nums[0])
    return None


# ─────────────────────────────────────────────────────────────
# BYBIT: get current price for a single coin
# ─────────────────────────────────────────────────────────────
_bybit_cache = {}   # { symbol: price } — filled once per run

def load_bybit_prices():
    """Fetch ALL Bybit spot tickers in one call and cache them."""
    global _bybit_cache
    try:
        resp = requests.get(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "linear"}, timeout=15
        )
        data = resp.json().get("result", {}).get("list", [])
        for t in data:
            sym = t.get("symbol", "")
            if sym.endswith("USDT"):
                coin = sym[:-4]
                try:
                    _bybit_cache[coin] = float(t.get("markPrice") or t.get("lastPrice") or 0)
                except (ValueError, TypeError):
                    pass
        print(f"   ✓ Bybit: {len(_bybit_cache)} prices loaded")
    except Exception as e:
        print(f"   ✗ Bybit price load failed: {e}")


def get_price(coin):
    """Return current Bybit price for a coin symbol."""
    return _bybit_cache.get(coin.upper(), None)


# ─────────────────────────────────────────────────────────────
# BYBIT AUTHENTICATED REQUEST (demo account)
# ─────────────────────────────────────────────────────────────
def bybit_request_auth(method, endpoint, params=None):
    """
    Authenticated Bybit V5 GET request for demo account.
    Used only for private endpoints (closed P&L, account data).
    Public market data uses the unauthenticated load_bybit_prices() path.
    """
    timestamp   = str(int(_btime.time() * 1000) - 3000)
    recv_window = "20000"
    query_str   = _burlencode(params) if params else ""
    sign_str    = f"{timestamp}{BYBIT_API_KEY}{recv_window}{query_str}"
    signature   = hmac.new(
        BYBIT_API_SECRET.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    headers = {
        "X-BAPI-API-KEY":      BYBIT_API_KEY,
        "X-BAPI-SIGN":         signature,
        "X-BAPI-TIMESTAMP":    timestamp,
        "X-BAPI-RECV-WINDOW":  recv_window,
    }
    if "demo" in BYBIT_BASE_URL:
        headers["X-BAPI-DEMO-TRADING"] = "1"
    url = f"{BYBIT_BASE_URL}{endpoint}"
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        return resp.json()
    except Exception as e:
        return {"retCode": -1, "retMsg": str(e)}


def fetch_bybit_closed_pnl(max_pages=4):
    """
    Fetch recent closed P&L records from Bybit Demo account.
    Paginates up to max_pages × 50 = 200 records.

    Returns list of dicts:
        symbol, closedPnl (USDT), pnl_pct (% at LEVERAGE), cumEntryValue,
        avgEntryPrice, avgExitPrice, closedSize, orderId (close order),
        updatedTime (ms epoch).

    Matching strategy: use (symbol, updatedTime) proximity to sheet resolved_at.
    The orderId here is the CLOSE order, NOT the entry order in COL_BYBIT_ID.
    """
    records = []
    cursor  = None
    for _ in range(max_pages):
        params = {"category": "linear", "settleCoin": "USDT", "limit": "50"}
        if cursor:
            params["cursor"] = cursor
        result = bybit_request_auth("GET", "/v5/position/closed-pnl", params)
        if result.get("retCode") != 0:
            print(f"   ⚠ Bybit closed-pnl error: {result.get('retMsg', '?')}")
            break
        lst = result.get("result", {}).get("list", [])
        for rec in lst:
            entry_val  = float(rec.get("cumEntryValue", 0) or 0)
            closed_pnl = float(rec.get("closedPnl", 0) or 0)
            # pnl_pct mirrors tracker's formula: (price_delta / entry) * leverage * 100
            # cumEntryValue = size × avgEntryPrice (un-leveraged notional)
            # margin = cumEntryValue / LEVERAGE
            pnl_pct = (closed_pnl / (entry_val / LEVERAGE) * 100) if entry_val > 0 else None
            records.append({
                "symbol":        rec.get("symbol", ""),
                "closedPnl":     closed_pnl,
                "pnl_pct":       pnl_pct,
                "cumEntryValue": entry_val,
                "avgEntryPrice": float(rec.get("avgEntryPrice", 0) or 0),
                "avgExitPrice":  float(rec.get("avgExitPrice", 0) or 0),
                "closedSize":    float(rec.get("closedSize", 0) or 0),
                "orderId":       rec.get("orderId", ""),
                "updatedTime":   int(rec.get("updatedTime", 0) or 0),
            })
        cursor = result.get("result", {}).get("nextPageCursor", "")
        if not cursor or not lst:
            break
    return records


# ─────────────────────────────────────────────────────────────
# TRADE RESULT LOGIC
# ─────────────────────────────────────────────────────────────
def check_result(direction, entry, sl, tp1, tp2, tp3, tp4, current_price):
    """
    Returns (status, exit_price, tp_hit, pnl_pct) or None if still OPEN.
    direction: "LONG" or "SHORT"
    All prices are floats. pnl_pct includes 10x leverage.
    """
    is_long = "LONG" in direction.upper() or "🟢" in direction

    tps = [(tp4, "TP4"), (tp3, "TP3"), (tp2, "TP2"), (tp1, "TP1")]
    tps = [(p, label) for p, label in tps if p is not None and p > 0]

    if is_long:
        # Check SL first
        if current_price <= sl:
            pnl = (sl - entry) / entry * 100 * LEVERAGE
            return "LOSS", sl, "SL", round(pnl, 2)
        # Check TPs (highest first)
        for tp_price, tp_label in tps:
            if current_price >= tp_price:
                pnl = (tp_price - entry) / entry * 100 * LEVERAGE
                return "WIN", tp_price, tp_label, round(pnl, 2)
    else:
        # SHORT
        if current_price >= sl:
            pnl = (entry - sl) / entry * 100 * LEVERAGE
            return "LOSS", sl, "SL", round(pnl, 2)
        for tp_price, tp_label in tps:
            if current_price <= tp_price:
                pnl = (entry - tp_price) / entry * 100 * LEVERAGE
                return "WIN", tp_price, tp_label, round(pnl, 2)

    return None   # still open


# ─────────────────────────────────────────────────────────────
# GOOGLE SHEETS CONNECTION
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
# STATS PRINTER
# ─────────────────────────────────────────────────────────────
def print_stats(all_rows):
    """Calculate and display running win rate and P&L stats."""
    resolved = [r for r in all_rows if r.get("status") in ("WIN", "LOSS")]
    if not resolved:
        print("\n📊 No resolved trades yet.")
        return

    wins   = [r for r in resolved if r["status"] == "WIN"]
    losses = [r for r in resolved if r["status"] == "LOSS"]

    win_pnls  = [r["pnl"] for r in wins   if _is_real_pnl(r["pnl"])]
    loss_pnls = [r["pnl"] for r in losses if _is_real_pnl(r["pnl"])]
    all_pnls  = [r["pnl"] for r in resolved if _is_real_pnl(r["pnl"])]

    win_rate      = len(wins) / len(resolved) * 100
    avg_win       = sum(win_pnls)  / len(win_pnls)  if win_pnls  else 0
    avg_loss      = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0
    total_pnl     = sum(all_pnls)
    gross_wins    = sum(p for p in all_pnls if p > 0)
    gross_losses  = abs(sum(p for p in all_pnls if p < 0))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    # Expectancy per trade
    wr = win_rate / 100
    expectancy = (wr * avg_win) + ((1 - wr) * avg_loss)

    # Max drawdown — peak-to-trough on running cumulative P&L
    running = 0
    peak    = 0
    max_dd  = 0
    for p in all_pnls:
        running += p
        if running > peak:
            peak = running
        dd = running - peak
        if dd < max_dd:
            max_dd = dd

    # Consecutive win/loss streak (current and max)
    max_win_streak = 0; max_loss_streak = 0
    cur_win = 0;        cur_loss = 0
    for r in resolved:
        if r["status"] == "WIN":
            cur_win += 1; cur_loss = 0
            max_win_streak = max(max_win_streak, cur_win)
        else:
            cur_loss += 1; cur_win = 0
            max_loss_streak = max(max_loss_streak, cur_loss)
    # Current streak (last N in a row)
    last_status = resolved[-1]["status"] if resolved else None
    cur_streak_count = 0
    for r in reversed(resolved):
        if r["status"] == last_status:
            cur_streak_count += 1
        else:
            break
    streak_icon = "🔥" if last_status == "WIN" else "❄️"
    streak_label = f"{streak_icon} {cur_streak_count}× {last_status} streak"

    long_trades  = [r for r in resolved if "LONG" in r["signal"].upper() or "🟢" in r["signal"]]
    short_trades = [r for r in resolved if "SHORT" in r["signal"].upper() or "🔴" in r["signal"]]
    long_wins    = [r for r in long_trades  if r["status"] == "WIN"]
    short_wins   = [r for r in short_trades if r["status"] == "WIN"]

    tp_counts = {}
    for r in wins:
        tp = r.get("tp_hit", "")
        tp_counts[tp] = tp_counts.get(tp, 0) + 1

    best  = max(resolved, key=lambda r: r["pnl"] if r["pnl"] is not None else -999)
    worst = min(resolved, key=lambda r: r["pnl"] if r["pnl"] is not None else  999)

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║        📊  WHALE-STREAM TRADE STATS              ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"  Total Resolved : {len(resolved)}  ({len(wins)} WIN / {len(losses)} LOSS)")
    print(f"  Win Rate       : {win_rate:.1f}%")
    if long_trades:
        lr = len(long_wins)/len(long_trades)*100
        print(f"  Long Win Rate  : {lr:.1f}%  ({len(long_wins)}/{len(long_trades)})")
    if short_trades:
        sr = len(short_wins)/len(short_trades)*100
        print(f"  Short Win Rate : {sr:.1f}%  ({len(short_wins)}/{len(short_trades)})")
    print(f"  Avg Win P&L    : +{avg_win:.1f}%  (with {LEVERAGE}x leverage)")
    print(f"  Avg Loss P&L   : {avg_loss:.1f}%  (with {LEVERAGE}x leverage)")
    print(f"  Total P&L      : {total_pnl:+.1f}%")
    print(f"  Profit Factor  : {profit_factor:.2f}  (>1.0 = profitable)")
    print(f"  Expectancy     : {expectancy:+.1f}% per trade  ({'✅ EDGE' if expectancy > 0 else '⚠️ NO EDGE YET'})")
    print(f"  Max Drawdown   : {max_dd:.1f}%  (with {LEVERAGE}x leverage)")
    print(f"  Win Streak Max : {max_win_streak}  |  Loss Streak Max: {max_loss_streak}")
    print(f"  Current Streak : {streak_label}")
    if tp_counts:
        tp_str = "  TP Distribution: " + " | ".join(f"{k}:{v}" for k, v in sorted(tp_counts.items()))
        print(tp_str)
    if best["pnl"] is not None:
        print(f"  Best Trade     : {best['coin']} {best['pnl']:+.1f}% ({best.get('tp_hit','')})")
    if worst["pnl"] is not None:
        print(f"  Worst Trade    : {worst['coin']} {worst['pnl']:+.1f}% ({worst.get('tp_hit','')})")
    print()

    open_count    = sum(1 for r in all_rows if r.get("status") == "OPEN")
    expired_count = sum(1 for r in all_rows if r.get("status") == "EXPIRED")
    print(f"  Still OPEN     : {open_count}")
    print(f"  Expired (not counted in win rate): {expired_count}")

    # ── Circuit breaker warning ────────────────────────────────
    # Sort resolved by resolution timestamp so we evaluate the 12 most
    # recently RESOLVED trades — not the 12 most recently LOGGED (sheet row
    # order), which can include much older signals that just sat open longer.
    resolved_by_time = sorted(resolved, key=lambda r: r.get("resolved_at", "") or "")
    today_pnls = [r["pnl"] for r in resolved_by_time[-12:] if _is_real_pnl(r["pnl"])]
    daily_pnl  = sum(today_pnls)
    # Suppress warning if currently in a win streak of 5+ (recent P&L is clearly positive)
    _in_win_streak = (last_status == "WIN" and cur_streak_count >= 5)
    if daily_pnl < -100 and not _in_win_streak:
        print()
        print("  ⚠️  CIRCUIT BREAKER: Recent P&L < -100%. Consider pausing new signals.")
    elif cur_streak_count >= 4 and last_status == "LOSS":
        print()
        print(f"  ⚠️  LOSS STREAK ALERT: {cur_streak_count} losses in a row. Review market regime.")
    print()


# ─────────────────────────────────────────────────────────────
# DASHBOARD HTML GENERATOR
# ─────────────────────────────────────────────────────────────
def write_dashboard_html(all_rows):
    """Generate a fully self-contained dashboard.html with embedded data.
    No external requests, no auth required — works from file:// protocol.
    """
    # ── Read real Bybit Demo balance (written by whale_stream_trader.py) ──
    bybit_balance    = None
    bybit_updated_at = ""
    bybit_positions  = 0
    try:
        with open(BYBIT_BALANCE_FILE, "r", encoding="utf-8") as f:
            bdata = json.load(f)
            bybit_balance    = float(bdata.get("balance", 0))
            bybit_updated_at = bdata.get("updated_at", "")
            bybit_positions  = int(bdata.get("open_positions", 0))
    except Exception:
        pass

    bybit_delta = (bybit_balance - BYBIT_START_BALANCE) if bybit_balance is not None else None  # is not None — 0.0 balance is valid
    bybit_pct   = (bybit_delta / BYBIT_START_BALANCE * 100) if bybit_delta is not None else None

    resolved = [r for r in all_rows if r["status"] in ("WIN", "LOSS")]
    wins     = [r for r in resolved if r["status"] == "WIN"]
    losses   = [r for r in resolved if r["status"] == "LOSS"]
    open_trades    = [r for r in all_rows if r["status"] == "OPEN"]
    expired_trades = [r for r in all_rows if r["status"] == "EXPIRED"]

    # Stats — filter out old "price ratio" entries (abs < 5 = not a real leveraged %)
    # _is_real_pnl() is defined at module level (see top of file)

    total_resolved = len(resolved)
    win_rate   = (len(wins) / total_resolved * 100) if total_resolved else 0
    all_pnls   = [r["pnl"] for r in resolved if _is_real_pnl(r["pnl"])]
    win_pnls   = [r["pnl"] for r in wins   if _is_real_pnl(r["pnl"])]
    loss_pnls  = [r["pnl"] for r in losses if _is_real_pnl(r["pnl"])]
    avg_win    = (sum(win_pnls) / len(win_pnls)) if win_pnls else 0
    avg_loss   = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0
    total_pnl  = sum(all_pnls)
    gross_wins   = sum(p for p in all_pnls if p > 0)
    gross_losses = abs(sum(p for p in all_pnls if p < 0))
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else float("inf")
    wr = win_rate / 100
    expectancy = (wr * avg_win) + ((1 - wr) * avg_loss) if total_resolved else 0

    # Long / Short breakdown
    long_trades  = [r for r in resolved if "LONG" in r["signal"].upper() or "🟢" in r["signal"]]
    short_trades = [r for r in resolved if "SHORT" in r["signal"].upper() or "🔴" in r["signal"]]
    long_wins    = [r for r in long_trades  if r["status"] == "WIN"]
    short_wins   = [r for r in short_trades if r["status"] == "WIN"]
    long_wr  = (len(long_wins) / len(long_trades) * 100) if long_trades else 0
    short_wr = (len(short_wins) / len(short_trades) * 100) if short_trades else 0

    # ── Gate Status calculations ──────────────────────────────
    # Gate 1 — Trade Volume
    gate1_resolved  = len(resolved)
    gate1_pct       = gate1_resolved / 150 * 100
    gate1_color     = "accent-color" if gate1_resolved >= 150 else "warn-color"
    gate1_bar_color = "#00d4a8" if gate1_resolved >= 150 else "#ffc107"

    # Gate 2 — LONG P&L (real trades only, abs(pnl) >= 5)
    long_real    = [r for r in resolved
                    if ("LONG" in r["signal"].upper() or "🟢" in r["signal"])
                    and _is_real_pnl(r["pnl"])]
    lw_pnls      = [r["pnl"] for r in long_real if r["status"] == "WIN"]
    ll_pnls      = [r["pnl"] for r in long_real if r["status"] == "LOSS"]
    long_net_pnl = sum(lw_pnls) + sum(ll_pnls)
    sum_wins_abs = sum(lw_pnls) if lw_pnls else 0
    sum_loss_abs = abs(sum(ll_pnls)) if ll_pnls else 0
    gate2_pf     = sum_wins_abs / sum_loss_abs if sum_loss_abs > 0 else 999.0
    gate2_pass   = long_net_pnl > 0 and gate2_pf > 1.0
    gate2_status = "PASS" if gate2_pass else "FAIL"
    gate2_color  = "win-color" if gate2_pass else "loss-color"

    # Gate 3 — SHORT WR (real trades only, filtering fake/wrong-direction entries)
    short_real = [r for r in resolved
                  if ("SHORT" in r["signal"].upper() or "🔴" in r["signal"])
                  and _is_real_pnl(r["pnl"])
                  and not (r["status"] == "LOSS" and r["pnl"] is not None and r["pnl"] > 0)]
    true_short_wins  = sum(1 for r in short_real if r["status"] == "WIN")
    true_short_total = len(short_real)
    true_short_wr    = (true_short_wins / true_short_total * 100) if true_short_total > 0 else 0.0
    gate3_color      = "win-color" if true_short_wr >= 50 else "loss-color"

    # Gate 6 — 3 consecutive profitable calendar weeks (computed inline)
    _week_pnl = defaultdict(float)
    for r in resolved:
        if not _is_real_pnl(r.get("pnl")):
            continue
        _ra = r.get("resolved_at", "")
        if not _ra:
            continue
        try:
            _dt = datetime.strptime(_ra[:10], "%Y-%m-%d").replace(tzinfo=BKK)
            _iso = _dt.isocalendar()
            _wk  = f"{_iso[0]}-W{_iso[1]:02d}"   # ISO week — avoids %W year-boundary bugs
            _week_pnl[_wk] += r["pnl"]
        except Exception:
            pass
    _sorted_weeks = sorted(_week_pnl.keys())
    _last3 = _sorted_weeks[-3:] if len(_sorted_weeks) >= 3 else []
    g6_ok  = len(_last3) == 3 and all(_week_pnl[w] > 0 for w in _last3)
    # Count current trailing streak (most recent consecutive profitable weeks)
    _consec = 0
    for _wk in reversed(_sorted_weeks):
        if _week_pnl[_wk] > 0:
            _consec += 1
        elif _week_pnl[_wk] == 0:
            continue  # empty week — don't break streak (bot may have been down)
        else:
            break
    g6_str = f"{'✅' if g6_ok else '❌'} {_consec}/3 wks"

    # Max drawdown
    running = 0; peak = 0; max_dd = 0
    for p in all_pnls:
        running += p
        if running > peak: peak = running
        dd = running - peak
        if dd < max_dd: max_dd = dd

    # Equity curve data (cumulative P&L — skip old price-ratio entries)
    equity_labels = []
    equity_values = []
    running = 0
    for r in resolved:
        if _is_real_pnl(r["pnl"]):
            running += r["pnl"]
            equity_labels.append(r["coin"])
            equity_values.append(round(running, 2))

    # Recent 30 resolved trades (newest last in list = show newest first)
    recent = list(reversed(resolved[-30:]))

    # Coin leaderboard (aggregate P&L per coin — real trades only)
    coin_pnl = {}
    coin_count = {}
    for r in resolved:
        c = r["coin"]
        pnl_val = r["pnl"] if _is_real_pnl(r["pnl"]) else 0
        coin_pnl[c]   = coin_pnl.get(c, 0) + pnl_val
        coin_count[c] = coin_count.get(c, 0) + 1
    # Only rank coins that have at least one real P&L entry
    real_coin_pnl = {c: v for c, v in coin_pnl.items() if v != 0}
    sorted_coins = sorted(real_coin_pnl.items(), key=lambda x: x[1], reverse=True)
    best_coins  = sorted_coins[:5]
    worst_coins = sorted_coins[-5:][::-1]

    # Current streak (computed before circuit breaker so we can suppress false alarms)
    last_status = resolved[-1]["status"] if resolved else None
    cur_streak_count = 0
    for r in reversed(resolved):
        if r["status"] == last_status:
            cur_streak_count += 1
        else:
            break

    # Circuit breaker — sort by resolved_at so we evaluate the 12 most
    # recently RESOLVED trades (not the 12 most recently logged by row order).
    resolved_by_time_cb = sorted(resolved, key=lambda r: r.get("resolved_at", "") or "")
    recent_pnls = [r["pnl"] for r in resolved_by_time_cb[-12:] if _is_real_pnl(r["pnl"])]
    _in_win_streak_db = (last_status == "WIN" and cur_streak_count >= 5)
    circuit_breaker = sum(recent_pnls) < -100 and not _in_win_streak_db

    # SHORT repair mode flag
    short_repair_active = os.path.exists(os.path.join(SCRIPT_DIR, "short_repair.flag"))

    # Recovery coin stats (H/FF) — for dashboard when in REPAIR MODE
    _rc_set = {"H", "FF"}
    _rc_stats = {}
    for _rcc in _rc_set:
        _rcc_trades = [r for r in short_real if r.get("coin", "").upper() == _rcc]
        _rcc_w = sum(1 for r in _rcc_trades if r["status"] == "WIN")
        _rc_stats[_rcc] = (_rcc_w, len(_rcc_trades) - _rcc_w)
    # Wins needed to reach ≥50% in last-20 SHORTs
    _s20r = short_real[-20:] if len(short_real) >= 20 else short_real
    _s20r_w = sum(1 for r in _s20r if r["status"] == "WIN")
    rc_wins_needed = max(0, 10 - _s20r_w)
    rc_h_w,   rc_h_l   = _rc_stats.get("H",   (0, 0))
    rc_ff_w,  rc_ff_l  = _rc_stats.get("FF",  (0, 0))

    # Pre-compute SHORT recovery HTML block (avoids nested f-string quote conflict)
    def _rc_color(w, l):
        return "var(--win)" if (w + l > 0 and w >= l) else "var(--text1)"
    if short_repair_active:
        rc_recovery_html = (
            '<div style="background:rgba(255,193,7,0.08);border:1px solid rgba(255,193,7,0.3);'
            'border-radius:8px;padding:12px 16px;margin-bottom:16px;display:flex;align-items:center;'
            'gap:24px;flex-wrap:wrap;">'
            '<span style="color:#ffc107;font-weight:600;font-size:13px;">'
            '🔧 SHORT RECOVERY — H / FF</span>'
            f'<span style="font-size:12px;color:var(--text2);">H: '
            f'<b style="color:{_rc_color(rc_h_w,rc_h_l)}">{rc_h_w}W/{rc_h_l}L</b></span>'
            f'<span style="font-size:12px;color:var(--text2);">FF: '
            f'<b style="color:{_rc_color(rc_ff_w,rc_ff_l)}">{rc_ff_w}W/{rc_ff_l}L</b></span>'
            f'<span style="font-size:12px;color:var(--text2);">| Need '
            f'<b style="color:#ffc107">{rc_wins_needed}</b> more win(s) → 50% last-20</span>'
            '</div>'
        )
    else:
        rc_recovery_html = ""

    # Conservative phase banner (blue — shown when repair is NOT active but cons flag exists)
    _cons_flag_path = os.path.join(SCRIPT_DIR, "short_conservative.flag")
    if not short_repair_active and os.path.exists(_cons_flag_path):
        try:
            with open(_cons_flag_path, "r") as _consf:
                _cons_info = json.load(_consf)
            _cons_created = _cons_info.get("created_at", "")
            _cons_hff_dash = [
                r for r in resolved
                if ("SHORT" in r["signal"].upper() or "🔴" in r["signal"])
                and _is_real_pnl(r.get("pnl"))
                and r.get("coin", "").upper() in {"H", "FF"}
                and r.get("resolved_at", "") > _cons_created[:10]
            ]
            _cons_n_dash = len(_cons_hff_dash)
        except Exception:
            _cons_n_dash = 0
        cons_html = (
            '<div style="background:rgba(33,150,243,0.08);border:1px solid rgba(33,150,243,0.3);'
            'border-radius:8px;padding:12px 16px;margin-bottom:16px;">'
            f'<span style="color:#2196f3;font-weight:600;font-size:13px;">'
            f'🔵 SHORT CONSERVATIVE PHASE — ramp-back {_cons_n_dash}/10 trades complete</span>'
            '</div>'
        )
    else:
        cons_html = ""

    # Generated timestamp
    bkk_time = datetime.now(BKK)
    gen_time = bkk_time.strftime("%Y-%m-%d %H:%M BKK")

    # Build JSON data blobs for JS
    j_equity_labels = json.dumps(equity_labels)
    j_equity_values = json.dumps(equity_values)
    j_recent = json.dumps([
        {"coin": r["coin"], "signal": r["signal"], "status": r["status"],
         "pnl": r["pnl"], "tp_hit": r.get("tp_hit", "")}
        for r in recent
    ])
    j_best_coins  = json.dumps([{"coin": c, "pnl": round(p, 1)} for c, p in best_coins])
    j_worst_coins = json.dumps([{"coin": c, "pnl": round(p, 1)} for c, p in worst_coins])
    j_dir_data = json.dumps({
        "long_total": len(long_trades), "long_wins": len(long_wins), "long_wr": round(long_wr, 1),
        "short_total": len(short_trades), "short_wins": len(short_wins), "short_wr": round(short_wr, 1)
    })

    streak_icon = "🔥" if last_status == "WIN" else "❄️"
    streak_label = f"{streak_icon} {cur_streak_count}× {last_status}" if last_status else "—"

    # ── Live Bybit balance detail (from bybit_balance.json) ─────
    _bal = {}
    try:
        with open(os.path.join(SCRIPT_DIR, "bybit_balance.json"), "r", encoding="utf-8") as _bf2:
            _bal = json.load(_bf2)
    except Exception:
        pass
    _total_bal   = float(_bal.get("totalWalletBalance", 0) or _bal.get("balance", 0) or 0)
    _avail_bal   = float(_bal.get("totalAvailableBalance", 0) or 0)
    _used_margin = float(_bal.get("totalPositionIM", 0) or 0)
    _unreal_pnl  = float(_bal.get("totalUnrealisedPnl", 0) or 0)
    _bal_updated = _bal.get("updated_at", "")
    # Fallback: if detailed fields missing, use the simple balance key
    if _total_bal == 0 and bybit_balance is not None:  # is not None — 0.0 is a valid balance
        _total_bal = bybit_balance
    _bal_color   = "#00d4a8" if _unreal_pnl >= 0 else "#ff4d4d"
    # Build balance card HTML (empty string if no balance data at all)
    if _total_bal > 0:
        _bal_avail_str  = f"${_avail_bal:.2f}" if _avail_bal else "—"
        _bal_margin_str = f"${_used_margin:.2f}" if _used_margin else "—"
        _balance_card_html = (
            '<div style="background:#1a1a2e;border:1px solid #00d4a8;border-radius:12px;'
            'padding:16px;margin-bottom:20px;display:grid;'
            'grid-template-columns:repeat(4,1fr);gap:12px;">'
            '<div>'
            '<div style="color:#888;font-size:11px;">BYBIT BALANCE</div>'
            f'<div style="color:#00d4a8;font-size:22px;font-weight:700;">${_total_bal:.2f}</div>'
            '<div style="color:#888;font-size:11px;">Total USDT</div>'
            '</div>'
            '<div>'
            '<div style="color:#888;font-size:11px;">AVAILABLE</div>'
            f'<div style="color:#fff;font-size:18px;font-weight:600;">{_bal_avail_str}</div>'
            '</div>'
            '<div>'
            '<div style="color:#888;font-size:11px;">USED MARGIN</div>'
            f'<div style="color:#ffc107;font-size:18px;font-weight:600;">{_bal_margin_str}</div>'
            '</div>'
            '<div>'
            '<div style="color:#888;font-size:11px;">UNREALISED P&amp;L</div>'
            f'<div style="color:{_bal_color};font-size:18px;font-weight:600;">{_unreal_pnl:+.2f}</div>'
            '</div>'
            '</div>'
        )
    else:
        _balance_card_html = ""

    # ── Open positions from monitor_state.json ──────────────────
    _mon_positions = {}
    try:
        with open(os.path.join(SCRIPT_DIR, "monitor_state.json"), "r", encoding="utf-8") as _mf:
            _mon_data = json.load(_mf)
            _mon_positions = _mon_data.get("positions", {})
    except Exception:
        pass
    _n_pos = len(_mon_positions)
    if _mon_positions:
        _pos_rows = []
        for _sym, _pd in _mon_positions.items():
            _coin_name = _sym.replace("USDT", "")
            _side = _pd.get("side", "")
            _side_label = "LONG" if _side == "Buy" else "SHORT"
            _side_color = "#00d4a8" if _side == "Buy" else "#ff6b7a"
            _qty   = _pd.get("size", 0)
            _entry = _pd.get("avgPrice", 0)
            _upnl  = _pd.get("unrealisedPnl", 0)
            _upnl_color = "#00d4a8" if _upnl >= 0 else "#ff4d4d"
            _pos_rows.append(
                f'<tr>'
                f'<td><strong>{_coin_name}</strong></td>'
                f'<td align="right"><span style="color:{_side_color}">{_side_label}</span></td>'
                f'<td align="right">{_qty:g}</td>'
                f'<td align="right">{_entry:g}</td>'
                f'<td align="right" style="color:{_upnl_color}">{_upnl:+.4f}</td>'
                f'</tr>'
            )
        _position_rows_html = "\n".join(_pos_rows)
    else:
        _position_rows_html = '<tr><td colspan="5" style="color:#888;text-align:center;">No open positions</td></tr>'
    _positions_card_html = (
        '<div style="background:#12122a;border-radius:12px;padding:16px;margin-bottom:20px;">'
        f'<div style="color:#888;font-size:12px;margin-bottom:8px;">&#128202; OPEN POSITIONS ({_n_pos})</div>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<tr style="color:#888;font-size:11px;">'
        '<th align="left">COIN</th><th align="right">SIDE</th>'
        '<th align="right">QTY</th><th align="right">ENTRY</th><th align="right">UPNL</th>'
        '</tr>'
        f'{_position_rows_html}'
        '</table>'
        '</div>'
    )

    # ── Go-Live milestone card ─────────────────────────────────
    # Shows countdown until July 1, then switches to "LIVE" days-since card.
    _go_live_date = date(2026, 7, 1)
    _today = datetime.now(BKK).date()
    _days_to_live = (_go_live_date - _today).days
    if _days_to_live > 0:
        _countdown_color = "#ff4d4d" if _days_to_live <= 3 else "#ffc107" if _days_to_live <= 7 else "#00d4a8"
        _countdown_card_html = (
            '<div style="text-align:center;padding:10px;background:#1a1a2e;border-radius:8px;margin-bottom:20px;">'
            f'<span style="color:{_countdown_color};font-size:24px;font-weight:700;">{_days_to_live}</span>'
            '<span style="color:#888;font-size:13px;"> days to July 1 Go-Live</span>'
            '</div>'
        )
    else:
        _days_live = abs(_days_to_live) + 1  # +1: Day 1 on launch day (July 1), Day 2 next, etc.
        _countdown_card_html = (
            '<div style="text-align:center;padding:10px;background:#1a1a2e;border-radius:8px;margin-bottom:20px;">'
            '<span style="color:#00d4a8;font-size:18px;font-weight:700;">🚀 LIVE</span>'
            f'<span style="color:#888;font-size:13px;"> — Day {_days_live} of live trading</span>'
            '</div>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="60">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🐳 WHALE-STREAM Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0d1117;
    --bg2: #161b22;
    --bg3: #21262d;
    --accent: #00d4a8;
    --accent2: #0099ff;
    --text: #e6edf3;
    --muted: #8b949e;
    --win: #28a745;
    --loss: #dc3545;
    --warn: #ffc107;
    --border: #30363d;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Courier New', monospace; font-size: 14px; padding: 16px; }}
  h1 {{ font-size: 22px; color: var(--accent); letter-spacing: 2px; margin-bottom: 4px; }}
  .subtitle {{ color: var(--muted); font-size: 12px; margin-bottom: 20px; }}
  .grid-6 {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 20px; }}
  .card {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }}
  .card .label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }}
  .card .value {{ font-size: 22px; font-weight: bold; }}
  .card .sub {{ font-size: 11px; color: var(--muted); margin-top: 4px; }}
  .win-color {{ color: var(--win); }}
  .loss-color {{ color: var(--loss); }}
  .accent-color {{ color: var(--accent); }}
  .warn-color {{ color: var(--warn); }}
  .chart-row {{ display: grid; grid-template-columns: 2fr 1fr; gap: 12px; margin-bottom: 20px; }}
  .chart-card {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }}
  .chart-card h3 {{ font-size: 13px; color: var(--muted); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }}
  .bottom-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ color: var(--muted); text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #21262d; }}
  tr:hover td {{ background: var(--bg3); }}
  .badge {{ display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: bold; }}
  .badge-win {{ background: rgba(40,167,69,0.2); color: var(--win); }}
  .badge-loss {{ background: rgba(220,53,69,0.2); color: var(--loss); }}
  .badge-long {{ background: rgba(0,212,168,0.15); color: var(--accent); }}
  .badge-short {{ background: rgba(220,53,69,0.15); color: #ff6b7a; }}
  .alert {{ background: rgba(255,193,7,0.1); border: 1px solid var(--warn); border-radius: 8px; padding: 12px 16px; color: var(--warn); margin-bottom: 20px; font-size: 13px; }}
  .footer {{ color: var(--muted); font-size: 11px; text-align: right; margin-top: 8px; }}
  .comparison-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }}
  .comp-card {{ border-radius: 8px; padding: 16px 20px; display: flex; flex-direction: column; gap: 4px; }}
  .comp-paper {{ background: rgba(0,212,168,0.06); border: 1px solid rgba(0,212,168,0.3); }}
  .comp-real  {{ background: rgba(255,193,7,0.06);  border: 1px solid rgba(255,193,7,0.4); }}
  .comp-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); }}
  .comp-value {{ font-size: 28px; font-weight: 700; }}
  .comp-sub   {{ font-size: 11px; color: var(--muted); }}
  .dir-bar {{ height: 24px; border-radius: 4px; display: flex; align-items: center; padding: 0 8px; font-size: 12px; margin-bottom: 8px; }}
  .leaderboard-item {{ display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--border); }}
  .leaderboard-item:last-child {{ border-bottom: none; }}
  @media (max-width: 900px) {{
    .grid-6 {{ grid-template-columns: repeat(3, 1fr); }}
    .chart-row, .bottom-row {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<h1>🐳 WHALE-STREAM</h1>
<div class="subtitle">Performance Dashboard — Updated {gen_time}</div>
<div style="font-size:11px;color:#888;text-align:right;padding:4px 16px;">
  🔄 Auto-refreshes every 60s | Last updated: {gen_time}
</div>

{"<div class='alert'>⚠️ CIRCUIT BREAKER: Recent P&amp;L < -100%. Consider pausing new signals.</div>" if circuit_breaker else ""}

<!-- COUNTDOWN + BALANCE + POSITIONS -->
{_countdown_card_html}
{_balance_card_html}
{_positions_card_html}

<!-- REAL vs PAPER COMPARISON -->
{f"""<div class="comparison-row">
  <div class="comp-card comp-paper">
    <div class="comp-label">📊 PAPER P&L (Signals)</div>
    <div class="comp-value {'win-color' if total_pnl >= 0 else 'loss-color'}">{total_pnl:+.0f}%</div>
    <div class="comp-sub">10x leverage · {total_resolved} resolved trades</div>
  </div>
  <div class="comp-card comp-real">
    <div class="comp-label">💰 REAL DEMO (Bybit)</div>
    <div class="comp-value {'win-color' if bybit_delta >= 0 else 'loss-color'}">${bybit_balance:.2f}</div>
    <div class="comp-sub">Started $500 · {bybit_delta:+.2f} ({bybit_pct:+.1f}%) · {bybit_positions} pos · as of {bybit_updated_at}</div>
  </div>
</div>""" if bybit_balance is not None else ""}

<!-- GATE STATUS -->
<div class="gate-row" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;">
  <div class="card">
    <div class="label">🎯 Gate 1 — Trade Volume</div>
    <div class="value {gate1_color}">{gate1_resolved}/150</div>
    <div class="sub">{gate1_pct:.0f}% complete — need 150 resolved trades</div>
    <div style="margin-top:8px;background:var(--bg3);border-radius:4px;height:6px;">
      <div style="background:{gate1_bar_color};height:6px;border-radius:4px;width:{min(gate1_pct,100):.0f}%"></div>
    </div>
  </div>
  <div class="card">
    <div class="label">💰 Gate 2 — LONG P&L</div>
    <div class="value {gate2_color}">{"✅ " if gate2_pass else "❌ "}{gate2_status}</div>
    <div class="sub">Long net P&L: {long_net_pnl:+.1f}% | PF: {gate2_pf:.2f}x</div>
  </div>
  <div class="card">
    <div class="label">📉 Gate 3 — SHORT WR</div>
    <div class="value {gate3_color}">{true_short_wr:.1f}%</div>
    <div class="sub">{"⏸ REPAIR MODE — recovery: H/FF only | " if short_repair_active else "✅ FULL MODE | "}{true_short_wins}W/{true_short_total-true_short_wins}L real trades</div>
  </div>
  <div class="card">
    <div class="label">📅 Gate 6 — Weekly Streak</div>
    <div class="value {'win-color' if g6_ok else 'loss-color'}">{g6_str}</div>
    <div class="sub">need 3 consecutive profitable weeks</div>
  </div>
</div>

{rc_recovery_html}
{cons_html}

<!-- STAT CARDS -->
<div class="grid-6">
  <div class="card">
    <div class="label">Win Rate</div>
    <div class="value {'win-color' if win_rate >= 50 else 'warn-color' if win_rate >= 40 else 'loss-color'}">{win_rate:.1f}%</div>
    <div class="sub">{len(wins)}W / {len(losses)}L</div>
  </div>
  <div class="card">
    <div class="label">Resolved</div>
    <div class="value accent-color">{total_resolved}</div>
    <div class="sub">{len(open_trades)} open · {len(expired_trades)} expired</div>
  </div>
  <div class="card">
    <div class="label">Long WR</div>
    <div class="value {'win-color' if long_wr >= 50 else 'warn-color' if long_wr >= 40 else 'loss-color'}">{long_wr:.1f}%</div>
    <div class="sub">{len(long_wins)}/{len(long_trades)} trades</div>
  </div>
  <div class="card">
    <div class="label">Short WR</div>
    <div class="value {gate3_color}">{true_short_wr:.1f}%</div>
    <div class="sub">{true_short_wins}/{true_short_total} real trades (filtered)</div>
  </div>
  <div class="card">
    <div class="label">Total P&L</div>
    <div class="value {'win-color' if total_pnl >= 0 else 'loss-color'}">{total_pnl:+.0f}%</div>
    <div class="sub">at 10x leverage</div>
  </div>
  <div class="card">
    <div class="label">Expectancy</div>
    <div class="value {'win-color' if expectancy >= 0 else 'loss-color'}">{expectancy:+.1f}%</div>
    <div class="sub">{'✅ EDGE' if expectancy > 0 else '⚠️ NO EDGE YET'} · PF {'∞' if profit_factor == float('inf') else f'{profit_factor:.2f}'}</div>
  </div>
</div>

<!-- CHARTS -->
<div class="chart-row">
  <div class="chart-card">
    <h3>Equity Curve (Cumulative P&L %)</h3>
    <canvas id="equityChart" height="120"></canvas>
  </div>
  <div class="chart-card">
    <h3>Long vs Short Direction</h3>
    <canvas id="dirChart" height="120"></canvas>
  </div>
</div>

<!-- BOTTOM ROW -->
<div class="bottom-row">
  <!-- Recent Trades -->
  <div class="chart-card">
    <h3>Recent Trades</h3>
    <table id="tradesTable">
      <thead><tr><th>Coin</th><th>Direction</th><th>Result</th><th>TP Hit</th><th>P&L</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
  <!-- Leaderboard -->
  <div class="chart-card">
    <h3>Top Coins (Cumulative P&L)</h3>
    <div style="margin-bottom:16px">
      <div style="color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">🏆 Best</div>
      <div id="bestCoins"></div>
    </div>
    <div>
      <div style="color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">💀 Worst</div>
      <div id="worstCoins"></div>
    </div>
    <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border)">
      <div style="color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">Streak</div>
      <div style="font-size:16px">{streak_label}</div>
      <div style="font-size:11px;color:var(--muted);margin-top:4px">Max DD: {max_dd:.1f}%</div>
    </div>
  </div>
</div>

<div class="footer">Generated by whale_stream_tracker.py · {gen_time}</div>

<script>
// ── Embedded data (no external requests needed) ──────────────
const EQUITY_LABELS = {j_equity_labels};
const EQUITY_VALUES = {j_equity_values};
const RECENT_TRADES = {j_recent};
const BEST_COINS    = {j_best_coins};
const WORST_COINS   = {j_worst_coins};
const DIR_DATA      = {j_dir_data};

// ── Equity Curve Chart ───────────────────────────────────────
const eCtx = document.getElementById('equityChart').getContext('2d');
const isProfit = v => v >= 0;
new Chart(eCtx, {{
  type: 'line',
  data: {{
    labels: EQUITY_LABELS,
    datasets: [{{
      label: 'Cumulative P&L %',
      data: EQUITY_VALUES,
      borderColor: '#00d4a8',
      backgroundColor: 'rgba(0,212,168,0.08)',
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      fill: true,
      tension: 0.3
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => `${{ctx.parsed.y > 0 ? '+' : ''}}${{ctx.parsed.y.toFixed(1)}}%`
        }}
      }}
    }},
    scales: {{
      x: {{ display: false }},
      y: {{
        grid: {{ color: '#21262d' }},
        ticks: {{ color: '#8b949e', callback: v => (v > 0 ? '+' : '') + v + '%' }}
      }}
    }}
  }}
}});

// ── Direction Chart ──────────────────────────────────────────
const dCtx = document.getElementById('dirChart').getContext('2d');
new Chart(dCtx, {{
  type: 'bar',
  data: {{
    labels: ['LONG', 'SHORT'],
    datasets: [
      {{ label: 'Wins',  data: [DIR_DATA.long_wins,  DIR_DATA.short_wins],  backgroundColor: 'rgba(40,167,69,0.7)' }},
      {{ label: 'Total', data: [DIR_DATA.long_total - DIR_DATA.long_wins, DIR_DATA.short_total - DIR_DATA.short_wins], backgroundColor: 'rgba(220,53,69,0.5)' }}
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ labels: {{ color: '#8b949e', font: {{ size: 11 }} }} }},
      tooltip: {{
        callbacks: {{
          footer: items => {{
            const dir = items[0].label;
            const wr = dir === 'LONG' ? DIR_DATA.long_wr : DIR_DATA.short_wr;
            return `Win Rate: ${{wr}}%`;
          }}
        }}
      }}
    }},
    scales: {{
      x: {{ stacked: true, ticks: {{ color: '#8b949e' }}, grid: {{ color: '#21262d' }} }},
      y: {{ stacked: true, ticks: {{ color: '#8b949e' }}, grid: {{ color: '#21262d' }} }}
    }}
  }}
}});

// ── Recent Trades Table ──────────────────────────────────────
const tbody = document.querySelector('#tradesTable tbody');
RECENT_TRADES.forEach(r => {{
  const isLong  = r.signal.toUpperCase().includes('LONG') || r.signal.includes('🟢');
  const dirBadge = isLong
    ? `<span class="badge badge-long">LONG</span>`
    : `<span class="badge badge-short">SHORT</span>`;
  const resBadge = r.status === 'WIN'
    ? `<span class="badge badge-win">WIN</span>`
    : `<span class="badge badge-loss">LOSS</span>`;
  const pnl = (r.pnl != null && Math.abs(r.pnl) >= 5)
    ? `<span class="${{r.pnl >= 0 ? 'win-color' : 'loss-color'}}">${{r.pnl > 0 ? '+' : ''}}${{r.pnl.toFixed(1)}}%</span>`
    : '—';
  tbody.insertAdjacentHTML('beforeend', `
    <tr>
      <td><strong>${{r.coin}}</strong></td>
      <td>${{dirBadge}}</td>
      <td>${{resBadge}}</td>
      <td style="color:#8b949e">${{r.tp_hit || '—'}}</td>
      <td>${{pnl}}</td>
    </tr>`);
}});

// ── Leaderboards ─────────────────────────────────────────────
function renderLeaderboard(id, coins, isGood) {{
  const el = document.getElementById(id);
  coins.forEach(c => {{
    const color = isGood ? 'var(--win)' : 'var(--loss)';
    el.insertAdjacentHTML('beforeend', `
      <div class="leaderboard-item">
        <span>${{c.coin}}</span>
        <span style="color:${{color}}">${{c.pnl > 0 ? '+' : ''}}${{c.pnl}}%</span>
      </div>`);
  }});
}}
renderLeaderboard('bestCoins',  BEST_COINS,  true);
renderLeaderboard('worstCoins', WORST_COINS, false);
</script>
</body>
</html>"""

    out_path = os.path.join(SCRIPT_DIR, "dashboard.html")
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp_path, out_path)   # atomic on NTFS — no partial-write corruption
    print(f"  📊 Dashboard written → {out_path}")


# ─────────────────────────────────────────────────────────────
# GATE CHECKLIST AUTO-UPDATER  (called on Sundays by main())
# ─────────────────────────────────────────────────────────────
def _update_gate_checklist(all_rows):
    """
    Compute all 6 gate statuses from live data and append a new row
    to the GATE REVIEW LOG in GATE5_REAL_CAPITAL_CHECKLIST.md.
    Replaces the '| _next review_ |' placeholder row with today's results.
    """
    today_str = datetime.now(BKK).strftime("%Y-%m-%d")

    resolved = [r for r in all_rows if r.get("status") in ("WIN", "LOSS")]
    wins     = [r for r in resolved if r["status"] == "WIN"]

    # ── Gate 1: ≥ 150 resolved trades ──────────────────────────
    g1_n   = len(resolved)
    g1_ok  = g1_n >= 150
    g1_str = f"{'✅' if g1_ok else '❌'} {g1_n}/150"

    # ── Gate 2: Overall WR ≥ 58% over last 30 resolved ──────────
    last30    = resolved[-30:] if len(resolved) >= 30 else resolved
    last30_w  = sum(1 for r in last30 if r["status"] == "WIN")
    g2_wr     = last30_w / len(last30) * 100 if last30 else 0
    g2_ok     = g2_wr >= 58 and len(last30) >= 30
    g2_str    = f"{'✅' if g2_ok else '❌'} {g2_wr:.1f}%"

    # ── Gate 3: SHORT WR ≥ 50% over last 20 real SHORT trades ────
    def _is_real_short(r):
        pnl = r.get("pnl")
        if pnl is None: return False
        if r.get("status") == "LOSS" and pnl > 0: return False  # wrong sign
        return abs(pnl) >= 5

    shorts_real = [r for r in resolved
                   if ("SHORT" in r.get("signal","").upper() or "🔴" in r.get("signal",""))
                   and _is_real_short(r)]
    last20s     = shorts_real[-20:] if len(shorts_real) >= 20 else []
    g3_sw       = sum(1 for r in last20s if r["status"] == "WIN")
    g3_wr       = g3_sw / len(last20s) * 100 if last20s else 0
    g3_ok       = g3_wr >= 50 and len(last20s) >= 20
    g3_str      = f"{'✅' if g3_ok else '❌'} {g3_wr:.1f}%"

    # ── Gate 4: Drawdown ≤ 25% from peak + balance > start ───────
    bybit_ok  = False
    g4_str    = "❓ no data"
    try:
        with open(BYBIT_BALANCE_FILE, "r", encoding="utf-8") as _bf:
            _bd     = json.load(_bf)
            _bal    = float(_bd.get("balance", 0))
            _start  = float(_bd.get("start_balance", 500))
            _dd_pct = (_start - _bal) / _start * 100
            bybit_ok = _dd_pct <= 25  # pass if drawdown ≤ 25%; flat account is fine
            g4_str  = f"{'✅' if bybit_ok else '❌'} {_dd_pct:+.1f}%"
    except Exception:
        pass

    # ── Gate 5: No circuit breaker in last 14 days ───────────────
    g5_ok  = not os.path.exists(PAUSED_FILE)
    g5_str = f"{'✅' if g5_ok else '❌'} {'No trigger' if g5_ok else 'TRIGGERED'}"

    # ── Gate 6: 3 consecutive profitable calendar weeks ──────────
    week_pnl = defaultdict(float)
    for r in resolved:
        if not _is_real_pnl(r.get("pnl")):
            continue
        try:
            _ra  = r.get("resolved_at", "")  # use resolve date (when money was made)
            if not _ra:
                continue
            _dt  = datetime.strptime(_ra[:10], "%Y-%m-%d").replace(tzinfo=BKK)
            _iso = _dt.isocalendar()
            _wk  = f"{_iso[0]}-W{_iso[1]:02d}"   # ISO week — avoids %W year-boundary bugs
            week_pnl[_wk] += r["pnl"]
        except Exception:
            pass
    sorted_weeks  = sorted(week_pnl.keys())
    consec = 0
    max_consec = 0
    for _wk in sorted_weeks:
        if week_pnl[_wk] > 0:
            consec += 1
            max_consec = max(max_consec, consec)
        elif week_pnl[_wk] == 0:
            pass  # empty week — don't reset streak (bot may have been down)
        else:
            consec = 0
    # Check if LAST 3 weeks are all profitable
    last3_weeks = sorted_weeks[-3:] if len(sorted_weeks) >= 3 else []
    g6_ok  = len(last3_weeks) == 3 and all(week_pnl[w] > 0 for w in last3_weeks)
    g6_str = f"{'✅' if g6_ok else '❌'} {max_consec}/3 wks"

    overall_ok = all([g1_ok, g2_ok, g3_ok, bybit_ok, g5_ok, g6_ok])
    result_str = "**PASS ✅**" if overall_ok else "**FAIL**"

    new_row  = f"| {today_str} | {g1_str} | {g2_str} | {g3_str} | {g4_str} | {g5_str} | {g6_str} | {result_str} |"
    next_row = "| _next review_ | | | | | | | |"

    checklist_path = os.path.join(SCRIPT_DIR, "GATE5_REAL_CAPITAL_CHECKLIST.md")
    try:
        with open(checklist_path, "r", encoding="utf-8") as _cf:
            content = _cf.read()

        if next_row in content:
            content = content.replace(next_row, new_row + "\n" + next_row)
        else:
            # Append before the closing note
            content = content.rstrip() + f"\n{new_row}\n{next_row}\n"

        with open(checklist_path, "w", encoding="utf-8") as _cf:
            _cf.write(content)

        print(f"   ✅ Gate checklist updated: {today_str} — {result_str}")
    except Exception as _e:
        print(f"   ⚠ Gate checklist file write failed: {_e}")


# ─────────────────────────────────────────────────────────────
# WEEKLY P&L DIGEST  (called on Sundays by main())
# ─────────────────────────────────────────────────────────────
def weekly_summary(all_rows):
    """Send weekly P&L digest to Telegram. Called every Sunday by tracker."""
    today = datetime.now(BKK).date()

    # Build resolved trades with real P&L only
    resolved = []
    for r in all_rows:
        if r.get("status") not in ("WIN", "LOSS"):
            continue
        pnl = r.get("pnl")
        if not _is_real_pnl(pnl):
            continue
        # Parse resolved_at timestamp — format "YYYY-MM-DD HH:MM" (BKK)
        resolved_at_raw = ""
        if isinstance(r, dict):
            # all_parsed dicts include "resolved_at" (added Task #95) — use it directly.
            resolved_at_raw = r.get("resolved_at", "")
        if not resolved_at_raw:
            continue
        try:
            res_date = datetime.strptime(resolved_at_raw[:16], "%Y-%m-%d %H:%M").date()
        except ValueError:
            continue
        iso = res_date.isocalendar()  # (year, week, weekday)
        resolved.append({
            "status":  r["status"],
            "pnl":     pnl,
            "year":    iso[0],
            "week":    iso[1],
            "date":    res_date,
        })

    if not resolved:
        send_telegram_alert("📊 <b>WEEKLY P&L DIGEST</b>\nNo resolved trades with real P&L found.")
        return

    # Determine current week and previous 2 weeks
    current_iso = today.isocalendar()
    cur_year, cur_week = current_iso[0], current_iso[1]

    def _prev_week(year, week, n):
        """Return (year, week) n weeks before (year, week)."""
        d = datetime.fromisocalendar(year, week, 1)  # Monday of that week
        d2 = d - timedelta(weeks=n)
        iso2 = d2.isocalendar()
        return iso2[0], iso2[1]

    weeks_to_show = []
    for offset in range(2, -1, -1):  # oldest → newest: offset 2, 1, 0
        yr, wk = _prev_week(cur_year, cur_week, offset)
        # Monday of this ISO week
        week_start = datetime.fromisocalendar(yr, wk, 1).date()
        weeks_to_show.append((yr, wk, week_start, offset == 0))

    # Count consecutive profitable weeks ending on (and including) current week
    # Walk backwards from the current week
    consecutive_profitable = 0
    check_year, check_week = cur_year, cur_week
    for _ in range(52):  # safety cap
        week_trades = [t for t in resolved if t["year"] == check_year and t["week"] == check_week]
        check_year, check_week = _prev_week(check_year, check_week, 1)  # advance before possible continue
        if not week_trades:
            continue  # skip empty weeks — don't break streak (drawdown protection weeks)
        net = sum(t["pnl"] for t in week_trades)
        if net > 0:
            consecutive_profitable += 1
        else:
            break

    # Build message lines
    lines = []
    lines.append("📊 <b>WEEKLY P&L DIGEST</b>")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    for yr, wk, week_start, is_current in weeks_to_show:
        week_trades = [t for t in resolved if t["year"] == yr and t["week"] == wk]
        if not week_trades:
            label = week_start.strftime("Week of %b %d").replace(" 0", " ")
            suffix = "  ← current" if is_current else ""
            lines.append(f"{label}: no trades{suffix}")
            continue
        total  = len(week_trades)
        wins   = sum(1 for t in week_trades if t["status"] == "WIN")
        losses = total - wins
        wr     = wins / total * 100
        net    = sum(t["pnl"] for t in week_trades)
        profit = net > 0
        icon   = "✅" if profit else "❌"
        suffix = "  ← current" if is_current else ""
        label  = week_start.strftime("Week of %b %d").replace(" 0", " ")
        lines.append(
            f"{label}: {total} trades | {wins}W/{losses}L | {wr:.1f}% WR | "
            f"Net: {net:+.1f}% {icon}{suffix}"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━━")

    gate6_needed = 3
    if consecutive_profitable >= gate6_needed:
        gate6_line = f"🟢 Gate 6 status: {consecutive_profitable}/{gate6_needed} consecutive profitable weeks — GATE OPEN"
    else:
        gate6_line = f"🔒 Gate 6 status: {consecutive_profitable}/{gate6_needed} consecutive profitable weeks"
    lines.append(gate6_line)

    send_telegram_alert("\n".join(lines))
    print(f"   📊 Weekly digest sent (Gate 6: {consecutive_profitable}/{gate6_needed} consecutive profitable weeks)")


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
    print("║   📈  WHALE-STREAM TRACKER — CHECKING TRADES    ║")
    print("╚══════════════════════════════════════════════════╝")
    print()

    bkk_time = datetime.now(BKK)
    now_str  = bkk_time.strftime("%Y-%m-%d %H:%M")

    # ── Heartbeat: alert if bot missed a scheduled run ─────────
    _bot_log = os.path.join(SCRIPT_DIR, "bot_log.txt")
    try:
        _bot_mtime = os.path.getmtime(_bot_log)
        _bot_last  = datetime.fromtimestamp(_bot_mtime, tz=BKK)
        _bot_age_h = (bkk_time - _bot_last).total_seconds() / 3600
        # Bot runs every 4h. >5h = missed at least one run.
        # Alert any time of day — new schedule starts at 00:00 so suppression
        # would silence the 00:00 and 04:00 midnight/early-morning slots.
        if _bot_age_h > 5.0:
            send_telegram_alert(
                f"⚠️ BOT MISSED A RUN\n"
                f"Last bot run: {_bot_last.strftime('%Y-%m-%d %H:%M')} BKK\n"
                f"Age: {_bot_age_h:.1f}h (expected ≤4h)\n"
                f"🔧 Check Task Scheduler → WhaleStream-Bot\n"
                f"Schedule: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 BKK"
            )
            print(f"   ⚠️ BOT HEARTBEAT ALERT sent — last run {_bot_age_h:.1f}h ago")
        else:
            print(f"   ✅ Bot heartbeat OK — last run {_bot_age_h:.1f}h ago")
    except FileNotFoundError:
        print(f"   ⚠️ bot_log.txt not found — bot may never have run")
    except Exception as _e:
        print(f"   ⚠️ Heartbeat check failed: {_e}")

    # ── Load Bybit prices ──────────────────────────────────────
    print("⚡ Loading Bybit real-time prices...")
    load_bybit_prices()

    # ── Connect to Google Sheets ───────────────────────────────
    print("📋 Connecting to Google Sheets...")
    try:
        sheet = connect_sheet()
    except Exception as e:
        print(f"✗ Google Sheets error: {e}")
        _mark_done("tracker", details={"error": f"sheets_connect_failed: {str(e)[:60]}"})
        return

    all_rows_raw = sheet.get_all_values()
    if len(all_rows_raw) < 2:
        print("   No trade rows found.")
        _mark_done("tracker", details={"rows": 0})
        return

    headers  = all_rows_raw[0]
    data_rows = all_rows_raw[1:]

    print(f"   ✓ {len(data_rows)} trade rows found")

    # ── Process each row ──────────────────────────────────────
    updates          = []   # list of (row_index_1based, col_index_1based, value)
    all_parsed       = []   # for stats
    _newly_resolved  = []   # trades resolved this run → feed to Debrief Agent

    for i, row in enumerate(data_rows):
        # Pad short rows (col 17 = COL_BYBIT_ID)
        while len(row) < 18:
            row.append("")

        coin       = row[COL_COIN].strip()
        signal     = row[COL_SIGNAL].strip()
        entry_zone = row[COL_ENTRY_ZONE].strip()
        sl_str     = row[COL_SL].strip()
        tp1_str    = row[COL_TP1].strip()
        tp2_str    = row[COL_TP2].strip()
        tp3_str    = row[COL_TP3].strip()
        tp4_str    = row[COL_TP4].strip()
        ts_str     = row[COL_TIMESTAMP].strip()
        status     = row[COL_STATUS].strip()
        pnl_str    = row[COL_PNL].strip()

        all_parsed.append({
            "coin":        coin,
            "signal":      signal,
            "status":      status,
            "pnl":         _parse_pnl(pnl_str),
            "tp_hit":      row[COL_TP_HIT].strip(),
            "resolved_at": row[COL_RESOLVED_AT].strip(),
            "ts":          ts_str,   # signal timestamp — needed for Gate 1 ETA + expiry alerts
        })

        # ── TP2/TP3 pursuit completion check (partial-close WIN rows) ──
        # When a trade was auto-traded (COL_BYBIT_ID set) and resolved WIN/TP1,
        # the 50% remainder is still chasing TP2/TP3 on Bybit.
        # Current price >= TP2 (LONG) or <= TP2 (SHORT) means the Bybit limit
        # order definitely filled. Upgrade TP_HIT and recompute blended P&L.
        # Only checks rows resolved in the last 72h (partial-close window).
        if (status == "WIN"
                and row[COL_TP_HIT].strip() == "TP1"
                and (row[COL_BYBIT_ID].strip() if len(row) > COL_BYBIT_ID else "")):
            _pc_res_str = row[COL_RESOLVED_AT].strip()
            if _pc_res_str:
                try:
                    _pc_res_dt = datetime.strptime(_pc_res_str[:16], "%Y-%m-%d %H:%M").replace(
                        tzinfo=BKK
                    )
                    _pc_age_h = (bkk_time - _pc_res_dt).total_seconds() / 3600
                    if _pc_age_h <= 72:
                        _pc_current = get_price(coin)
                        _pc_entry   = (parse_price(row[COL_ENTRY_PRICE].strip())
                                       or parse_entry_midpoint(entry_zone))
                        _pc_tp1     = parse_price(tp1_str)
                        _pc_tp2     = parse_price(tp2_str)
                        _pc_tp3     = parse_price(tp3_str) if tp3_str else None
                        _pc_tp4     = parse_price(tp4_str) if tp4_str else None
                        _pc_is_long = "LONG" in signal.upper() or "🟢" in signal
                        if _pc_current and _pc_entry and _pc_tp1 and _pc_tp2:
                            _pc_upgrade = None
                            if _pc_is_long:
                                if _pc_tp4 and _pc_current >= _pc_tp4:
                                    _pc_upgrade = ("TP1+TP4", _pc_tp4, "TP4")
                                elif _pc_tp3 and _pc_current >= _pc_tp3:
                                    _pc_upgrade = ("TP1+TP3", _pc_tp3, "TP3")
                                elif _pc_current >= _pc_tp2:
                                    _pc_upgrade = ("TP1+TP2", _pc_tp2, "TP2")
                            else:
                                if _pc_tp4 and _pc_current <= _pc_tp4:
                                    _pc_upgrade = ("TP1+TP4", _pc_tp4, "TP4")
                                elif _pc_tp3 and _pc_current <= _pc_tp3:
                                    _pc_upgrade = ("TP1+TP3", _pc_tp3, "TP3")
                                elif _pc_current <= _pc_tp2:
                                    _pc_upgrade = ("TP1+TP2", _pc_tp2, "TP2")
                            if _pc_upgrade:
                                _pc_label, _pc_exit, _pc_tp_name = _pc_upgrade
                                if _pc_is_long:
                                    _pnl1 = (_pc_tp1  - _pc_entry) / _pc_entry * 100 * LEVERAGE
                                    _pnl2 = (_pc_exit - _pc_entry) / _pc_entry * 100 * LEVERAGE
                                else:
                                    _pnl1 = (_pc_entry - _pc_tp1)  / _pc_entry * 100 * LEVERAGE
                                    _pnl2 = (_pc_entry - _pc_exit) / _pc_entry * 100 * LEVERAGE
                                _blended   = (_pnl1 + _pnl2) / 2
                                _blend_str = f"{_blended:+.2f}% [T]"
                                _sr = i + 2
                                updates.append((_sr, COL_TP_HIT + 1, _pc_label))
                                updates.append((_sr, COL_PNL + 1,    _blend_str))
                                all_parsed[-1]["tp_hit"] = _pc_label
                                all_parsed[-1]["pnl"]    = _blended
                                _di = "🟢" if _pc_is_long else "🔴"
                                print(f"   🎯 {coin:8} {_pc_label}  blended P&L {_blend_str}  ({_pc_tp_name} @ {_pc_exit:.6g})")
                                send_telegram_alert(
                                    f"🎯 <b>PARTIAL CLOSE COMPLETE — {_pc_label}</b>\n"
                                    f"  {_di} {coin}\n"
                                    f"  Remainder (75%) reached {_pc_tp_name} @ {_pc_exit:.6g}\n"
                                    f"  Blended P&L: <b>{_blended:+.1f}%</b>"
                                    f" (25%@TP1 + 25%@{_pc_tp_name})\n"
                                    f"  TP1 resolved {_pc_age_h:.0f}h ago"
                                )
                except Exception:
                    pass

        # Only process OPEN rows from here on
        if status != "OPEN":
            continue
        if not coin or coin in ("STAY OUT", "—", ""):
            continue

        # ── Check for timeout (EXPIRED) ────────────────────────
        # Two-tier expiry:
        #   • No Bybit Order ID (never placed) → expire after 8h.
        #     Trader skips signals >4h old, so after 8h they will NEVER
        #     be traded. Keeping them blocks SigBot from re-generating
        #     the coin and keeps Strategist's queue permanently empty.
        #   • Has Bybit Order ID (placed, tracking TP/SL) → expire after
        #     TRADE_TIMEOUT_HOURS (72h) to allow TP2/TP3/TP4 resolution.
        bybit_id = row[COL_BYBIT_ID].strip() if len(row) > COL_BYBIT_ID else ""
        _timeout = 8 if not bybit_id else TRADE_TIMEOUT_HOURS
        try:
            trade_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M")
            trade_dt = trade_dt.replace(tzinfo=BKK)
            age_hours = (bkk_time - trade_dt).total_seconds() / 3600
            if age_hours > _timeout:
                sheet_row = i + 2  # +2: 1-indexed + skip header
                updates.append((sheet_row, COL_STATUS + 1,      "EXPIRED"))
                updates.append((sheet_row, COL_RESOLVED_AT + 1, now_str))
                all_parsed[-1]["status"] = "EXPIRED"
                if not bybit_id:
                    print(f"   ⏰ EXPIRED (never placed): {coin} — {age_hours:.0f}h old, Trader won't fill signals >4h")
                else:
                    print(f"   ⏰ {coin} EXPIRED ({age_hours:.0f}h old)")
                # ── EXPIRED Telegram alert ─────────────────────
                _exp_direction = "LONG" if ("LONG" in signal.upper() or "🟢" in signal) else "SHORT"
                _exp_reason = "never placed — entry zone stale" if not bybit_id else "not resolved in 72h"
                send_telegram_alert(
                    f"⏰ <b>EXPIRED</b>: {coin} {_exp_direction} — {_exp_reason}"
                )
                continue
        except Exception:
            pass

        # ── Get current price ──────────────────────────────────
        current = get_price(coin)
        if current is None or current == 0:
            # Fast-expire: if no Bybit price found AND open >12h → expired immediately.
            # Prevents ZEC/TAO/AKT/DEXE/XMR stacking up for 72h before expiring.
            try:
                trade_dt_fe = datetime.strptime(ts_str, "%Y-%m-%d %H:%M")
                trade_dt_fe = trade_dt_fe.replace(tzinfo=BKK)
                age_fe = (bkk_time - trade_dt_fe).total_seconds() / 3600
                if age_fe > 12:
                    sheet_row = i + 2
                    updates.append((sheet_row, COL_STATUS + 1,      "EXPIRED"))
                    updates.append((sheet_row, COL_RESOLVED_AT + 1, now_str))
                    all_parsed[-1]["status"] = "EXPIRED"
                    print(f"   ⏰ {coin} FAST-EXPIRED (no Bybit price, {age_fe:.0f}h open)")
                    # ── EXPIRED Telegram alert (fast-expire) ──
                    _fexp_direction = "LONG" if ("LONG" in signal.upper() or "🟢" in signal) else "SHORT"
                    send_telegram_alert(
                        f"⏰ <b>EXPIRED</b>: {coin} {_fexp_direction} — no Bybit price for {age_fe:.0f}h, fast-expired"
                    )
                    continue
            except Exception:
                pass
            print(f"   ⚠ {coin}: no Bybit price found — skipping")
            continue

        # ── Parse levels ───────────────────────────────────────
        entry  = parse_entry_midpoint(entry_zone)
        sl     = parse_price(sl_str)
        tp1    = parse_price(tp1_str)
        tp2    = parse_price(tp2_str)
        tp3    = parse_price(tp3_str)
        tp4    = parse_price(tp4_str)

        if entry is None or sl is None or tp1 is None:
            print(f"   ⚠ {coin}: could not parse entry/SL/TP — skipping")
            continue

        # ── Direction sanity check ─────────────────────────────
        # If SL or TP1 are on the wrong side of entry, Claude generated a
        # malformed signal. Without this guard, the SL check fires immediately
        # and produces a fake LOSS with positive P&L (e.g. SHORT LOSS +1.2%).
        # Skip these signals — they'll expire naturally at 72h.
        _is_long_sig = "LONG" in signal.upper() or "🟢" in signal
        _malformed = False
        if _is_long_sig:
            if sl >= entry:
                print(f"   ⚠ {coin}: malformed LONG — SL {sl:.6g} >= entry {entry:.6g} (skipping)")
                _malformed = True
            elif tp1 <= entry:
                print(f"   ⚠ {coin}: malformed LONG — TP1 {tp1:.6g} <= entry {entry:.6g} (skipping)")
                _malformed = True
        else:
            if sl <= entry:
                print(f"   ⚠ {coin}: malformed SHORT — SL {sl:.6g} <= entry {entry:.6g} (skipping)")
                _malformed = True
            elif tp1 >= entry:
                print(f"   ⚠ {coin}: malformed SHORT — TP1 {tp1:.6g} >= entry {entry:.6g} (skipping)")
                _malformed = True
        if _malformed:
            continue

        # ── Check result ───────────────────────────────────────
        result = check_result(signal, entry, sl, tp1, tp2, tp3, tp4, current)

        # Fill entry price on first check
        entry_price_stored = row[COL_ENTRY_PRICE].strip()
        sheet_row = i + 2
        if not entry_price_stored:
            updates.append((sheet_row, COL_ENTRY_PRICE + 1, round(entry, 8)))

        if result is not None:
            if not bybit_id:
                # ── Paper signal — never placed on Bybit. DO NOT resolve as WIN/LOSS ──
                # Without this guard, signals that were skipped by the trader (REPAIR MODE,
                # Price Invalid, stale entry, risk cap, etc.) were being counted as real wins
                # — inflating WR stats while the Bybit balance actually lost money.
                # These signals will expire naturally at 72h via the timeout guard above.
                _paper_dir = "LONG" if ("LONG" in signal.upper() or "🟢" in signal) else "SHORT"
                print(f"   📄 {coin} {_paper_dir}: paper signal (no Bybit order ID) — would have {result[0]}, NOT resolving (expires at 72h)")
                continue
            res_status, exit_price, tp_hit, pnl = result
            pnl_display = f"{pnl:+.2f}% [T]"
            updates.append((sheet_row, COL_STATUS      + 1, res_status))
            updates.append((sheet_row, COL_EXIT_PRICE  + 1, round(exit_price, 8)))
            updates.append((sheet_row, COL_TP_HIT      + 1, tp_hit))
            updates.append((sheet_row, COL_PNL         + 1, pnl_display))
            updates.append((sheet_row, COL_RESOLVED_AT + 1, now_str))
            all_parsed[-1].update({"status": res_status, "pnl": pnl, "tp_hit": tp_hit, "resolved_at": now_str})
            icon = "✅" if res_status == "WIN" else "❌"
            print(f"   {icon} {coin:8} {signal[:8]}  {res_status}  {tp_hit}  {pnl_display}  (entry {entry:.6g} → exit {exit_price:.6g})")
            # ── WIN / LOSS Telegram alert ──────────────────────
            _direction = "LONG" if ("LONG" in signal.upper() or "🟢" in signal) else "SHORT"
            # Compute running stats inline from all_parsed (which includes this trade
            # via all_parsed[-1].update(...) called just above)
            _alert_resolved = [r for r in all_parsed if r.get("status") in ("WIN", "LOSS")]
            _alert_wins     = sum(1 for r in _alert_resolved if r.get("status") == "WIN")
            _alert_losses   = sum(1 for r in _alert_resolved if r.get("status") == "LOSS")
            _alert_total    = len(_alert_resolved)
            _alert_wr       = (_alert_wins / _alert_total * 100) if _alert_total else 0.0
            # Gate 1 milestone note (every 5 resolved trades from 55 onward)
            _gate1_note = ""
            if _alert_total >= 55 and _alert_total % 5 == 0:
                _gate1_note = (
                    f"\n📊 Gate 1 progress: {_alert_total}/150 — "
                    f"{150 - _alert_total} trades to go"
                )
            if res_status == "WIN":
                _pnl_str  = f"+{pnl:.1f}%" if pnl > 0 else f"{pnl:.1f}%"
                _tp_label = tp_hit if tp_hit else "TP"
                send_telegram_alert(
                    f"✅ <b>REAL TRADE WIN — {coin} {_direction}</b>\n"
                    f"{'🟢 LONG' if _direction == 'LONG' else '🔴 SHORT'} | {_tp_label} hit\n"
                    f"Entry: {entry:.6g} → Exit: {exit_price:.6g}\n"
                    f"P&amp;L: <b>{_pnl_str}</b> (10× leverage)\n"
                    f"💰 Bybit Order: {bybit_id[:12]}...\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"Real: {_alert_wins}W/{_alert_losses}L | WR: {_alert_wr:.1f}% | Gate 1: {_alert_total}/150"
                    f"{_gate1_note}"
                )
            else:
                send_telegram_alert(
                    f"❌ <b>REAL TRADE LOSS — {coin} {_direction}</b>\n"
                    f"{'🟢 LONG' if _direction == 'LONG' else '🔴 SHORT'} | SL hit\n"
                    f"Entry: {entry:.6g} → Exit: {exit_price:.6g}\n"
                    f"P&amp;L: <b>{pnl:.1f}%</b> (10× leverage)\n"
                    f"💰 Bybit Order: {bybit_id[:12]}...\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"Real: {_alert_wins}W/{_alert_losses}L | WR: {_alert_wr:.1f}% | Gate 1: {_alert_total}/150"
                    f"{_gate1_note}"
                )
            # ── Queue for Post-Trade Debrief Agent ────────────────
            _newly_resolved.append({
                "coin":        coin,
                "direction":   _direction,
                "confidence":  row[COL_CONF].strip(),
                "pattern":     row[COL_PATTERN].strip(),
                "entry":       entry,
                "exit_price":  exit_price,
                "outcome":     res_status,
                "tp_hit":      tp_hit or "",
                "pnl":         pnl,
            })
        else:
            pct_from_entry = (current - entry) / entry * 100 if entry else 0
            is_long = "LONG" in signal.upper() or "🟢" in signal
            # Direction-aware: for LONG, +% = toward TP; for SHORT, -% = toward TP
            toward_tp = (pct_from_entry > 0 and is_long) or (pct_from_entry < 0 and not is_long)
            direction_label = "✓TP" if toward_tp else "⚠SL"
            print(f"   ⏳ {coin:8} {signal[:8]}  OPEN  current={current:.6g}  {pct_from_entry:+.2f}% [{direction_label}]")

    # ── Apply all updates to sheet in ONE batch call ──────────
    if updates:
        print(f"\n📝 Writing {len(updates)} cell updates to Google Sheets (1 batch call)...")
        batch_data = [
            {"range": rowcol_to_a1(r, c), "values": [[v]]}
            for r, c, v in updates
        ]
        sheet.batch_update(batch_data, value_input_option="USER_ENTERED")
        print("   ✓ All updates written")
    else:
        print("\n   No updates needed this run.")

    # ── Trigger Post-Trade Debrief Agent (non-blocking) ──────────
    # Spawns whale_stream_debrief.py as a background subprocess for each
    # newly-resolved WIN/LOSS trade. Tracker never waits for it — if the
    # debrief fails, trading is completely unaffected.
    if _newly_resolved:
        try:
            _debrief_script = os.path.join(SCRIPT_DIR, "whale_stream_debrief.py")
            if os.path.exists(_debrief_script):
                _flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                subprocess.Popen(
                    [sys.executable, _debrief_script, json.dumps(_newly_resolved)],
                    creationflags=_flags
                )
                print(f"\n🧠 Debrief Agent launched — {len(_newly_resolved)} trade(s) queued for analysis")
            else:
                print("\n   ℹ Debrief Agent script not found — skipping")
        except Exception as _de:
            print(f"\n   ⚠ Debrief Agent failed to start: {_de}")  # never block tracker

    # ── Bybit closed P&L write-back ───────────────────────────
    # Fetches actual realised P&L from Bybit Demo and overwrites the
    # tracker's estimated P&L for resolved trades. Estimated P&L uses
    # TP price as exit; actual P&L reflects real fill + fees.
    # Format written: "+45.20% [B]"  — "[B]" = Bybit actual (not estimated).
    # _parse_pnl() uses regex and handles this suffix transparently.
    try:
        print("\n📊 Fetching Bybit closed P&L for write-back...")
        _cpnl    = fetch_bybit_closed_pnl()
        print(f"   ✓ {len(_cpnl)} closed P&L record(s) fetched from Bybit Demo")

        _pnl_wb_updates = []
        _pnl_wb_matched = 0

        for _wi, _wr in enumerate(data_rows):
            while len(_wr) < 18:
                _wr.append("")
            _ws = _wr[COL_STATUS].strip()
            if _ws not in ("WIN", "LOSS"):
                continue
            _wbybit  = _wr[COL_BYBIT_ID].strip()
            if not _wbybit:
                continue   # no order ID logged → never traded → skip
            _wcoin   = _wr[COL_COIN].strip().upper()
            _wsym    = _wcoin + "USDT"
            _wexist  = _wr[COL_PNL].strip()
            if "[B]" in _wexist:
                continue   # already has Bybit write-back → don't overwrite

            # Parse resolved_at for time-proximity matching
            _wres_str = _wr[COL_RESOLVED_AT].strip()
            if not _wres_str:
                continue
            try:
                _wres_dt = datetime.strptime(_wres_str[:16], "%Y-%m-%d %H:%M").replace(
                    tzinfo=BKK
                )
                _wres_ms = _wres_dt.timestamp() * 1000
            except Exception:
                continue

            # Parse sheet entry price for proximity guard
            _wentry = 0.0
            try:
                _wentry_s = _wr[COL_ENTRY_PRICE].strip() if len(_wr) > COL_ENTRY_PRICE else ""
                _wentry   = float(_wentry_s) if _wentry_s else 0.0
            except Exception:
                pass

            # Find best-matching closed-pnl record:
            #   same symbol + updatedTime within ±6h of resolved_at
            #   + avgEntryPrice within ±3% (guards against wrong-match when
            #     the same coin is traded twice within 6h)
            # (partial close positions may have 2 records; we pick the
            #  closest one. For a full picture, both records' pnl sums
            #  would be needed — left as a future enhancement.)
            _best_rec   = None
            _best_delta = float("inf")
            for _cr in _cpnl:
                if _cr["symbol"] != _wsym:
                    continue
                _delta_ms = abs(_cr["updatedTime"] - _wres_ms)
                _delta_h  = _delta_ms / 3_600_000
                if _delta_h <= 6 and _delta_ms < _best_delta:
                    # Entry price proximity check (skip if entry known but >3% off)
                    if _wentry > 0:
                        _ep = _cr.get("avgEntryPrice", 0)
                        if _ep > 0 and abs(_ep - _wentry) / _wentry > 0.03:
                            continue  # different trade — same coin, wrong entry
                    _best_rec   = _cr
                    _best_delta = _delta_ms

            if _best_rec and _best_rec["pnl_pct"] is not None:
                _pnl_str = f"{_best_rec['pnl_pct']:+.2f}% [B]"
                _sheet_row = _wi + 2
                _pnl_wb_updates.append((_sheet_row, COL_PNL + 1, _pnl_str))
                _pnl_wb_matched += 1
                print(
                    f"   ✓ {_wcoin}: actual P&L {_pnl_str}  "
                    f"(was: {_wexist or 'blank'})  "
                    f"exit={_best_rec['avgExitPrice']:.6g}"
                )

                # ── TP_HIT upgrade: if row is TP1 and Bybit avgExitPrice
                # indicates TP2 or TP3 was actually reached, upgrade the label.
                # This fixes the timing gap where price hit TP2 on Bybit but
                # had already retreated below TP2 by the tracker's 30-min snapshot.
                _wtp_hit = _wr[COL_TP_HIT].strip()
                if _wtp_hit == "TP1" and _wr[COL_BYBIT_ID].strip():
                    _wavg_exit = _best_rec.get("avgExitPrice", 0)
                    if _wavg_exit and _wavg_exit > 0:
                        _wtp2_str = _wr[COL_TP2].strip() if len(_wr) > COL_TP2 else ""
                        _wtp3_str = _wr[COL_TP3].strip() if len(_wr) > COL_TP3 else ""
                        _wtp2 = parse_price(_wtp2_str) if _wtp2_str else None
                        _wtp3 = parse_price(_wtp3_str) if _wtp3_str else None
                        _wtp1_str = _wr[COL_TP1].strip() if len(_wr) > COL_TP1 else ""
                        _wtp1 = parse_price(_wtp1_str) if _wtp1_str else None
                        _w_is_long = ("LONG" in _wr[COL_SIGNAL].strip().upper()
                                      or "🟢" in _wr[COL_SIGNAL].strip())
                        _new_tp_hit = None
                        if _w_is_long:
                            if _wtp3 and _wtp3 > 0 and _wavg_exit >= _wtp3 * 0.995:
                                _new_tp_hit = "TP1+TP3"
                            elif _wtp2 and _wtp2 > 0 and _wavg_exit >= _wtp2 * 0.995:
                                _new_tp_hit = "TP1+TP2"
                        else:
                            if _wtp3 and _wtp3 > 0 and _wavg_exit <= _wtp3 * 1.005:
                                _new_tp_hit = "TP1+TP3"
                            elif _wtp2 and _wtp2 > 0 and _wavg_exit <= _wtp2 * 1.005:
                                _new_tp_hit = "TP1+TP2"
                        if _new_tp_hit:
                            _pnl_wb_updates.append((_sheet_row, COL_TP_HIT + 1, _new_tp_hit))
                            _di2 = "🟢" if _w_is_long else "🔴"
                            _tp2_disp = f"{_wtp2:.6g}" if _wtp2 else "N/A"
                            print(f"   🎯 {_wcoin}: TP_HIT upgraded TP1 → {_new_tp_hit}"
                                  f"  (Bybit avgExit={_wavg_exit:.6g}"
                                  f" vs TP2={_tp2_disp})")
                            send_telegram_alert(
                                f"🎯 <b>TP_HIT UPGRADED — {_new_tp_hit}</b>\n"
                                f"  {_di2} {_wcoin}\n"
                                f"  Bybit avgExitPrice {_wavg_exit:.6g} confirms"
                                f" {_new_tp_hit.split('+')[1]} was reached\n"
                                f"  (Tracker had logged TP1 due to 30-min timing gap)\n"
                                f"  Actual P&L: <b>{_pnl_str}</b>"
                            )

        if _pnl_wb_updates:
            _wb_batch = [
                {"range": rowcol_to_a1(_r, _c), "values": [[_v]]}
                for _r, _c, _v in _pnl_wb_updates
            ]
            sheet.batch_update(_wb_batch, value_input_option="USER_ENTERED")
            print(f"   ✓ Bybit actual P&L written for {_pnl_wb_matched} trade(s)")
        else:
            print("   ℹ No new Bybit P&L matches found this run")
    except Exception as _pe:
        print(f"   ⚠ Bybit closed P&L write-back failed: {_pe}")

    # ── Print stats ───────────────────────────────────────────
    print_stats(all_parsed)

    # ── Generate dashboard HTML ───────────────────────────────
    write_dashboard_html(all_parsed)

    # ── Circuit breaker Telegram alerts (pause / un-pause) ───────
    # The flag is written by whale_stream_trader.py; the tracker fires
    # a Telegram each run while paused, and a one-time alert when it
    # detects the flag has been cleared (bot resumed).
    _cb_state_file = os.path.join(SCRIPT_DIR, "cb_paused_prev.json")
    _cb_was_paused = False
    try:
        with open(_cb_state_file, "r") as _cbf:
            _cb_was_paused = json.load(_cbf).get("paused", False)
    except Exception:
        pass

    _cb_is_paused = os.path.exists(PAUSED_FILE)

    if _cb_is_paused:
        # Read the timestamp from the flag file if available
        _cb_since = ""
        try:
            with open(PAUSED_FILE, "r", encoding="utf-8") as _cbrf:
                _cb_since = _cbrf.readline().strip()
        except Exception:
            pass
        send_telegram_alert(
            f"🚨 <b>CIRCUIT BREAKER STILL ACTIVE</b>\n"
            f"  Bot is PAUSED — no new orders are being placed.\n"
            f"  {_cb_since}\n"
            f"  Review the losing streak, then run <code>CLEAR_PAUSE.bat</code>\n"
            f"  or delete <code>paused.flag</code> to resume trading."
        )
        print("   🚨 Circuit breaker ACTIVE — Telegram alert sent")
    elif _cb_was_paused and not _cb_is_paused:
        # Transition: was paused, now clear → bot has been resumed
        send_telegram_alert(
            f"✅ <b>CIRCUIT BREAKER RESET</b>\n"
            f"  paused.flag removed — bot will resume trading on next run."
        )
        print("   ✅ Circuit breaker cleared — resume Telegram alert sent")

    # Persist current state for next run
    try:
        with open(_cb_state_file, "w") as _cbwf:
            json.dump({"paused": _cb_is_paused}, _cbwf)
    except Exception:
        pass

    # ── Post-run Telegram pipeline summary ───────────────────────
    try:
        _bkk_now   = datetime.now(BKK)
        _open      = [r for r in all_parsed if r.get("status") == "OPEN"]
        _resolved  = [r for r in all_parsed if r.get("status") in ("WIN", "LOSS")]
        _gate1_n   = len(_resolved)
        _gate1_pct = min(_gate1_n / 150 * 100, 100)

        # Expiry risk: OPEN trades approaching 72h timeout
        # Tier 1 (48h-59h): at risk, ~12-24h left
        # Tier 2 (60h+): critical, <12h left — should manually close if profitable
        _expiring_soon = []     # 48h-59h: at risk
        _critical_close = []    # 60h+: critical, should manually close if profitable
        for _r in _open:
            _ts_str = _r.get("ts", "")
            try:
                _trade_dt = datetime.strptime(_ts_str, "%Y-%m-%d %H:%M").replace(tzinfo=BKK)
                _age_h = (_bkk_now - _trade_dt).total_seconds() / 3600
                if _age_h >= 60:
                    _critical_close.append((_r.get("coin", "?"), _r.get("signal", "?"), _age_h))
                elif _age_h >= 48:
                    _expiring_soon.append((_r.get("coin", "?"), _age_h))
            except Exception:
                pass

        _gate1_bar = "✅ CLEARED" if _gate1_n >= 150 else f"{_gate1_n}/150 ({_gate1_pct:.0f}%)"

        # Gate 1 ETA: resolved rate over last 7 days
        _seven_days_ago = _bkk_now - timedelta(days=7)
        _recent_resolved = []
        for _r in all_parsed:
            if _r.get("status") not in ("WIN", "LOSS"):
                continue
            _ts = _r.get("resolved_at", "") or _r.get("ts", "")  # use resolve date for accurate ETA
            try:
                _dt = datetime.strptime(_ts[:16], "%Y-%m-%d %H:%M").replace(tzinfo=BKK)
                if _dt >= _seven_days_ago:
                    _recent_resolved.append(_dt)
            except Exception:
                pass
        _days_with_data = max((_bkk_now - min(_recent_resolved)).total_seconds() / 86400, 1) if _recent_resolved else 7
        _daily_rate = len(_recent_resolved) / _days_with_data if _recent_resolved else 0
        _trades_needed = max(150 - _gate1_n, 0)
        if _daily_rate > 0 and _gate1_n < 150:
            _eta_days = _trades_needed / _daily_rate
            _gate1_eta = f"~{_eta_days:.0f}d ({_daily_rate:.1f}/day)"
        elif _gate1_n >= 150:
            _gate1_eta = "✅ CLEARED"
        else:
            _gate1_eta = "insufficient data"

        # Rolling LONG WR (last 20 LONG resolved trades)
        _long_resolved = [r for r in all_parsed
                          if ("LONG" in r.get("signal", "").upper() or "🟢" in r.get("signal", ""))
                          and r.get("status") in ("WIN", "LOSS")]
        _long_recent   = _long_resolved[-20:] if len(_long_resolved) >= 20 else []
        _long_overall  = [r for r in _long_resolved if r.get("status") == "WIN"]
        _overall_long_wr = len(_long_overall) / len(_long_resolved) * 100 if _long_resolved else 0
        _lr_wr = 0.0   # defensive init — used in decay-alert below (line: if _long_recent and _lr_wr < 50)

        if _long_recent:
            _lr_wins = sum(1 for r in _long_recent if r["status"] == "WIN")
            _lr_wr   = _lr_wins / len(_long_recent) * 100
            _wr_diff = _lr_wr - _overall_long_wr
            _trend   = "↑" if _wr_diff > 3 else ("↓" if _wr_diff < -3 else "→")
            _long_wr_line = f"  📈 LONG WR last {len(_long_recent)}: {_lr_wr:.0f}% {_trend} (overall {_overall_long_wr:.0f}%)"
        else:
            _long_wr_line = f"  📈 LONG WR: {_overall_long_wr:.0f}% overall ({len(_long_resolved)} trades)"

        # Gate 2: overall LONG WR vs 58% target
        _gate2_ok  = _overall_long_wr >= 58 and len(_long_resolved) >= 30
        _gate2_bar = "✅ CLEARED" if _gate2_ok else f"❌ {_overall_long_wr:.0f}% (need 58%, {len(_long_resolved)} trades)"

        # SHORT repair mode status
        _repair_flag = os.path.join(SCRIPT_DIR, "short_repair.flag")
        _in_repair   = os.path.exists(_repair_flag)
        _short_status_line = (
            "  🔧 SHORT: REPAIR MODE (blocked until WR ≥50%)"
            if _in_repair else
            "  ✅ SHORT: FULL MODE"
        )

        # SHORT recovery coin progress (H/FF) — shown only in REPAIR MODE
        _rc_line = None
        if _in_repair:
            _rc_coins = {"H", "FF"}
            _rc_real_shorts = [
                r for r in all_parsed
                if ("SHORT" in r.get("signal", "").upper() or "🔴" in r.get("signal", ""))
                and _is_real_pnl(r.get("pnl"))
                and r.get("coin", "").upper() in _rc_coins
                and r.get("status") in ("WIN", "LOSS")
            ]

            # ── AUTO-EXIT: lift repair mode when WR ≥ 55% over ≥ 6 trades ──
            if len(_rc_real_shorts) >= 6:
                _rc_exit_wins = sum(1 for r in _rc_real_shorts if r["status"] == "WIN")
                _rc_exit_wr   = _rc_exit_wins / len(_rc_real_shorts) * 100
                if _rc_exit_wr >= 55:
                    try:
                        os.remove(_repair_flag)
                        _cons_flag = os.path.join(SCRIPT_DIR, "short_conservative.flag")
                        with open(_cons_flag, "w") as _cf:
                            json.dump({"created_at": datetime.now(BKK).isoformat(), "trades_target": 10}, _cf)
                        send_telegram_alert(
                            f"🎉 <b>SHORT REPAIR MODE LIFTED</b>\n"
                            f"  H/FF combined WR: {_rc_exit_wr:.0f}%"
                            f" over {len(_rc_real_shorts)} trades\n"
                            f"  Exit criteria met (≥55% WR, ≥6 trades).\n"
                            f"  SHORT signals now open to all non-blacklisted coins.\n"
                            f"  Entering SHORT CONSERVATIVE phase — H/FF only, ≥93% conf, max 1/run for next 10 trades."
                        )
                        _in_repair = False
                        _short_status_line = (
                            "  ✅ SHORT: FULL MODE (repair mode AUTO-LIFTED this run 🎉)"
                        )
                        print(
                            f"   🎉 SHORT REPAIR AUTO-LIFTED — "
                            f"{_rc_exit_wr:.0f}% WR over {len(_rc_real_shorts)} trades"
                        )
                    except Exception as _re:
                        print(f"   ⚠ Failed to remove short_repair.flag: {_re}")

            if _rc_real_shorts:
                _rc_parts = []
                for _rc in ["H", "FF"]:
                    _rc_t = [r for r in _rc_real_shorts if r.get("coin", "").upper() == _rc]
                    if _rc_t:
                        _rc_w = sum(1 for r in _rc_t if r["status"] == "WIN")
                        _rc_parts.append(f"{_rc}={_rc_w}W/{len(_rc_t)-_rc_w}L")
                # Wins needed to reach 50% last-20
                _s20 = [r for r in all_parsed
                        if ("SHORT" in r.get("signal", "").upper() or "🔴" in r.get("signal", ""))
                        and _is_real_pnl(r.get("pnl"))
                        and r.get("status") in ("WIN", "LOSS")][-20:]
                _s20_w = sum(1 for r in _s20 if r["status"] == "WIN")
                _wins_needed = max(0, 10 - _s20_w)
                _rc_line = f"  🔄 Recovery: {' '.join(_rc_parts)} | need {_wins_needed} more win(s)"
            else:
                _rc_line = "  🔄 Recovery: H/FF SHORTs unlocked — no trades placed yet"

        # ── Conservative phase auto-exit check ────────────────────
        _cons_flag_path = os.path.join(SCRIPT_DIR, "short_conservative.flag")
        if not _in_repair and os.path.exists(_cons_flag_path):
            try:
                with open(_cons_flag_path, "r") as _cff:
                    _cons_data = json.load(_cff)
                _cons_created_at = _cons_data.get("created_at", "")
                _cons_target     = _cons_data.get("trades_target", 10)
                # Count H/FF SHORTs resolved AFTER the flag's created_at
                _cons_hff_all = [
                    r for r in all_parsed
                    if ("SHORT" in r.get("signal", "").upper() or "🔴" in r.get("signal", ""))
                    and _is_real_pnl(r.get("pnl"))
                    and r.get("coin", "").upper() in {"H", "FF"}
                    and r.get("status") in ("WIN", "LOSS")
                    and r.get("resolved_at", "") > _cons_created_at[:10]
                ]
                _cons_count = len(_cons_hff_all)
                _cons_wins  = sum(1 for r in _cons_hff_all if r["status"] == "WIN")
                _cons_wr    = (_cons_wins / _cons_count * 100) if _cons_count > 0 else 0.0
                if _cons_count >= _cons_target and _cons_wr >= 50:
                    os.remove(_cons_flag_path)
                    send_telegram_alert(
                        f"✅ SHORT CONSERVATIVE phase complete — {_cons_count} SHORTs at {_cons_wr:.0f}% WR."
                        f" Full SHORT access restored to all non-blacklisted coins."
                    )
                    print(f"   ✅ SHORT CONSERVATIVE phase complete — {_cons_count} trades @ {_cons_wr:.0f}% WR")
                    _short_status_line = "  ✅ SHORT: FULL MODE (conservative phase COMPLETE this run 🎉)"
                elif _cons_count >= _cons_target and _cons_wr < 50:
                    _new_target = _cons_count + 10
                    with open(_cons_flag_path, "w") as _cfw:
                        json.dump({"created_at": _cons_created_at, "trades_target": _new_target}, _cfw)
                    send_telegram_alert(
                        f"⚠️ SHORT CONSERVATIVE extended — {_cons_count} trades but only {_cons_wr:.0f}% WR."
                        f" Need ≥50% to unlock. Continuing 10 more trades."
                    )
                    print(f"   ⚠ SHORT CONSERVATIVE extended — {_cons_count} trades @ {_cons_wr:.0f}% WR, need ≥50%")
                    _short_status_line = f"  ⚠️ SHORT: CONSERVATIVE phase ({_cons_count}/{_new_target} trades, {_cons_wr:.0f}% WR)"
                else:
                    _short_status_line = f"  ⚠️ SHORT: CONSERVATIVE phase ({_cons_count}/10 trades, {_cons_wr:.0f}% WR)"
            except Exception as _ce:
                print(f"   ⚠ Conservative phase check failed: {_ce}")

        _lines = [
            f"📊 <b>TRACKER RUN — {_bkk_now.strftime('%a %H:%M')} BKK</b>",
            f"  🎯 Gate 1: {_gate1_bar}  ⏱ ETA: {_gate1_eta}",
            f"  🎯 Gate 2: {_gate2_bar}",
            _long_wr_line,
            _short_status_line,
        ]
        if _rc_line:
            _lines.append(_rc_line)
        _lines.append(f"  ⏳ OPEN trades: {len(_open)} waiting to resolve")
        # LONG WR decay alert — fires only when WR is genuinely bad
        if _long_recent and _lr_wr < 50:
            _lines.append(
                f"  ⚠️ LONG WR DECAY — Last {len(_long_recent)}: {_lr_wr:.0f}% "
                f"(below 50% — review coin/pattern selection)"
            )

        if _expiring_soon:
            _exp_str = ", ".join(f"{c} ({h:.0f}h)" for c, h in sorted(_expiring_soon, key=lambda x: -x[1]))
            _lines.append(f"  ⚠️ Expiring soon (<24h left): {_exp_str}")
        else:
            _lines.append(f"  ✅ No trades expiring in next 24h")
        for _coin, _dir, _age_h in sorted(_critical_close, key=lambda x: -x[2]):
            _hours_left = 72 - _age_h
            _lines.append(
                f"  🚨 CRITICAL — {_coin} {_dir} is {_age_h:.0f}h old "
                f"({_hours_left:.0f}h left). Check Bybit NOW — close manually if in profit!"
            )

        send_telegram_alert("\n".join(_lines))
    except Exception as _e:
        print(f"⚠ Post-run Telegram summary failed: {_e}")

    # ── Gate 1 milestone Telegram bursts ─────────────────────────
    # Fires a celebration burst the first time resolved count crosses
    # 50 / 75 / 100 / 125 / 150. State persisted in milestone_state.json
    # so each milestone fires exactly once, even across restarts.
    try:
        _ms_file = os.path.join(SCRIPT_DIR, "milestone_state.json")
        try:
            with open(_ms_file, "r") as _msfh:
                _ms_state = json.load(_msfh)
        except Exception:
            _ms_state = {"fired": []}

        _ms_resolved = [r for r in all_parsed if r.get("status") in ("WIN", "LOSS")]
        _ms_n        = len(_ms_resolved)
        _ms_wins     = sum(1 for r in _ms_resolved if r.get("status") == "WIN")
        _ms_wr       = _ms_wins / _ms_n * 100 if _ms_n else 0

        _ms_longs   = [r for r in _ms_resolved
                       if "LONG" in r.get("signal", "").upper() or "🟢" in r.get("signal", "")]
        _ms_long_w  = sum(1 for r in _ms_longs if r.get("status") == "WIN")
        _ms_long_wr = _ms_long_w / len(_ms_longs) * 100 if _ms_longs else 0

        _ms_pnl_vals = [r.get("pnl") for r in _ms_resolved if _is_real_pnl(r.get("pnl"))]
        _ms_avg_pnl  = sum(_ms_pnl_vals) / len(_ms_pnl_vals) if _ms_pnl_vals else None

        _ms_fired_any = False
        for _ms_thresh in [50, 75, 100, 125, 150]:
            if _ms_n >= _ms_thresh and _ms_thresh not in _ms_state.get("fired", []):
                _ms_pct  = _ms_thresh / 150 * 100
                if _ms_thresh == 150:
                    _ms_head = "🏆 <b>GATE 1 MILESTONE — 150 RESOLVED TRADES!</b>"
                    _ms_sub  = "Gate 1 complete. Real capital assessment window is now open."
                    _ms_next = ""
                else:
                    _ms_head = f"🎯 <b>GATE 1 CHECKPOINT — {_ms_thresh} TRADES RESOLVED!</b>"
                    _ms_sub  = f"Progress: {_ms_thresh}/150 ({_ms_pct:.0f}% of Gate 1)"
                    _ms_next = f"\n  Next checkpoint: {150 - _ms_thresh} more trades to go"
                _ms_pnl_line = (
                    f"\n  📊 Avg P&L (real trades): {_ms_avg_pnl:+.1f}%"
                    if _ms_avg_pnl is not None else ""
                )
                _ms_msg = (
                    f"{_ms_head}\n"
                    f"  {_ms_sub}\n"
                    f"  Overall WR : {_ms_wr:.0f}%  ({_ms_wins}W/{_ms_n - _ms_wins}L)\n"
                    f"  LONG WR    : {_ms_long_wr:.0f}%  ({len(_ms_longs)} trades)"
                    f"{_ms_pnl_line}{_ms_next}"
                )
                send_telegram_alert(_ms_msg)
                print(f"   🎯 Milestone burst sent — {_ms_thresh} resolved trades")
                _ms_state.setdefault("fired", []).append(_ms_thresh)
                _ms_fired_any = True

        if _ms_fired_any:
            with open(_ms_file, "w") as _msfh2:
                json.dump(_ms_state, _msfh2)
    except Exception as _mse:
        print(f"   ⚠ Milestone burst failed: {_mse}")

    # ── Weekly summary + short analysis (fires on Sundays only) ──
    if _bkk_now.weekday() == 6:  # 6 = Sunday
        weekly_summary(all_parsed)
        # Auto-run analyze_shorts.py so SHORT recovery detection fires weekly
        try:
            _shorts_script = os.path.join(SCRIPT_DIR, "analyze_shorts.py")
            print("📊 Sunday: Running analyze_shorts.py for SHORT recovery check...")
            subprocess.run([sys.executable, _shorts_script], timeout=120)
            print("   ✓ analyze_shorts.py completed")
        except Exception as _e:
            print(f"   ⚠ analyze_shorts.py auto-run failed: {_e}")

        # ── Auto-update Gate checklist ───────────────────────
        try:
            _update_gate_checklist(all_parsed)
        except Exception as _ge:
            print(f"   ⚠ Gate checklist update failed: {_ge}")

    # ── Monday Gate 1 progress snapshot ──────────────────────────────────────
    if _bkk_now.weekday() == 0:  # 0 = Monday
        try:
            _ml = [r for r in all_parsed
                   if ("LONG" in r.get("signal", "").upper() or "🟢" in r.get("signal", ""))
                   and _is_real_pnl(r.get("pnl"))
                   and r.get("status") in ("WIN", "LOSS")]
            # Gate 1 = 150+ resolved real LONG trades (volume gate)
            _g1_ok = len(_ml) >= 150
            _g1_remaining = max(0, 150 - len(_ml))
            if _g1_ok:
                _g1_str = f"✅ GATE 1 CLEARED — {len(_ml)} resolved LONGs"
            else:
                _g1_str = f"⏳ {len(_ml)}/150 real LONGs ({_g1_remaining} more needed)"
            # Gate 2 = 58% WR over all resolved LONGs (min 30)
            _ml_all   = _ml
            _ml_all_w = sum(1 for r in _ml_all if r["status"] == "WIN")
            _ml_all_wr = _ml_all_w / len(_ml_all) * 100 if _ml_all else 0
            _g2_ok = _ml_all_wr >= 58 and len(_ml_all) >= 30
            _g2_str = (
                f"✅ {_ml_all_wr:.0f}% over {len(_ml_all)} trades"
                if _g2_ok else
                f"❌ {_ml_all_wr:.0f}% over {len(_ml_all)} trades (need 58% / 30+)"
            )

            send_telegram_alert(
                f"📅 <b>MONDAY GATE SNAPSHOT</b>\n"
                f"  Gate 1 (volume):    {_g1_str}\n"
                f"  Gate 2 (WR):        {_g2_str}\n"
                f"  Total resolved LONGs: {len(_ml_all)}"
            )
            print("📅 Monday Gate snapshot sent to Telegram")
        except Exception as _me:
            print(f"   ⚠ Monday Gate snapshot failed: {_me}")
    # Build details for Daily Checklist live display
    _bkk_finish = datetime.now(BKK)
    _nr_wins    = sum(1 for r in _newly_resolved if r.get("outcome") == "WIN")
    _nr_losses  = sum(1 for r in _newly_resolved if r.get("outcome") == "LOSS")
    _open_cnt   = sum(1 for r in all_parsed if r.get("status") == "OPEN")
    _mark_done("tracker", details={
        "resolved":  len(_newly_resolved),
        "wins":      _nr_wins,
        "losses":    _nr_losses,
        "open":      _open_cnt,
        "last_run":  f"{_bkk_finish.strftime('%H:%M')} BKK"
    })
    # Completion log — enables watchdog check_tracker() primary path
    print(f"[{_bkk_finish.strftime('%Y-%m-%d %H:%M')} BKK] Tracker run complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as _tracker_crash:
        print(f"⚠ Tracker crashed: {_tracker_crash}")
        # Guarantee checklist tick even on unhandled exception
        try:
            _mark_done("tracker", details={"error": str(_tracker_crash)[:80], "last_run": "crashed"})
        except Exception:
            pass
