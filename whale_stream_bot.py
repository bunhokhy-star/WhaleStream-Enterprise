"""
╔══════════════════════════════════════════════════════════════╗
║        WHALE-STREAM v47.46   —  FULL AUTOMATION BOT          ║
║                                                              ║
║  What this script does (automatically, every run):          ║
║  1. Fetches top 200 coins from CoinGecko (free, no key)     ║
║  2. Sends all data to Claude with your WHALE-STREAM prompt  ║
║  3. Posts the analysis result to your Telegram group         ║
║  4. Logs top 3 LONG + top 3 SHORT signals to Google Sheets  ║
║                                                              ║
║  HOW TO RUN:                                                 ║
║    python whale_stream_bot.py                                ║
║                                                              ║
║  HOW TO SCHEDULE (run every 4 hours automatically):         ║
║    Windows Task Scheduler  →  see SETUP_GUIDE.md            ║
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

# ─────────────────────────────────────────────────────────────
# AUTO-INSTALL: installs any missing libraries automatically
# ─────────────────────────────────────────────────────────────
import subprocess
import sys
import io
import os
import json
import re

# Force UTF-8 output — prevents UnicodeEncodeError on Windows CP1252 consoles / Task Scheduler.
# reconfigure() can silently fail in Python 3.14 when stdout is redirected to a file;
# replacing the TextIOWrapper directly is the guaranteed fix.
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


REQUIRED_PACKAGES = {
    "anthropic":            "anthropic",
    "requests":             "requests",
    "gspread":              "gspread",
    "google.oauth2":        "google-auth",
}

def get_pip_python():
    """Find a Python executable that has pip available."""
    candidates = [
        r"C:\Users\MAX\AppData\Local\Python\bin\python.exe",
        "py",
        sys.executable,
    ]
    for exe in candidates:
        try:
            result = subprocess.run(
                [exe, "-m", "pip", "--version"],
                capture_output=True, timeout=10
            )
            if result.returncode == 0:
                return exe
        except Exception:
            continue
    return sys.executable  # fallback

PIP_PYTHON = get_pip_python()

print("🔍 Checking required libraries...")
for module, package in REQUIRED_PACKAGES.items():
    try:
        __import__(module)
        print(f"   ✓ {package}")
    except ImportError:
        print(f"   ⬇ Installing {package}...")
        _pip_cmd = [PIP_PYTHON, "-m", "pip", "install", package, "--quiet"]
        if PIP_PYTHON != sys.executable:
            _pip_cmd += ["--target", str(__import__("pathlib").Path(sys.executable).parent.parent / "Lib" / "site-packages")]
        subprocess.check_call(_pip_cmd)
        print(f"   ✓ {package} installed")

print("   All libraries ready.\n")

# ─────────────────────────────────────────────────────────────
# SECTION 1: CONFIGURATION  ← Fill in your keys here
# ─────────────────────────────────────────────────────────────

# Secrets loaded from local_config.py (gitignored). Fallback: env vars.
try:
    from local_config import ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    # TELEGRAM_SIGNAL_CHAT_ID is optional — if not set in local_config, signals go to ops channel
    try:
        from local_config import TELEGRAM_SIGNAL_CHAT_ID
    except ImportError:
        TELEGRAM_SIGNAL_CHAT_ID = TELEGRAM_CHAT_ID
except ImportError:
    import os as _os
    ANTHROPIC_API_KEY        = _os.getenv("ANTHROPIC_API_KEY", "")
    TELEGRAM_BOT_TOKEN       = _os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID         = _os.getenv("TELEGRAM_CHAT_ID", "")
    TELEGRAM_SIGNAL_CHAT_ID  = _os.getenv("TELEGRAM_SIGNAL_CHAT_ID", TELEGRAM_CHAT_ID)

# ── SHORT coin blocklist (code-level enforcement — mirrors prompt blocklist) ──
# These coins have 0% SHORT WR in historical data and are permanently banned.
SHORT_COIN_BLOCKLIST = {
    "ENA",   # 0W/5L — 0% WR, avg -60.6%
    "XLM",   # 0W/2L — 0% WR, avg -38.0%
    "BCH",   # 0W/2L — 0% WR, avg -44.0%
    "CHZ",   # 3 consec. losses (Jun 20-21) — found floor, shorts stopped  ← added v47.41
    "VVV",   # 0W/3L — 0% WR, avg -57.9%  ← updated count v46.53
    "ZRO",   # 0W/1L — 0% WR, avg -40.9%
    "WLD",   # 0W/2L — 0% WR, avg -49.7%  ← added v46.5
    "INJ",   # 0W/2L — 0% WR, avg -59.8%  ← added v46.5
    "AVAX",  # 0W/1L — 0% WR, avg -49.1%  ← added v46.5
}
# ── Auto-blocklist SHORT coins from debrief data (v47.29) ──────────────────────
# coin_blocklist_auto.json now includes blocked_shorts (≥3 SHORT losses + 0 wins).
# Merged at startup — no manual edit needed. Runs AFTER SHORT_COIN_BLOCKLIST defined.
try:
    _auto_bl_short_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coin_blocklist_auto.json")
    if os.path.exists(_auto_bl_short_path):
        with open(_auto_bl_short_path, "r", encoding="utf-8") as _abls_f:
            _auto_bl_short_data = json.load(_abls_f)
        _auto_bl_short_coins = set(c.upper() for c in _auto_bl_short_data.get("blocked_shorts", []))
        SHORT_COIN_BLOCKLIST = SHORT_COIN_BLOCKLIST | _auto_bl_short_coins
        if _auto_bl_short_coins:
            print(f"   🚫 AUTO-BLOCKLIST SHORT: {', '.join(sorted(_auto_bl_short_coins))} added from coin_blocklist_auto.json")
except Exception:
    pass  # fail silently — hardcoded blocklist still applies

# ── LONG coin blocklist (code-level enforcement) ──────────────────────────────
# Populated when a coin shows 0% LONG WR over 2+ LONG trades with clearly negative avg P&L.
# Run analyze_shorts.py → check "LONG WIN RATE BY COIN" → add POOR-rated coins here.
LONG_COIN_BLOCKLIST = {
    "ZRO",   # 0W/2L — 0% WR, avg -59.5%  ← added v46.37 (2026-06-23)
    "HYPE",  # 0W/2L — 0% WR, avg -54.3%  ← added v46.37 (2026-06-23)
    "COMP",  # 0W/3L — 0% WR, avg -59.8%  ← added v46.62 (2026-06-26)
    "QNT",   # 0W/3L — 0% WR, avg -65.6%  ← added v46.62 (2026-06-26)
    "WIF",   # 1W/4L — 25% WR, avg -48.7% ← added v46.62 (2026-06-26)
    "WLD",   # 0W/2L — 0% WR, counter-trend coin ← added v47.5 (2026-06-28)
    "XLM",   # 0W/2L — 0% LONG WR (also SHORT-blocked) ← added v47.41
    "ENA",    # 0W/1L — SHORT already blocked; LONG also losing ← added v47.43
    "PENDLE", # 1W/3L — 25% WR (206-trade analysis Jun 2026) ← added v47.46
}
# ── Auto-blocklist from debrief data (v47.28) ──────────────────────────────────
# coin_blocklist_auto.json written by debrief save_memory() whenever a coin
# reaches ≥3 LONG losses + 0 LONG wins. Merged at startup — no manual edit needed.
try:
    _auto_bl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coin_blocklist_auto.json")
    if os.path.exists(_auto_bl_path):
        with open(_auto_bl_path, "r", encoding="utf-8") as _abl_f:
            _auto_bl_data = json.load(_abl_f)
        _auto_bl_coins = set(c.upper() for c in _auto_bl_data.get("blocked_longs", []))
        LONG_COIN_BLOCKLIST = LONG_COIN_BLOCKLIST | _auto_bl_coins
        if _auto_bl_coins:
            print(f"   🚫 AUTO-BLOCKLIST: {', '.join(sorted(_auto_bl_coins))} added from coin_blocklist_auto.json")
except Exception:
    pass  # fail silently — hardcoded blocklist still applies

# ── Dynamic blocklist from weekly scorecard YES replies (v47.44) ───────────────
# telegram_commands.py writes dynamic_blocklist.json when user replies YES to
# a weekly recommendation. Merged here at startup — no code edits needed.
try:
    _dyn_bl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dynamic_blocklist.json")
    if os.path.exists(_dyn_bl_path):
        with open(_dyn_bl_path, "r", encoding="utf-8") as _dbl_f:
            _dyn_bl_data = json.load(_dbl_f)
        _dyn_long  = set(c.upper() for c in _dyn_bl_data.get("LONG", []))
        _dyn_short = set(c.upper() for c in _dyn_bl_data.get("SHORT", []))
        if _dyn_long:
            LONG_COIN_BLOCKLIST  = LONG_COIN_BLOCKLIST  | _dyn_long
            print(f"   🚫 DYNAMIC BLOCK (LONG):  {', '.join(sorted(_dyn_long))} — user-confirmed via weekly scorecard")
        if _dyn_short:
            SHORT_COIN_BLOCKLIST = SHORT_COIN_BLOCKLIST | _dyn_short
            print(f"   🚫 DYNAMIC BLOCK (SHORT): {', '.join(sorted(_dyn_short))} — user-confirmed via weekly scorecard")
except Exception:
    pass  # fail silently — hardcoded blocklists still apply

# ── Probation watchlist (v47.33) ──────────────────────────────────────────────
# Coins that recently expired from the auto-blocklist and are on 3-trade probation.
# Loaded once at startup — inject into graveyard prompt so Claude knows not to
# confidently generate signals for these coins without extra caution.
BOT_PROBATION_LONGS:  set = set()
BOT_PROBATION_SHORTS: set = set()
try:
    _wl_path_bot = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blocklist_watchlist.json")
    if os.path.exists(_wl_path_bot):
        with open(_wl_path_bot, "r", encoding="utf-8") as _wlf_bot:
            _wl_data_bot = json.load(_wlf_bot)
        for _wk_bot, _we_bot in _wl_data_bot.get("watchlist", {}).items():
            _wc_bot  = _we_bot.get("coin", "").upper()
            _wdr_bot = _we_bot.get("direction", "").upper()
            if _wc_bot and _wdr_bot == "LONG":
                BOT_PROBATION_LONGS.add(_wc_bot)
            elif _wc_bot and _wdr_bot == "SHORT":
                BOT_PROBATION_SHORTS.add(_wc_bot)
        if BOT_PROBATION_LONGS or BOT_PROBATION_SHORTS:
            print(f"   🔶 PROBATION: LONG={sorted(BOT_PROBATION_LONGS)} SHORT={sorted(BOT_PROBATION_SHORTS)}")
except Exception:
    pass  # fail silently — non-critical

# ── Soft-avoid from coin P&L (v47.35) ────────────────────────────────────────
# Coins with avg P&L < -0.5% over ≥10 trades in pattern_memory coin_stats.
# Injected into graveyard prompt — Claude sees these as historically cash-negative
# and applies a higher confidence bar before including them in a signal batch.
BOT_SOFT_AVOID: set = set()
try:
    _pm_path_bot = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pattern_memory.json")
    if os.path.exists(_pm_path_bot):
        with open(_pm_path_bot, "r", encoding="utf-8") as _pmf_bot:
            _pm_data_bot = json.load(_pmf_bot)
        for _sa_coin, _sa_v in _pm_data_bot.get("coin_stats", {}).items():
            _sa_cnt = _sa_v.get("pnl_count", 0)
            _sa_tot = _sa_v.get("pnl_total", 0.0)
            if _sa_cnt >= 10 and (_sa_tot / _sa_cnt) < -0.5:
                BOT_SOFT_AVOID.add(_sa_coin.upper())
    if BOT_SOFT_AVOID:
        print(f"   ⚠ SOFT-AVOID (avg P&L <-0.5%, ≥10 trades): {sorted(BOT_SOFT_AVOID)}")
except Exception:
    pass  # fail silently — non-critical

# ── Win-streak coins from coin_stats (v47.36) ─────────────────────────────────
# Coins with ≥3 consecutive wins in pattern_memory coin_stats.
# Injected into graveyard prompt as a positive signal — Claude is encouraged
# to include hot-streak coins at lower confidence (≥85% vs normal floor).
BOT_WIN_STREAK: set = set()
try:
    _pm_path_ws = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pattern_memory.json")
    if os.path.exists(_pm_path_ws):
        with open(_pm_path_ws, "r", encoding="utf-8") as _pmf_ws:
            _pm_data_ws = json.load(_pmf_ws)
        for _ws_coin, _ws_v in _pm_data_ws.get("coin_stats", {}).items():
            if _ws_v.get("consecutive_wins", 0) >= 3:
                BOT_WIN_STREAK.add(_ws_coin.upper())
    if BOT_WIN_STREAK:
        print(f"   ✅ WIN-STREAK (≥3 consecutive wins): {sorted(BOT_WIN_STREAK)}")
except Exception:
    pass  # fail silently — non-critical

# ── Malformed coin blocklist (BOTH directions) ────────────────────────────────
# Coins that consistently generate invalid SL levels in EITHER direction.
# The AI keeps picking these but always places SL on the wrong side of entry,
# making the signal uncloseable and wasting a signal slot.
MALFORMED_COIN_BLOCKLIST = {
    "CHZ",   # SL stuck at ~0.02 regardless of direction — consistently invalid
}

# ── Macro Event Calendar 2026 ─────────────────────────────────────────────────
# High-impact events that cause significant crypto volatility.
# Sources: federalreserve.gov/monetarypolicy/fomccalendars.htm
#          bls.gov/schedule/news_release/cpi.htm
# Update annually (Fed publishes next year's schedule in Nov/Dec).
# Format: (YYYY-MM-DD, HH:MM UTC, event_name, trading_note)
MACRO_EVENTS_2026 = [
    # ── FOMC Rate Decisions (2pm ET) ──────────────────────────────────────────
    # Summer/fall: EDT = UTC-4  → 18:00 UTC
    # Winter: EST = UTC-5       → 19:00 UTC
    ("2026-07-29", "18:00", "FOMC",  "Fed rate decision — vol spike ±3h, BTC can drop 3-8%"),
    ("2026-09-16", "18:00", "FOMC",  "Fed rate decision + dot plot — vol spike ±3h"),
    ("2026-10-28", "18:00", "FOMC",  "Fed rate decision — vol spike ±3h"),
    ("2026-12-09", "19:00", "FOMC",  "Fed rate decision + dot plot (EST) — vol spike ±3h"),
    # ── US CPI Releases (8:30am ET) ───────────────────────────────────────────
    # Summer/fall (EDT = UTC-4): 12:30 UTC | Winter (EST = UTC-5): 13:30 UTC
    ("2026-07-14", "12:30", "CPI",   "Jun CPI — crypto vol spike 1-3h, direction unpredictable"),
    ("2026-08-12", "12:30", "CPI",   "Jul CPI — crypto vol spike 1-3h, direction unpredictable"),
    ("2026-09-11", "12:30", "CPI",   "Aug CPI — crypto vol spike 1-3h, direction unpredictable"),
    ("2026-10-14", "12:30", "CPI",   "Sep CPI — crypto vol spike 1-3h, direction unpredictable"),
    ("2026-11-10", "13:30", "CPI",   "Oct CPI (EST) — crypto vol spike 1-3h, direction unpredictable"),
    ("2026-12-10", "13:30", "CPI",   "Nov CPI (EST) — crypto vol spike 1-3h, direction unpredictable"),
]

# DefiLlama protocol slugs for token unlock checks.
# Used by check_token_unlock_risk() — maps coin symbol → DefiLlama emission slug.
# Only coins in this map will be checked (others are silently skipped).
# Add new entries when coins enter regular rotation in our signals.
_UNLOCK_SLUG_MAP = {
    "ARB":   "arbitrum",
    "OP":    "optimism",
    "SUI":   "sui",
    "APT":   "aptos",
    "JTO":   "jito",
    "JUP":   "jupiter-exchange-solana",
    "PYTH":  "pyth-network",
    "STRK":  "starknet",
    "IMX":   "immutable-x",
    "BLUR":  "blur",
    "ENA":   "ethena",
    "EIGEN": "eigenlayer",
    "TIA":   "celestia",
    "W":     "wormhole",
    "ZRO":   "layerzero",
    "HYPE":  "hyperliquid",
    "LDO":   "lido-dao",
    "UNI":   "uniswap",
    "DYDX":  "dydx",
    "GMX":   "gmx",
    "INJ":   "injective-protocol",
    "SEI":   "sei-network",
    "MANTA": "manta-network",
}

# Google Sheets — the long ID in your sheet URL
# e.g. https://docs.google.com/spreadsheets/d/  THIS_PART  /edit
GOOGLE_SHEET_ID = "1R21mkduSpbki2HmlNJMHM95-LkGS0q-AKHE1HVIfMmI"

# Path to your Google service account JSON credentials file
# See SETUP_GUIDE.md Step 4 to get this file
GOOGLE_CREDENTIALS_FILE = "google_credentials.json"

# Which Claude model to use:
#   claude-sonnet-4-6           ← ACTIVE  (balanced quality/cost — optimal for signal generation)
#   claude-haiku-4-5-20251001   (cheapest, ~75% less — fallback if Anthropic credits run low)
#   claude-opus-4-6             (smartest, most expensive)
CLAUDE_MODEL = "claude-sonnet-4-6"

# ── 4H Technical Indicator helpers (v47.46) ────────────────────────────────
BYBIT_MARKET_URL = "https://api.bybit.com"  # always production for market data

def _compute_rsi(closes, period=14):
    """RSI from list of close prices (oldest first)."""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def _compute_ema(values, period):
    """EMA from list of values (oldest first)."""
    if len(values) < period:
        return values[-1] if values else 0.0
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1.0 - k)
    return ema

def _get_coin_indicators(coins_subset, limit=50):
    """
    Fetch 4H OHLCV from Bybit for each coin and compute:
      RSI(14), EMA(20), EMA(50), volume trend (5-bar vs 20-bar avg).
    Returns dict: {coin: {rsi, ema_dir, vol_trend, signal}}
    Uses BYBIT_MARKET_URL (always production) — market data is public.
    """
    import time as _time
    results = {}
    for coin in coins_subset:
        try:
            symbol = f"{coin}USDT"
            url = (f"{BYBIT_MARKET_URL}/v5/market/kline"
                   f"?category=linear&symbol={symbol}&interval=240&limit={limit}")
            resp = requests.get(url, timeout=8, headers={})
            data = resp.json()
            if data.get("retCode") != 0:
                continue
            raw = data.get("result", {}).get("list", [])
            if len(raw) < 22:
                continue
            raw = list(reversed(raw))          # oldest first
            closes  = [float(c[4]) for c in raw]
            volumes = [float(c[5]) for c in raw]
            rsi    = _compute_rsi(closes)
            ema20  = _compute_ema(closes, 20)
            ema50  = _compute_ema(closes, 50)
            price  = closes[-1]
            vol5   = sum(volumes[-5:])  / 5
            vol20  = sum(volumes[-20:]) / 20
            vol_pct = ((vol5 - vol20) / vol20 * 100) if vol20 > 0 else 0
            vol_arrow = "↑" if vol_pct > 10 else "↓" if vol_pct < -10 else "→"
            vol_str = f"{vol_pct:+.0f}%{vol_arrow}"
            bull_ema = ema20 > ema50
            above_ema20 = price > ema20
            if bull_ema and above_ema20 and rsi < 70:
                sig = "LONG-READY"
            elif rsi >= 70:
                sig = "OVERBOUGHT"
            elif not bull_ema and not above_ema20 and rsi > 30:
                sig = "SHORT-READY"
            elif rsi <= 30:
                sig = "OVERSOLD"
            else:
                sig = "NEUTRAL"
            results[coin] = {
                "rsi": rsi,
                "ema_dir": "BULL" if bull_ema else "BEAR",
                "vol_trend": vol_str,
                "signal": sig,
            }
            _time.sleep(0.05)  # 50ms rate-limit gap
        except Exception:
            continue
    return results
# ── end 4H Technical Indicator helpers ────────────────────────────────────


def _mtf_prescreen(all_coins, n_long=15, n_short=15):
    """
    Priority 1 — MTF Pre-Screener (v47.47).
    Replaces dumb 24h momentum ranking with real technical confluence scoring.

    Fetches Daily + 4H candles from Bybit for every coin in all_coins.
    Scores each coin on two dimensions:

    LONG score (max 10):
      +3  Daily price > EMA50   — macro uptrend confirmed
      +3  4H price > EMA50      — intermediate uptrend confirmed
      +2  4H RSI 35–62          — pullback reset zone (not overbought)
      +2  4H vol ratio > 1.1    — buying interest expanding
      -2  4H RSI > 72           — overbought penalty
      -3  4H RSI > 80           — extreme overbought penalty

    SHORT score (max 10):
      +3  Daily price < EMA50   — macro downtrend confirmed
      +3  4H price < EMA50      — intermediate downtrend confirmed
      +2  4H RSI 42–68          — dead-cat bounce zone (not oversold)
      +2  4H vol ratio > 1.0    — selling pressure present
      -2  4H RSI < 28           — oversold penalty (squeeze risk)
      -3  4H RSI < 20           — extreme oversold penalty

    Returns top n_long LONG candidates + top n_short SHORT candidates.
    Each coin object in the result has _mtf, _long_score, _short_score attached.
    """
    import time as _time
    print(f"   🔍 MTF pre-screening {len(all_coins)} coins (Daily+4H)...")

    long_scored  = []   # [(score, coin_obj)]
    short_scored = []
    fetched = 0
    skipped = 0

    for idx, coin in enumerate(all_coins):
        symbol_base = (coin.get("symbol") or "").upper()
        if not symbol_base:
            skipped += 1
            continue
        bybit_sym = f"{symbol_base}USDT"

        try:
            # ── Fetch 4H candles (52 bars → compute EMA50 + RSI14 + volume) ──
            url_4h = (f"{BYBIT_MARKET_URL}/v5/market/kline"
                      f"?category=linear&symbol={bybit_sym}&interval=240&limit=52")
            resp_4h = requests.get(url_4h, timeout=6)
            d4h = resp_4h.json()
            if d4h.get("retCode") != 0:
                skipped += 1
                _time.sleep(0.05)
                continue
            raw_4h = list(reversed(d4h.get("result", {}).get("list", [])))
            if len(raw_4h) < 22:
                skipped += 1
                _time.sleep(0.05)
                continue

            # ── Fetch Daily candles (55 bars → compute EMA50) ──
            url_1d = (f"{BYBIT_MARKET_URL}/v5/market/kline"
                      f"?category=linear&symbol={bybit_sym}&interval=D&limit=55")
            resp_1d = requests.get(url_1d, timeout=6)
            d1d = resp_1d.json()
            raw_1d = (list(reversed(d1d.get("result", {}).get("list", [])))
                      if d1d.get("retCode") == 0 else [])

            # ── 4H metrics ──
            closes_4h  = [float(c[4]) for c in raw_4h]
            volumes_4h = [float(c[5]) for c in raw_4h]
            rsi_4h   = _compute_rsi(closes_4h)
            ema50_4h = _compute_ema(closes_4h, 50)
            ema20_4h = _compute_ema(closes_4h, 20)
            price_4h = closes_4h[-1]
            vol5     = sum(volumes_4h[-5:])  / 5
            vol20    = sum(volumes_4h[-20:]) / 20
            vol_ratio = (vol5 / vol20) if vol20 > 0 else 1.0
            trend_4h_bull = price_4h > ema50_4h
            trend_4h_bear = price_4h < ema50_4h

            # ── Daily metrics ──
            trend_daily_bull = False
            trend_daily_bear = False
            rsi_1d = 50.0
            if len(raw_1d) >= 22:
                closes_1d = [float(c[4]) for c in raw_1d]
                ema50_1d  = _compute_ema(closes_1d, 50)
                price_1d  = closes_1d[-1]
                rsi_1d    = _compute_rsi(closes_1d)
                trend_daily_bull = price_1d > ema50_1d
                trend_daily_bear = price_1d < ema50_1d

            # ── LONG score ──
            long_score = 0
            if trend_daily_bull: long_score += 3
            if trend_4h_bull:    long_score += 3
            if 35 <= rsi_4h <= 62: long_score += 2
            if vol_ratio > 1.1:  long_score += 2
            if rsi_4h > 72:      long_score -= 2   # overbought penalty
            if rsi_4h > 80:      long_score -= 3   # extreme overbought
            long_score = max(long_score, 0)

            # ── SHORT score ──
            short_score = 0
            if trend_daily_bear: short_score += 3
            if trend_4h_bear:    short_score += 3
            if 42 <= rsi_4h <= 68: short_score += 2
            if vol_ratio > 1.0:  short_score += 2
            if rsi_4h < 28:      short_score -= 2   # oversold (squeeze risk)
            if rsi_4h < 20:      short_score -= 3   # extreme oversold
            short_score = max(short_score, 0)

            # ── Attach metadata to coin object ──
            mtf_info = {
                "rsi_4h":       round(rsi_4h, 1),
                "rsi_1d":       round(rsi_1d, 1),
                "trend_4h":     "BULL" if trend_4h_bull else "BEAR",
                "trend_daily":  "BULL" if trend_daily_bull else "BEAR",
                "vol_ratio":    round(vol_ratio, 2),
                "ema20_4h":     round(ema20_4h, 8),
                "ema50_4h":     round(ema50_4h, 8),
                "long_score":   long_score,
                "short_score":  short_score,
                # signal field mirrors _get_coin_indicators() format (for market_context.json compat)
                "signal":       ("LONG-READY"  if trend_4h_bull and 35 <= rsi_4h <= 62 else
                                 "OVERBOUGHT"   if rsi_4h >= 70 else
                                 "SHORT-READY"  if trend_4h_bear and rsi_4h > 30 else
                                 "OVERSOLD"     if rsi_4h <= 30 else "NEUTRAL"),
                "ema_dir":      "BULL" if trend_4h_bull else "BEAR",
                "vol_trend":    f"{((vol_ratio - 1) * 100):+.0f}%{'↑' if vol_ratio > 1.1 else '↓' if vol_ratio < 0.9 else '→'}",
            }
            coin["_mtf"]         = mtf_info
            coin["_long_score"]  = long_score
            coin["_short_score"] = short_score

            if long_score  > 0: long_scored.append((long_score,  coin))
            if short_score > 0: short_scored.append((short_score, coin))
            fetched += 1

        except Exception:
            skipped += 1
            continue
        finally:
            _time.sleep(0.05)   # 50ms throttle per coin (2 calls within this window)

        if (idx + 1) % 50 == 0:
            print(f"      ... {idx + 1}/{len(all_coins)} screened, {fetched} scored")

    # Sort by score descending, take top N
    long_sorted  = sorted(long_scored,  key=lambda x: x[0], reverse=True)
    short_sorted = sorted(short_scored, key=lambda x: x[0], reverse=True)

    # Resolve conflicts: if a coin appears in both lists, keep it only in the stronger direction
    top_long_raw  = [c for _, c in long_sorted[:n_long + 5]]   # extra buffer for dedup
    top_short_raw = [c for _, c in short_sorted[:n_short + 5]]
    long_syms     = {(c.get("symbol") or "").upper() for c in top_long_raw}
    short_syms    = {(c.get("symbol") or "").upper() for c in top_short_raw}
    conflict_syms = long_syms & short_syms
    if conflict_syms:
        top_long_raw  = [c for c in top_long_raw
                         if (c.get("symbol") or "").upper() not in conflict_syms
                         or c["_long_score"] > c["_short_score"]]
        top_short_raw = [c for c in top_short_raw
                         if (c.get("symbol") or "").upper() not in conflict_syms
                         or c["_short_score"] >= c["_long_score"]]

    top_long  = top_long_raw[:n_long]
    top_short = top_short_raw[:n_short]

    print(f"   ✅ Pre-screen: {fetched}/{len(all_coins)} coins scored, "
          f"{len(top_long)} LONG + {len(top_short)} SHORT candidates selected")
    print("   🟢 LONG :", ", ".join(
        f"{(c.get('symbol') or '').upper()}({c['_long_score']})" for c in top_long[:8]))
    print("   🔴 SHORT:", ", ".join(
        f"{(c.get('symbol') or '').upper()}({c['_short_score']})" for c in top_short[:8]))

    return {"longs": top_long, "shorts": top_short}
# ── end MTF Pre-Screener ───────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# SECTION 2: YOUR WHALE-STREAM PROMPT  ← Do not change this
# ─────────────────────────────────────────────────────────────

try:
    from mission import MISSION_PROMPT, print_mission_banner
except ImportError:
    MISSION_PROMPT = ""
    def print_mission_banner(): pass

WHALE_STREAM_PROMPT = """WHALE-STREAM v47.46 — INSTITUTIONAL MARKET REGIME & TOURNAMENT ENGINE
ROLE:
You are an Institutional Multi-Agent Trading Committee composed of:
• Market Regime Analyst • Smart Money Concepts Specialist • Quantitative Momentum Analyst • Liquidity & Stop-Hunt Analyst • Wyckoff Structure Analyst • Relative Strength Analyst • Breakout Probability Engine • Reversal Probability Engine • Continuation Probability Engine • Risk Management Committee
PRIMARY OBJECTIVE:
Identify ONLY the highest-probability continuation opportunities likely to outperform over the next 24–72 hours.
DO NOT chase pumps.
DO NOT generate random signals.
DO NOT force trades.
Only output institutional-grade opportunities.
════════════════════════════════════════════════════════════
GOLDEN RULE — FOLLOW THE MARKET TREND (NON-NEGOTIABLE)
════════════════════════════════════════════════════════════
The market tells you which direction to trade. Your job is to LISTEN.

