"""
╔══════════════════════════════════════════════════════════════╗
║   WHALE-STREAM STRATEGIST v1.3 — SIGNAL QUALITY COUNCIL     ║
║                                                              ║
║  Team role: runs at :10 (Bot fires :00, Trader fires :20)   ║
║                                                              ║
║  The Bot (Scout) finds the best setups in the market.        ║
║  The Strategist asks: "Should WE take THIS trade, given      ║
║  OUR history on this coin?"                                  ║
║                                                              ║
║  Key principle: not every signal is worth taking.            ║
║  If the last entry on a coin was poor quality, we wait       ║
║  for a better setup rather than repeating the mistake.       ║
║                                                              ║
║  OUTPUT: strategist_decisions.json  (read by trader.py)      ║
║                                                              ║
║  HOW TO RUN:                                                 ║
║    python whale_stream_strategist.py                         ║
║                                                              ║
║  SCHEDULE:  :10 past every 4-hour mark (via Task Scheduler)  ║
║    00:10, 04:10, 08:10, 12:10, 16:10, 20:10 BKK             ║
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
import sys
import json
import subprocess
import requests
from datetime import datetime, timezone, timedelta

# ── Force UTF-8 output (prevents crash in Task Scheduler) ─────
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
        _html = _re.sub(r'var WS_EMBEDDED=\{[\s\S]*?\};', _inject, _html)
        with open(_html_path, "w", encoding="utf-8") as _hf:
            _hf.write(_html)
    except Exception:
        pass


# ── Auto-install missing libraries ─────────────────────────────
REQUIRED = {"anthropic": "anthropic", "gspread": "gspread", "google.oauth2": "google-auth"}
for mod, pkg in REQUIRED.items():
    try:
        __import__(mod)
    except ImportError:
        print(f"   ⬇ Installing {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

# ═══════════════════════════════════════════════════════════════
# SECTION 1 — CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# Secrets: loaded from local_config.py (gitignored). Fallback: env vars.
try:
    from local_config import ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    import os as _os
    ANTHROPIC_API_KEY  = _os.getenv("ANTHROPIC_API_KEY", "")
    TELEGRAM_BOT_TOKEN = _os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = _os.getenv("TELEGRAM_CHAT_ID", "")

# Google Sheets (same sheet as the rest of the team)
GOOGLE_SHEET_ID         = "1R21mkduSpbki2HmlNJMHM95-LkGS0q-AKHE1HVIfMmI"
GOOGLE_CREDENTIALS_FILE = "google_credentials.json"

# Claude model for the Strategist.
# Using Haiku: the decision logic is smaller/simpler than full signal generation.
# Upgrade to claude-sonnet-4-6 if decision quality seems insufficient.
STRATEGIST_MODEL = "claude-haiku-4-5-20251001"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Output file consumed by whale_stream_trader.py
DECISIONS_FILE     = os.path.join(SCRIPT_DIR, "strategist_decisions.json")
LOG_FILE           = os.path.join(SCRIPT_DIR, "strategist_log.txt")
PAUSED_FILE        = os.path.join(SCRIPT_DIR, "paused.flag")
BALANCE_FILE       = os.path.join(SCRIPT_DIR, "bybit_balance.json")
MONITOR_FILE       = os.path.join(SCRIPT_DIR, "monitor_state.json")
MEMORY_FILE        = os.path.join(SCRIPT_DIR, "pattern_memory.json")   # written by Debrief Agent

# How far back to look for "current" signals.
# Bot dedup prevents re-writing the same OPEN signal within a day, so signals
# written at midnight must still be visible 20+ hours later. Use 26h (full day + buffer).
SIGNAL_WINDOW_HOURS = 26

# How many historical resolved trades to look back per coin for quality assessment
MAX_HISTORY_ROWS = 60   # scan last 60 rows to find per-coin history

# ═══════════════════════════════════════════════════════════════
# SECTION 2 — GOOGLE SHEETS COLUMN INDICES  (matches tracker.py)
# ═══════════════════════════════════════════════════════════════
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
COL_BYBIT_ID    = 17

# ═══════════════════════════════════════════════════════════════
# SECTION 3 — HELPERS
# ═══════════════════════════════════════════════════════════════

def log(msg):
    bkk = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M BKK")
    line = f"[{bkk}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def connect_sheet():
    creds_path = os.path.join(SCRIPT_DIR, GOOGLE_CREDENTIALS_FILE)
    # Use google.oauth2 directly — bypasses gspread.auth which fails on some Python 3.14 setups
    from google.oauth2.service_account import Credentials as _GCreds
    try:
        from gspread.client import Client as _GClient
    except ImportError:
        import subprocess as _sp, sys as _sys
        _sp.check_call([_sys.executable, "-m", "pip", "install", "--upgrade", "gspread", "--quiet"])
        from gspread.client import Client as _GClient
    _SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = _GCreds.from_service_account_file(creds_path, scopes=_SCOPES)
    client = _GClient(auth=creds)
    return client.open_by_key(GOOGLE_SHEET_ID).sheet1


def bkk_now():
    return datetime.now(timezone(timedelta(hours=7)))


def parse_bkk_timestamp(ts_str):
    """Parse 'YYYY-MM-DD HH:MM BKK' → aware datetime (BKK = UTC+7)."""
    try:
        clean = ts_str.replace(" BKK", "").strip()
        dt    = datetime.strptime(clean, "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=timezone(timedelta(hours=7)))
    except Exception:
        return None


def safe_float(s):
    """Convert string like '+45.20%' or '0.685' to float, None on failure."""
    try:
        return float(str(s).replace("%", "").replace("+", "").strip())
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# SECTION 4 — DATA COLLECTION
# ═══════════════════════════════════════════════════════════════

def load_latest_signals(all_rows):
    """
    Find OPEN signals from the most recent bot run (within SIGNAL_WINDOW_HOURS).
    Returns list of dicts with signal data.
    """
    now   = bkk_now()
    cutoff = now - timedelta(hours=SIGNAL_WINDOW_HOURS)
    signals = []

    for row in all_rows:
        if len(row) <= COL_STATUS:
            continue
        status = row[COL_STATUS].strip().upper()
        if status != "OPEN":
            continue
        ts_str = row[COL_TIMESTAMP].strip() if len(row) > COL_TIMESTAMP else ""
        ts     = parse_bkk_timestamp(ts_str)
        if ts and ts < cutoff:
            continue   # too old — from a previous run

        coin      = row[COL_COIN].strip().upper()
        direction = row[COL_SIGNAL].strip().upper()
        conf_raw  = row[COL_CONF].strip() if len(row) > COL_CONF else ""
        pattern   = row[COL_PATTERN].strip() if len(row) > COL_PATTERN else ""
        entry     = row[COL_ENTRY_ZONE].strip() if len(row) > COL_ENTRY_ZONE else ""
        conf      = safe_float(conf_raw) or 0.0

        if not coin or direction not in ("LONG", "SHORT"):
            continue

        signals.append({
            "coin":      coin,
            "direction": direction,
            "confidence": conf,
            "pattern":   pattern,
            "entry":     entry,
            "timestamp": ts_str,
        })

    return signals


def build_coin_history(all_rows, signals):
    """
    For each coin+direction in signals, find recent resolved trades (WIN/LOSS)
    in the last MAX_HISTORY_ROWS rows.

    Returns dict: {("COIN", "DIRECTION"): [trade_dict, ...]}
    trades are ordered newest-first.
    """
    # Which (coin, direction) pairs do we care about?
    targets = set((s["coin"], s["direction"]) for s in signals)

    # Scan the last MAX_HISTORY_ROWS data rows
    scan_rows = all_rows[-MAX_HISTORY_ROWS:] if len(all_rows) > MAX_HISTORY_ROWS else all_rows

    history = {t: [] for t in targets}

    for row in reversed(scan_rows):   # newest first
        if len(row) <= COL_STATUS:
            continue
        coin      = row[COL_COIN].strip().upper()
        direction = row[COL_SIGNAL].strip().upper()
        status    = row[COL_STATUS].strip().upper()
        key       = (coin, direction)

        if key not in targets:
            continue
        if status not in ("WIN", "LOSS"):
            continue

        tp_hit   = row[COL_TP_HIT].strip()    if len(row) > COL_TP_HIT   else ""
        pnl      = row[COL_PNL].strip()        if len(row) > COL_PNL      else ""
        resolved = row[COL_RESOLVED_AT].strip() if len(row) > COL_RESOLVED_AT else ""
        pattern  = row[COL_PATTERN].strip()    if len(row) > COL_PATTERN  else ""

        history[key].append({
            "outcome":  status,          # "WIN" or "LOSS"
            "tp_hit":   tp_hit,          # "TP1", "TP2", "TP3", ""
            "pnl":      pnl,             # "+45.20%" or "-30.00%"
            "resolved": resolved,
            "pattern":  pattern,
        })

    return history


def load_portfolio_state():
    """
    Read current open positions from monitor_state.json and balance from bybit_balance.json.
    Returns (positions_dict, balance, drawdown_pct).
    """
    positions    = {}
    balance      = 0.0
    drawdown_pct = 0.0

    try:
        with open(MONITOR_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            positions = data.get("positions", {})
    except Exception:
        pass

    try:
        with open(BALANCE_FILE, "r", encoding="utf-8") as f:
            data          = json.load(f)
            balance       = float(data.get("balance", 0))
            start_balance = float(data.get("start_balance", 500))
            drawdown_pct  = (start_balance - balance) / start_balance * 100 if start_balance > 0 else 0
    except Exception:
        pass

    return positions, balance, drawdown_pct


def get_btc_7d_pct():
    """
    Fetch BTC 7-day % change from CoinGecko (same source as bot.py).
    Returns float or None on failure.
    """
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": "bitcoin",
            "price_change_percentage": "7d",
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data and isinstance(data, list):
            return data[0].get("price_change_percentage_7d_in_currency")
    except Exception:
        pass
    return None


def get_btc_market_bias():
    """
    BTC Market Regime Filter — determines which direction to trade.

    Fetches last 20 completed × 4h BTC candles from Bybit V5 (no API key needed).
    Compares current BTC price to 20-period SMA:
      - Price > SMA by >2% → BULLISH  → only trade LONGs (veto SHORTs)
      - Price < SMA by >2% → BEARISH  → only trade SHORTs (veto LONGs)
      - Within ±2% of SMA  → NEUTRAL  → trade both directions

    Returns: (bias, current_price, sma20, pct_from_sma)
    bias = "BEARISH" / "BULLISH" / "NEUTRAL"
    All other values are None on API failure (defaults to NEUTRAL).
    """
    try:
        url = "https://api.bybit.com/v5/market/kline"
        params = {
            "category": "linear",
            "symbol":   "BTCUSDT",
            "interval": "240",   # 4-hour candles
            "limit":    "21",    # 20 completed + 1 current (incomplete)
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("retCode") != 0:
            return "NEUTRAL", None, None, None

        candles = data["result"]["list"]
        if len(candles) < 21:
            return "NEUTRAL", None, None, None

        # Bybit returns newest first.
        # candles[0] = current (still open/incomplete), candles[1:21] = last 20 closed.
        # Each candle: [timestamp, open, high, low, close, volume, turnover]
        closes  = [float(c[4]) for c in candles[1:21]]  # 20 completed closes
        sma20   = sum(closes) / len(closes)
        current = float(candles[0][4])                   # current candle close (live)

        pct_from_sma = (current - sma20) / sma20 * 100

        if pct_from_sma < -2.0:
            bias = "BEARISH"
        elif pct_from_sma > 2.0:
            bias = "BULLISH"
        else:
            bias = "NEUTRAL"

        return bias, current, sma20, pct_from_sma

    except Exception as e:
        print(f"   ⚠ Market bias fetch failed: {e}")
        return "NEUTRAL", None, None, None


# ═══════════════════════════════════════════════════════════════
# SECTION 5 — STRATEGIST PROMPT
# ═══════════════════════════════════════════════════════════════

try:
    from mission import MISSION_PROMPT, print_mission_banner
except ImportError:
    MISSION_PROMPT = ""
    def print_mission_banner(): pass

STRATEGIST_SYSTEM = (MISSION_PROMPT + """You are the WHALE-STREAM Trading Strategist — the second layer of review between signal generation and execution.