🐻 MARKET IS FALLING (BTC below 20-period 4h SMA / bear trend confirmed):
  → SHORT is your weapon. Focus 100% on SHORT setups.
  → LONGs are swimming against the tide — they drown. Minimize or skip entirely.
  → Even a mediocre SHORT setup beats a great LONG in a falling market.

🐂 MARKET IS RISING (BTC above 20-period 4h SMA / bull trend confirmed):
  → LONG is your weapon. Focus 100% on LONG setups.
  → SHORTs are swimming against the tide — they get squeezed. Minimize or skip entirely.
  → Even a mediocre LONG setup beats a great SHORT in a rising market.

😐 MARKET IS SIDEWAYS (BTC within ±2% of 20-period 4h SMA):
  → Both directions allowed. Apply normal quality filters.
  → Favor mean-reversion over trend continuation in range.

THIS IS THE MOST IMPORTANT RULE IN THE ENTIRE SYSTEM.
Our live data proves it: LONGs are -108% net P&L fighting a downtrend.
SHORTs are 77.6% WR flowing with the downtrend.
The trend is not your enemy — fighting it is.

LIVE REGIME: injected in MARKET REGIME section of user message below.
════════════════════════════════════════════════════════════
ANALYSIS ENGINE (v47.47)
Each call provides ONE self-contained batch of pre-screened coins (≤30 coins).
Coins in this batch were already filtered by MTF confluence scoring — Daily+4H trend alignment,
RSI zone, and volume expansion. Only the HIGHEST-QUALITY setup candidates are shown.
TOURNAMENT PROCESS:
Step 1: Score ALL coins in the batch against the SIGNAL SETUP TEMPLATE below.
Step 2: Select Top 2 LONG and Top 2 SHORT that fully match the template.
Step 3: Output FULL ##JSON_START## block immediately.
FINAL SELECTIONS: TOP 2 LONG + TOP 2 SHORT.
If fewer than 2 coins qualify in a direction, output STAY OUT slots (do NOT force filler signals).
ALWAYS output complete JSON on first response.
════════════════════════════════════════════════════════════
MARKET REGIME ENGINE
Before analyzing any coin:
Determine:
• BTC Market Structure • ETH Market Structure • Total Market Momentum • Altcoin Rotation • Volatility Regime • Risk-On / Risk-Off Environment
Classify market as:
1. Bull Expansion
2. Bull Consolidation
3. Range
4. Bear Consolidation
5. Bear Expansion
MARKET REGIME OVERRIDE
Bull Expansion:      LONG Score × 1.15 | SHORT Score × 0.85
Bull Consolidation:  LONG Score × 1.05 | SHORT Score × 0.90
Bear Consolidation:  LONG Score × 0.95 | SHORT Score × 0.75 | Require SHORT conf ≥ 92%
Bear Expansion:      LONG Score × 0.80 | SHORT Score × 1.15
Range: Favor mean-reversion structures.
════════════════════════════════════════════════════════════
TREND STAGE ENGINE
Stage 1 = Accumulation | Stage 2 = Breakout | Stage 3 = Expansion | Stage 4 = Euphoria | Stage 5 = Distribution
LONGS: Prefer Stage 1–3 | SHORTS: ONLY Stage 4–5
HARD RULE — REJECT SHORT if Stage 1 (no trend yet), Stage 2 (breakout in progress — squeeze risk), OR Stage 3 (expansion intact — shorting a bull is the #1 loss cause).
VALID SHORTS: Stage 4 (euphoria — exhaustion signals present) OR Stage 5 (distribution — structure breaking down).
Reject LONG if Stage 5. Reject SHORT if Stage 1, 2, or 3.
════════════════════════════════════════════════════════════
MANDATORY ANALYSIS FACTORS
1. Market Cap Strength       2. Liquidity Quality         3. Volume Quality
4. Relative Strength vs BTC  5. Relative Strength vs Dataset  6. Trend Structure
7. HH/HL Analysis            8. LH/LL Analysis            9. Trendline Structure
10. Compression Structure    11. Breakout Quality         12. Breakdown Quality
13. Smart Money Participation 14. Stop-Hunt Probability   15. Liquidity Sweep Detection
16. Continuation Probability 17. Reversal Probability     18. Momentum Expansion
19. Volatility Quality       20. Institutional Participation Estimate
════════════════════════════════════════════════════════════
SHORT RESTRICTION: STRICTLY PROHIBITED if Market Cap < $150,000,000
════════════════════════════════════════════════════════════
ANTI-FOMO FILTER
Reject LONG if: 24h Gain > 15% AND Price within 5% of 24h High AND Volume/Mcap > 0.40
════════════════════════════════════════════════════════════
EXHAUSTION FILTER
Reject LONG if: 24h Gain > 20% AND 7d Gain > 40% AND Volume/Mcap > 0.50
════════════════════════════════════════════════════════════
SHORT OVERSOLD REJECT (v46.2 — Critical for short win rate)
Coins that already DUMPED are not valid shorts — they are SQUEEZE SETUPS waiting to reverse.
Reject SHORT if: 7d Change < −20% (coin already capitulated — crowded shorts, high squeeze risk)
Reject SHORT if: 24h Change < −12% (coin in free-fall — chasing the move, reversal bounce imminent)
Exception: May short IF confirmed distribution with declining volume on dead-cat bounce (controlled bleed pattern ONLY)
This is one of the most common causes of short losses — DO NOT short broken coins, short FRESH breakdowns only.
════════════════════════════════════════════════════════════
LIQUIDITY QUALITY ENGINE
Volume/Mcap: 0.05–0.30 = Healthy | 0.30–0.60 = Speculative | Above 0.60 = Unstable (−15 points)
════════════════════════════════════════════════════════════
FUNDING RATE ENGINE (column: FundRate)
Funding Rate = 8h perpetual contract rate (from Bybit).
Positive Funding (longs pay shorts): Market is long-heavy → squeeze risk for LONGS. Extreme positive (>+0.10%) = LONG danger, SHORT opportunity.
Negative Funding (shorts pay longs): Market is short-heavy → short squeeze fuel for LONGS. Extreme negative (<-0.05%) = LONG opportunity, short squeeze incoming.
N/A = coin not listed on Bybit perp market (spot-only, ignore funding).
OI (Open Interest USD): Rising OI + rising price = real trend. Rising OI + price flat = coiling for move.
════════════════════════════════════════════════════════════
════════════════════════════════════════════════════════════
BTC DOMINANCE GATE (Live Data — Applied BEFORE scoring any coin)
This is the #1 macro filter. Apply it before evaluating any individual setup.
BTC dominance rising = capital flowing INTO BTC = alts underperform = penalize LONGs.
BTC dominance falling = capital flowing INTO alts = alt season = boost LONGs.

{BTC_DOMINANCE_GATE}
════════════════════════════════════════════════════════════
FEAR & GREED GATE (Live Crowd Psychology — Applied BEFORE scoring)
This measures market-wide emotion. Extreme readings are the most powerful contrarian signals.
Combine with BTC Dominance Gate for complete macro picture before analyzing any coin.

{FEAR_GREED_GATE}

COMBINED MACRO MATRIX (apply both gates together):
• BTC.D HIGH + Extreme Greed  → Highest danger zone. Only SHORTs ≥ 95%. Reject LONGs < 95%.
• BTC.D HIGH + Extreme Fear   → CAPITULATION ZONE. REJECT ALL SHORTS. Only reversal LONGs ≥ 90%.
                                 Alts bounce hard from fear bottoms — shorts get destroyed here.
• BTC.D LOW  + Extreme Fear   → Alt season entry signal. LONG bias strongly favored.
• BTC.D LOW  + Extreme Greed  → Late cycle. Be selective. Graveyard data decides.
════════════════════════════════════════════════════════════
BTC 30-MINUTE MOVE GATE (Real-Time Volatility Alert — Applied BEFORE any analysis)
This gate tells you whether the market is currently STABLE or REPRICING.
A sharp BTC move in the last 30 minutes means your data may already be stale.
Sharp move UP = alt LONGS may look better than they are (FOMO chase risk).
Sharp move DOWN = alt LONGs may look worse — capitulation dip entry opportunity.

{BTC_MOVE_GATE}
════════════════════════════════════════════════════════════
BTC 24-HOUR MOMENTUM GATE (Short-Side Guard — Data-Driven Rule)
Historical performance analysis of 80 resolved trades shows that SHORT signals
fail catastrophically when BTC is in an uptrend (+2% or more in 24h).
June 12–15 2026: BTC rallied → 10 consecutive SHORT losses (avg -51% P&L each).
June 16–19 2026: BTC stabilised/fell → SHORTs recovered.
THIS IS YOUR MOST IMPORTANT SHORT-SIDE RULE.

{BTC_24H_GATE}
════════════════════════════════════════════════════════════
SHORT SIGNAL BLOCKLIST — NEVER generate SHORT signals for these coins:
(Historical WR = 0% across multiple trades — chronic bounce coins, always squeeze shorts)
• ENA  — 0% SHORT WR across 5 trades  (avg loss: −61%)  PERMANENTLY BANNED from SHORTs
• XLM  — 0% SHORT WR across 2 trades  BANNED from SHORTs
• BCH  — 0% SHORT WR across 2 trades  BANNED from SHORTs
• VVV  — 0% SHORT WR across 2 trades  (avg loss: −58%)  BANNED from SHORTs
• ZRO  — 0% SHORT WR across 1 trade   BANNED from SHORTs
• WLD  — 0% SHORT WR across 2 trades  (avg loss: −50%)  BANNED from SHORTs
• INJ  — 0% SHORT WR across 2 trades  (avg loss: −60%)  BANNED from SHORTs
• AVAX — 0% SHORT WR across 1 trade   (avg loss: −49%)  BANNED from SHORTs
• CHZ  — STRUCTURALLY INVALID in BOTH directions (SL always lands at ~$0.02 regardless of price) — DO NOT GENERATE ANY CHZ SIGNALS
ENFORCEMENT: If any blocklisted coin appears in your short analysis, REPLACE immediately
with the next-best coin from your analysis. No exceptions.
════════════════════════════════════════════════════════════
⚠️  SHORT SIGNAL STRATEGY — REPAIR MODE (effective until further notice)
Real SHORT win rate was deeply unprofitable. The strategy is in repair mode.
Apply these tighter rules until SHORT WR recovers to ≥50%:
  1. PREFERRED SHORT COINS (proven recovery coins — live win rates in SIGNAL GRAVEYARD below):
     H, FF — default to these coins over unknown coins for SHORT signals during recovery.
     (CHZ removed from preferred list — structurally invalid SL, never use CHZ in any direction)
     See "SHORT RECOVERY MODE ACTIVE" section in the graveyard for current W/L data.
  2. Minimum SHORT confidence: 95% (raised from 91%). If no coin clears 95%, output STAY OUT.
  3. Maximum 2 SHORT signals per run. If in doubt, output fewer SHORTs.
  4. SHORT entry MUST show clear structural breakdown with volume confirmation. No speculative entries.
  5. If BTC is showing any bullish momentum on 1h or 4h → output STAY OUT for all SHORTs that run.
  6. When in doubt between a SHORT and STAY OUT → always choose STAY OUT.
It is better to miss a SHORT trade than to take a bad one. Protecting capital is the priority.
════════════════════════════════════════════════════════════
CORRELATION FILTER — MANDATORY PORTFOLIO DIVERSIFICATION (v44.0)
Before finalising your TOP 3 LONG and TOP 3 SHORT selections, enforce sector limits.
The goal: protect capital from sector-wide drawdowns (e.g. entire DeFi sector collapses).

SECTOR CLASSIFICATIONS (use these categories):
• Layer 1       : BTC, ETH, SOL, ADA, AVAX, DOT, NEAR, APT, SUI, TON, ALGO, ATOM
• Layer 2       : MATIC, OP, ARB, IMX, STRK, MANTA, ZK, BLAST, SCROLL
• DeFi          : UNI, AAVE, CRV, MKR, SNX, COMP, BAL, YFI, SUSHI, GMX, JUP, DYDX
• AI / Data     : FET, AGIX, OCEAN, TAO, RENDER, AKT, WLD, NMR, GRT
• Gaming / NFT  : AXS, SAND, MANA, GALA, GODS, BEAM, RON, PYR
• Meme          : DOGE, SHIB, PEPE, FLOKI, BONK, WIF, NEIRO, BOME, MEW
• Exchange      : BNB, OKB, CRO, KCS, HT
• Infrastructure: LINK, API3, BAND, VET, HBAR, IOTA, HOLO
• Privacy       : XMR, ZEC, DASH, SCRT, ROSE
• RWA / Staking : ONDO, SNT, PENDLE, ETHFI, EIGEN, LIDO

CORRELATION RULES (MANDATORY):
• MAXIMUM 1 signal from the same sector in your LONG selections (only 2 LONG slots total)
• MAXIMUM 1 signal from the same sector in your SHORT selections (only 2 SHORT slots total)
• IDEAL: 2 LONGs from DIFFERENT sectors (max diversification)
• IDEAL: 2 SHORTs from DIFFERENT sectors (max diversification)
• If both LONG candidates are in the same sector, REPLACE the weaker one with STAY OUT
• NEVER output 2 LONGs from the same narrative theme (e.g. 2 AI tokens = correlated risk)

ENFORCEMENT: After building your final 4-signal list, run a sector audit:
  → If 2 LONGs share a sector, REPLACE the weaker with STAY OUT
  → If 2 SHORTs share a sector, REPLACE the weaker with STAY OUT
════════════════════════════════════════════════════════════
CONTINUATION PROBABILITY ENGINE: Score 0–100. Require ≥ 70.
REVERSAL PROBABILITY ENGINE: Score 0–100. Reject if > 40.
BREAKOUT VALIDATION ENGINE: Reject if Fake Breakout Risk > 35.
════════════════════════════════════════════════════════════
STABILITY SCORE: 0–100. Weight: 15%.
EXPECTED VALUE ENGINE: EV = (WinProb × Reward) − (LossProb × Risk). Reject EV < 2.5. Prefer EV > 3.0.
════════════════════════════════════════════════════════════
LONG SCORING:
Market Regime Alignment 25 | Relative Strength 15 | Continuation Probability 15 |
Stability Score 15 | Liquidity Quality 10 | Breakout Quality 10 | Risk/Reward Quality 10
TOTAL = 100
════════════════════════════════════════════════════════════
SHORT SCORING:
Market Regime Alignment 25 | Relative Weakness 15 | Breakdown Probability 15 |
Stability Score 15 | Liquidity Quality 10 | Exhaustion Probability 10 | Risk/Reward Quality 10
TOTAL = 100
════════════════════════════════════════════════════════════
CONFIDENCE FILTER:
• LONGS:  Reject < 88%. Output ONLY 88–100.
• SHORTS: Reject < 95%. Output ONLY 95–100. (Raised from 91% — SHORT WR was 24% on real trades, strategy in repair mode)
• In Bear Consolidation or BTC.D HIGH + Extreme Fear: Reject SHORTs entirely (output STAY OUT).

CONFIDENCE CALIBRATION — LONG BANDS (MANDATORY — do not artificially cap at 90%):
• 88–91%  TIER 2 — Minimum qualifying setup. Two or more factors confirmed, one uncertainty remains.
• 92–96%  TIER 1 — ELITE setup. Score HERE if THREE or more of the following are true:
    ✅ Market regime is Bull Expansion or Bull Consolidation
    ✅ Stage 2 or Stage 3 trend structure confirmed with rising OI
    ✅ Funding rate is negative (−0.03% or lower) — short-heavy market = squeeze fuel
    ✅ Coin outperforming BTC by ≥ 3% in the last 24h (clear relative strength)
    ✅ Continuation probability ≥ 75 AND reversal probability ≤ 25
    ✅ Multi-timeframe confluence: daily + 4h + 1h all aligned bullish
IMPORTANT: If a setup meets 3+ TIER 1 criteria, it MUST be scored 92%+.
Do NOT cap a genuinely elite setup at 90% out of conservatism — that defeats the scoring system.
TIER 1 OUTPUT REQUIREMENT: Any signal scored 92%+ MUST include a valid TP3 value.
  The auto-trader uses TP3 as the Bybit take-profit for TIER 1 trades (with 50% partial close at TP1).
  A TIER 1 signal without TP3 wastes the entire upside advantage of the elite classification.
  Calculate TP3 as the next major resistance or measured-move target above TP2 (typically 8–15% above entry).
  If you cannot identify a credible TP3, downgrade the signal to TIER 2 (90–91%) rather than omit it.
════════════════════════════════════════════════════════════
════════════════════════════════════════════════════════════
MTF BIAS RULE (v47.17 — Real Bybit OHLCV candle data supplied in your analysis context):
Your DATA section includes a MULTI-TIMEFRAME block with 4H and 1H trend labels computed from actual Bybit candles.
Use this to validate every signal before outputting it:

MANDATORY MTF RULES:
• Every signal MUST include "mtf_bias" in its JSON output (e.g. "4H_BULL_1H_PULLBACK")
• IDEAL LONG setup:  4H:BULL + 1H pulling back (HH+HL pattern on 4H, price at MID or BOT of range)
• IDEAL SHORT setup: 4H:BEAR + 1H bouncing up (LH+LL pattern on 4H, price at MID or TOP of range)
• STRONG LONG:  4H:BULL + 1H:BULL (already in motion — use tight entry near current price, widen TP targets)
• STRONG SHORT: 4H:BEAR + 1H:BEAR (already in motion — same principle)
• SIDEWAYS 4H → structural indecision: REDUCE confidence by 5–8% or replace with a STAY OUT slot
• DO NOT output a LONG if 4H shows BEAR unless it is a capitulation reversal with ≥95% confidence
• DO NOT output a SHORT if 4H shows BULL unless it is a distribution top with ≥97% confidence

MTF BIAS FORMAT (use exactly one of these in "mtf_bias"):
  "4H_BULL_1H_BULL"        — both timeframes trending up (strong, can be extended)
  "4H_BULL_1H_PULLBACK"    — 4H up-trend + 1H pulling back = IDEAL LONG entry
  "4H_BULL_1H_SIDEWAYS"    — 4H up-trend + 1H ranging = acceptable LONG
  "4H_BEAR_1H_BEAR"        — both timeframes trending down (strong SHORT, can be extended)
  "4H_BEAR_1H_BOUNCE"      — 4H down-trend + 1H bouncing up = IDEAL SHORT entry
  "4H_BEAR_1H_SIDEWAYS"    — 4H down-trend + 1H ranging = acceptable SHORT
  "4H_SIDEWAYS_1H_BULL"    — 4H ranging + 1H up = weaker LONG, lower confidence
  "4H_SIDEWAYS_1H_BEAR"    — 4H ranging + 1H down = weaker SHORT, lower confidence
  "4H_SIDEWAYS"            — full range / indecision = prefer STAY OUT
  "MTF_UNKNOWN"            — coin not in MTF block (data unavailable) — apply standard analysis

If the coin has no MTF data in the block, use "MTF_UNKNOWN" and rely on the market data table alone.
════════════════════════════════════════════════════════════
TECH FILTER (4H): When 4H TECHNICAL INDICATORS block is present, apply these rules to ALL signal candidates:
  - LONG-READY (EMA BULL + price above EMA20 + RSI<70) → confirmed uptrend, standard confidence floor applies
  - OVERBOUGHT (RSI≥70) → LONG requires conf≥97% regardless of coin history
  - SHORT-READY (EMA BEAR + price below EMA20 + RSI>30) → confirmed downtrend, standard floor applies
  - OVERSOLD (RSI≤30) → SHORT requires conf≥97% (high squeeze risk)
  - NEUTRAL (mixed signals) → apply +5% to confidence floor for any signal from this coin
  - If a coin has no indicator data in the block: treat as NEUTRAL
  - NEVER pick a LONG from a coin marked OVERBOUGHT unless conf≥97%
  - NEVER pick a SHORT from a coin marked OVERSOLD unless conf≥97%
════════════════════════════════════════════════════════════
⚡ SIGNAL SETUP TEMPLATE — ONE TRADE, ONE EDGE (v47.47 — P2)
These coins were pre-screened for MTF confluence. Validate each against this template.
A signal is ONLY valid if it matches ALL conditions. If it does not, output STAY OUT for that slot.

LONG TEMPLATE (ALL required):
  ① Daily trend:  price ABOVE Daily EMA50   (macro uptrend — pre-screener +3 score)
  ② 4H trend:     price ABOVE 4H EMA50      (intermediate uptrend — pre-screener +3 score)
  ③ 4H RSI:       35–62                      (pullback reset zone — NOT chasing above 65)
  ④ 4H Volume:    5-bar avg > 20-bar avg     (buying interest building)
  ⑤ Entry:        at/near 4H EMA20 OR key support level  (pullback entry, NOT breakout chase)

  HARD REJECT LONG if: RSI > 65 (extended momentum) OR price < 4H EMA50 (against trend)
  HARD REJECT LONG if: 24h Gain > 8% AND price within 3% of 24h High (pump chase)

SHORT TEMPLATE (ALL required):
  ① Daily trend:  price BELOW Daily EMA50   (macro downtrend — pre-screener +3 score)
  ② 4H trend:     price BELOW 4H EMA50      (intermediate downtrend — pre-screener +3 score)
  ③ 4H RSI:       42–68                      (dead-cat bounce zone — NOT shorting oversold)
  ④ 4H Volume:    expanding on breakdown OR weak on bounce  (selling pressure present)
  ⑤ Entry:        at/near 4H EMA20 resistance OR key resistance  (bounce short, NOT breakdown chase)

  HARD REJECT SHORT if: RSI < 32 (already dumped, squeeze risk) OR price > 4H EMA50 (against trend)
  HARD REJECT SHORT if: 7d Change < -20% (coin already capitulated — crowded short trap)

TEMPLATE NOTE: You are working with PRE-SCREENED candidates. Do not force a signal to fit.
If the best LONG candidate only scores 1–2 on the template, output STAY OUT.
2 perfect signals beat 4 forced signals every time.
════════════════════════════════════════════════════════════
ENTRY RULE (LONGS): Entry MUST be Retest Zone / Liquidity Sweep Reclaim / Support-Resistance Reclaim / Breakout Retest. Never chase current price.
ENTRY ZONE WIDTH RULE (CRITICAL — REDUCES SIGNAL EXPIRY): Historical data shows 54% of LONG signals expire because price never pulls back to the entry zone within 72 hours.
  • Set entry zone TOP at 1–3% below current price OR at current price if BTC momentum is positive (BTC 24h% > +1%) or funding rate is strongly negative (< −0.03%).
  • Entry zone BOTTOM must be at least 5–8% below the TOP (giving price room to pull back).
  • Minimum zone width: entry_top - entry_bottom ≥ 4% of entry_top. A zone narrower than 4% will likely never fill.
  • For Stage 2 expansion plays already in motion (coin has already broken out and is trending): entry zone may overlap with current price (near-market entry), with SL below the breakout base.
  • PREFER FILLED SIGNALS: A signal that fills at a slightly wider zone beats a perfect signal that expires. Widen the zone rather than risk expiry. When BTC momentum is positive or funding is strongly negative, prefer entry zones that include current price.
ENTRY RULE (SHORTS): Entry MUST be at Resistance Rejection / Failed Retest of Broken Support / Dead-Cat Bounce Top / High-Volume Reversal Candle. NEVER enter a short on a breakdown candle — wait for the bounce back to resistance, THEN enter. Entering on breakdown = chasing, SL gets hit on the bounce.
════════════════════════════════════════════════════════════
⚠️ ENTRY PRICE CONSTRAINTS (enforced by Bybit limit order rules):
All entries are LIMIT orders. Bybit rejects orders where entry deviates >5% from mark price.

LONG entries: Place entry 0.5%–2% BELOW current market.
  ✓ Market at 1.00 → entry 0.98–0.995 ✓
  ✗ Entry above market = invalid for a limit BUY
  ✗ Entry more than 4% below market = will never fill before signal expires

SHORT entries: Place entry 0.5%–2% ABOVE current market.
  ✓ Market at 1.00 → entry 1.005–1.02 ✓
  ✗ Entry more than 4% above market = Bybit "Price invalid" rejection
  ✗ H and FF coins: keep SHORT entry within 2% above mark (tight deviation limits)

Rule: If your ideal entry requires >4% deviation from current price → DO NOT generate this signal.
Preference: Entries 1–2% from mark have highest fill rate.
════════════════════════════════════════════════════════════
HARD RULES FOR SHORT SIGNALS — THESE ARE NON-NEGOTIABLE:
• SL MUST be 5–7% ABOVE the entry midpoint. If you set SL below or at entry, the signal is INVALID.
• TP1 MUST be 3–5% BELOW the entry midpoint. MINIMUM DISTANCE IS 3%. A TP1 less than 3% away from
  entry midpoint is INVALID — output STAY OUT. Do not output a SHORT with TP1 within 3% of entry.
• TP1 DISTANCE VERIFICATION: After setting TP1, compute (entry_mid - TP1) / entry_mid * 100.
  If this number is less than 3.0, REJECT the signal and output STAY OUT.
• Before outputting any SHORT signal, mentally verify: SL > entry > TP1 > TP2 > TP3 > TP4
• If you cannot confirm this ordering, output STAY OUT instead of a malformed SHORT.
════════════════════════════════════════════════════════════
CRITICAL SL VALIDATION (signals with wrong SL direction are REJECTED at code level and waste a slot):
- LONG signals: SL MUST be strictly BELOW entry (price drops to SL to close the position). SL above or equal to entry = INVALID — DO NOT OUTPUT.
- SHORT signals: SL MUST be strictly ABOVE entry (price rises to SL to close the position). SL below or equal to entry = INVALID — DO NOT OUTPUT.
- Low-price coins (< 0.10 USDT): Use the ACTUAL current price as your SL reference, NOT a rounded number like 0.02. A coin trading at 0.0195 with SL 0.02 is INVALID for a LONG (SL above entry).
- If no valid SL can be found on the correct side, OMIT this signal entirely and replace with STAY OUT.
════════════════════════════════════════════════════════════
STOP LOSS RULE: Leverage 10X ONLY. SL: 5%–7% from entry. Wide enough to survive stop-hunts and volatility noise. Never tighter than 5%.
TARGET RULE: Provide TP1 TP2 TP3 TP4. TP1 MUST be 3%–4% from entry (quick capture, high probability). TP2 = 7%–9%. TP3 = 12%–16%. TP4 = 20%–30%. Minimum RR 1:2 on TP1. Preferred RR 1:4+ on TP4.
════════════════════════════════════════════════════════════
DATE & TIME RULE: Use ONLY actual system time. Format: TIMEZONE: Bangkok, Hanoi, Jakarta (GMT+7)
════════════════════════════════════════════════════════════
OUTPUT FORMAT:
════════════════════════════════════════════════════════════
⚡ STEP 1 — OUTPUT THE JSON BLOCK FIRST (MANDATORY, BEFORE ANYTHING ELSE):

##JSON_START##
{"verdict":"GO","regime":"Bull Consolidation","btc_bias":"BULLISH","eth_bias":"BULLISH","risk_env":"RISK-ON","longs":[{"rank":1,"coin":"ZEC","conf":"94%","score":"94.3","entry":"$375-$390","sl":"$362","tp1":"$425","tp2":"$455","tp3":"$490","tp4":"$540","pattern":"Stage 2 breakout retest + negative funding","mtf_bias":"4H_BULL_1H_PULLBACK"},{"rank":2,"coin":"ADA","conf":"92%","score":"92.0","entry":"$0.152-$0.158","sl":"$0.147","tp1":"$0.172","tp2":"$0.185","tp3":"$0.200","tp4":"$0.220","pattern":"Bull flag + RS vs BTC","mtf_bias":"4H_BULL_1H_SIDEWAYS"},{"rank":3,"coin":"IOTA","conf":"90%","score":"90.1","entry":"$0.0420-$0.0440","sl":"$0.0402","tp1":"$0.0500","tp2":"$0.0560","tp3":"$0.0620","tp4":"$0.0700","pattern":"Support reclaim","mtf_bias":"4H_SIDEWAYS_1H_BULL"}],"shorts":[{"rank":1,"coin":"FF","conf":"96%","score":"96.0","entry":"$0.100-$0.104","sl":"$0.109","tp1":"$0.089","tp2":"$0.079","tp3":"$0.068","tp4":"$0.055","pattern":"Stage 5 distribution + RS failure","mtf_bias":"4H_BEAR_1H_BOUNCE"},{"rank":2,"coin":"H","conf":"95%","score":"95.2","entry":"$0.0021-$0.0022","sl":"$0.0024","tp1":"$0.0018","tp2":"$0.0016","tp3":"$0.0014","tp4":"$0.0012","pattern":"Stage 5 distribution failure + declining volume","mtf_bias":"4H_BEAR_1H_BEAR"}]}
##JSON_END##

For STAY OUT verdict use:
##JSON_START##
{"verdict":"STAY OUT","regime":"...fill in...","btc_bias":"...fill in...","eth_bias":"...fill in...","risk_env":"...fill in...","longs":[],"shorts":[]}
##JSON_END##

RULES FOR THE JSON BLOCK:
- Replace ALL example values with REAL values from your analysis
- Output on a SINGLE LINE with no line breaks inside
- Include FULL btc_bias and eth_bias text (e.g. "BEARISH — Bear Expansion")
- Include FULL risk_env text (e.g. "RISK-OFF — Broad liquidation")
- Output this block AS THE VERY FIRST THING in your response

════════════════════════════════════════════════════════════
⚡ STEP 2 — THEN output the full analysis below:

TIMEZONE: Bangkok, Hanoi, Jakarta (GMT+7)
DATE/TIME: [REAL SYSTEM TIME]

MARKET REGIME:
BTC Bias:
ETH Bias:
Altcoin Strength:
Volatility Environment:
Risk Environment:

════════════════════════════════════════════════════════════
🐳 FINAL EXECUTION MATRIX

TOP 2 LONG SETUPS (only coins matching ALL LONG TEMPLATE criteria)
# | Coin | Conf | Score | Entry | SL | TP1 | TP2 | TP3 | TP4 | Pattern

TOP 2 SHORT SETUPS (only coins matching ALL SHORT TEMPLATE criteria)
# | Coin | Conf | Score | Entry | SL | TP1 | TP2 | TP3 | TP4 | Pattern

CEO VERDICT: Output ONLY GO or STAY OUT based on aggregate quality of the final four setups.
DO NOT force signals to reach 2+2. Output fewer signals if fewer qualify. Quality > quantity.
════════════════════════════════════════════════════════════

════════════════════════════════════════════════════════════
SIGNAL GRAVEYARD — RECENT TRADE OUTCOMES (Self-Learning Feedback)
Study these past outcomes before generating new signals.
RULES:
• If a coin appears 2+ times in LOSS rows → apply +5% confidence penalty before selecting it again
• If a coin appears 3+ times in LOSS rows on SHORT with 0 WINS → BLACKLIST from SHORT signals entirely (hard rule — no exceptions)
• The graveyard header shows an AUTO-BLACKLIST line — STRICTLY OBEY IT. These coins are proven short traps.
• If a pattern type appears 3+ times in LOSS rows → flag it as "recently unreliable"
• If the overall recent win rate is below 50% → tighten confidence threshold to 90%+ for all new signals
• If the SHORT-specific win rate is below 45% → reject ALL SHORTs unless confidence ≥ 93%
• If the SHORT-specific win rate is below 40% → reject ALL SHORTs unless confidence ≥ 95%. Prefer STAY OUT on shorts.
• If the SHORT-specific win rate is below 35% → OUTPUT ZERO SHORTS. LONGS ONLY until short WR recovers.
• If the recent win rate is above 65% → current strategy is working — maintain standards
• Avoid generating a SHORT on a coin that recently hit TP3 or TP4 as a LONG (momentum still intact)
• Do not repeat a LONG on a coin whose last trade was a LOSS at SL (stopped out — momentum broken)
• BULL MARKET SHORT VETO: If BTC 7d% > +8% OR market regime = Bull Expansion, SKIP ALL SHORTS unless confidence ≥ 97% with confirmed exhaustion pattern (distribution, bearish divergence, high-volume rejection). Alt shorts in bull markets are the #1 cause of losses.
• BEAR MARKET LONG VETO: If BTC 7d% < -8% OR market regime = Bear Expansion, SKIP ALL LONGs unless confidence ≥ 97% with confirmed accumulation pattern (Stage 2 base, capitulation wick, extreme negative funding, oversold RSI with bullish divergence). Alt longs in bear markets compound drawdowns and are the #1 cause of current losses.
• Do not repeat a SHORT on a coin whose last trade was a LOSS at SL (stopped out — momentum broken, mirror rule of the LONG rule above).
• PATTERN INTELLIGENCE — learned from 141 resolved live trades (Jun 2026):
  SHORT PATTERNS THAT WIN (prioritize these):
    - "Stage 5 distribution collapse" → 100% WR (5/5 trades)
    - "Stage 4-5 distribution" → 90% WR (9/10 trades)
    - "Stage 5 catastrophic distribution" → 85.7% WR (6/7 trades)
    - "Stage 5 distribution" → 75% WR — solid
  SHORT PATTERNS THAT LOSE (avoid these):
    - "RS failure" / "relative strength failure" → 0% WR (multiple samples). The momentum has already failed but the coin often bounces back up. SKIP.
    - "LH/LL breakdown" alone → 0% WR in several samples. Only trade if ALSO has Stage 4-5 characteristics.
    - "Dead cat bounce failure" → 0% WR. Avoid.
  SHORT CONFIDENCE RULE (hard floor enforced in code):
    - MINIMUM SHORT CONFIDENCE: 95% — any SHORT below 95% will be AUTO-DROPPED by the system (REPAIR MODE)
    - 88-94% confidence band has poor WR — do NOT output SHORTs in this range
    - 93-95% band: 100% WR (9/9). 95%+ band: 94.1% WR (48/51). These are the ONLY acceptable SHORT zones.
    - If a setup feels like 90-92% confidence → either find the extra edge to push to 93%+ or SKIP it entirely
  LONG CONFIDENCE RULE (hard floor enforced in code):
    - MINIMUM LONG CONFIDENCE: 88% — any LONG below 88% will be AUTO-DROPPED by the system
    - 85-87% LONG band has 39.1% WR and avg -12.5% P&L — do NOT output LONGs in this range
    - 88-91% band: 52% WR, avg +13.1% P&L. These are the acceptable LONG zones.
    - If a setup feels like 85-87% → either find the extra edge to push to 88%+ or SKIP it entirely
    - CAUTION: 92%+ LONG band only 6 trades at 50% WR, avg -53% P&L. Do NOT force elite ratings — stay in 88-91% zone.
  LONG PATTERNS THAT WIN (prioritize these):
    - "Stage 2 expansion" → 100% WR (3/3 trades)
    - "Stage 2 expansion retest" → 75% WR (3/4 trades)
    - "Stage 2-3 expansion retest" → 60% WR
    - "Bull flag continuation with negative funding" → good
  LONG PATTERNS THAT LOSE (avoid these):
    - "Continuation breakout" standalone → 0% WR
    - "Meme sector" patterns → 0% WR (AVOID meme coins as LONGs)
    - "Momentum continuation" → 0% WR in multiple samples
    - "Stage 2-3 breakout retest" → only 33.3% WR — be cautious
  LONG STAR COINS (proven high WR over multiple trades):
    - AERO: 100% WR (8/8 trades) — strong preference when in Stage 2
    - TIA: 100% WR (4/4 trades) — strong preference
    - JUP: 75% WR (3/4 trades) — good track record
    - EIGEN: 67% WR — acceptable
  LONG POOR COINS (blocked or weak — avoid as LONG signals):
    - ZRO, HYPE, COMP, QNT, WIF, WLD: 0-25% WR → already code-blocked (v46.62/v47.5) — DO NOT generate LONG signals for these coins
    - XLM, SOL: 33% WR → use only with very strong pattern confluence

{SIGNAL_GRAVEYARD}
════════════════════════════════════════════════════════════

DATA TO ANALYZE:
→ See MARKET DATA section in user message below.
════════════════════════════════════════════════════════════
"""

# ── Derived static system prompt (placeholders replaced with references) ──
# This is sent as the cached "system" block — identical every run = cache hit.
WHALE_STREAM_SYSTEM = (
    (MISSION_PROMPT + WHALE_STREAM_PROMPT)
    .replace(
        "{BTC_DOMINANCE_GATE}",
        "→ LIVE BTC DOMINANCE READING: provided in the LIVE GATES section of the user message."
    )
    .replace(
        "{FEAR_GREED_GATE}",
        "→ LIVE FEAR & GREED READING: provided in the LIVE GATES section of the user message."
    )
    .replace(
        "{BTC_MOVE_GATE}",
        "→ LIVE BTC 30-MIN MOVE READING: provided in the LIVE GATES section of the user message."
    )
    .replace(
        "{BTC_24H_GATE}",
        "→ LIVE BTC 24H MOMENTUM READING: provided in the LIVE GATES section of the user message."
    )
    .replace(
        "{COIN_PERFORMANCE}",
        "→ LONG COIN PERFORMANCE SUMMARY: provided in the LIVE GATES section of the user message."
    )
    .replace(
        "{SIGNAL_GRAVEYARD}",
        "→ SIGNAL GRAVEYARD: provided in the LIVE GATES section of the user message."
    )
    .replace(
        "→ See MARKET DATA section in user message below.\n════════════════════════════════════════════════════════════",
        "→ MARKET DATA: provided in the MARKET DATA section of the user message."
    )
)

# ── Dynamic user message template (changes every run — not cached) ──
DYNAMIC_DATA_TEMPLATE = """\
════════════════════════════════════════════════════════════
LIVE INTELLIGENCE GATES (apply BEFORE scoring any coin):

BTC DOMINANCE GATE:
{BTC_DOMINANCE_GATE}

FEAR & GREED GATE:
{FEAR_GREED_GATE}

BTC 30-MIN MOVE GATE:
{BTC_MOVE_GATE}

BTC 24H MOMENTUM GATE (Short-Side Guard):
{BTC_24H_GATE}

════════════════════════════════════════════════════════════
{COIN_PERFORMANCE}

{MTF_BLOCK}
════════════════════════════════════════════════════════════
SIGNAL GRAVEYARD — RECENT TRADE OUTCOMES (Self-Learning Feedback):
{SIGNAL_GRAVEYARD}

════════════════════════════════════════════════════════════
DATA TO ANALYZE:
{MARKET_DATA}
{BATCH_NOTE}"""

# ─────────────────────────────────────────────────────────────
# SECTION 3: MAIN CODE  ← No need to change anything below
# ─────────────────────────────────────────────────────────────

import requests
import time
from datetime import datetime, timezone, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BKK = timezone(timedelta(hours=7))   # Bangkok timezone (UTC+7) — used everywhere


def _parse_conf(sig):
    """Parse confidence value from a signal dict. Returns int (0 if unparseable)."""
    try:
        return int(str(sig.get("conf", "0")).replace("%", "").strip())
    except (ValueError, TypeError):
        return 0


def check_macro_event_risk(window_high_h: float = 4, window_medium_h: float = 12) -> list:
    """
    Return warning strings for FOMC/CPI events within the risk window.
    Empty list = no events → trade normally.

    Risk tiers:
      HIGH   (≤4h)  → 🔴 avoid new entries, confidence ≥93% required
      MEDIUM (≤12h) → 🟡 prefer SHORT/mean-reversion, caution on LONGs
      POST   (0-2h after event) → 🔴 market still settling, avoid entries
    """
    now = datetime.now(timezone.utc)
    warnings = []
    for date_str, time_str, name, note in MACRO_EVENTS_2026:
        event_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        event_dt = event_dt.replace(tzinfo=timezone.utc)
        delta_h = (event_dt - now).total_seconds() / 3600
        if -2 <= delta_h <= 0:
            warnings.append(
                f"🔴 {name} JUST HAPPENED {abs(delta_h):.1f}h AGO — market still volatile. "
                f"AVOID NEW ENTRIES for at least 2h post-event. ({note})"
            )
        elif 0 < delta_h <= window_high_h:
            warnings.append(
                f"🔴 {name} IN {delta_h:.1f}h — HIGH RISK WINDOW. {note}. "
                f"Only output signals confidence ≥93%. Default action = STAY OUT."
            )
        elif window_high_h < delta_h <= window_medium_h:
            warnings.append(
                f"🟡 {name} IN {delta_h:.0f}h — CAUTION WINDOW. {note}. "
                f"Prefer SHORT/mean-reversion setups. Avoid LONG breakouts."
            )
    return warnings


def check_token_unlock_risk(horizon_hours: int = 48, threshold_pct: float = 3.0) -> list:
    """
    Check DefiLlama emission API for upcoming large token unlocks.
    Warns when ≥threshold_pct% of circulating supply unlocks within horizon_hours.
    Fails silently — never blocks the trading cycle.

    Returns list of warning strings (empty = no large unlocks found or API unavailable).
    """
    warnings = []
    try:
        now_utc = datetime.now(timezone.utc)
        horizon_dt = now_utc + timedelta(hours=horizon_hours)

        for coin, slug in _UNLOCK_SLUG_MAP.items():
            try:
                url = f"https://api.llama.fi/emission/{slug}"
                resp = _SESSION.get(url, timeout=5)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if not isinstance(data, dict):
                    continue

                # DefiLlama emission format:
                # { "circSupply": float, "maxSupply": float,
                #   "events": [{"date": unix_ts, "amount": tokens, "category": "..."}, ...] }
                circ = float(data.get("circSupply") or 0)
                if circ <= 0:
                    continue

                for event in (data.get("events") or []):
                    ts = event.get("date", 0)
                    if not ts:
                        continue
                    event_dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                    if now_utc <= event_dt <= horizon_dt:
                        amount = float(event.get("amount") or 0)
                        pct = (amount / circ) * 100
                        if pct >= threshold_pct:
                            hours_until = (event_dt - now_utc).total_seconds() / 3600
                            category = event.get("category", "unlock")
                            warnings.append(
                                f"⚠️ TOKEN UNLOCK — {coin}: {pct:.1f}% of circulating supply "
                                f"unlocks in {hours_until:.0f}h ({category}). "
                                f"AVOID LONG {coin}. Consider SHORT if setup confirms."
                            )
            except Exception:
                pass  # per-coin failure — skip and continue

    except Exception:
        pass  # whole function fail — never crash the bot

    return warnings


def _make_retry_session(retries=4, backoff=1.5):
    """Create a requests Session with automatic retry on transient errors."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session

_SESSION = _make_retry_session()

# Always resolve paths relative to this script's folder
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def fetch_bybit_funding_rates():
    """
    Fetch ALL Bybit linear perpetual tickers in one call.
    Returns dict: { "BTC": {"funding_rate": 0.0001, "oi_usd": 1234567890}, ... }
    Funding rate > 0 = longs pay shorts (bullish sentiment, potential SHORT squeeze).
    Funding rate < 0 = shorts pay longs (bearish sentiment, potential LONG squeeze).
    """
    url = "https://api.bybit.com/v5/market/tickers"
    try:
        resp = _SESSION.get(url, params={"category": "linear"}, timeout=15)
        resp.raise_for_status()
        tickers = resp.json().get("result", {}).get("list", [])
        funding_map = {}
        for t in tickers:
            sym = t.get("symbol", "")
            if sym.endswith("USDT") and not sym.endswith("USDT3L") and not sym.endswith("USDT3S"):
                coin = sym[:-4]
                try:
                    fr  = float(t.get("fundingRate", 0) or 0)
                    oi  = float(t.get("openInterestValue", 0) or 0)
                    funding_map[coin] = {"funding_rate": fr, "oi_usd": oi}
                except (ValueError, TypeError):
                    pass
        print(f"   ✓ Bybit: {len(funding_map)} perp funding rates loaded")
        return funding_map
    except Exception as e:
        print(f"   ⚠ Bybit funding rate fetch failed ({e}) — skipping")
        return {}


def fetch_signal_graveyard():
    """
    Read the last 20 WIN/LOSS resolved trades from Google Sheets.
    Returns a formatted table string injected into the Claude prompt.
    This creates a self-improving feedback loop — Claude learns from its own
    recent performance before generating new signals.
    """
    try:
        creds_path = os.path.join(SCRIPT_DIR, GOOGLE_CREDENTIALS_FILE)
        if not os.path.exists(creds_path):
            return "", 50, ""

        # Use google.oauth2 directly — bypasses gspread.auth which fails on some Python 3.14 setups
        from google.oauth2.service_account import Credentials as _GCreds
        try:
            from gspread.client import Client as _GClient
        except ImportError:
            import subprocess as _sp
            _sp.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "gspread", "--quiet"])
            from gspread.client import Client as _GClient
        _SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = _GCreds.from_service_account_file(creds_path, scopes=_SCOPES)
        client = _GClient(auth=creds)
        sheet  = client.open_by_key(GOOGLE_SHEET_ID).sheet1

        all_rows = sheet.get_all_values()
        if len(all_rows) < 2:
            return "", 50, ""

        # Collect all WIN/LOSS rows (skip OPEN, EXPIRED, NO SIGNAL)
        resolved = []
        for row in all_rows[1:]:  # skip header
            while len(row) < 17:
                row.append("")
            status = row[11].strip()
            if status not in ("WIN", "LOSS"):
                continue
            signal_col = row[1].strip()
            direction  = "LONG" if ("Long" in signal_col or "🟢" in signal_col) else "SHORT"
            pattern    = row[9].strip()

            # Skip malformed / fake entries so they don't corrupt Claude's
            # feedback loop. Two types:
            # 1. Wrong P&L sign (SL/TP on wrong side of entry)
            # 2. Tiny P&L abs < 5% — fake instant resolution (TP/SL within
            #    noise of entry price). Real 10x trades always move ≥ 0.5% raw.
            try:
                pnl_val = float(row[15].strip().replace("%", ""))
                if direction == "SHORT" and status == "LOSS" and pnl_val > 0:
                    continue  # malformed SHORT — SL below entry
                if direction == "LONG" and status == "WIN" and pnl_val < 0:
                    continue  # malformed LONG — TP below entry
                if direction == "SHORT" and status == "WIN" and pnl_val < 0:
                    continue  # malformed SHORT WIN with negative P&L
                if direction == "LONG" and status == "LOSS" and pnl_val > 0:
                    continue  # malformed LONG LOSS with positive P&L
                if abs(pnl_val) < 5:
                    continue  # fake instant resolution — too small to be real
            except (ValueError, TypeError):
                pass  # can't parse P&L — leave entry in

            resolved.append({
                "coin":      row[0].strip(),
                "direction": direction,
                "pattern":   (pattern[:38] + "…") if len(pattern) > 38 else (pattern or "—"),
                "entry":     row[3].strip(),
                "tp_hit":    row[14].strip() or "—",
                "pnl":       row[15].strip() or "—",
                "status":    status,
            })

        if not resolved:
            return "", 50, ""

        # ── Coin performance summary (last 30 resolved LONGs) ──────
        _coin_perf = {}
        _resolved_longs = [r for r in resolved if r["direction"] == "LONG"]
        _recent_longs_30 = _resolved_longs[-30:]  # last 30 resolved LONGs
        for _row in _recent_longs_30:
            _coin = _row["coin"]
            if _coin not in _coin_perf:
                _coin_perf[_coin] = {"w": 0, "l": 0}
            if _row["status"] == "WIN":
                _coin_perf[_coin]["w"] += 1
            else:
                _coin_perf[_coin]["l"] += 1

        _coin_lines = []
        for _coin, _stats in sorted(_coin_perf.items(), key=lambda x: -(x[1]["w"] / (x[1]["w"] + x[1]["l"]))):
            _n = _stats["w"] + _stats["l"]
            if _n < 2:
                continue
            _wr = _stats["w"] / _n
            _emoji = "⭐" if _wr >= 0.70 else "✅" if _wr >= 0.55 else "⚠️" if _wr >= 0.40 else "❌"
            _coin_lines.append(f"  {_emoji} {_coin:<10} {_stats['w']}W/{_stats['l']}L ({_wr*100:.0f}%)")

        if _coin_lines:
            coin_perf_text = (
                f"LONG COIN PERFORMANCE (last 30 resolved, min 2 trades):\n"
                + "\n".join(_coin_lines[:10])
            )
        else:
            coin_perf_text = "LONG COIN PERFORMANCE: insufficient data (need ≥2 resolved LONGs per coin)"

        # Most recent 20 only
        recent   = resolved[-20:]
        wins     = sum(1 for r in recent if r["status"] == "WIN")
        losses   = len(recent) - wins
        win_rate = wins / len(recent) * 100

        # SHORT-specific stats from recent 20
        recent_shorts = [r for r in recent if r["direction"] == "SHORT"]
        recent_longs  = [r for r in recent if r["direction"] == "LONG"]
        short_wins    = sum(1 for r in recent_shorts if r["status"] == "WIN")
        long_wins     = sum(1 for r in recent_longs  if r["status"] == "WIN")
        short_wr = (short_wins / len(recent_shorts) * 100) if recent_shorts else 50  # 50=neutral when no recent shorts (prevents false 95% floor)
        long_wr  = (long_wins  / len(recent_longs)  * 100) if recent_longs  else 0

        # Auto-blacklist: coins with 3+ SHORT losses and 0 SHORT wins (ALL resolved, not just recent 20)
        all_shorts     = [r for r in resolved if r["direction"] == "SHORT"]
        short_loss_map = {}
        short_win_map  = {}
        for r in all_shorts:
            c = r["coin"]
            if r["status"] == "LOSS":
                short_loss_map[c] = short_loss_map.get(c, 0) + 1
            else:
                short_win_map[c]  = short_win_map.get(c, 0) + 1
        blacklisted = [c for c, cnt in short_loss_map.items()
                       if cnt >= 3 and short_win_map.get(c, 0) == 0]

        # ── Compact graveyard (saves ~40% tokens vs wide-table format) ──────────
        # Permanent ban lists are already in the cached system prompt — skip here.
        _in_repair_mode = os.path.exists(os.path.join(SCRIPT_DIR, "short_repair.flag"))
        lines = []

        # Single-line stats header (was 3 lines)
        lines.append(
            f"GRAVEYARD [{len(recent)}T | WR:{win_rate:.0f}%({wins}W/{losses}L) | "
            f"L:{long_wr:.0f}%({long_wins}W/{len(recent_longs)-long_wins}L) | "
            f"S:{short_wr:.0f}%({short_wins}W/{len(recent_shorts)-short_wins}L)]"
        )
        if not _in_repair_mode:
            if short_wr < 40:
                lines.append(f"⚠️ S_WR CRITICAL ({short_wr:.0f}%<40%) — REQUIRE SHORT CONF≥95% OR SKIP")
            elif short_wr < 45:
                lines.append(f"⚠️ S_WR LOW ({short_wr:.0f}%<45%) — REQUIRE SHORT CONF≥93%")
        if blacklisted:
            lines.append(f"🚫 S_AUTO_BAN(3+L,0W): {', '.join(blacklisted)}")

        # Compact table — 67 chars/row vs 100 (saves ~33% per row × 20 rows)
        lines.append(f"{'COIN':<8} {'D':<2} {'PATTERN':<28} {'ENTRY':<12} {'TP':<4} {'PNL%':<7} RES")
        lines.append("─" * 67)
        for r in recent:
            pat = (r['pattern'][:26] + "…") if len(r['pattern']) > 26 else r['pattern']
            d   = "L" if r["direction"] == "LONG" else "S"
            res = "WIN" if r["status"] == "WIN" else "LOSS"
            lines.append(
                f"{r['coin']:<8} {d:<2} {pat:<28} {r['entry']:<12} "
                f"{r['tp_hit']:<4} {r['pnl']:<7} {res}"
            )
        lines.append("─" * 67)

        # ── SHORT recovery guidance (injected when repair mode is active) ──
        if _in_repair_mode:
            # Compute H/FF WRs dynamically from current resolved data
            _rc_coins = {"H": (0, 0), "FF": (0, 0)}
            for _rr in resolved:
                _rrc = _rr.get("coin", "").upper()
                if _rrc in _rc_coins and _rr["direction"] == "SHORT":
                    _rw, _rl = _rc_coins[_rrc]
                    if _rr["status"] == "WIN":
                        _rc_coins[_rrc] = (_rw + 1, _rl)
                    else:
                        _rc_coins[_rrc] = (_rw, _rl + 1)
            def _rc_fmt(coin, w, l):
                _tot = w + l
                _wr = f"{w/(_tot)*100:.0f}%" if _tot > 0 else "N/A"
                _note = (
                    "← BEST — prioritise" if w > 0 and l == 0 else
                    "← Promising" if w > 0 and (l == 0 or w >= l) else
                    "← Monitor closely" if _tot > 0 else
                    "← No trades yet"
                )
                return f"   {coin:<5} ({w}W/{l}L — {_wr} WR) {_note}"
            _rc_lines = [_rc_fmt(c, *v) for c, v in _rc_coins.items()]
            lines.append(
                "⚠️  SHORT RECOVERY MODE ACTIVE — ONLY output SHORT signals for these approved coins:\n"
                + "\n".join(_rc_lines) + "\n"
                "   For all other coins: DO NOT output SHORT signals during recovery phase.\n"
                "   Exception: if setup is 95%+ confidence and coin is NOT on the permanent ban list,\n"
                "   you may include it — but default to STAY OUT for SHORTs on unknown coins."
            )

        # ── LONG dynamic avoid list — compact 1-line (perm bans already in cached system prompt) ──
        _long_loss_map = {}
        _long_win_map  = {}
        for _lr in _resolved_longs:
            _lc = _lr["coin"]
            if _lr["status"] == "LOSS":
                _long_loss_map[_lc] = _long_loss_map.get(_lc, 0) + 1
            else:
                _long_win_map[_lc]  = _long_win_map.get(_lc, 0) + 1
        _long_avoid = sorted([c for c, cnt in _long_loss_map.items()
                              if cnt >= 2 and _long_win_map.get(c, 0) == 0])
        _long_avoid_extra = [c for c in _long_avoid if c not in LONG_COIN_BLOCKLIST]
        if _long_avoid_extra:
            lines.append(f"🚫 L_AVOID(0%WR≥2T): {', '.join(_long_avoid_extra)} — skip unless conf≥97%")

        # ── Streak warning: graveyard memory trap (v47.43) ───────────────────
        # Detects coins with ≥3 consecutive same-direction losses at the tail of their history.
        # Target: EIGEN-pattern — early wins inflate graveyard WR, hiding momentum exhaustion.
        _streak_warns = []
        for _dir_key, _dir_label, _dir_blocklist in [
            ("LONG",  "LONG",  LONG_COIN_BLOCKLIST),
            ("SHORT", "SHORT", SHORT_COIN_BLOCKLIST),
        ]:
            _dir_trades = [r for r in resolved if r["direction"] == _dir_key]
            _by_coin = {}
            for _r in _dir_trades:
                _by_coin.setdefault(_r["coin"], []).append(_r)
            for _coin, _coin_trades in _by_coin.items():
                if _coin in _dir_blocklist:
                    continue   # already blocked — no need to warn
                if len(_coin_trades) < 4:
                    continue   # too few trades; skip to avoid noise
                _consec_losses = 0
                for _t in reversed(_coin_trades):
                    if _t["status"] == "LOSS":
                        _consec_losses += 1
                    else:
                        break
                if _consec_losses >= 3:
                    _sw_wins = sum(1 for _t in _coin_trades if _t["status"] == "WIN")
                    _sw_loss = len(_coin_trades) - _sw_wins
                    _streak_warns.append(
                        f"⚠ STREAK TRAP: {_coin} {_dir_label} — "
                        f"{_sw_wins}W/{_sw_loss}L all-time but {_consec_losses} consecutive recent losses. "
                        f"Graveyard WR inflated by early wins. Do NOT boost confidence. Apply standard floor."
                    )
        for _sw in _streak_warns:
            lines.append(_sw)

        # ── LONG proven whitelist + SHORT proven list (v47.43) ────────────────
        # Dynamically computed from all resolved trades so the lists self-update.
        _lwl_map = {}   # coin -> (wins, total) for LONGs
        _swl_map = {}   # coin -> (wins, total) for SHORTs
        for _pr in resolved:
            _pc = str(_pr.get("coin", "")).upper()
            _pw = 1 if _pr["status"] == "WIN" else 0
            if _pr["direction"] == "LONG":
                _w2, _t2 = _lwl_map.get(_pc, (0, 0))
                _lwl_map[_pc] = (_w2 + _pw, _t2 + 1)
            else:
                _w2, _t2 = _swl_map.get(_pc, (0, 0))
                _swl_map[_pc] = (_w2 + _pw, _t2 + 1)

        _proven_long_wl = sorted([
            c for c, (w, t) in _lwl_map.items()
            if t >= 3 and (w / t) >= 0.60 and c not in LONG_COIN_BLOCKLIST
        ])
        if _proven_long_wl:
            lines.append(
                f"✅ L_PROVEN(≥60%WR,≥3T): {', '.join(_proven_long_wl)} — standard floor. "
                f"ALL other LONG coins require conf≥95% (unproven or <60% WR)."
            )

        _proven_short_wl = sorted([
            c for c, (w, t) in _swl_map.items()
            if t >= 2 and w == t and c not in SHORT_COIN_BLOCKLIST
        ])
        if _proven_short_wl:
            lines.append(
                f"✅ S_PROVEN(100%WR,≥2T): {', '.join(_proven_short_wl)} — "
                f"priority SHORT targets as H approaches floor. Stage 4-5 breakdown patterns confirmed."
            )
        # ── end proven lists ──────────────────────────────────────────────────

        graveyard_text = "\n".join(lines)

        # ── Task 2: MTF bias win-rate table from pattern_memory.json ────────
        try:
            _mem_path = os.path.join(os.path.dirname(__file__), "pattern_memory.json")
            if os.path.exists(_mem_path):
                with open(_mem_path, "r", encoding="utf-8") as _mf:
                    _mem = json.load(_mf)
                _mtf_stats = _mem.get("mtf_stats", {})
                if _mtf_stats:
                    _mtf_rows = []
                    for _bias, _cnts in sorted(_mtf_stats.items()):
                        _w = _cnts.get("wins", 0)
                        _l = _cnts.get("losses", 0)
                        _tot = _w + _l
                        if _tot < 3:
                            continue          # not enough data yet
                        _wr = 100 * _w / _tot
                        _flag = "✅" if _wr >= 60 else ("⚠️" if _wr >= 45 else "🚫")
                        _mtf_rows.append(f"  {_flag} {_bias:<28s} {_w}W/{_l}L  {_wr:.0f}% WR")
                    if _mtf_rows:
                        graveyard_text += (
                            "\n\nMTF_BIAS WIN RATE (4H+1H structure at signal time):\n"
                            + "\n".join(_mtf_rows)
                            + "\n  ✅≥60% = favour  ⚠️=neutral  🚫<45% = avoid"
                        )
        except Exception as _mtf_e:
            pass   # non-critical — graveyard still works without mtf table

        # ── Task 3 (v47.21): Adaptive confidence floors from coin_stats ─────
        # Raise the effective bar for habitually weak coins; note strong ones.
        try:
            _mem_path2 = os.path.join(os.path.dirname(__file__), "pattern_memory.json")
            if os.path.exists(_mem_path2):
                with open(_mem_path2, "r", encoding="utf-8") as _mf2:
                    _mem2 = json.load(_mf2)
                _coin_stats = _mem2.get("coin_stats", {})
                _weak_floors  = []   # coins needing higher confidence bar
                _strong_notes = []   # coins with proven track record
                for _cn, _cs in _coin_stats.items():
                    _cw  = _cs.get("wins", 0)
                    _cl  = _cs.get("losses", 0)
                    _ct  = _cw + _cl
                    if _ct < 3:
                        continue
                    _cwr = 100 * _cw / _ct
                    if _cwr < 40:
                        _weak_floors.append(f"{_cn}(WR={_cwr:.0f}%,{_ct}T→require≥93%)")
                    elif _cwr >= 70 and _ct >= 5:
                        _strong_notes.append(f"{_cn}(WR={_cwr:.0f}%,{_ct}T)")
                if _weak_floors or _strong_notes:
                    _adaptive_lines = ["\n\nADAPTIVE CONFIDENCE FLOORS (from trade history):"]
                    if _weak_floors:
                        _adaptive_lines.append(
                            "⬆️  RAISE FLOOR — these coins have poor WR; require ≥93% confidence:\n"
                            + "  " + ", ".join(_weak_floors)
                        )
                    if _strong_notes:
                        _adaptive_lines.append(
                            "✅  PROVEN coins — standard 88% floor applies; they have delivered:\n"
                            + "  " + ", ".join(_strong_notes)
                        )
                    graveyard_text += "\n".join(_adaptive_lines)
        except Exception:
            pass   # non-critical

        # ── Option A (v47.23): Inject recent AVOID lessons per coin ──────────
        # Debrief agent writes per-coin AVOID lessons to pattern_memory coin_lessons.
        # Claude sees these at signal-generation time — mistakes not repeated at source.
        try:
            _mem_path3 = os.path.join(os.path.dirname(__file__), "pattern_memory.json")
            if os.path.exists(_mem_path3):
                with open(_mem_path3, "r", encoding="utf-8") as _mf3:
                    _mem3 = json.load(_mf3)
                _coin_lessons = _mem3.get("coin_lessons", {})
                _avoid_lines = []
                for _coin_name, _dirs in _coin_lessons.items():
                    for _dir_name, _lessons in _dirs.items():
                        # Only inject AVOID-flagged lessons
                        _avoid = [l for l in _lessons if l.startswith("[AVOID]")]
                        for _lesson_txt in _avoid[-2:]:  # keep last 2 per coin+direction
                            _avoid_lines.append(
                                f"  ⛔ {_coin_name} {_dir_name}: {_lesson_txt[len('[AVOID]'):].strip()}"
                            )
                if _avoid_lines:
                    graveyard_text += (
                        "\n\nRECENT AVOID LESSONS (from post-trade debrief — DO NOT repeat these):\n"
                        + "\n".join(_avoid_lines[:15])  # cap at 15 to stay within token budget
                    )
        except Exception:
            pass   # non-critical — graveyard still works without lessons
        # ── end AVOID lessons ─────────────────────────────────────────────────

        # ── Option B (v47.25): Pattern WR injection ───────────────────────────
        # Compute per-pattern WR from debriefs in pattern_memory.json.
        # Inject top 3 winners (WR≥65%, ≥3 trades) and worst 3 losers (WR≤40%, ≥3 trades).
        try:
            _mem_path4 = os.path.join(os.path.dirname(__file__), "pattern_memory.json")
            if os.path.exists(_mem_path4):
                with open(_mem_path4, "r", encoding="utf-8") as _mf4:
                    _mem4 = json.load(_mf4)
                _pat_stats: dict = {}  # pattern → {wins, losses}
                for _db in _mem4.get("debriefs", []):
                    _pat = _db.get("pattern", "").strip()
                    if not _pat or _pat in ("-", "N/A", "UNKNOWN", ""):
                        continue
                    # Normalise: take first 60 chars to avoid runaway pattern text
                    _pat = _pat[:60]
                    if _pat not in _pat_stats:
                        _pat_stats[_pat] = {"wins": 0, "losses": 0}
                    _outcome = _db.get("outcome", "").upper()
                    if _outcome == "WIN":
                        _pat_stats[_pat]["wins"] += 1
                    elif _outcome == "LOSS":
                        _pat_stats[_pat]["losses"] += 1

                _pat_lines = []
                _good_pats = sorted(
                    [(_p, _v) for _p, _v in _pat_stats.items()
                     if _v["wins"] + _v["losses"] >= 3
                     and _v["wins"] / (_v["wins"] + _v["losses"]) >= 0.65],
                    key=lambda x: x[1]["wins"] / (x[1]["wins"] + x[1]["losses"]),
                    reverse=True,
                )[:3]
                _bad_pats = sorted(
                    [(_p, _v) for _p, _v in _pat_stats.items()
                     if _v["wins"] + _v["losses"] >= 3
                     and _v["wins"] / (_v["wins"] + _v["losses"]) <= 0.40],
                    key=lambda x: x[1]["wins"] / (x[1]["wins"] + x[1]["losses"]),
                )[:3]

                if _good_pats or _bad_pats:
                    _pat_lines.append("\n\nPATTERN WIN RATES (from live debrief history):")
                    if _good_pats:
                        _pat_lines.append("  ✅ PROVEN WINNERS — prioritise signals matching these patterns:")
                        for _pp, _pv in _good_pats:
                            _pn = _pv["wins"] + _pv["losses"]
                            _pwr = 100 * _pv["wins"] / _pn
                            _pat_lines.append(f"    [{_pwr:.0f}% WR / {_pn} trades] {_pp}")
                    if _bad_pats:
                        _pat_lines.append("  🚫 CHRONIC LOSERS — avoid signals that match these patterns:")
                        for _pp, _pv in _bad_pats:
                            _pn = _pv["wins"] + _pv["losses"]
                            _pwr = 100 * _pv["wins"] / _pn
                            _pat_lines.append(f"    [{_pwr:.0f}% WR / {_pn} trades] {_pp}")
                    graveyard_text += "\n".join(_pat_lines)
        except Exception:
            pass   # non-critical
        # ── end Pattern WR injection ──────────────────────────────────────────

        # ── Task 4 (v47.33): Probation coin caution ───────────────────────────
        try:
            _prob_lines: list = []
            if BOT_PROBATION_LONGS:
                _prob_lines.append(
                    "  🔶 LONG PROBATION: " + ", ".join(sorted(BOT_PROBATION_LONGS))
                    + " — recently expelled from auto-blocklist; require ≥95% confidence before generating a signal"
                )
            if BOT_PROBATION_SHORTS:
                _prob_lines.append(
                    "  🔶 SHORT PROBATION: " + ", ".join(sorted(BOT_PROBATION_SHORTS))
                    + " — recently expelled from auto-blocklist; require ≥95% confidence before generating a signal"
                )
            if _prob_lines:
                graveyard_text += (
                    "\n\nPROBATION COINS (recently expelled from auto-blocklist — treat like borderline candidates):\n"
                    + "\n".join(_prob_lines)
                )
        except Exception:
            pass   # non-critical
        # ── end Probation coin caution ────────────────────────────────────────

        # ── Task 5 (v47.35): Soft-avoid from coin P&L ────────────────────────
        try:
            if BOT_SOFT_AVOID:
                graveyard_text += (
                    "\n\nUNDERPERFORMING COINS (historically negative avg P&L — P&L-driven caution, not a hard block):\n"
                    "  ⚠ SOFT-AVOID: " + ", ".join(sorted(BOT_SOFT_AVOID))
                    + " — avg P&L below -0.5% over ≥10 trades; only include if setup is exceptionally clean (95%+ confidence)"
                )
        except Exception:
            pass  # non-critical
        # ── end Soft-avoid injection ──────────────────────────────────────────

        # ── v47.36C: Win-streak coins — positive momentum signal ─────────────
        try:
            if BOT_WIN_STREAK:
                graveyard_text += (
                    "\n\nHOT-STREAK COINS (≥3 consecutive wins — momentum is on their side):\n"
                    "  ✅ WIN STREAK: " + ", ".join(sorted(BOT_WIN_STREAK))
                    + " — currently on a winning run; you may include these at slightly lower confidence (≥85%) if the setup is clean"
                )
        except Exception:
            pass  # non-critical
        # ── end Win-streak injection ──────────────────────────────────────────

        print(f"   ✓ Signal Graveyard: {len(recent)} trades (overall {win_rate:.0f}% WR | long {long_wr:.0f}% | short {short_wr:.0f}%)")
        if blacklisted:
            print(f"   🚫 Short blacklist: {', '.join(blacklisted)}")
        if _long_avoid:
            print(f"   🚫 Long avoid list : {', '.join(_long_avoid)}")
        print(f"   📈 Coin perf summary: {len(_coin_lines)} coins ranked (from last 30 resolved LONGs)")
        if _in_repair_mode:
            print(f"   🔧 SHORT RECOVERY MODE — approved coins injected into graveyard prompt")
        return graveyard_text, short_wr, coin_perf_text

    except Exception as e:
        print(f"   ⚠ Signal Graveyard fetch failed ({e}) — skipping")
        try:
            send_to_telegram(None, formatted_msg=(
                f"⚠️ <b>WHALE-STREAM BOT WARNING</b>\n"
                f"Signal Graveyard fetch failed — Claude will run without trade history.\n"
                f"Error: {str(e)[:200]}"
            ))
        except Exception:
            pass
        return "", 50, ""  # neutral WR — no filtering applied when graveyard unavailable