The Bot (Scout) already ran market analysis and selected the best technical setups.
Your job is different: decide whether WE should take each trade, given OUR specific history on this coin.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GOLDEN RULE — FOLLOW THE MARKET TREND
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The simplest truth in trading: trade WITH the trend, never against it.

🐻 Market BEARISH (BTC falling, below SMA) → SHORTs flow with the tide. LONGs fight it and lose.
🐂 Market BULLISH (BTC rising, above SMA) → LONGs flow with the tide. SHORTs fight it and lose.
😐 Market NEUTRAL (BTC sideways) → Both directions allowed with normal quality filters.

NOTE: The code already pre-vetoed any signals fighting the current trend before you see them.
Your job is to reinforce this principle — if a signal direction seems to fight the market, VETO it.
Our proof: LONGs were -108% net P&L fighting a downtrend. SHORTs were 77.6% WR flowing with it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUTOMATIC VETO — no exceptions:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Last trade on this coin+direction = LOSS (SL hit) → VETO
   Momentum is broken. The coin needs to prove itself before we re-enter the same direction.

2. Pattern contains "RS failure", "relative strength failure", "dead cat bounce",
   "dead cat", or "meme" → VETO
   These have 0% win rate in our live trade history. Non-negotiable skip.

3. SHORT signal confidence is in 90–92% range AND pattern does NOT explicitly mention
   "Stage 4-5 distribution", "Stage 5 distribution", or "Stage 5 collapse" → VETO
   This is the 90-92% SHORT confidence paradox — only 36.4% WR in our data.
   The paradox: if it's genuinely 93%+ quality, bump to APPROVE. If it only "feels" 91%, veto.