def fetch_btc_dominance():
    """
    Fetch BTC dominance % from CoinGecko global endpoint (free, no key).
    Returns a formatted context string for injection into the Claude prompt.
    BTC dominance rising = alts underperform = penalize LONG signals.
    BTC dominance falling = alt season = boost LONG confidence.
    """
    url = "https://api.coingecko.com/api/v3/global"
    try:
        resp = _SESSION.get(url, timeout=15)
        resp.raise_for_status()
        data  = resp.json().get("data", {})
        btc_d = data.get("market_cap_percentage", {}).get("btc", 0)
        eth_d = data.get("market_cap_percentage", {}).get("eth", 0)
        total_mcap_chg = data.get("market_cap_change_percentage_24h_usd", 0)

        # Classify dominance regime
        if btc_d >= 58:
            level    = "EXTREME — Severe alt headwind"
            guidance = (
                "BTC is absorbing nearly all capital. "
                "REJECT all alt LONG signals with confidence < 92%. "
                "SHORT setups on weak alts are strongly favored."
            )
        elif btc_d >= 54:
            level    = "HIGH — Moderate alt headwind"
            guidance = (
                "BTC dominance elevated. Rotation INTO BTC likely. "
                "Apply -8 point penalty to all alt LONG scores. "
                "Only select alt LONGs with rock-solid setups (90%+ confidence)."
            )
        elif btc_d >= 50:
            level    = "NEUTRAL — Balanced market"
            guidance = (
                "BTC and alts roughly balanced. "
                "Apply standard confidence thresholds. "
                "No bonus or penalty for LONG/SHORT."
            )
        elif btc_d >= 45:
            level    = "LOW — Alt season conditions"
            guidance = (
                "Capital rotating INTO alts. Favorable for alt LONGs. "
                "Apply +5 point bonus to high-conviction alt LONG scores. "
                "SHORT signals need extra confirmation — momentum favors bulls."
            )
        else:
            level    = "VERY LOW — Peak alt season"
            guidance = (
                "Peak alt season. Alts outperforming BTC across the board. "
                "Maximize LONG opportunities. "
                "SHORT signals require extremely strong exhaustion evidence."
            )

        lines = [
            f"BTC Dominance : {btc_d:.2f}%  [{level}]",
            f"ETH Dominance : {eth_d:.2f}%",
            f"Total MCap 24h: {total_mcap_chg:+.2f}%",
            f"Gate Rule     : {guidance}",
        ]
        result = "\n".join(lines)
        print(f"   ✓ BTC Dominance: {btc_d:.2f}% [{level}]")
        return result

    except Exception as e:
        print(f"   ⚠ BTC Dominance fetch failed ({e}) — skipping gate")
        return "BTC Dominance: unavailable — apply standard thresholds."