4. BTC 7-day % < -8% (bear market confirmed) AND signal is LONG AND confidence < 97% → VETO
   Alt longs in bear markets compound drawdowns. Our #1 loss pattern.

5. BTC 7-day % > +8% (bull market confirmed) AND signal is SHORT AND confidence < 97% → VETO
   Counter-trend shorts against strong BTC momentum have been our worst performers.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUALITY GRADES (when no auto-veto applies):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Grade the signal and return decision accordingly:

A+  → APPROVE  (last trade WIN at TP2 or better, strong proven pattern, regime aligned)
A   → APPROVE  (last trade WIN, solid pattern)
B   → APPROVE  (no history yet on this coin, or TP1 hit last time, or mixed history with good pattern)
C   → REDUCE_SIZE (weak pattern, or confidence in borderline zone, or conflicting signals — trade at 50% size)
D   → VETO     (multiple soft red flags stacking up even without a hard auto-veto)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STAR COINS (strong APPROVE bias when in their proven direction):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LONG star coins: AERO (100% WR / 8 trades), TIA (100% WR / 4 trades), JUP (75% WR / 4 trades)
SHORT star patterns: Stage 5 distribution collapse (100%), Stage 4-5 distribution (90%)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (JSON only — no prose, no explanation outside the JSON):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "decisions": [
    {
      "coin": "COIN",
      "direction": "LONG",
      "decision": "APPROVE",
      "grade": "A",
      "reason": "one concise sentence explaining why"
    }
  ],
  "regime_note": "one sentence on current market regime and overall bias",
  "approved_count": 0,
  "vetoed_count": 0,
  "reduced_count": 0
}

Valid decision values: "APPROVE", "VETO", "REDUCE_SIZE"
Valid grade values: "A+", "A", "B", "C", "D"
""")


def load_pattern_memory():
    """
    Load pattern_memory.json (written by whale_stream_debrief.py).
    Returns the full dict, or an empty structure if unavailable.
    """
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        coin_count = len(data.get("coin_lessons", {}))
        debrief_count = len(data.get("debriefs", []))
        print(f"   📚 Pattern memory loaded: {debrief_count} debriefs, {coin_count} coin(s) with lessons")
        return data
    except Exception as e:
        print(f"   ⚠ Could not load pattern_memory.json: {e}")
        return {}


def build_strategist_user_message(signals, history, positions, balance, drawdown_pct, btc_7d, memory=None):
    """Build the user-side prompt with all context the Strategist needs."""
    lines = []
    lines.append("=== PROPOSED SIGNALS FROM BOT ===")

    for s in signals:
        key   = (s["coin"], s["direction"])
        trades = history.get(key, [])
        wins   = sum(1 for t in trades if t["outcome"] == "WIN")
        losses = sum(1 for t in trades if t["outcome"] == "LOSS")
        wr     = wins / len(trades) * 100 if trades else None

        lines.append(f"\n--- {s['coin']} {s['direction']} ---")
        lines.append(f"  Confidence : {s['confidence']:.0f}%")
        lines.append(f"  Pattern    : {s['pattern']}")
        lines.append(f"  Entry zone : {s['entry']}")

        if not trades:
            lines.append(f"  History    : No resolved trades yet on this coin+direction")
        else:
            lines.append(f"  History    : {wins}W / {losses}L  ({wr:.0f}% WR, {len(trades)} sample(s))")
            lines.append(f"  Recent trades (newest first):")
            for i, t in enumerate(trades[:4]):   # show last 4
                tp_str  = f" @ {t['tp_hit']}" if t["tp_hit"] else ""
                pnl_str = f" {t['pnl']}" if t["pnl"] else ""
                lines.append(f"    [{i+1}] {t['outcome']}{tp_str}{pnl_str}  pattern='{t['pattern']}'")

    # ── Pattern Memory Injection ───────────────────────────────
    # Inject lessons from whale_stream_debrief.py for coins in this signal batch.
    # Helps Claude recognise repeat losers and double down on proven winners.
    if memory:
        coin_lessons    = memory.get("coin_lessons", {})
        avoid_patterns  = memory.get("avoid_patterns", [])
        prefer_patterns = memory.get("prefer_patterns", [])
        signal_coins    = {s["coin"] for s in signals}

        relevant_lessons = {
            coin: coin_lessons[coin]
            for coin in signal_coins
            if coin in coin_lessons
        }

        if relevant_lessons or avoid_patterns or prefer_patterns:
            lines.append("\n=== PATTERN MEMORY (lessons from recent resolved trades) ===")
            for coin, directions in relevant_lessons.items():
                for direction, lesson_list in directions.items():
                    # Only show if this coin is actually in a matching direction signal
                    if any(s["coin"] == coin and s["direction"] == direction for s in signals):
                        lines.append(f"\n  {coin} {direction} lessons (most recent first):")
                        for lesson in reversed(lesson_list[-4:]):  # show up to 4, newest last = most relevant
                            lines.append(f"    • {lesson}")
            if avoid_patterns:
                lines.append(f"\n  ⚠ Avoid these patterns (repeated losers): {', '.join(avoid_patterns[:6])}")
            if prefer_patterns:
                lines.append(f"\n  ✅ Prefer these patterns (proven winners): {', '.join(prefer_patterns[:6])}")

    lines.append("\n=== PORTFOLIO STATE ===")
    lines.append(f"  Balance    : ${balance:,.2f}  (drawdown {drawdown_pct:.1f}%)")
    lines.append(f"  Open positions: {len(positions)}")
    if positions:
        for sym, pos in positions.items():
            lines.append(f"    {sym}: {pos.get('side', '?')}  pnl=${pos.get('unrealisedPnl', 0):.2f}")

    lines.append("\n=== MARKET REGIME ===")
    if btc_7d is not None:
        regime = "Bear" if btc_7d < -8 else "Bull" if btc_7d > 8 else "Neutral"
        lines.append(f"  BTC 7d change: {btc_7d:+.2f}%  → {regime} market regime")
    else:
        lines.append("  BTC 7d change: unavailable — apply neutral regime assumptions")

    lines.append(f"\n=== YOUR TASK ===")
    lines.append("Review each proposed signal above. Apply AUTOMATIC VETO rules first.")
    lines.append("For remaining signals, apply QUALITY GRADES and output your decision.")
    lines.append("Output JSON only.")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# SECTION 6 — CLAUDE API CALL
# ═══════════════════════════════════════════════════════════════

def call_strategist_claude(user_message):
    """Call Claude with the Strategist prompt. Returns raw response text."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print(f"   🧠 Model: {STRATEGIST_MODEL}")
    message = client.messages.create(
        model=STRATEGIST_MODEL,
        max_tokens=2048,
        system=[{"type": "text", "text": STRATEGIST_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text


def parse_strategist_response(response_text):
    """
    Extract JSON from Claude's response.
    Returns parsed dict or None on failure.
    """
    import re

    # Try direct JSON parse first
    try:
        return json.loads(response_text.strip())
    except Exception:
        pass

    # Try extracting from markdown code fence
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # Try finding first complete JSON object via brace depth
    start = response_text.find('{')
    if start != -1:
        depth = 0
        in_str = False
        esc    = False
        for i, ch in enumerate(response_text[start:], start):
            if esc:       esc = False; continue
            if ch == '\\' and in_str: esc = True; continue
            if ch == '"': in_str = not in_str; continue
            if in_str:    continue
            if ch == '{': depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(response_text[start:i+1])
                    except Exception:
                        break

    return None


# ═══════════════════════════════════════════════════════════════
# SECTION 7 — WRITE DECISIONS & TELEGRAM
# ═══════════════════════════════════════════════════════════════

def write_decisions(decisions_data):
    """Write the final decisions to strategist_decisions.json."""
    try:
        with open(DECISIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(decisions_data, f, indent=2)
        print(f"   ✓ Decisions written → strategist_decisions.json")
    except Exception as e:
        print(f"   ✗ Failed to write decisions: {e}")


def send_telegram_summary(decisions_data, signals):
    """Send a Telegram summary of what the Strategist approved / vetoed."""
    run_at        = decisions_data.get("run_at", "?")
    approved      = decisions_data.get("approved_count", 0)
    vetoed        = decisions_data.get("vetoed_count", 0)
    reduced       = decisions_data.get("reduced_count", 0)
    regime_note   = decisions_data.get("regime_note", "")
    market_bias   = decisions_data.get("market_bias", "NEUTRAL")
    decisions     = decisions_data.get("decisions", [])

    bias_emoji = "🐻" if market_bias == "BEARISH" else ("🐂" if market_bias == "BULLISH" else "😐")
    lines = [
        f"🧠 <b>STRATEGIST REVIEW</b> — {run_at}",
        f"  {bias_emoji} Market: <b>{market_bias}</b>",
        f"  ✅ Approved: {approved}  ⛔ Vetoed: {vetoed}  ⚠️ Reduced: {reduced}",
    ]

    if regime_note:
        lines.append(f"  📊 Regime: {regime_note}")

    lines.append("")
    for d in decisions:
        coin      = d.get("coin", "?")
        direction = d.get("direction", "?")
        decision  = d.get("decision", "?")
        grade     = d.get("grade", "?")
        reason    = d.get("reason", "")
        icon = "✅" if decision == "APPROVE" else ("⚠️" if decision == "REDUCE_SIZE" else "⛔")
        lines.append(f"  {icon} <b>{coin} {direction}</b> [{grade}]  {reason}")

    send_telegram("\n".join(lines))


# ═══════════════════════════════════════════════════════════════
# SECTION 8 — MAIN
# ═══════════════════════════════════════════════════════════════

def _get_cycle_id():
    """Return a stable cycle ID for the current 4h window, e.g. '2026-06-28_0800'."""
    now = bkk_now()
    cycle_hour = (now.hour // 4) * 4
    return f"{now.strftime('%Y-%m-%d')}_{cycle_hour:02d}00"


def main():
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║   🧠  WHALE-STREAM STRATEGIST v1.3                  ║")
    print("║   Signal Quality Council — APPROVE / VETO / REDUCE  ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    bkk_str = bkk_now().strftime("%Y-%m-%d %H:%M BKK")
    print_mission_banner()
    log(f"=== Strategist run started {bkk_str} ===")

    # ── Detect re-check mode (--recheck flag bypasses cycle guard) ──
    import sys as _sys
    _is_recheck = "--recheck" in _sys.argv

    # ── Cycle guard: skip if already done this 4h slot ──────────────
    import json as _jcg, datetime as _dcg
    _cg_path  = os.path.join(SCRIPT_DIR, "daily_status.json")
    _cg_hour  = _dcg.datetime.now().hour
    _cg_cycle = str((_cg_hour // 4) * 4).zfill(2)
    _cg_key   = f"strategist_{_cg_cycle}"
    if not _is_recheck:   # re-checks always bypass the guard
        try:
            with open(_cg_path, encoding="utf-8") as _cgf:
                _cg_data = _jcg.load(_cgf)
            if _cg_data.get("date") == _dcg.date.today().isoformat() and _cg_data.get(_cg_key):
                print(f"[CYCLE GUARD] {_cg_key} already completed today — skipping duplicate run.")
                return
        except Exception:
            pass  # status missing → proceed normally
    # ── End cycle guard ─────────────────────────────────────────────

    # ════════════════════════════════════════════════════════════════
    # RE-CHECK MODE — rules-only intra-cycle evaluation (no Claude)
    # ════════════════════════════════════════════════════════════════
    if _is_recheck:
        print("\n🔄 STRATEGIST RE-CHECK MODE — rules-based (no Claude API)")
        log("Strategist re-check started")

        # Load previous decisions for this cycle
        _prev_decisions = {}
        _prev = {}
        try:
            with open(DECISIONS_FILE, "r", encoding="utf-8") as _pf:
                _prev = json.load(_pf)
            _prev_cycle = _prev.get("cycle_id", "")
            for _d in _prev.get("decisions", []):
                _key = (_d.get("coin", "").upper(), _d.get("direction", "").upper())
                _prev_decisions[_key] = {
                    "decision": _d.get("decision", "APPROVE"),
                    "reason":   _d.get("reason", ""),
                    "grade":    _d.get("grade", "B"),
                }
            print(f"   ✓ Loaded {len(_prev_decisions)} previous decision(s)  [cycle {_prev_cycle}]")
        except Exception as _pe:
            print(f"   ⚠ Could not load previous decisions: {_pe} — nothing to re-check")
            _mark_done("strategist", details={"approved": [], "vetoed": [], "recheck": True, "error": "no_prev_decisions"})
            return

        # Connect to Google Sheets for current signals
        try:
            sheet     = connect_sheet()
            all_rows  = sheet.get_all_values()
            data_rows = all_rows[1:] if len(all_rows) > 1 else []
        except Exception as _se:
            print(f"   ✗ Sheets failed: {_se} — skipping re-check")
            _mark_done("strategist", details={"approved": [], "vetoed": [], "recheck": True, "error": "sheets_failed"})
            return

        signals = load_latest_signals(data_rows)
        if not signals:
            print("   ℹ No current signals — nothing to re-check")
            _mark_done("strategist", details={"approved": [], "vetoed": [], "recheck": True})
            return

        # Fetch BTC market bias (fast, no Claude)
        market_bias, _btc_px, _btc_sma, _btc_pct = get_btc_market_bias()
        print(f"   📈 BTC regime: {market_bias}")

        # Fetch current prices for entry-staleness check
        _current_prices = {}
        try:
            _pr = requests.get(
                "https://api.bybit.com/v5/market/tickers",
                params={"category": "linear"}, timeout=10
            )
            for _t in _pr.json().get("result", {}).get("list", []):
                _sym = _t.get("symbol", "")
                if _sym.endswith("USDT"):
                    try:
                        _current_prices[_sym[:-4]] = float(_t.get("lastPrice", 0) or 0)
                    except (ValueError, TypeError):
                        pass
            print(f"   ✓ Prices fetched for {len(_current_prices)} coins")
        except Exception as _pre:
            print(f"   ⚠ Price fetch failed: {_pre} — staleness check skipped")

        # Load pattern memory
        memory = load_pattern_memory()

        # ── Apply 3 rules per signal ─────────────────────────────────
        _new_decisions = []
        _changes       = []

        for _sig in signals:
            _coin = _sig.get("coin", "?").upper()
            _raw_dir = _sig.get("direction", "").upper()
            _direction = "LONG" if "LONG" in _raw_dir else "SHORT"
            _key = (_coin, _direction)
            _prev_dec    = _prev_decisions.get(_key, {}).get("decision", "APPROVE")
            _prev_reason = _prev_decisions.get(_key, {}).get("reason", "carry-forward")
            _prev_grade  = _prev_decisions.get(_key, {}).get("grade", "B")
            _new_dec     = _prev_dec
            _new_reason  = _prev_reason

            # Rule 1 — BTC regime flip
            if market_bias == "BEARISH" and _direction == "LONG" and _new_dec != "VETO":
                _new_dec    = "VETO"
                _new_reason = "Re-check R1: BTC regime BEARISH — vetoing LONG"
            elif market_bias == "BULLISH" and _direction == "SHORT" and _new_dec != "VETO":
                _new_dec    = "VETO"
                _new_reason = "Re-check R1: BTC regime BULLISH — vetoing SHORT"

            # Rule 2 — Entry-zone staleness (>5% past entry high/low)
            if _new_dec != "VETO":
                _px = _current_prices.get(_coin, 0)
                _entry_str = str(_sig.get("entry", "")).replace(",", "").replace("$", "").strip()
                if _px and _entry_str:
                    try:
                        if " - " in _entry_str:
                            _parts = [float(x) for x in _entry_str.split(" - ") if x.strip()]
                        elif "-" in _entry_str:
                            _parts = [float(x) for x in _entry_str.split("-") if x.strip()]
                        else:
                            _v = float(_entry_str)
                            _parts = [_v * 0.98, _v * 1.02]
                        _el, _eh = min(_parts), max(_parts)
                        if _direction == "LONG" and _px > _eh * 1.05:
                            _new_dec    = "VETO"
                            _new_reason = (f"Re-check R2: entry zone missed — "
                                           f"price {_px:.4g} > entry high {_eh:.4g} +5%")
                        elif _direction == "SHORT" and _px < _el * 0.95:
                            _new_dec    = "VETO"
                            _new_reason = (f"Re-check R2: entry zone missed — "
                                           f"price {_px:.4g} < entry low {_el:.4g} -5%")
                    except (ValueError, TypeError):
                        pass

            # Rule 3 — Pattern memory: ≥3 consecutive losses
            if _new_dec != "VETO":
                _consec = (memory.get("coin_lessons", {})
                               .get(_coin, {})
                               .get("consecutive_losses", 0))
                if _consec >= 3:
                    _new_dec    = "VETO"
                    _new_reason = (f"Re-check R3: pattern memory — "
                                   f"{_coin} has {_consec} consecutive losses")

            # Track changes
            if _new_dec != _prev_dec:
                _changes.append({
                    "coin":      _coin,
                    "direction": _direction,
                    "prev":      _prev_dec,
                    "new":       _new_dec,
                    "reason":    _new_reason,
                })
                _icon = "APPROVE→VETO" if _new_dec == "VETO" else "VETO→APPROVE"
                print(f"   🔄 {_icon}: {_coin} {_direction} — {_new_reason}")

            _new_decisions.append({
                "coin":      _coin,
                "direction": _direction,
                "decision":  _new_dec,
                "grade":     _prev_grade,
                "reason":    _new_reason,
            })

        if not _changes:
            print(f"   ✅ No changes — all {len(_new_decisions)} decision(s) carry forward")
        else:
            print(f"\n   ⚡ {len(_changes)} change(s) — writing updated decisions file")

        # Write updated decisions
        _recheck_num = _prev.get("recheck_count", 0) + 1
        _rc_approved = [d["coin"] for d in _new_decisions if d["decision"] == "APPROVE"]
        _rc_vetoed   = [d["coin"] for d in _new_decisions if d["decision"] == "VETO"]

        _updated = dict(_prev)
        _updated["decisions"]       = _new_decisions
        _updated["recheck_at"]      = bkk_str
        _updated["recheck_count"]   = _recheck_num
        _updated["recheck_changes"] = _changes
        _updated["approved_count"]  = len(_rc_approved)
        _updated["vetoed_count"]    = len(_rc_vetoed)
        write_decisions(_updated)

        # Telegram only when decisions changed
        if _changes:
            _lines = []
            for _c in _changes:
                _arr = "✅→⛔" if _c["new"] == "VETO" else "⛔→✅"
                _lines.append(f"  {_arr} {_c['coin']} {_c['direction']}: {_c['reason']}")
            send_telegram(
                f"🔄 <b>STRATEGIST RE-CHECK #{_recheck_num}</b> — {bkk_str}\n"
                f"{len(_changes)} change(s):\n" + "\n".join(_lines) +
                f"\n\n📊 Now: {len(_rc_approved)} approved, {len(_rc_vetoed)} vetoed"
            )

        _mark_done("strategist", details={"approved": _rc_approved, "vetoed": _rc_vetoed, "recheck": True})
        log(f"Re-check #{_recheck_num} complete — {len(_changes)} change(s)")
        print(f"\n✅ Re-check #{_recheck_num} complete.")
        return
    # ── End re-check mode ────────────────────────────────────────────

    # ── Note if circuit breaker is active (don't block the run — just log it) ──
    if os.path.exists(PAUSED_FILE):
        log("⚠ Circuit breaker ACTIVE — decisions will still be written but Trader is paused")
        print("   ⚠ Note: paused.flag exists — Trader is paused but Strategist will still run")

    # ── Load portfolio state ─────────────────────────────────────
    print("📊 Loading portfolio state...")
    positions, balance, drawdown_pct = load_portfolio_state()
    print(f"   Balance: ${balance:,.2f}  Drawdown: {drawdown_pct:.1f}%")
    print(f"   Open positions: {len(positions)}")

    # ── Connect to Google Sheets ─────────────────────────────────
    print("\n📋 Loading signals from Google Sheets...")
    try:
        sheet    = connect_sheet()
        all_rows = sheet.get_all_values()
        data_rows = all_rows[1:] if len(all_rows) > 1 else []
    except Exception as e:
        log(f"✗ Google Sheets connection failed: {e}")
        print(f"   ✗ Failed to connect: {e}")
        _mark_done("strategist", details={"approved": [], "vetoed": [], "error": "sheets_failed"})
        return

    # ── Find latest OPEN signals ─────────────────────────────────
    signals = load_latest_signals(data_rows)
    print(f"   ✓ Found {len(signals)} OPEN signal(s) from last bot run (within {SIGNAL_WINDOW_HOURS}h)")

    if not signals:
        log("No signals to review — no OPEN signals found in last 26h")
        print("\n   No signals to review. Bot may not have run yet or no signals generated.")
        # Write empty decisions so trader knows strategist ran
        empty = {
            "run_at":          bkk_str,
            "cycle_id":        _get_cycle_id(),
            "recheck_count":   0,
            "recheck_changes": [],
            "decisions":       [],
            "regime_note":     "No signals to review",
            "approved_count":  0,
            "vetoed_count":    0,
            "reduced_count":   0,
        }
        write_decisions(empty)
        _mark_done("strategist", details={
            "approved": [],
            "vetoed":   [],
        })
        return

    # ── Build per-coin trade history ─────────────────────────────
    print("\n📚 Analysing trade history per coin...")
    history = build_coin_history(data_rows, signals)
    for (coin, direction), trades in history.items():
        wins   = sum(1 for t in trades if t["outcome"] == "WIN")
        losses = sum(1 for t in trades if t["outcome"] == "LOSS")
        print(f"   {coin} {direction}: {wins}W / {losses}L ({len(trades)} samples)")

    # ── Get BTC 7-day % for regime check ────────────────────────
    print("\n📈 Fetching BTC 7-day change...")
    btc_7d = get_btc_7d_pct()
    if btc_7d is not None:
        regime = "Bear" if btc_7d < -8 else "Bull" if btc_7d > 8 else "Neutral"
        print(f"   BTC 7d: {btc_7d:+.2f}%  ({regime} regime)")
    else:
        print("   BTC 7d: unavailable (CoinGecko offline?)")

    # ── BTC Market Regime Filter (code-level pre-veto) ───────────────────
    # Trade WITH the trend: BEARISH → SHORT only, BULLISH → LONG only, NEUTRAL → both.
    print("\n📊 BTC Market Regime Filter...")
    market_bias, btc_price, btc_sma, btc_pct_sma = get_btc_market_bias()

    if btc_price is not None:
        bias_emoji = "🐻" if market_bias == "BEARISH" else ("🐂" if market_bias == "BULLISH" else "😐")
        print(f"   BTC price: ${btc_price:,.0f}  |  20-period 4h SMA: ${btc_sma:,.0f}  |  {btc_pct_sma:+.1f}% from SMA")
        print(f"   {bias_emoji} MARKET BIAS: {market_bias}")
        log(f"Market bias: {market_bias}  BTC ${btc_price:,.0f}  SMA ${btc_sma:,.0f}  ({btc_pct_sma:+.1f}%)")
    else:
        print("   ⚠ Could not determine BTC bias — NEUTRAL (no pre-filter applied)")
        log("Market bias: NEUTRAL (Bybit kline unavailable)")

    # Pre-veto signals fighting the trend
    original_signal_count = len(signals)
    regime_vetoed = []

    if market_bias == "BEARISH":
        fighting_trend = [s for s in signals if s["direction"] == "LONG"]
        signals        = [s for s in signals if s["direction"] != "LONG"]
        for s in fighting_trend:
            reason = f"REGIME VETO — market BEARISH (BTC {(btc_pct_sma or 0):+.1f}% below 4h SMA) — no LONGs"
            regime_vetoed.append({"coin": s["coin"], "direction": "LONG",
                                   "decision": "VETO", "grade": "D", "reason": reason})
            log(f"Regime pre-veto: {s['coin']} LONG ({reason})")
            print(f"   🐻 VETO: {s['coin']} LONG — market BEARISH")

    elif market_bias == "BULLISH":
        fighting_trend = [s for s in signals if s["direction"] == "SHORT"]
        signals        = [s for s in signals if s["direction"] != "SHORT"]
        for s in fighting_trend:
            reason = f"REGIME VETO — market BULLISH (BTC {(btc_pct_sma or 0):+.1f}% above 4h SMA) — no SHORTs"
            regime_vetoed.append({"coin": s["coin"], "direction": "SHORT",
                                   "decision": "VETO", "grade": "D", "reason": reason})
            log(f"Regime pre-veto: {s['coin']} SHORT ({reason})")
            print(f"   🐂 VETO: {s['coin']} SHORT — market BULLISH")

    if regime_vetoed:
        dropped_count = original_signal_count - len(signals)
        print(f"   → Pre-filtered {dropped_count} signal(s) fighting the trend. {len(signals)} remain for Claude review.")

    # If regime filter wiped everything, short-circuit without calling Claude
    if not signals and original_signal_count > 0:
        bias_lbl   = "BEARISH — all LONGs pre-vetoed" if market_bias == "BEARISH" else "BULLISH — all SHORTs pre-vetoed"
        bias_emoji2 = "🐻" if market_bias == "BEARISH" else "🐂"
        log(f"No signals remain after regime filter — {bias_lbl}")
        print(f"\n   No signals remain after regime filter ({bias_lbl}).")
        empty = {
            "run_at":          bkk_str,
            "cycle_id":        _get_cycle_id(),
            "recheck_count":   0,
            "recheck_changes": [],
            "decisions":       regime_vetoed,
            "regime_note":     f"Market {bias_lbl}",
            "approved_count":  0,
            "vetoed_count":    len(regime_vetoed),
            "reduced_count":   0,
            "market_bias":     market_bias,
        }
        write_decisions(empty)
        send_telegram(
            f"🧠 <b>STRATEGIST</b> — {bkk_str}\n"
            f"{bias_emoji2} <b>REGIME FILTER: {market_bias}</b>\n"
            f"  BTC is {abs(btc_pct_sma or 0):.1f}% {'below' if market_bias == 'BEARISH' else 'above'} 20-period 4h SMA\n"
            f"  {len(regime_vetoed)} signal(s) vetoed — trading only WITH the trend.\n"
            f"  ⛔ Vetoed: {', '.join(v['coin'] + ' ' + v['direction'] for v in regime_vetoed)}"
        )
        _mark_done("strategist", details={
            "approved": [],
            "vetoed":   [v["coin"] for v in regime_vetoed],
        })
        return

    # ── Load Pattern Memory ──────────────────────────────────────
    print("\n📚 Loading pattern memory...")
    memory = load_pattern_memory()

    # ── Build Claude prompt ──────────────────────────────────────
    print("\n🧠 Calling Strategist Claude...")
    user_msg = build_strategist_user_message(
        signals, history, positions, balance, drawdown_pct, btc_7d, memory=memory
    )

    # ── Call Claude ──────────────────────────────────────────────
    try:
        raw_response = call_strategist_claude(user_msg)
        print(f"   ✓ Response received ({len(raw_response)} chars)")
    except Exception as e:
        log(f"✗ Claude API call failed: {e}")
        print(f"   ✗ Claude call failed: {e}")
        # SAFETY: VETO all signals when Claude is unavailable — do NOT approve blindly
        _vetoed_coins = [s["coin"] for s in signals]
        fallback = {
            "run_at":         bkk_str,
            "cycle_id":       _get_cycle_id(),
            "recheck_count":  0,
            "recheck_changes":[],
            "decisions":      [{"coin": s["coin"], "direction": s["direction"],
                                "decision": "VETO", "grade": "F",
                                "reason": "Strategist Claude API unavailable — VETO for safety"} for s in signals],
            "regime_note":    "⛔ Claude API failed — all signals VETOED (safety fallback)",
            "approved_count": 0,
            "vetoed_count":   len(signals),
            "reduced_count":  0,
        }
        write_decisions(fallback)
        send_telegram(
            f"⚠️ <b>STRATEGIST ALERT</b> — Claude API call FAILED\n"
            f"All {len(signals)} signal(s) VETOED for safety.\n"
            f"Error: {str(e)[:100]}\n"
            f"Next cycle will retry. Check Anthropic status if this persists."
        )
        _mark_done("strategist", details={"approved": [], "vetoed": _vetoed_coins, "error": "claude_failed"})
        return

    # ── Parse decisions ──────────────────────────────────────────
    parsed = parse_strategist_response(raw_response)
    if not parsed:
        log(f"✗ Failed to parse Strategist JSON response. Raw: {raw_response[:300]}")
        print(f"   ✗ Could not parse response — see log for raw output")
        print(f"   Raw tail: {raw_response[-200:]}")
        # SAFETY: VETO all on parse failure — same principle as API failure
        _vetoed_coins = [s["coin"] for s in signals]
        _parse_fallback = {
            "run_at":          bkk_str,
            "cycle_id":        _get_cycle_id(),
            "recheck_count":   0,
            "recheck_changes": [],
            "decisions":       [{"coin": s["coin"], "direction": s["direction"],
                                 "decision": "VETO", "grade": "F",
                                 "reason": "Strategist response parse error — VETO for safety"} for s in signals],
            "regime_note":     "⛔ Parse error — all signals VETOED (safety fallback)",
            "approved_count":  0,
            "vetoed_count":    len(signals),
            "reduced_count":   0,
        }
        write_decisions(_parse_fallback)
        send_telegram(
            f"⚠️ <b>STRATEGIST ALERT</b> — Response parse FAILED\n"
            f"All {len(signals)} signal(s) VETOED for safety.\n"
            f"Check strategist_log.txt for raw response."
        )
        _mark_done("strategist", details={"approved": [], "vetoed": _vetoed_coins, "error": "parse_failed"})
        return

    # ── Merge regime pre-vetoes into decisions ────────────────────
    # regime_vetoed contains any signals dropped before Claude saw them.
    # Append them so the full picture is visible in the decisions file + Telegram.
    all_decisions = regime_vetoed + parsed.get("decisions", [])
    parsed["decisions"] = all_decisions

    # ── Enrich and tally ─────────────────────────────────────────
    approved = sum(1 for d in parsed.get("decisions", []) if d.get("decision") == "APPROVE")
    vetoed   = sum(1 for d in parsed.get("decisions", []) if d.get("decision") == "VETO")
    reduced  = sum(1 for d in parsed.get("decisions", []) if d.get("decision") == "REDUCE_SIZE")

    parsed["run_at"]         = bkk_str
    parsed["approved_count"] = approved
    parsed["vetoed_count"]   = vetoed
    parsed["reduced_count"]  = reduced
    parsed["signal_count"]   = original_signal_count
    parsed["btc_7d_pct"]     = btc_7d
    parsed["market_bias"]    = market_bias

    # ── Print decisions ──────────────────────────────────────────
    print(f"\n   Results: {approved} APPROVED  {vetoed} VETOED  {reduced} REDUCE_SIZE")
    print()
    for d in parsed.get("decisions", []):
        icon = "✅" if d.get("decision") == "APPROVE" else ("⚠️" if d.get("decision") == "REDUCE_SIZE" else "⛔")
        print(f"   {icon}  {d.get('coin','?')} {d.get('direction','?')} [{d.get('grade','?')}]  {d.get('reason','')}")

    regime_note = parsed.get("regime_note", "")
    if regime_note:
        print(f"\n   Regime: {regime_note}")

    # ── Write decisions to file ──────────────────────────────────
    parsed["cycle_id"]       = _get_cycle_id()
    parsed["recheck_count"]  = 0
    parsed["recheck_changes"]= []
    print()
    write_decisions(parsed)

    # ── Log summary ──────────────────────────────────────────────
    log(f"Decisions: {approved} APPROVED, {vetoed} VETOED, {reduced} REDUCE_SIZE — "
        f"signals reviewed: {len(signals)}")

    # ── Send Telegram ─────────────────────────────────────────────
    send_telegram_summary(parsed, signals)

    _approved_coins = [d.get("coin","?") for d in parsed.get("decisions",[]) if d.get("decision") == "APPROVE"]
    _vetoed_coins   = [d.get("coin","?") for d in parsed.get("decisions",[]) if d.get("decision") == "VETO"]
    _mark_done("strategist", details={"approved": _approved_coins, "vetoed": _vetoed_coins})
    print()
    print("✅ Strategist complete.")
    print()


if __name__ == "__main__":
    main()