def fetch_fear_greed():
    """
    Fetch Crypto Fear & Greed Index from alternative.me (free, no key).
    Gets today + yesterday to calculate momentum (rising/falling sentiment).
    Returns formatted string for Claude prompt injection.
    0-24 = Extreme Fear | 25-44 = Fear | 45-55 = Neutral
    56-74 = Greed | 75-100 = Extreme Greed
    """
    url = "https://api.alternative.me/fng/?limit=2"
    try:
        resp = _SESSION.get(url, timeout=15)
        resp.raise_for_status()
        entries = resp.json().get("data", [])
        if not entries:
            return "Fear & Greed Index: unavailable — apply standard thresholds."

        today     = entries[0]
        yesterday = entries[1] if len(entries) > 1 else None

        score_now  = int(today.get("value", 50))
        label_now  = today.get("value_classification", "Neutral")
        score_prev = int(yesterday.get("value", score_now)) if yesterday else score_now
        delta      = score_now - score_prev
        trend      = f"{'▲ Rising' if delta > 0 else '▼ Falling' if delta < 0 else '→ Flat'} ({delta:+d} from yesterday)"

        # Classify and generate trading guidance
        if score_now <= 24:
            zone     = "EXTREME FEAR"
            guidance = (
                "Market in panic. Historically the best LONG entry zone. "
                "Smart money accumulates here. Strongly favor LONG setups. "
                "SHORTs are contrarian and risky — avoid unless technical breakdown is clear."
            )
        elif score_now <= 44:
            zone     = "FEAR"
            guidance = (
                "Market cautious. Good conditions for LONGs on strong setups. "
                "Avoid forcing trades. Quality over quantity."
            )
        elif score_now <= 55:
            zone     = "NEUTRAL"
            guidance = (
                "Balanced sentiment. No emotional edge either direction. "
                "Apply standard analysis. Let technicals decide."
            )
        elif score_now <= 74:
            zone     = "GREED"
            guidance = (
                "Market getting greedy. LONG setups need extra confirmation — "
                "late buyers get trapped. SHORT setups on exhausted coins are attractive. "
                "Tighten confidence threshold for LONGs to 90%+."
            )
        else:
            zone     = "EXTREME GREED"
            guidance = (
                "Market in euphoria — historically the highest-risk zone for LONGs. "
                "REJECT alt LONG signals below 93% confidence. "
                "HIGH-PRIORITY SHORT setups on overextended coins. "
                "Apply ANTI-FOMO filter aggressively."
            )

        # Trend modifier
        if delta >= 10:
            trend_note = "Sentiment ACCELERATING upward — crowd FOMO building."
        elif delta <= -10:
            trend_note = "Sentiment COLLAPSING — panic selling, watch for capitulation LONG entries."
        else:
            trend_note = "Sentiment relatively stable."

        lines = [
            f"Fear & Greed Index : {score_now}/100  [{zone}]",
            f"Yesterday          : {score_prev}/100  |  Trend: {trend}",
            f"Trend Note         : {trend_note}",
            f"Gate Rule          : {guidance}",
        ]
        result = "\n".join(lines)
        print(f"   ✓ Fear & Greed: {score_now}/100 [{zone}] {trend}")
        return result

    except Exception as e:
        print(f"   ⚠ Fear & Greed fetch failed ({e}) — skipping")
        return "Fear & Greed Index: unavailable — apply standard thresholds."


def fetch_btc_move_gate():
    """
    Check if BTC made a sharp move (>2%) in the last 30 minutes.
    Uses Bybit kline (candlestick) API — free, no key needed.
    Sharp BTC moves mean the market is repricing — signals on stale data are dangerous.
    """
    url = "https://api.bybit.com/v5/market/kline"
    try:
        resp = _SESSION.get(url, params={
            "category": "spot",
            "symbol":   "BTCUSDT",
            "interval": "30",    # 30-minute candles
            "limit":    "3",     # current + 2 completed candles (90 min window)
        }, timeout=15)
        resp.raise_for_status()
        candles = resp.json().get("result", {}).get("list", [])

        if len(candles) < 2:
            return "BTC 30-min move: unavailable — proceed with standard caution."

        # Bybit kline format: [startTime, open, high, low, close, volume, turnover]
        # candles[0] = most recent (current/forming candle)
        # candles[1] = last completed 30-min candle
        current = candles[0]
        prev    = candles[1]
        prev2   = candles[2] if len(candles) > 2 else candles[1]

        close_now  = float(current[4])
        open_30m   = float(prev[1])
        open_60m   = float(prev2[1])
        move_30m   = (close_now - open_30m) / open_30m * 100
        move_60m   = (close_now - open_60m) / open_60m * 100
        abs_30m    = abs(move_30m)

        if abs_30m >= 3.0:
            alert = "🚨 EXTREME MOVE"
            guidance = (
                f"BTC moved {move_30m:+.2f}% in 30 minutes. Market is violently repricing. "
                "Signals generated now are on stale data. "
                "STRONGLY RECOMMENDED: Output STAY OUT unless a setup is >93% confidence. "
                "If outputting signals, widen all stop losses by 2% to absorb volatility noise."
            )
        elif abs_30m >= 2.0:
            alert = "⚠️ SIGNIFICANT MOVE"
            guidance = (
                f"BTC moved {move_30m:+.2f}% in 30 minutes. Elevated volatility. "
                "Tighten confidence threshold to 91%+. "
                "Widen stop losses by 1-2%. Prefer signals moving WITH BTC direction."
            )
        elif abs_30m >= 1.0:
            alert = "📊 MODERATE MOVE"
            guidance = (
                f"BTC moved {move_30m:+.2f}% in 30 minutes. Normal trading range. "
                "Proceed with standard analysis. Monitor closely after entry."
            )
        else:
            alert = "✅ STABLE"
            guidance = (
                f"BTC flat ({move_30m:+.2f}% in 30min). "
                "Excellent conditions for signal analysis. Standard thresholds apply."
            )

        lines = [
            f"BTC Price Now : ${close_now:>10,.2f}",
            f"30-min Move   : {move_30m:+.2f}%  {'📈 UP' if move_30m > 0 else '📉 DOWN'}  [{alert}]",
            f"60-min Move   : {move_60m:+.2f}%  {'📈 UP' if move_60m > 0 else '📉 DOWN'}",
            f"Gate Rule     : {guidance}",
        ]
        result = "\n".join(lines)
        print(f"   ✓ BTC Move Gate: {move_30m:+.2f}% (30min) [{alert}]")
        return result

    except Exception as e:
        print(f"   ⚠ BTC Move Gate fetch failed ({e}) — skipping")
        return "BTC 30-min move: unavailable — proceed with standard caution."


def fetch_btc_24h_momentum():
    """
    Fetch BTC 24h price change % from Bybit public tickers API.
    Used as a SHORT-SIDE GUARD: when BTC rallies, alt short signals fail catastrophically.
    Historical data (80 trades): 10 consecutive SHORT losses during June 12-15 BTC rally.
    """
    try:
        resp = _SESSION.get(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "linear", "symbol": "BTCUSDT"},
            timeout=10,
        )
        data = resp.json()
        if data.get("retCode") == 0:
            items = data["result"].get("list", [])
            if items:
                pct_str   = items[0].get("price24hPcnt", "0")
                change_24h = float(pct_str) * 100
                price      = float(items[0].get("lastPrice", 0))

                if change_24h >= 3.0:
                    alert    = "🚀 STRONG RALLY"
                    guidance = (
                        f"BTC is UP {change_24h:+.1f}% in 24h (${price:,.0f}). "
                        "⚠ DANGER ZONE FOR SHORTS. Historical data shows cascading SHORT failures during BTC rallies. "
                        "MANDATORY RULE: Output MAXIMUM 1 SHORT this run, confidence ≥95% only (REPAIR MODE floor). "
                        "If no SHORT qualifies at ≥95%, output 0 SHORTs — replace with a 5th LONG instead."
                    )
                elif change_24h >= 1.5:
                    alert    = "📈 UPTREND"
                    guidance = (
                        f"BTC is UP {change_24h:+.1f}% in 24h (${price:,.0f}). "
                        "Caution on SHORTs — uptrend environment. "
                        "Limit to maximum 2 SHORTs. Each SHORT must be ≥95% confidence (REPAIR MODE floor applies). "
                        "Prefer SHORTs on coins showing clear exhaustion/rejection, not just downtrending."
                    )
                elif change_24h <= -3.0:
                    alert    = "🐻 STRONG DOWNTREND"
                    guidance = (
                        f"BTC is DOWN {change_24h:+.1f}% in 24h (${price:,.0f}). "
                        "⚠ DANGER ZONE FOR LONGS. Even 'Stage 2' coins with positive 7d momentum stop out when BTC drops 3%+ intraday — cascade effect confirmed in live data (Jun 22-25 2026: 15 LONG losses in 48h). "
                        "MANDATORY RULE: Output MAXIMUM 1 LONG this run, only if coin has RS > +8% vs BTC AND negative funding AND proven graveyard winner. "
                        "FAVOURABLE SHORT environment: SHORTs perform well in BTC downtrends. Up to 3 SHORTs allowed at ≥95%."
                    )  # v47.41: added LONG danger warning
                elif change_24h <= -1.5:
                    alert    = "📉 DOWNTREND"
                    guidance = (
                        f"BTC is DOWN {change_24h:+.1f}% in 24h (${price:,.0f}). "
                        "Mild downtrend — SHORTs have reasonable conditions. "
                        "SHORT thresholds: ≥95% in REPAIR MODE (see SHORT SIGNAL STRATEGY above). Up to 3 SHORTs allowed."
                    )
                else:
                    alert    = "➡ NEUTRAL"
                    guidance = (
                        f"BTC is {change_24h:+.1f}% in 24h (${price:,.0f}). "
                        "Neutral/ranging — standard analysis applies. "
                        "SHORT signals require ≥95% in REPAIR MODE (see SHORT SIGNAL STRATEGY above). Up to 3 SHORTs allowed."
                    )

                result = f"BTC 24h Change: {change_24h:+.1f}% [{alert}] at ${price:,.0f}\n{guidance}"
                print(f"   ✓ BTC 24h Momentum: {change_24h:+.1f}% [{alert}]")
                return result, change_24h  # v47.41: return tuple (text, float) for code-level gating
    except Exception as e:
        print(f"   ⚠ BTC 24h momentum fetch failed ({e})")
    return "BTC 24h momentum: unavailable — apply SHORT thresholds per REPAIR MODE rules (≥95%, max 3 SHORTs).", 0.0


def fetch_bybit_realtime():
    """
    Fetch ALL spot tickers from Bybit in one single call — real-time data, no API key needed.
    Returns dict: { "BTC": {price, ch_24h, volume_usd, high, low}, ... }
    """
    url = "https://api.bybit.com/v5/market/tickers"
    try:
        resp = _SESSION.get(url, params={"category": "spot"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        tickers = data.get("result", {}).get("list", [])
        bybit_map = {}
        for t in tickers:
            sym = t.get("symbol", "")
            if sym.endswith("USDT") and not sym.endswith("USDT3L") and not sym.endswith("USDT3S"):
                coin = sym[:-4]   # strip USDT → "BTC", "ETH", etc.
                try:
                    bybit_map[coin] = {
                        "price":      float(t.get("lastPrice",    0) or 0),
                        "ch_24h":     float(t.get("price24hPcnt", 0) or 0) * 100,
                        "volume_usd": float(t.get("turnover24h",  0) or 0),
                        "high":       float(t.get("highPrice24h", 0) or 0),
                        "low":        float(t.get("lowPrice24h",  0) or 0),
                    }
                except (ValueError, TypeError):
                    pass
        print(f"   ✓ Bybit: {len(bybit_map)} USDT pairs loaded (real-time)")
        return bybit_map
    except Exception as e:
        print(f"   ⚠ Bybit fetch failed ({e}) — will use CoinGecko prices only")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# MTF (Multi-Timeframe) CHART DATA FUNCTIONS  — added v47.17
# Fetches real Bybit OHLCV candles and computes compact trend summaries.
# No API key required — all calls use the public market/kline endpoint.
# ─────────────────────────────────────────────────────────────────────────────

def get_klines(symbol, interval, limit=20):
    """
    Fetch OHLCV klines from Bybit public API (no auth required).
    symbol   : e.g. "BTCUSDT"
    interval : "60" (1H) | "240" (4H) | "D" (daily)
    Returns list of dicts [{open, high, low, close, volume}], oldest-first.
    Returns [] on any error — callers must handle empty gracefully.
    """
    url = "https://api.bybit.com/v5/market/kline"
    try:
        resp = _SESSION.get(url, params={
            "category": "linear",   # USDT perpetual — matches what we trade
            "symbol":   symbol,
            "interval": interval,
            "limit":    limit,
        }, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if data.get("retCode") != 0:
            return []
        # Bybit returns newest-first; reverse to oldest-first for analysis
        raw = list(reversed(data.get("result", {}).get("list", [])))
        candles = []
        for r in raw:
            try:
                candles.append({
                    "open":   float(r[1]),
                    "high":   float(r[2]),
                    "low":    float(r[3]),
                    "close":  float(r[4]),
                    "volume": float(r[5]),
                })
            except (IndexError, ValueError, TypeError):
                pass
        return candles
    except Exception:
        return []


def _mtf_trend_label(candles, sma_period=10):
    """
    Compute trend label + pattern from a candle list.
    Returns (label, pct_above_sma, pattern_hint).
    label: "BULL" | "BEAR" | "SIDEWAYS" | "UNKNOWN"
    pct_above_sma: int 0-100
    pattern_hint: "HH+HL" | "LH+LL" | "CHOPPY" | "RANGE"
    """
    if len(candles) < sma_period + 2:
        return "UNKNOWN", 50, "RANGE"

    closes = [c["close"] for c in candles]
    sma    = sum(closes[-sma_period:]) / sma_period
    above  = sum(1 for c in closes[-sma_period:] if c > sma)
    pct    = int(above / sma_period * 100)
    current = closes[-1]

    # Structure: compare recent highs/lows vs 3 candles earlier
    highs = [c["high"] for c in candles[-6:]]
    lows  = [c["low"]  for c in candles[-6:]]
    if len(highs) >= 4:
        hh = highs[-1] > highs[-3]
        hl = lows[-1]  > lows[-3]
        lh = highs[-1] < highs[-3]
        ll = lows[-1]  < lows[-3]
        if   hh and hl:   pattern = "HH+HL"
        elif lh and ll:   pattern = "LH+LL"
        elif hh and ll:   pattern = "CHOPPY"
        else:             pattern = "RANGE"
    else:
        pattern = "RANGE"

    # Trend decision: majority of recent closes vs SMA + current price side
    if pct >= 65 and current > sma:
        label = "BULL"
    elif pct <= 35 and current < sma:
        label = "BEAR"
    else:
        label = "SIDEWAYS"

    return label, pct, pattern


def compute_coin_mtf_summary(symbol):
    """
    Fetch 4H×20 + 1H×30 candles for one coin and return a compact 1-line string.
    symbol: coin ticker (e.g. "BTC") — USDT is appended automatically.
    Returns None if Bybit data is unavailable for this coin.
    """
    bybit_sym = f"{symbol}USDT"
    c4h = get_klines(bybit_sym, "240", 20)   # 4H × 20 candles = last 80h
    c1h = get_klines(bybit_sym,  "60", 30)   # 1H × 30 candles = last 30h
    if not c4h or not c1h:
        return None

    label_4h, pct_4h, pat_4h = _mtf_trend_label(c4h, sma_period=10)
    label_1h, pct_1h, pat_1h = _mtf_trend_label(c1h, sma_period=15)

    # 4H range position — where is close within the 20-candle high-low range?
    h4_high  = max(c["high"]  for c in c4h)
    h4_low   = min(c["low"]   for c in c4h)
    h4_close = c4h[-1]["close"]
    rng      = h4_high - h4_low
    pct_pos  = (h4_close - h4_low) / rng * 100 if rng > 0 else 50
    pos_str  = "TOP" if pct_pos >= 70 else "MID" if pct_pos >= 35 else "BOT"

    return (
        f"4H:{label_4h}({pct_4h}%)[{pat_4h}] "
        f"1H:{label_1h}({pct_1h}%)[{pat_1h}] "
        f"RngPos:{pos_str}({pct_pos:.0f}%)"
    )


def fetch_mtf_block(all_coins, n=20):
    """
    Select top N coins by 24h Bybit volume, fetch MTF summary for each,
    and return a formatted text block for injection into the Claude prompt.
    Fails gracefully — returns empty string if all fetches fail.
    Takes ~10-15s for 20 coins (throttled to avoid Bybit rate limits).
    """
    # Top N by 24h USDT volume (already enriched with Bybit data by fetch_top_300_coins)
    top = sorted(all_coins, key=lambda c: c.get("total_volume", 0), reverse=True)[:n]

    lines = [
        "════════════════════════════════════════════════════════════",
        f"MULTI-TIMEFRAME (MTF) CHART DATA — TOP {n} COINS BY VOLUME (Real Bybit Candles)",
        "Use this data to validate signal direction before scoring. Each line shows:",
        "  4H-trend(SMA%) [pattern] | 1H-trend(SMA%) [pattern] | 4H-range position",
        "Patterns: HH+HL=uptrend  LH+LL=downtrend  RANGE=consolidation  CHOPPY=mixed",
        "IDEAL LONG : 4H:BULL + 1H pulling back (HH+HL pattern, BOT/MID range)",
        "IDEAL SHORT: 4H:BEAR + 1H bouncing up  (LH+LL pattern, MID/TOP range)",
        "SIDEWAYS 4H: structural indecision — prefer lower confidence or STAY OUT",
        "────────────────────────────────────────────────────────────",
    ]

    fetched = 0
    for coin in top:
        symbol = (coin.get("symbol") or "").upper()
        if not symbol:
            continue
        summary = compute_coin_mtf_summary(symbol)
        if summary:
            lines.append(f"  {symbol:<10} {summary}")
            fetched += 1
        else:
            lines.append(f"  {symbol:<10} MTF: unavailable (not a USDT perp or API timeout)")
        time.sleep(0.06)   # 60ms throttle — Bybit kline endpoint allows ~30 req/s

    lines.append("════════════════════════════════════════════════════════════")
    print(f"   ✓ MTF block: {fetched}/{len(top)} coins fetched successfully")
    return "\n".join(lines) if fetched > 0 else ""


def fetch_top_300_coins():
    """
    Hybrid data fetch (v45.1 — top 200 coins, down from 300):
      • Bybit  → real-time price, 24h%, volume, high/low  (1 fast call, no rate limit)
      • CoinGecko → market cap ranking + 7d%              (needed for $150M short filter)
    Bybit data overwrites CoinGecko where available.
    Top 200 coins cover 99%+ of all tradeable volume — the same signals fire.
    Saves ~33% of Claude input tokens per run (≈$4-6/month at current cadence).
    """
    # ── Step A: Bybit real-time snapshot (single call) ──
    print("⚡ Fetching real-time data from Bybit...")
    bybit    = fetch_bybit_realtime()
    funding  = fetch_bybit_funding_rates()

    # ── Step B: CoinGecko for market cap + 7d% + ranking ──
    print("📊 Fetching market cap rankings from CoinGecko...")
    all_coins = []
    for page in range(1, 3):  # 2 pages × 100 = 200 coins (was 3 pages = 300)
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "page": page,
            "price_change_percentage": "24h,7d",
            "sparkline": "false"
        }
        try:
            resp = _SESSION.get(url, params=params, timeout=30)
            resp.raise_for_status()
            coins = resp.json()
            all_coins.extend(coins)
            print(f"   ✓ CoinGecko page {page}: {len(coins)} coins (total: {len(all_coins)})")
        except Exception as e:
            print(f"   ✗ CoinGecko page {page} failed: {e}")
        if page < 2:          # sleep only between pages, not after the last one
            time.sleep(2)

    # ── Step C: Merge — Bybit overwrites price/volume fields + funding ──
    enriched = 0
    for coin in all_coins:
        symbol = (coin.get("symbol") or "").upper()
        if symbol in bybit:
            b = bybit[symbol]
            if b["price"] > 0:
                coin["current_price"]                      = b["price"]
                coin["price_change_percentage_24h"]        = b["ch_24h"]
                coin["total_volume"]                       = b["volume_usd"]
                coin["high_24h"]                           = b["high"]
                coin["low_24h"]                            = b["low"]
                enriched += 1
        # Attach funding rate + open interest from perp market
        if symbol in funding:
            coin["funding_rate"] = funding[symbol]["funding_rate"]
            coin["open_interest"] = funding[symbol]["oi_usd"]
        else:
            coin["funding_rate"]  = None
            coin["open_interest"] = None

    print(f"   ✓ {enriched}/{len(all_coins)} coins enriched with Bybit real-time data")

    # ── Step D: Filter to Bybit-listed coins with valid price only (v46.2 fix) ──────
    # Coins not on Bybit spot (or with price=0) cannot be traded or tracked — remove them.
    # v46.1 BUG: checked `symbol in bybit` but coins with price=0 passed the filter.
    # v46.2 FIX: require price > 0 — ensures coin has a real, tradeable market on Bybit.
    # This eliminates signals for ZEC, XMR, DASH, TAO, DEXE, AKT (when delisted)
    # that accumulate as EXPIRED and pollute win-rate data.
    before = len(all_coins)
    all_coins = [
        c for c in all_coins
        if bybit.get((c.get("symbol") or "").upper(), {}).get("price", 0) > 0
    ]
    removed = before - len(all_coins)
    if removed:
        print(f"   ✓ Bybit filter (price>0): {len(all_coins)} tradeable coins kept ({removed} coins removed)")

    return all_coins


def format_market_data(all_coins):
    """
    Format coin data into the structured table format
    your WHALE-STREAM prompt expects.
    """
    batches = []

    for batch_num in range(1, 3):   # up to 2 batches × 100 = 200 coins max
        start = (batch_num - 1) * 100
        end   = batch_num * 100
        coins = all_coins[start:end]
        if not coins:               # skip empty batches (e.g. after MTF pre-screen with ≤30 coins)
            continue

        lines = []
        lines.append(f"\n{'═'*95}")
        lines.append(f"  BATCH {batch_num}  —  Rank #{start+1} to #{end}  (Top {end} by Market Cap)")
        lines.append(f"{'═'*95}")
        lines.append(
            f"{'Rank':<5} {'Symbol':<10} {'Name':<20} "
            f"{'Price (USD)':>14} {'24h%':>8} {'7d%':>8} "
            f"{'Market Cap':>18} {'24h Volume':>18} {'Vol/MCap':>10} "
            f"{'24h High':>14} {'24h Low':>13} {'FundRate':>10} {'OI (USD)':>16}"
        )
        lines.append("─" * 160)

        for i, coin in enumerate(coins):
            rank        = start + i + 1
            symbol      = (coin.get("symbol") or "").upper()
            name        = (coin.get("name") or "")[:18]
            price       = coin.get("current_price") or 0
            ch_24h      = coin.get("price_change_percentage_24h") or 0
            ch_7d       = coin.get("price_change_percentage_7d_in_currency") or 0
            mcap        = coin.get("market_cap") or 0
            volume      = coin.get("total_volume") or 0
            high_24h    = coin.get("high_24h") or price
            low_24h     = coin.get("low_24h") or price
            vol_mcap    = (volume / mcap) if mcap > 0 else 0
            fr          = coin.get("funding_rate")
            oi          = coin.get("open_interest")

            # Format price nicely depending on magnitude
            if price >= 1000:
                price_str = f"${price:>12,.2f}"
            elif price >= 1:
                price_str = f"${price:>12,.4f}"
            elif price >= 0.001:
                price_str = f"${price:>12,.6f}"
            else:
                price_str = f"${price:>12,.8f}"

            fr_str = f"{fr*100:>+8.4f}%" if fr is not None else "      N/A"
            oi_str = f"${oi:>14,.0f}"    if oi is not None else "             N/A"

            lines.append(
                f"{rank:<5} {symbol:<10} {name:<20} "
                f"{price_str} {ch_24h:>+7.2f}% {ch_7d:>+7.2f}% "
                f"${mcap:>17,.0f} ${volume:>17,.0f} {vol_mcap:>9.3f} "
                f"${high_24h:>13,.4f} ${low_24h:>12,.4f} {fr_str} {oi_str}"
            )

        batches.append("\n".join(lines))

    return batches   # list of 2 strings — caller makes 2 separate Claude calls


def analyze_with_claude(market_data_text, graveyard_text="", dominance_text="", fear_greed_text="", btc_move_text="", btc_24h_text="", batch_note="", coin_perf_text="", mtf_block_text=""):
    """
    Send market data to Claude using WHALE-STREAM prompt with prompt caching.

    Cost optimisations (v45.1):
      • Static trading rules sent as SYSTEM with cache_control — charged at 10% on cache hits
      • Dynamic gates + market data sent as USER message — never cached (changes every run)
      • 200 coins instead of 300 — saves ~33% of input tokens per run

    5 intelligence layers injected every run:
      1. Signal Graveyard     — last 20 WIN/LOSS outcomes (self-learning)
      2. BTC Dominance Gate   — macro capital flow direction
      3. Fear & Greed Gate    — crowd psychology / sentiment
      4. BTC 30-min Move Gate — real-time volatility / repricing alert
      5. BTC 24h Momentum     — short-side guard (new: blocks shorts during BTC rallies)
    """
    import anthropic
    print("🧠 Sending to Claude for WHALE-STREAM analysis...")
    print(f"   Model: {CLAUDE_MODEL}")
    print(f"   🪦 Graveyard    : {'injected' if graveyard_text else 'empty (no resolved trades yet)'}")
    print(f"   📊 BTC.D Gate   : {'injected' if dominance_text else 'unavailable'}")
    print(f"   😱 F&G Gate     : {'injected' if fear_greed_text else 'unavailable'}")
    print(f"   ⚡ BTC Move Gate: {'injected' if btc_move_text else 'unavailable'}")
    print(f"   📈 BTC 24h Gate : {'injected' if btc_24h_text else 'unavailable'}")
    print(f"   📉 MTF Block    : {'injected' if mtf_block_text else 'unavailable (skipped)'}")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    no_history_msg   = "  No resolved trades yet — this is your first or early session. Apply standard confidence thresholds."
    graveyard_block  = graveyard_text  if graveyard_text  else no_history_msg
    dominance_block  = dominance_text  if dominance_text  else "BTC Dominance: unavailable — apply standard thresholds."
    fear_greed_block = fear_greed_text if fear_greed_text else "Fear & Greed Index: unavailable — apply standard thresholds."
    btc_move_block   = btc_move_text   if btc_move_text   else "BTC 30-min move: unavailable — proceed with standard caution."
    btc_24h_block    = btc_24h_text    if btc_24h_text    else "BTC 24h momentum: unavailable — apply standard SHORT thresholds (≥95%, max 3 SHORTs)."
    coin_perf_block  = coin_perf_text  if coin_perf_text  else "LONG COIN PERFORMANCE: insufficient data (no resolved LONGs yet)"
    mtf_block        = mtf_block_text  if mtf_block_text  else ""

    # Build dynamic user message (gates + graveyard + market data — changes every run)
    user_content = DYNAMIC_DATA_TEMPLATE.format(
        BTC_DOMINANCE_GATE = dominance_block,
        FEAR_GREED_GATE    = fear_greed_block,
        BTC_MOVE_GATE      = btc_move_block,
        BTC_24H_GATE       = btc_24h_block,
        COIN_PERFORMANCE   = coin_perf_block,
        MTF_BLOCK          = mtf_block,
        SIGNAL_GRAVEYARD   = graveyard_block,
        MARKET_DATA        = market_data_text,
        BATCH_NOTE         = batch_note,
    )

    # ── API call with prompt caching on the static system prompt ──
    # WHALE_STREAM_SYSTEM is identical every run → Anthropic caches it.
    # Cache hits cost 10% of normal input price = significant savings on test runs
    # and any back-to-back runs. Scheduled 4-hour runs get a cache WRITE benefit
    # (the first run writes the cache; TTL may extend with repeated use).
    # max_tokens=16000: raised from 8000 — full analysis (regime + 6 signals + explanations)
    # routinely exceeded 8k tokens, causing silent truncation and ##JSON_START## loss.
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=[
            {
                "type": "text",
                "text": WHALE_STREAM_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {"role": "user", "content": user_content}
        ],
    )

    result      = message.content[0].text if message.content else ""
    stop_reason = message.stop_reason

    # ── Token usage report ──
    usage       = message.usage
    inp         = getattr(usage, "input_tokens",               0) or 0
    out         = getattr(usage, "output_tokens",              0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read  = getattr(usage, "cache_read_input_tokens",     0) or 0
    print(f"   ✓ Analysis complete ({len(result)} chars, stop={stop_reason})")
    print(f"   📊 Tokens — Input: {inp:,} | Output: {out:,} | Cache write: {cache_write:,} | Cache read: {cache_read:,}")
    if cache_read > 0:
        saved_usd = cache_read / 1_000_000 * 3.00 * 0.90   # 90% discount on cache hits
        print(f"   💰 Cache HIT — saved ~${saved_usd:.4f} on {cache_read:,} cached tokens!")
    elif cache_write > 0:
        print(f"   📝 Cache WRITE — {cache_write:,} tokens cached for future runs.")

    # ── Rescue retry: output was cut off AND JSON block is missing ────────────
    # Safety net for the rare case where 16k tokens still isn't enough, or the model
    # emitted preamble text that pushed the JSON past the token limit.
    # Strategy: pass the truncated response as the "assistant" turn, then ask Claude
    # to complete ONLY the JSON block. This is cheap (~2k tokens output) and reliable
    # because Claude already did the analysis — it just needs to write out the JSON.
    if stop_reason == "max_tokens" and (
        "##JSON_START##" not in result or "##JSON_END##" not in result
    ):
        print("   ⚠ Output cut off AND no JSON found — sending rescue call...")
        try:
            rescue_msg = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2000,
                system=[
                    {
                        "type": "text",
                        "text": WHALE_STREAM_SYSTEM,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {"role": "user",      "content": user_content},
                    {"role": "assistant", "content": result},
                    {"role": "user",      "content": (
                        "Your previous response was cut off by the token limit before you output "
                        "the ##JSON_START## block. Please output ONLY the ##JSON_START## JSON block "
                        "from your analysis right now. Single line, no other text before or after."
                    )},
                ],
            )
            rescue_text = rescue_msg.content[0].text if rescue_msg.content else ""
            rescue_out  = getattr(rescue_msg.usage, "output_tokens", 0) or 0
            if "##JSON_START##" in rescue_text:
                print(f"   ✅ Rescue call succeeded! ({rescue_out} tokens) — JSON recovered")
                result = rescue_text   # use rescue text as the result
            else:
                print(f"   ✗ Rescue call also failed to produce ##JSON_START## ({rescue_out} tokens)")
                print(f"   Rescue tail: {rescue_text[-200:]}")
        except Exception as rescue_err:
            print(f"   ✗ Rescue call exception: {rescue_err}")

    # ── Debug: verify JSON block present ──────────────────────────────────────
    if "##JSON_START##" in result:
        idx = result.find("##JSON_START##")
        print(f"   ✓ ##JSON_START## found at char {idx}")
        print(f"   JSON preview: {result[idx:idx+300]}")
    else:
        print("   ✗ ##JSON_START## NOT found — will fall back to STAY OUT")
        print(f"   Last 400 chars: {result[-400:]}")

    return result


def _extract_first_json_object(text):
    """
    Scan `text` for the first '{' then walk forward counting brace depth
    to find its matching '}'. Returns the extracted JSON string, or None.
    This is robust to concatenated JSON objects — only the first complete
    object is returned, ignoring anything after the closing brace.
    """
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None


def parse_json_signals(analysis_text):
    """
    Extract the structured JSON block from Claude's output.
    Looks for ##JSON_START## ... ##JSON_END## delimiters.
    Returns a dict with verdict, regime, longs[], shorts[].

    Robust to concatenated JSON objects ("Extra data" error): uses brace-depth
    scanning to extract ONLY the first complete JSON object, ignoring anything
    after its closing brace.
    """
    # Primary: custom delimiters — extract text between markers, then parse
    # only the first complete JSON object (handles concatenated double-JSON).
    start_marker = analysis_text.find('##JSON_START##')
    if start_marker != -1:
        after_marker = analysis_text[start_marker + len('##JSON_START##'):]
        # Strip to end marker if present, otherwise use full remaining text
        end_marker = after_marker.find('##JSON_END##')
        candidate = after_marker[:end_marker].strip() if end_marker != -1 else after_marker.strip()
        json_str = _extract_first_json_object(candidate)
        if json_str:
            try:
                return json.loads(json_str)
            except Exception as e:
                print(f"   ⚠ JSON parse error (delimiters): {e}")
                print(f"      Raw JSON snippet: {json_str[:200]}")

    # Fallback: markdown code fence — extract first complete JSON object
    match = re.search(r'```json\s*(\{)', analysis_text, re.DOTALL)
    if match:
        fence_content = analysis_text[match.start(1):]
        json_str = _extract_first_json_object(fence_content)
        if json_str:
            try:
                return json.loads(json_str)
            except Exception as e:
                print(f"   ⚠ JSON parse error (code fence): {e}")

    # Fallback: scan from ##JSON_START## position using brace-depth extractor
    start_idx = analysis_text.find('##JSON_START##')
    if start_idx != -1:
        json_str = _extract_first_json_object(analysis_text[start_idx:])
        if json_str:
            try:
                return json.loads(json_str)
            except Exception as e:
                print(f"   ⚠ JSON parse error (brace search): {e}")

    return None


def build_telegram_message(data, bkk_time, graveyard_text=""):
    """
    Clean, compact Telegram message optimised for phone screens.
    graveyard_text: raw graveyard string — used to extract SHORT WR line for phone visibility.
    """
    ts     = bkk_time.strftime("%a %Y-%m-%d %H:%M GMT+7")
    longs  = data.get("longs",  [])
    shorts = data.get("shorts", [])

    lines = []
    lines.append(f"🐳 WHALE-STREAM v47.46")
    lines.append(f"📅 {ts}")

    # ── Market regime summary ─────────────────────────────────
    regime   = data.get("regime",   "")
    risk_env = data.get("risk_env", "")
    if regime:
        lines.append(f"📊 {regime}")
    if risk_env:
        # Shorten to first clause
        short_risk = risk_env.split("—")[0].strip() if "—" in risk_env else risk_env[:50]
        lines.append(f"⚡ {short_risk}")

    # ── SHORT WR status from graveyard ───────────────────────
    if graveyard_text:
        for gline in graveyard_text.splitlines():
            if "S_WR" in gline or "S_AUTO_BAN" in gline or gline.strip().startswith("GRAVEYARD ["):
                lines.append(gline.strip())
    # ── Signal quality summary line ───────────────────────────
    def _avg_conf(signals):
        vals = []
        for s in signals:
            try: vals.append(int(str(s.get("conf","0")).replace("%","").strip()))
            except: pass
        return round(sum(vals)/len(vals)) if vals else 0

    l_conf = _avg_conf(longs)
    s_conf = _avg_conf(shorts)
    summary_parts = []
    if longs:  summary_parts.append(f"{len(longs)}🟢 avg {l_conf}%")
    if shorts: summary_parts.append(f"{len(shorts)}🔴 avg {s_conf}%")
    if not longs and not shorts: summary_parts.append("STAY OUT")
    lines.append("📈 " + " · ".join(summary_parts))
    # ─────────────────────────────────────────────────────────

    def signal_block(s, emoji):
        conf = s.get("conf", "")
        # Shorten pattern to first sentence / 60 chars
        pattern = s.get("pattern", "")
        if len(pattern) > 60:
            pattern = pattern[:57].rstrip(" ,—-") + "…"
        return [
            "",
            f"{emoji} {s['coin']}  {conf}",
            f"📥 {s.get('entry','')}  🛑 {s.get('sl','')}",
            f"🎯 {s.get('tp1','')} · {s.get('tp2','')} · {s.get('tp3','')} · {s.get('tp4','')}",
            f"💡 {pattern}" if pattern else "",
        ]

    if longs:
        lines.append("")
        lines.append("─── 🟢 LONG ───")
        for s in longs:
            lines.extend(signal_block(s, "🟢"))
    else:
        lines.append("")
        lines.append("🟢 No long setups met threshold")

    if shorts:
        lines.append("")
        lines.append("─── 🔴 SHORT ───")
        for s in shorts:
            lines.extend(signal_block(s, "🔴"))
    else:
        lines.append("")
        lines.append("🔴 No short setups met threshold")

    return "\n".join(l for l in lines if l != "")


def send_to_telegram(analysis_text, formatted_msg=None, chat_id=None):
    """
    Send the nicely formatted signal message to Telegram.
    chat_id defaults to TELEGRAM_CHAT_ID (ops channel).
    Pass TELEGRAM_SIGNAL_CHAT_ID for clean signal-only posts.
    Uses formatted_msg if provided, otherwise falls back to raw analysis.
    """
    print("📨 Sending analysis to Telegram...")

    full_message     = formatted_msg if formatted_msg else analysis_text
    _target_chat_id  = chat_id if chat_id else TELEGRAM_CHAT_ID
    base_url         = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Split into 4000-char chunks (leave buffer below 4096 limit)
    chunk_size = 4000
    chunks = []
    remaining = full_message
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break
        # Try to split at a newline boundary
        split_at = remaining.rfind("\n", 0, chunk_size)
        if split_at == -1:
            split_at = chunk_size
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")

    for idx, chunk in enumerate(chunks, 1):
        payload = {
            "chat_id": _target_chat_id,
            "text": chunk,
        }
        try:
            resp = requests.post(base_url, json=payload, timeout=15)
            if not resp.ok:
                print(f"   ✗ Telegram error (chunk {idx}): {resp.status_code}")
                print(f"      Reason: {resp.json().get('description', resp.text)}")
            else:
                print(f"   ✓ Telegram message {idx}/{len(chunks)} sent")
        except Exception as e:
            print(f"   ✗ Telegram error (chunk {idx}): {e}")

        if idx < len(chunks):
            time.sleep(0.5)


# parse_signals_from_analysis() removed in v47.1 — dead code, never called.
# Signals are extracted via parse_json_signals() using ##JSON_START## / ##JSON_END## markers.


def log_to_google_sheets(data, bkk_time):
    """
    Log all trade signals (up to 5 LONG + 3 SHORT) to Google Sheets.
    Columns: Coin | Signal | Confidence | Entry Zone | Stop Loss |
             TP1 | TP2 | TP3 | TP4 | Pattern | Timestamp |
             Status | Entry Price | Exit Price | TP Hit | P&L % | Resolved At
    """
    print("📝 Logging to Google Sheets...")
    # Initialise counters — computed in if/else below; safe defaults prevent NameError
    # when signals exist but are all dropped by dedup/blocklist before entering the block.
    _gate1_resolved = 0
    _open_count     = 0

    timestamp = bkk_time.strftime("%Y-%m-%d %H:%M")

    # Resolve credentials path relative to script folder
    creds_path = os.path.join(SCRIPT_DIR, GOOGLE_CREDENTIALS_FILE)
    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            f"google_credentials.json not found.\n"
            f"Please copy it to: {SCRIPT_DIR}"
        )

    # Use google.oauth2 directly — bypasses gspread.auth which fails on some Python 3.14 setups
    from google.oauth2.service_account import Credentials as _GCreds
    try:
        from gspread.client import Client as _GClient
    except ImportError:
        import subprocess as _sp
        _sp.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "gspread", "--quiet"])
        from gspread.client import Client as _GClient
    _SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = _GCreds.from_service_account_file(creds_path, scopes=_SCOPES)
    client = _GClient(auth=creds)
    sheet  = client.open_by_key(GOOGLE_SHEET_ID).sheet1

    HEADERS = [
        "Coin", "Signal", "Confidence", "Entry Zone", "Stop Loss",
        "TP1", "TP2", "TP3", "TP4", "Pattern", "Timestamp",
        "Status", "Entry Price", "Exit Price", "TP Hit", "P&L %", "Resolved At"
    ]

    # Always ensure headers are correct (17 columns now)
    existing = sheet.row_values(1)
    if not existing or existing[0] != "Coin" or len(existing) < len(HEADERS):
        sheet.update(range_name='A1', values=[HEADERS])
        # Add dropdown to TP Hit column (col O = index 14) and Status col (col L = index 11)
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
        spreadsheet.batch_update({"requests": [
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet.id,
                        "startRowIndex": 1, "endRowIndex": 2000,
                        "startColumnIndex": 14, "endColumnIndex": 15,  # TP Hit
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [
                                {"userEnteredValue": "SL"},
                                {"userEnteredValue": "TP1"},
                                {"userEnteredValue": "TP2"},
                                {"userEnteredValue": "TP3"},
                                {"userEnteredValue": "TP4"},
                            ]
                        },
                        "showCustomUi": True,
                        "strict": False,
                    }
                }
            },
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet.id,
                        "startRowIndex": 1, "endRowIndex": 2000,
                        "startColumnIndex": 11, "endColumnIndex": 12,  # Status
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [
                                {"userEnteredValue": "OPEN"},
                                {"userEnteredValue": "WIN"},
                                {"userEnteredValue": "LOSS"},
                                {"userEnteredValue": "EXPIRED"},
                                {"userEnteredValue": "NO SIGNAL"},
                            ]
                        },
                        "showCustomUi": True,
                        "strict": False,
                    }
                }
            }
        ]})

    all_signals = (
        [dict(s, direction="LONG")  for s in data.get("longs",  [])] +
        [dict(s, direction="SHORT") for s in data.get("shorts", [])]
    )

    # ── TOP-3 FILTER: keep only top 3 LONG + top 3 SHORT by confidence ──
    # Goal: trade only the highest-conviction setups each run.
    # Fewer trades = higher quality = better capital preservation.
    def _parse_conf_val(s):
        """Parse confidence as float: '92%' → 92.0, '91' → 91.0"""
        raw = str(s.get("conf", s.get("confidence", "0")))
        nums = re.findall(r'[\d]+\.?[\d]*', raw)
        return float(nums[0]) if nums else 0.0

    _longs_all  = [s for s in all_signals if s["direction"] == "LONG"]
    _shorts_all = [s for s in all_signals if s["direction"] == "SHORT"]
    _top_longs  = sorted(_longs_all,  key=_parse_conf_val, reverse=True)[:3]
    _top_shorts = sorted(_shorts_all, key=_parse_conf_val, reverse=True)[:3]
    _pre_filter = len(all_signals)
    all_signals = _top_longs + _top_shorts
    _dropped = _pre_filter - len(all_signals)
    if _dropped > 0:
        print(f"   🎯 TOP-3 FILTER: {_pre_filter} raw signals → kept top {len(_top_longs)} LONG + {len(_top_shorts)} SHORT ({_dropped} lower-confidence signals dropped)")
    else:
        print(f"   🎯 TOP-3 FILTER: {_pre_filter} signals (all kept — already within top-3 per direction)")
    # ── end top-3 filter ─────────────────────────────────────────────────

    # ── Streak-aware 6th slot (v47.39I) ──────────────────────────────────
    # If BOT_WIN_STREAK is non-empty, check for a win-streak coin that was
    # cut by the top-3 filter. Allow one bonus signal (4th+ rank) from a
    # hot coin — but only if it wasn't already included after filtering.
    try:
        if BOT_WIN_STREAK:
            _included_keys = {f"{s.get('coin','').upper()}_{s['direction']}" for s in all_signals}
            _overflow_sigs = (
                sorted(_longs_all,  key=_parse_conf_val, reverse=True)[3:] +
                sorted(_shorts_all, key=_parse_conf_val, reverse=True)[3:]
            )
            _streak_bonus = None
            _streak_bonus_cf = -1.0
            for _ov in _overflow_sigs:
                _ov_coin = _ov.get("coin", "").upper()
                _ov_key  = f"{_ov_coin}_{_ov['direction']}"
                if _ov_coin in BOT_WIN_STREAK and _ov_key not in _included_keys:
                    _ov_cf = _parse_conf_val(_ov)
                    if _ov_cf > _streak_bonus_cf:
                        _streak_bonus_cf = _ov_cf
                        _streak_bonus = _ov
            if _streak_bonus:
                all_signals.append(_streak_bonus)
                print(f"   🔥 STREAK SLOT: +{_streak_bonus.get('coin')} {_streak_bonus['direction']} "
                      f"({_streak_bonus_cf:.0f}%) — win-streak bonus 6th signal")
    except Exception:
        pass  # non-critical
    # ── end streak slot ───────────────────────────────────────────────────

    # ── Coin correlation guard (v47.39J) ─────────────────────────────────
    # If the same coin appears as both LONG and SHORT after filtering,
    # drop the lower-confidence direction to avoid contradictory orders.
    try:
        _cg_long_map  = {}   # coin → signal
        _cg_short_map = {}   # coin → signal
        for _cgs in all_signals:
            _cg_coin = _cgs.get("coin", "").upper()
            if _cgs["direction"] == "LONG":
                _cg_long_map[_cg_coin] = _cgs
            else:
                _cg_short_map[_cg_coin] = _cgs
        _conflict_coins = set(_cg_long_map) & set(_cg_short_map)
        for _cc in _conflict_coins:
            _cl_sig = _cg_long_map[_cc]
            _cs_sig = _cg_short_map[_cc]
            if _parse_conf_val(_cl_sig) >= _parse_conf_val(_cs_sig):
                all_signals.remove(_cs_sig)
                print(f"   🔀 CORR GUARD: {_cc} LONG+SHORT conflict — dropped lower-conf SHORT "
                      f"({_parse_conf_val(_cs_sig):.0f}% < {_parse_conf_val(_cl_sig):.0f}%)")
            else:
                all_signals.remove(_cl_sig)
                print(f"   🔀 CORR GUARD: {_cc} LONG+SHORT conflict — dropped lower-conf LONG "
                      f"({_parse_conf_val(_cl_sig):.0f}% < {_parse_conf_val(_cs_sig):.0f}%)")
    except Exception:
        pass  # non-critical
    # ── end correlation guard ─────────────────────────────────────────────

    # ── PER-COIN 4H REGIME FILTER (v47.27) ───────────────────────────────
    # Drop LONG signals where the coin's own 4H trend is clearly BEAR.
    # Drop SHORT signals where the coin's own 4H trend is clearly BULL.
    # Same SMA20 ±2% logic as BTC regime (reuses Bybit public kline API).
    # Fails silently on API error — signals are kept, never dropped on timeout.
    def _get_coin_4h_regime(coin_sym):
        """Fetch coin's own 4H SMA20 bias. Returns 'BULL', 'BEAR', or 'NEUTRAL'."""
        try:
            import requests as _cr
            _cr_r = _cr.get(
                "https://api.bybit.com/v5/market/kline",
                params={"category": "linear", "symbol": f"{coin_sym}USDT",
                        "interval": "240", "limit": "22"},
                timeout=5,
            )
            _cr_d = _cr_r.json()
            if _cr_d.get("retCode") != 0:
                return "NEUTRAL"
            _cr_cs = _cr_d["result"]["list"]
            if len(_cr_cs) < 21:
                return "NEUTRAL"
            _cr_closes = [float(c[4]) for c in _cr_cs[1:21]]
            _cr_sma    = sum(_cr_closes) / 20
            _cr_cur    = float(_cr_cs[0][4])
            _cr_pct    = (_cr_cur - _cr_sma) / _cr_sma * 100
            return "BEAR" if _cr_pct < -2.0 else ("BULL" if _cr_pct > 2.0 else "NEUTRAL")
        except Exception:
            return "NEUTRAL"   # keep signal on any error

    _regime_kept, _regime_dropped_list = [], []
    for _csig in all_signals:
        _csig_coin = _csig.get("coin", "")
        _csig_dir  = _csig.get("direction", "")
        _csig_reg  = _get_coin_4h_regime(_csig_coin)
        _counter   = (_csig_dir == "LONG" and _csig_reg == "BEAR") or \
                     (_csig_dir == "SHORT" and _csig_reg == "BULL")
        if _counter:
            _regime_dropped_list.append(f"{_csig_coin} {_csig_dir}({_csig_reg})")
            print(f"   🌊 4H COIN FILTER: {_csig_coin} {_csig_dir} dropped — coin 4H is {_csig_reg} (counter-trend)")
        else:
            _regime_kept.append(_csig)
    if _regime_dropped_list:
        print(f"   🌊 4H COIN FILTER: dropped {len(_regime_dropped_list)} counter-trend → {len(_regime_kept)} signals remain")
    all_signals = _regime_kept
    # ── end per-coin 4H regime filter ────────────────────────────────────

    if all_signals:
        # ── Dedup: skip same coin+direction already OPEN in last 4h ──
        # Using 4h window (not "today") so stale signals from earlier cycles
        # don't block fresh entry zones from new bot runs.
        _cutoff_str = (bkk_time - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M")
        existing_rows = sheet.get_all_values()[1:]  # skip header
        # Count resolved trades for Gate 1 progress
        _gate1_resolved = sum(
            1 for r in existing_rows
            if len(r) >= 12 and r[11].strip() in ("WIN", "LOSS")
        )
        _open_count = sum(
            1 for r in existing_rows
            if len(r) >= 12 and r[11].strip() == "OPEN"
        )
        already_open = set()
        for r in existing_rows:
            if len(r) >= 12 and r[11] == "OPEN" and len(r[10]) >= 16:
                if r[10][:16] >= _cutoff_str:   # logged within last 4h
                    coin_key = r[0].upper()
                    # r[1] is like "🟢 Long" or "🔴 Short"
                    dir_key  = "LONG" if "Long" in r[1] else "SHORT"
                    already_open.add(f"{coin_key}_{dir_key}")
        if already_open:
            print(f"   ℹ Skipping duplicates (coin+direction) already OPEN in last 4h: {len(already_open)} combos")
        # ─────────────────────────────────────────────────────────
        def _parse_entry_mid(entry_zone):
            """Return midpoint of a range like '$435-$445', or single value."""
            nums = re.findall(r'[\d]+\.?[\d]*', str(entry_zone).replace(",", ""))
            if len(nums) >= 2:
                return (float(nums[0]) + float(nums[1])) / 2
            elif len(nums) == 1:
                return float(nums[0])
            return None

        def _parse_price_val(price_str):
            """Strip $ signs and convert to float."""
            nums = re.findall(r'[\d]+\.?[\d]*', str(price_str).replace(",", ""))
            return float(nums[0]) if nums else None

        rows = []
        invalid_rows = []
        for s in all_signals:
            coin      = s.get("coin", "")
            direction = s.get("direction", "")
            combo_key = f"{coin.upper()}_{direction.upper()}"
            if combo_key in already_open:
                continue   # same coin + same direction already OPEN in last 4h
            signal_emoji = "🟢 Long" if direction == "LONG" else "🔴 Short"

            # ── SHORT coin blocklist (code-level enforcement) ──────────
            if direction == "SHORT" and coin.upper() in SHORT_COIN_BLOCKLIST:
                print(f"   🚫 BLOCKLISTED SHORT COIN — {coin}: permanently banned (0% historical WR)")
                invalid_rows.append([
                    coin,
                    signal_emoji,
                    s.get("conf", ""),
                    s.get("entry", ""),
                    s.get("sl", ""),
                    s.get("tp1", ""),
                    s.get("tp2", ""),
                    s.get("tp3", ""),
                    s.get("tp4", ""),
                    s.get("pattern", ""),
                    timestamp,
                    "INVALID",  # Status — blocklisted coin
                    "",         # Entry Price
                    "",         # Exit Price
                    "",         # TP Hit
                    "",         # P&L %
                    "",         # Resolved At
                ])
                continue
            # ── end SHORT coin blocklist ────────────────────────────────

            # ── LONG coin blocklist (code-level enforcement) ──────────────────────────────
            if direction == "LONG" and coin.upper() in LONG_COIN_BLOCKLIST:
                print(f"   🚫 BLOCKLISTED LONG COIN — {coin}: 0% historical LONG WR")
                invalid_rows.append([
                    coin,
                    signal_emoji,
                    s.get("conf", ""),
                    s.get("entry", ""),
                    s.get("sl", ""),
                    s.get("tp1", ""),
                    s.get("tp2", ""),
                    s.get("tp3", ""),
                    s.get("tp4", ""),
                    s.get("pattern", ""),
                    timestamp,
                    "INVALID",  # Status — blocklisted LONG coin
                    "",         # Entry Price
                    "",         # Exit Price
                    "",         # TP Hit
                    "",         # P&L %
                    "",         # Resolved At
                ])
                continue
            # ── end LONG coin blocklist ─────────────────────────────────────

            # ── Malformed coin blocklist (BOTH directions) ────────────────
            if coin.upper() in MALFORMED_COIN_BLOCKLIST:
                print(f"   ⚠ {coin}: SKIPPING — in MALFORMED_COIN_BLOCKLIST (consistently invalid SL levels)")
                continue  # do NOT write to sheet at all
            # ── end malformed coin blocklist ──────────────────────────────

            # ── SL/TP direction validation ──────────────────────────────
            entry_mid = _parse_entry_mid(s.get("entry", ""))
            sl_val    = _parse_price_val(s.get("sl",    ""))
            tp1_val   = _parse_price_val(s.get("tp1",   ""))
            malformed_reason = None
            if entry_mid is not None and sl_val is not None and tp1_val is not None:
                if direction == "LONG":
                    if sl_val >= entry_mid:
                        malformed_reason = f"LONG SL ({sl_val}) >= entry ({entry_mid:.4f}) — SL must be below entry"
                    elif tp1_val <= entry_mid:
                        malformed_reason = f"LONG TP1 ({tp1_val}) <= entry ({entry_mid:.4f}) — TP1 must be above entry"
                    else:
                        _tp1_dist = (tp1_val - entry_mid) / entry_mid * 100
                        if _tp1_dist < 3.0:
                            malformed_reason = f"LONG TP1 only {_tp1_dist:.2f}% from entry — minimum 3.0% required"
                elif direction == "SHORT":
                    if sl_val <= entry_mid:
                        malformed_reason = f"SHORT SL ({sl_val}) <= entry ({entry_mid:.4f}) — SL must be above entry"
                    elif tp1_val >= entry_mid:
                        malformed_reason = f"SHORT TP1 ({tp1_val}) >= entry ({entry_mid:.4f}) — TP1 must be below entry"
                    else:
                        _tp1_dist = (entry_mid - tp1_val) / entry_mid * 100
                        if _tp1_dist < 3.0:
                            malformed_reason = f"SHORT TP1 only {_tp1_dist:.2f}% from entry — minimum 3.0% required (was the root cause of fake +1% WINs)"
            if malformed_reason:
                # Skip entirely — do NOT write to sheet (not even as INVALID).
                # Writing INVALID rows still wastes sheet capacity and confuses the tracker.
                print(f"   ⚠ {coin}: SKIPPING malformed {direction} — {malformed_reason}")
                continue  # do NOT write as OPEN or INVALID
            # ────────────────────────────────────────────────────────────

            # Combine pattern + mtf_bias into the pattern field (no new column needed)
            _pattern_raw  = s.get("pattern", "")
            _mtf_bias_raw = s.get("mtf_bias", "")
            _pattern_full = (
                f"{_pattern_raw} [{_mtf_bias_raw}]"
                if _mtf_bias_raw and _mtf_bias_raw != "MTF_UNKNOWN"
                else _pattern_raw
            )
            rows.append([
                coin,
                signal_emoji,
                s.get("conf", ""),
                s.get("entry", ""),
                s.get("sl", ""),
                s.get("tp1", ""),
                s.get("tp2", ""),
                s.get("tp3", ""),
                s.get("tp4", ""),
                _pattern_full,
                timestamp,
                "OPEN",  # Status  — tracker will update this
                "",      # Entry Price (midpoint, filled by tracker)
                "",      # Exit Price
                "",      # TP Hit
                "",      # P&L %
                "",      # Resolved At
            ])
        if invalid_rows:
            sheet.append_rows(invalid_rows, value_input_option="USER_ENTERED")
            print(f"   ⚠ {len(invalid_rows)} malformed signal(s) written as INVALID (paper trail)")
        if rows:
            sheet.append_rows(rows, value_input_option="USER_ENTERED")
            print(f"   ✓ {len(rows)} signal(s) logged as OPEN in Google Sheets")
        else:
            print("   ℹ All signals already logged today — nothing new added")

        valid_count   = len(rows)
        invalid_count = len(invalid_rows)
        blocked_coins = [r[0] for r in invalid_rows]  # first cell = coin name
    else:
        existing_rows = sheet.get_all_values()[1:]
        _gate1_resolved = sum(
            1 for r in existing_rows
            if len(r) >= 12 and r[11].strip() in ("WIN", "LOSS")
        )
        _open_count = sum(
            1 for r in existing_rows
            if len(r) >= 12 and r[11].strip() == "OPEN"
        )
        sheet.append_row([
            "STAY OUT", "—", "—", "—", "—",
            "—", "—", "—", "—", "—", timestamp,
            "NO SIGNAL", "", "", "", "", ""
        ])
        print("   ⚠ STAY OUT — logged summary row")
        valid_count   = 0
        invalid_count = 0
        blocked_coins = []

    return valid_count, invalid_count, blocked_coins, _gate1_resolved, _open_count


# ─────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────

def main():
    # ── Cycle guard: skip if already done this 4h slot ──────────────
    _cg_path  = os.path.join(SCRIPT_DIR, "daily_status.json")
    _cg_now   = datetime.now(BKK)
    _cg_cycle = str((_cg_now.hour // 4) * 4).zfill(2)
    _cg_key   = f"sigbot_{_cg_cycle}"
    try:
        with open(_cg_path, encoding="utf-8") as _cgf:
            _cg_data = json.load(_cgf)
        if _cg_data.get("date") == _cg_now.date().isoformat() and _cg_data.get(_cg_key):
            print(f"[CYCLE GUARD] {_cg_key} already completed today — skipping duplicate run.")
            return
    except Exception:
        pass  # status missing → proceed normally
    # ── End cycle guard ─────────────────────────────────────────────

    # Circuit breaker check — must be before any Claude call or signal work
    _pause_file = os.path.join(SCRIPT_DIR, "paused.flag")
    if os.path.exists(_pause_file):
        print(f"[CIRCUIT BREAKER] paused.flag active — skipping Bot run")
        _mark_done("sigbot", details={"paused": True})
        return

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║   🐳  WHALE-STREAM v47.47  — AUTO BOT STARTING    ║")
    print("╚══════════════════════════════════════════════════╝")
    # Check conservative flag early so we can show it in the startup banner
    _short_conservative_early = os.path.exists(os.path.join(SCRIPT_DIR, "short_conservative.flag"))
    if _short_conservative_early:
        print("⚠️ SHORT CONSERVATIVE PHASE ACTIVE (recently exited repair mode)")
    print()

    # ── Step 1: Load Signal Graveyard (past outcomes → feedback loop) ──
    print("🪦 Loading Signal Graveyard from Google Sheets...")
    graveyard, short_wr_recent, coin_perf = fetch_signal_graveyard()

    # ── Flag checks ──────────────────────────────────────────
    _short_conservative = os.path.exists(os.path.join(SCRIPT_DIR, "short_conservative.flag"))

    # ── Inject SHORT CONSERVATIVE PHASE block into graveyard prompt ──
    # Only inject when conservative flag is active AND repair mode is NOT active
    # (repair mode guidance supersedes conservative — they are mutually exclusive).
    _repair_flag_active = os.path.exists(os.path.join(SCRIPT_DIR, "short_repair.flag"))
    if _short_conservative and not _repair_flag_active:
        _conservative_block = (
            "\n" + "─" * 100 + "\n"
            "⚠️ SHORT CONSERVATIVE PHASE ACTIVE (recently exited repair mode)\n"
            "- Maximum 1 SHORT signal this run (rank 2 slot only — never rank 1)\n"
            "- SHORT confidence floor: ≥93% (system-wide hard floor since v46.53)\n"
            "- Allowed SHORT coins: H, FF only — same restriction as REPAIR MODE\n"
            "- Rationale: Ramp back gradually. Prove SHORTs work before full access."
        )
        graveyard = (graveyard + _conservative_block) if graveyard else _conservative_block.strip()
        print("   ⚠️ SHORT CONSERVATIVE PHASE — block injected into graveyard prompt")

    # ── Step 1b: Macro Event Guard + Token Unlock Risk ──────
    print("📅 Checking macro event calendar + token unlock risk...")
    macro_risks  = check_macro_event_risk()
    unlock_risks = check_token_unlock_risk()
    all_risks    = macro_risks + unlock_risks
    if all_risks:
        risk_block = (
            "\n" + "═" * 80 + "\n"
            "⚠️  MARKET EVENT RISK — READ BEFORE SCORING ANY COIN:\n"
            + "\n".join(f"   {r}" for r in all_risks)
            + "\n" + "═" * 80
        )
        graveyard = (graveyard + risk_block) if graveyard else risk_block.strip()
        _macro_count  = len(macro_risks)
        _unlock_count = len(unlock_risks)
        print(f"   🚨 Event risks injected: {_macro_count} macro, {_unlock_count} token unlock")
        for _r in all_risks:
            print(f"      {_r[:100]}")
    else:
        print("   ✅ No macro or token unlock events in risk window")

    # ── Step 1d: Fetch BTC Dominance Gate ───────────────────
    print("📊 Fetching BTC Dominance Gate...")
    dominance = fetch_btc_dominance()

    # ── Step 1e: Fetch Fear & Greed Index ───────────────────
    print("😱 Fetching Fear & Greed Index...")
    fear_greed = fetch_fear_greed()

    # ── Step 1f: Fetch BTC 30-min Move Gate ─────────────────
    print("⚡ Fetching BTC 30-min Move Gate (volatility check)...")
    btc_move = fetch_btc_move_gate()

    # ── Step 1g: Fetch BTC 24h Momentum (short-side guard) ───
    print("📈 Fetching BTC 24h Momentum Gate (short-side guard)...")
    btc_24h_text, btc_24h_pct = fetch_btc_24h_momentum()  # v47.41: unpack (text, float)

    # ── Step 2: Fetch market data ───────────────────────────
    all_coins = fetch_top_300_coins()
    if len(all_coins) < 80:
        print("✗ ERROR: Not enough coins fetched. Check your internet connection.")
        _mark_done("sigbot", details={"longs": [], "shorts": [], "error": "fetch_failed"})
        return

    # ── Step 2b: MTF Pre-Screen — score ALL coins before Claude sees anything (v47.47 — P1) ──
    # Replaces dumb 24h momentum ranking. Fetches Daily+4H candles for all 200 coins,
    # scores by confluence (trend alignment + RSI zone + volume), selects top 30 candidates.
    # Claude receives ONLY these 30 coins — highest quality, not largest 24h move.
    print("🔍 MTF pre-screening all coins (Daily+4H confluence scoring — P1)...")
    _mtf_result       = _mtf_prescreen(all_coins, n_long=15, n_short=15)
    _long_candidates  = _mtf_result["longs"]    # top 15 LONG-ready coins
    _short_candidates = _mtf_result["shorts"]   # top 15 SHORT-ready coins

    # Merge into ordered list (LONG candidates first), deduplicate by symbol
    _seen_syms      = set()
    _screened_coins = []
    for _c in (_long_candidates + _short_candidates):
        _sym = (_c.get("symbol") or "").upper()
        if _sym and _sym not in _seen_syms:
            _seen_syms.add(_sym)
            _screened_coins.append(_c)
    print(f"   📋 {len(_screened_coins)} pre-screened coins passed to Claude (was 200)")

    # ── Step 2c: Fetch MTF 1H chart data for top-volume coins (entry timing) ────────────
    # Provides 1H trend labels to supplement P1 Daily+4H scores.
    print("📉 Fetching MTF chart data (1H trends for top 20 by volume)...")
    mtf_block = fetch_mtf_block(all_coins, n=20)

    # ── Step 3: Format ONLY the screened coins for Claude ───────────────────
    # With ≤30 coins, format_market_data() produces 1 batch (empty batch 2 is skipped).
    print(f"🔧 Formatting {len(_screened_coins)} pre-screened coins for Claude prompt...")
    batches = format_market_data(_screened_coins)

    # Build MTF indicator block from pre-screener results (replaces _get_coin_indicators)
    _indicator_lines = ["── MTF PRE-SCREEN SCORES (Daily+4H confluence — P1) ──"]
    for _c in _screened_coins:
        _m   = _c.get("_mtf", {})
        _sym = (_c.get("symbol") or "").upper()
        if _m:
            _ls  = _m.get("long_score",  0)
            _ss  = _m.get("short_score", 0)
            _dir = "LONG-BIAS" if _ls >= _ss else "SHORT-BIAS"
            _indicator_lines.append(
                f"{_sym}: Daily={_m.get('trend_daily','?')} 4H={_m.get('trend_4h','?')} "
                f"RSI4H={_m.get('rsi_4h','?')} vol×{_m.get('vol_ratio','?')} "
                f"EMA20_4H={_m.get('ema20_4h','?')} "
                f"→ LONG_SCORE={_ls} SHORT_SCORE={_ss} [{_dir}]"
            )
    _indicator_text = "\n".join(_indicator_lines) if _screened_coins else ""

    # Inject MTF scores into the batch
    if _indicator_text and batches:
        batches[0] = batches[0] + f"\n\n{_indicator_text}\n"

    # ── Write market_context.json for cross-agent data sharing (v47.47) ──────
    try:
        _mc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_context.json")
        _mc_data = {
            "generated_at":    datetime.now(BKK).isoformat(),
            "fear_greed_text": fear_greed,
            "screened_coins":  [(_c.get("symbol") or "").upper() for _c in _screened_coins],
            "indicators":      {
                (_c.get("symbol") or "").upper(): _c.get("_mtf", {})
                for _c in _screened_coins
            },
        }
        with open(_mc_path, "w", encoding="utf-8") as _mcf:
            json.dump(_mc_data, _mcf, indent=2)
        print(f"   ✅ market_context.json written ({len(_screened_coins)} coins)")
    except Exception as _mc_err:
        print(f"   ⚠ market_context.json write skipped: {_mc_err}")

    # ── Step 4: Analyze with Claude — Single call (P1: ≤30 pre-screened coins) ──
    # v47.47: MTF pre-screen reduces from 200→30 coins. All fit in one batch.
    # One Claude call instead of two → 50% lower API cost + higher signal quality.
    _STANDALONE = (
        "\n════════════════════════════════════════════════════════════\n"
        "⚡ INSTRUCTION: This is a complete, self-contained analysis request.\n"
        "Analyze ALL pre-screened coins in the DATA above (MTF-filtered, ≤30 coins).\n"
        "Apply the SIGNAL SETUP TEMPLATE. Output your FULL ##JSON_START## JSON block now.\n"
        "TOP 2 LONG + TOP 2 SHORT only. If fewer qualify, output STAY OUT for that slot.\n"
        "════════════════════════════════════════════════════════════"
    )

    try:
        print("🧠 Claude analysis — MTF pre-screened coins (P1 — single batch)...")
        analysis1 = analyze_with_claude(
            batches[0],
            graveyard_text=graveyard, dominance_text=dominance,
            fear_greed_text=fear_greed, btc_move_text=btc_move,
            btc_24h_text=btc_24h_text, batch_note=_STANDALONE,
            coin_perf_text=coin_perf, mtf_block_text=mtf_block,
        )
    except Exception as e:
        print(f"✗ Claude analysis failed (batch 1): {e}")
        _mark_done("sigbot", details={"longs": [], "shorts": [], "error": "claude_failed"})
        return

    # No batch 2: MTF pre-screen reduces to ≤30 coins — all fit in one Claude call (v47.47 P1)
    analysis2 = ""

    # Bangkok time used across all outputs
    bkk_time = datetime.now(BKK)

    # ── Step 5: Parse + merge JSON signals from both batches ────────────
    def _make_fallback(raw_text):
        regime_m = re.search(r'(?:BEAR|BULL|RANGE)[^\n]{0,30}(?:EXPANSION|CONSOLIDATION|RANGE)', raw_text, re.IGNORECASE)
        btc_m    = re.search(r'BTC Bias\s*[:\-]+\s*([^\n]{5,40})', raw_text, re.IGNORECASE)
        eth_m    = re.search(r'ETH Bias\s*[:\-]+\s*([^\n]{5,40})', raw_text, re.IGNORECASE)
        risk_m   = re.search(r'Risk Env[^\n]*[:\-]+\s*([^\n]{5,40})', raw_text, re.IGNORECASE)
        return {
            "verdict":  "STAY OUT",
            "regime":   regime_m.group(0).strip() if regime_m else "Unknown",
            "btc_bias": btc_m.group(1).strip()    if btc_m   else "—",
            "eth_bias": eth_m.group(1).strip()    if eth_m   else "—",
            "risk_env": risk_m.group(1).strip()   if risk_m  else "—",
            "longs":    [],
            "shorts":   [],
        }

    data1 = parse_json_signals(analysis1)
    data2 = parse_json_signals(analysis2) if analysis2 else None

    if not data1:
        print("   ⚠ Batch 1 JSON parse failed — building STAY OUT fallback")
        data1 = _make_fallback(analysis1)
    if not data2:
        if analysis2:
            print("   ⚠ Batch 2 JSON parse failed — using batch 1 signals only")
        data2 = {"longs": [], "shorts": []}

    # Merge longs + shorts from both batches, deduplicate by coin symbol
    seen_l, seen_s = set(), set()
    merged_longs, merged_shorts = [], []
    for sig in data1.get("longs", []) + data2.get("longs", []):
        sym = sig.get("coin", "").upper()
        if sym and sym not in seen_l:
            seen_l.add(sym)
            merged_longs.append(sig)
    for sig in data1.get("shorts", []) + data2.get("shorts", []):
        sym = sig.get("coin", "").upper()
        if sym and sym not in seen_s:
            seen_s.add(sym)
            merged_shorts.append(sig)

    # ── Programmatic SHORT confidence filter (belt + suspenders) ──────────────
    # ORDERING NOTE: This filter runs BEFORE the cross-direction conflict guard
    # intentionally. A weak SHORT (e.g. 88% conf) must not kill a valid LONG via
    # the conflict guard if that SHORT would be dropped here anyway. Filtering
    # SHORTs first ensures the conflict guard only sees SHORTs that would survive.
    min_short_conf = 95 if short_wr_recent <= 50 else 93  # 95% floor until SHORT WR recovers to >50% (v47.8)
    before = len(merged_shorts)
    merged_shorts = [s for s in merged_shorts if _parse_conf(s) >= min_short_conf]
    dropped = before - len(merged_shorts)
    if dropped:
        print(f"   🛡  SHORT WR {short_wr_recent:.0f}% → AUTO-DROPPED {dropped} short(s) below {min_short_conf}% confidence")

    # ── Cross-direction conflict guard ─────────────────────────────────────────
    # A coin cannot be both LONG and SHORT simultaneously — drop both sides if conflict.
    # Runs AFTER SHORT conf filter so low-confidence SHORTs cannot kill valid LONGs.
    _conflict_coins = {s.get("coin", "").upper() for s in merged_shorts} & \
                      {s.get("coin", "").upper() for s in merged_longs}
    if _conflict_coins:
        print(f"   ⚠ Cross-direction conflict removed (LONG+SHORT same coin): {_conflict_coins}")
        merged_longs  = [s for s in merged_longs  if s.get("coin", "").upper() not in _conflict_coins]
        merged_shorts = [s for s in merged_shorts if s.get("coin", "").upper() not in _conflict_coins]

    # ── Programmatic LONG confidence filter (code-level floor) ──────────────
    # 85-87% LONG band: 39.1% WR, avg -12.5% P&L — confirmed loser tier (v46.62).
    # This strips any LONG Claude emitted below 88% even if prompt was ignored.
    LONG_MIN_CONF = 88
    before_long = len(merged_longs)
    merged_longs = [s for s in merged_longs if _parse_conf(s) >= LONG_MIN_CONF]
    dropped_long = before_long - len(merged_longs)
    if dropped_long:
        print(f"   🛡  LONG floor {LONG_MIN_CONF}% — AUTO-DROPPED {dropped_long} long(s) below threshold")

    signal_data = {
        "verdict":  data1.get("verdict",  "GO"),
        "regime":   data1.get("regime",   ""),
        "btc_bias": data1.get("btc_bias", ""),
        "eth_bias": data1.get("eth_bias", ""),
        "risk_env": data1.get("risk_env", ""),
        "longs":    merged_longs,
        "shorts":   merged_shorts,
    }
    print(f"   ✓ Merged: {len(merged_longs)} LONG + {len(merged_shorts)} SHORT signals from 2 batches")

    # ── DYNAMIC SIGNAL COUNT based on BTC 4H regime (v47.22) ────────────────
    # Re-check BTC 4H bias (cheap public API, no auth) to adjust how many
    # signals we keep. Sideways market = fewer signals = less noise.
    # Strong trending market = more signals = more opportunities.
    # Fails silently — defaults to 3+3 if API is unreachable.
    def _get_btc_regime_bot():
        try:
            import requests as _req
            r = _req.get(
                "https://api.bybit.com/v5/market/kline",
                params={"category": "linear", "symbol": "BTCUSDT",
                        "interval": "240", "limit": "22"},
                timeout=6,
            )
            d = r.json()
            if d.get("retCode") != 0:
                return "NEUTRAL", 0.0
            cs = d["result"]["list"]
            if len(cs) < 21:
                return "NEUTRAL", 0.0
            closes = [float(c[4]) for c in cs[1:21]]
            sma20  = sum(closes) / 20
            cur    = float(cs[0][4])
            pct    = (cur - sma20) / sma20 * 100
            bias   = "BEAR" if pct < -2.0 else ("BULL" if pct > 2.0 else "NEUTRAL")
            return bias, round(pct, 2)
        except Exception:
            return "NEUTRAL", 0.0

    _btc_regime, _btc_regime_pct = _get_btc_regime_bot()
    # Signal count rules (P3 — max 2 LONG + 2 SHORT per run):
    # MTF pre-screen already selects quality. Less is more — stop scraping for filler.
    #   NEUTRAL:     2 LONG + 2 SHORT
    #   BULL:        2 LONG + 2 SHORT (was 3+2/4+2 — capped at 2+2)
    #   BEAR:        1 LONG + 2 SHORT (1 LONG max in downtrend)
    # BTC 24h override below can further reduce LONG to 0 in hard downtrends.
    if _btc_regime == "NEUTRAL":
        _n_long, _n_short = 2, 2
        _regime_note = f"SIDEWAYS ({_btc_regime_pct:+.1f}%) — 2+2"
    elif _btc_regime == "BULL":
        _n_long, _n_short = 2, 2   # P3: was 3+2/4+2
        _regime_note = f"BULL ({_btc_regime_pct:+.1f}%) — 2+2"
    else:  # BEAR
        _n_long, _n_short = 1, 2   # P3: was 1+3/1+4
        _regime_note = f"BEAR ({_btc_regime_pct:+.1f}%) — 1+2"
    # ── BTC 24h LONG count override (v47.41) ─────────────────────────────────
    # Hard cap on LONGs when BTC is dropping hard intraday.
    # Root cause: Jun 22-25 2026 — BTC fell 8%+ over 48h; bot generated 15+ LONGs that
    # all stopped out because the 4H SMA20 regime lags 24h spot moves by several candles.
    # This provides a faster, independent guard on top of the 4H regime.
    if btc_24h_pct <= -5.0:
        if _n_long > 0:
            _n_long = 0
            _regime_note += f" | BTC24h {btc_24h_pct:+.1f}%→0L"
            print(f"   📉 BTC 24h override: {btc_24h_pct:+.1f}% → LONGs suppressed to 0")
    elif btc_24h_pct <= -3.0:
        if _n_long > 1:
            _n_long = 1
            _regime_note += f" | BTC24h {btc_24h_pct:+.1f}%→max1L"
            print(f"   📉 BTC 24h override: {btc_24h_pct:+.1f}% → LONGs capped at 1")
    # ── SHORT slot expansion: compensate suppressed LONGs in bear (P3: capped at 3 max) ──
    if btc_24h_pct <= -3.0 and _n_short < 3:
        _n_short = 3
        _regime_note += f" | BTC24h bear→3S"
        print(f"   📈 BTC 24h bear: SHORT slots expanded to 3 (compensates for LONG suppression)")
    # ── end BTC 24h LONG override ─────────────────────────────────────────────
    print(f"   📡 BTC 4H Regime: {_regime_note} → keeping top {_n_long}🟢 + {_n_short}🔴")
    # ── end dynamic count ─────────────────────────────────────────────────────

    # ── TOP-N FILTER (main): trim signal_data BEFORE Telegram + Sheets ───────
    # This is the authoritative filter. The filter inside log_to_google_sheets()
    # is a safety backstop only. signal_data is the single source of truth for
    # Telegram, Sheets, and the trader.
    def _top3_key(sig):
        raw = str(sig.get("conf", sig.get("confidence", "0")))
        nums = re.findall(r'[\d]+\.?[\d]*', raw)
        return float(nums[0]) if nums else 0.0
    _raw_n_long  = len(signal_data["longs"])
    _raw_n_short = len(signal_data["shorts"])
    signal_data["longs"]  = sorted(signal_data["longs"],  key=_top3_key, reverse=True)[:_n_long]
    signal_data["shorts"] = sorted(signal_data["shorts"], key=_top3_key, reverse=True)[:_n_short]
    _n_top_dropped = (_raw_n_long - len(signal_data["longs"])) + (_raw_n_short - len(signal_data["shorts"]))
    if _n_top_dropped > 0:
        print(f"   🎯 TOP-N FILTER: {_raw_n_long}🟢 + {_raw_n_short}🔴 raw → kept top {len(signal_data['longs'])}🟢 + {len(signal_data['shorts'])}🔴 ({_n_top_dropped} dropped)")
    else:
        print(f"   🎯 TOP-N FILTER: already within limit — no signals dropped")
    # ── H SHORT price floor (v47.43) — suppress H SHORT when price < $0.05 ────
    # At near-zero prices TP levels compress and a squeeze reversal can hurt many
    # simultaneously-open H SHORT positions (bot was taking 11 H SHORTs in one day).
    _h_coin = next((c for c in all_coins if (c.get("symbol") or "").upper() == "H"), None)
    if _h_coin:
        _h_price = float(_h_coin.get("current_price") or 999)
        if _h_price < 0.05:
            _h_short_before = len(signal_data["shorts"])
            signal_data["shorts"] = [s for s in signal_data["shorts"]
                                      if not (str(s.get("coin", "")).upper() == "H"
                                              and s.get("direction") == "SHORT")]
            _h_dropped = _h_short_before - len(signal_data["shorts"])
            if _h_dropped > 0:
                print(f"   🚫 H SHORT floor: price ${_h_price:.4f} < $0.05 → {_h_dropped} H SHORT(s) suppressed")
    # ── LONG coin whitelist: non-proven coins need conf≥95% (v47.43) ─────────
    # Proven = ≥3 LONG trades AND ≥60% WR in trade_log.json.
    # Eliminates the 0W/1L exploratory junk that drags LONG WR to 50%.
    try:
        _lwl_log_path = os.path.join(SCRIPT_DIR, "trade_log.json")
        with open(_lwl_log_path, "r", encoding="utf-8") as _lwl_f:
            resolved = json.load(_lwl_f)
        if not isinstance(resolved, list):
            resolved = []
    except Exception:
        resolved = []
    _lwl_wr = {}
    for _r in resolved:
        if _r.get("direction") != "LONG":
            continue
        _c = str(_r.get("coin", "")).upper()
        _w3, _t3 = _lwl_wr.get(_c, (0, 0))
        _lwl_wr[_c] = (_w3 + (1 if _r["status"] == "WIN" else 0), _t3 + 1)
    _proven_long_set = {
        c for c, (w, t) in _lwl_wr.items()
        if t >= 3 and (w / t) >= 0.60 and c not in LONG_COIN_BLOCKLIST
    }
    if _proven_long_set:   # only enforce once we have proven data
        _long_before_wl = len(signal_data["longs"])
        _filtered_longs = []
        for _ls in signal_data["longs"]:
            _lc = str(_ls.get("coin", "")).upper()
            if _lc in _proven_long_set:
                _filtered_longs.append(_ls)
            else:
                _lconf = _top3_key(_ls)
                if _lconf >= 95.0:
                    _filtered_longs.append(_ls)
                else:
                    print(f"   🎯 LONG WL: {_lc} conf={_lconf:.0f}% < 95% (non-proven) → dropped")
        signal_data["longs"] = _filtered_longs
        _long_wl_dropped = _long_before_wl - len(signal_data["longs"])
        if _long_wl_dropped > 0:
            print(f"   ✅ LONG WL FILTER: {_long_before_wl}🟢 → {len(signal_data['longs'])}🟢 kept ({_long_wl_dropped} non-proven below 95% dropped)")
    # ── end LONG whitelist filter ─────────────────────────────────────────────
    # ── end top-N filter ──────────────────────────────────────────────────────

    tg_msg = build_telegram_message(signal_data, bkk_time, graveyard_text=graveyard)
    print("\n" + "─"*60)
    print(tg_msg)
    print("─"*60 + "\n")

    # ── Step 6: Send signals to signal channel, ops summary stays on ops channel ──
    try:
        # Signals → TELEGRAM_SIGNAL_CHAT_ID (clean signal-only channel)
        # Falls back to TELEGRAM_CHAT_ID if signal channel not configured
        send_to_telegram(analysis1, formatted_msg=tg_msg, chat_id=TELEGRAM_SIGNAL_CHAT_ID)
    except Exception as e:
        print(f"✗ Telegram send failed: {e}")

    # ── Step 7: Log to Google Sheets ────────────────────────
    valid_logged   = 0
    invalid_logged = 0
    blocked_coins  = []
    gate1_total    = 0
    open_pipeline  = 0
    try:
        valid_logged, invalid_logged, blocked_coins, gate1_total, open_pipeline = log_to_google_sheets(signal_data, bkk_time)
    except Exception as e:
        print(f"✗ Google Sheets logging failed: {e}")
        print("  (Check that GOOGLE_CREDENTIALS_FILE exists and GOOGLE_SHEET_ID is correct)")

    # ── Step 8: Send end-of-run Signal Quality summary to Telegram ──
    try:
        _ts    = bkk_time.strftime("%a %Y-%m-%d %H:%M GMT+7")
        _n_long  = len(signal_data.get("longs",  []))
        _n_short = len(signal_data.get("shorts", []))

        if invalid_logged == 0:
            _quality_line = f"🛡 Signal quality: {valid_logged} valid | 0 INVALID (all clean)"
        else:
            _blocked_str  = ", ".join(blocked_coins) if blocked_coins else "unknown"
            _quality_line = (
                f"⚠️ Signal quality: {valid_logged} valid | {invalid_logged} INVALID (blocked)\n"
                f"🚫 Blocked coins: {_blocked_str}"
            )

        _gate1_pct = min(gate1_total / 150 * 100, 100)
        _gate1_bar = "✅ CLEARED" if gate1_total >= 150 else f"{gate1_total}/150 ({_gate1_pct:.0f}%)"
        # In REPAIR MODE, name the recovery coins that were signaled as SHORTs.
        # In CONSERVATIVE PHASE, show the restricted status instead of the normal SHORT count.
        _repair_active = os.path.exists(os.path.join(SCRIPT_DIR, "short_repair.flag"))
        if _repair_active and _n_short > 0:
            _short_coins = [s.get("coin", "?").upper() for s in signal_data.get("shorts", [])]
            _short_label = f"{_n_short}🔴 SHORT [{', '.join(_short_coins)} — recovery]"
        elif _short_conservative and not _repair_active:
            _short_label = f"⏸ SHORT: CONSERVATIVE phase (H/FF only, ≥93%, max 1/run)"
        else:
            _short_label = f"{_n_short}🔴 SHORT"
        _summary = (
            f"📋 Run summary — {_ts}\n"
            f"  Signals: {_n_long}🟢 LONG · {_short_label}\n"
            f"  🎯 Gate 1: {_gate1_bar}\n"
            f"  ⏳ Pipeline: {open_pipeline} OPEN signals waiting\n"
            f"  {_quality_line}"
        )
        send_to_telegram(None, formatted_msg=_summary)
    except Exception as e:
        print(f"⚠ End-of-run Telegram summary failed: {e}")

    _now_bkk = datetime.now(BKK).strftime("%Y-%m-%d %H:%M")
    print(f"[{_now_bkk} BKK] Bot run complete")
    print()
    print("✅  WHALE-STREAM run complete!")
    print()
    _long_coins  = [s.get("coin", "?").upper() for s in signal_data.get("longs",  [])]
    _short_coins = [s.get("coin", "?").upper() for s in signal_data.get("shorts", [])]
    _mark_done("sigbot", details={"longs": _long_coins, "shorts": _short_coins})


if __name__ == "__main__":
    main()
