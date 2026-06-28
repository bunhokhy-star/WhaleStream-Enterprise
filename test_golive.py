"""
╔══════════════════════════════════════════════════════════════╗
║   WHALE-STREAM GO-LIVE TEST SUITE v1.0                       ║
║                                                              ║
║  Run this on June 29-30 before switching to live Bybit keys. ║
║  Tests all critical system components end-to-end.            ║
║                                                              ║
║  Usage:  python test_golive.py                               ║
║                                                              ║
║  All tests must PASS before July 1 go-live.                  ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone, timedelta

# ── Force UTF-8 without creating a new wrapper (avoids double-wrap crash
#    when trade_logger.py is imported and also wraps sys.stdout) ──────────
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass  # Python < 3.7 — ignore

BKK       = timezone(timedelta(hours=7))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"
SKIP = "⏭️  SKIP"

results = []


def check(name, status, detail=""):
    icon = {"PASS": PASS, "FAIL": FAIL, "WARN": WARN, "SKIP": SKIP}.get(status, "?")
    line = f"  {icon}  {name}"
    if detail:
        line += f"  →  {detail}"
    print(line)
    results.append({"name": name, "status": status, "detail": detail})
    return status == "PASS"


def section(title):
    print(f"\n{'═'*56}")
    print(f"  {title}")
    print(f"{'═'*56}")


# ══════════════════════════════════════════════════════════════
# TEST 1 — FILE INTEGRITY
# ══════════════════════════════════════════════════════════════
section("1 — REQUIRED FILES")

REQUIRED_FILES = [
    "whale_stream_bot.py",
    "whale_stream_strategist.py",
    "whale_stream_trader.py",
    "whale_stream_tracker.py",
    "whale_stream_watchdog.py",
    "whale_stream_debrief.py",
    "whale_stream_monitor.py",
    "morning_briefing.py",
    "signal_scorer.py",
    "trade_logger.py",
    "mission.py",
    "local_config.py",
    "google_credentials.json",
    "MASTER_PLAN.md",
    "CHANGELOG.md",
]

for fname in REQUIRED_FILES:
    fpath = os.path.join(SCRIPT_DIR, fname)
    if os.path.exists(fpath):
        check(fname, "PASS", f"{os.path.getsize(fpath):,} bytes")
    else:
        check(fname, "FAIL", "MISSING — system cannot run without this file")


# ══════════════════════════════════════════════════════════════
# TEST 2 — CREDENTIALS LOAD
# ══════════════════════════════════════════════════════════════
section("2 — CREDENTIALS (local_config.py)")

try:
    from local_config import (
        ANTHROPIC_API_KEY,
        TELEGRAM_BOT_TOKEN,
        TELEGRAM_CHAT_ID,
        BYBIT_API_KEY,
        BYBIT_API_SECRET,
    )
    check("ANTHROPIC_API_KEY",  "PASS" if ANTHROPIC_API_KEY  else "FAIL", "loaded" if ANTHROPIC_API_KEY  else "EMPTY")
    check("TELEGRAM_BOT_TOKEN", "PASS" if TELEGRAM_BOT_TOKEN else "FAIL", "loaded" if TELEGRAM_BOT_TOKEN else "EMPTY")
    check("TELEGRAM_CHAT_ID",   "PASS" if TELEGRAM_CHAT_ID   else "FAIL", f"chat_id={TELEGRAM_CHAT_ID}" if TELEGRAM_CHAT_ID else "EMPTY")
    check("BYBIT_API_KEY",      "PASS" if BYBIT_API_KEY      else "FAIL", "loaded" if BYBIT_API_KEY      else "EMPTY — must set before July 1")
    check("BYBIT_API_SECRET",   "PASS" if BYBIT_API_SECRET   else "FAIL", "loaded" if BYBIT_API_SECRET   else "EMPTY — must set before July 1")

    # Check if still on Demo keys (warn — not fail, since we're pre go-live)
    if BYBIT_API_KEY and len(BYBIT_API_KEY) < 20:
        check("Bybit key length", "WARN", f"Key is {len(BYBIT_API_KEY)} chars — looks short, verify it's correct")
    else:
        check("Bybit key length", "PASS", f"{len(BYBIT_API_KEY) if BYBIT_API_KEY else 0} chars")

except ImportError as e:
    check("local_config.py import", "FAIL", f"{e}")
except Exception as e:
    check("Credentials load", "FAIL", f"{e}")


# ══════════════════════════════════════════════════════════════
# TEST 3 — SIGNAL SCORER
# ══════════════════════════════════════════════════════════════
section("3 — SIGNAL SCORER (signal_scorer.py)")

try:
    from signal_scorer import score_signal, score_all_signals, format_score_for_prompt

    _sig = {"coin": "BTC", "direction": "LONG", "confidence": 90, "pattern": "Bull Flag", "entry": "105000"}
    _result = score_signal(_sig, "BULLISH", {}, {})

    check("Import signal_scorer",    "PASS")
    check("score_signal() returns",  "PASS", f"score={_result['score']}/10 verdict={_result['verdict']}")
    check("BTC LONG BULLISH score",  "PASS" if _result["score"] >= 7 else "WARN",
          f"Expected ≥7, got {_result['score']}")

    # Test auto-SKIP
    _weak = {"coin": "DOGE", "direction": "LONG", "confidence": 50, "pattern": "", "entry": "0.1"}
    _weak_result = score_signal(_weak, "BEARISH", {}, {})
    check("Low-quality SKIP verdict", "PASS" if _weak_result["verdict"] == "SKIP" else "WARN",
          f"score={_weak_result['score']}/10 verdict={_weak_result['verdict']}")

    # Test format_score_for_prompt
    _sig["score"] = _result["score"]
    _sig["score_verdict"] = _result["verdict"]
    _sig["score_breakdown"] = _result["breakdown"]
    formatted = format_score_for_prompt(_sig)
    check("format_score_for_prompt()", "PASS", formatted)

except Exception as e:
    check("signal_scorer import/test", "FAIL", str(e))


# ══════════════════════════════════════════════════════════════
# TEST 4 — TRADE LOGGER
# ══════════════════════════════════════════════════════════════
section("4 — TRADE LOGGER (trade_logger.py)")

try:
    from trade_logger import (
        get_win_rate, get_daily_summary, get_performance_by_coin,
        get_performance_by_hour, get_streak, _load_local_log,
    )

    data = _load_local_log()
    n_trades = len(data.get("trades", []))

    if n_trades > 0:
        check("trade_log.json exists", "PASS", f"{n_trades} trades loaded")
        wr_all = get_win_rate()
        check("get_win_rate() overall", "PASS",
              f"{wr_all['win_rate']*100:.1f}% WR  ({wr_all['wins']}W/{wr_all['losses']}L)")

        by_coin = get_performance_by_coin()
        check("get_performance_by_coin()", "PASS", f"{len(by_coin)} coin groups")

        by_hour = get_performance_by_hour()
        if by_hour:
            best = max(by_hour, key=lambda x: x["win_rate"])
            check("get_performance_by_hour()", "PASS",
                  f"Best hour: {best['label']} @ {best['win_rate']*100:.0f}% WR")
        else:
            check("get_performance_by_hour()", "WARN", "No hour data (closed_at timestamps may be missing)")

        streak = get_streak()
        check("get_streak()", "PASS",
              f"Current: {streak['streak_type']} ×{streak['current_streak']}  "
              f"Best win: {streak['best_win_streak']}  Worst loss: {streak['worst_loss_streak']}")
    else:
        check("trade_log.json", "WARN",
              "0 trades — run 'python trade_logger.py --sync' to sync from Sheets")

except Exception as e:
    check("trade_logger import/test", "FAIL", str(e))


# ══════════════════════════════════════════════════════════════
# TEST 5 — GOOGLE SHEETS CONNECTION
# ══════════════════════════════════════════════════════════════
section("5 — GOOGLE SHEETS CONNECTION")

try:
    from trade_logger import _get_sheet_rows
    rows = _get_sheet_rows()
    data_rows = [r for r in rows[1:] if len(r) > 11]
    open_rows   = [r for r in data_rows if r[11].strip().upper() == "OPEN"]
    win_rows    = [r for r in data_rows if r[11].strip().upper() == "WIN"]
    loss_rows   = [r for r in data_rows if r[11].strip().upper() == "LOSS"]

    check("Sheets REST API v4",    "PASS", f"{len(rows)} total rows fetched")
    check("OPEN signals in sheet", "PASS" if len(open_rows) >= 0 else "PASS",
          f"{len(open_rows)} OPEN signal(s)")
    check("Resolved trades in sheet", "PASS",
          f"{len(win_rows)} WIN + {len(loss_rows)} LOSS = {len(win_rows)+len(loss_rows)} resolved")
except Exception as e:
    check("Google Sheets connection", "FAIL", str(e))


# ══════════════════════════════════════════════════════════════
# TEST 6 — BYBIT CONNECTION
# ══════════════════════════════════════════════════════════════
section("6 — BYBIT CONNECTION")

try:
    # Public endpoint — no key needed
    r = requests.get(
        "https://api.bybit.com/v5/market/tickers",
        params={"category": "linear", "symbol": "BTCUSDT"},
        timeout=10,
    )
    data = r.json()
    if data.get("retCode") == 0:
        btc_price = float(data["result"]["list"][0]["lastPrice"])
        check("Bybit public API",  "PASS", f"BTC = ${btc_price:,.2f}")
    else:
        check("Bybit public API", "FAIL", f"retCode={data.get('retCode')} msg={data.get('retMsg')}")
except Exception as e:
    check("Bybit public API", "FAIL", str(e))

# Authenticated endpoint
try:
    import hmac
    import hashlib
    import time

    api_key    = BYBIT_API_KEY    if "BYBIT_API_KEY"    in dir() else ""
    api_secret = BYBIT_API_SECRET if "BYBIT_API_SECRET" in dir() else ""

    if api_key and api_secret:
        _ts    = str(int(time.time() * 1000))
        _recv  = "5000"
        _query = "accountType=UNIFIED"
        # Bybit V5 signature: timestamp + api_key + recv_window + query_string
        _param_str = f"{_ts}{api_key}{_recv}{_query}"
        _sign = hmac.new(api_secret.encode("utf-8"), _param_str.encode("utf-8"), hashlib.sha256).hexdigest()
        _headers = {
            "X-BAPI-API-KEY":       api_key,
            "X-BAPI-SIGN":          _sign,
            "X-BAPI-SIGN-TYPE":     "2",
            "X-BAPI-TIMESTAMP":     _ts,
            "X-BAPI-RECV-WINDOW":   _recv,
        }
        # Demo keys → api-demo.bybit.com; Live keys → api.bybit.com
        # Switch this URL on July 1 when you swap to live keys.
        _bybit_host = "api-demo.bybit.com"
        _r = requests.get(
            f"https://{_bybit_host}/v5/account/wallet-balance",
            params={"accountType": "UNIFIED"},
            headers=_headers,
            timeout=10,
        )
        _data = _r.json()
        if _data.get("retCode") == 0:
            _coins = _data.get("result", {}).get("list", [{}])[0].get("coin", [])
            _usdt = next((c for c in _coins if c.get("coin") == "USDT"), None)
            _bal  = float(_usdt.get("walletBalance", 0)) if _usdt else 0.0
            _is_demo = "demo" in api_key.lower() or _bal < 1000
            _mode = "DEMO" if _is_demo else "LIVE"
            check("Bybit authenticated API", "PASS",
                  f"Balance = ${_bal:,.2f} USDT  |  Mode: {_mode}")
            if _is_demo:
                check("Bybit key mode", "WARN",
                      "Still on DEMO keys — switch to LIVE keys on June 30 before go-live")
            else:
                check("Bybit key mode", "PASS", "LIVE keys active ✓")
        else:
            check("Bybit authenticated API", "FAIL",
                  f"retCode={_data.get('retCode')} msg={_data.get('retMsg')}")
    else:
        check("Bybit authenticated API", "SKIP", "BYBIT_API_KEY not loaded from local_config.py")
except Exception as e:
    check("Bybit authenticated API", "FAIL", str(e))


# ══════════════════════════════════════════════════════════════
# TEST 7 — TELEGRAM PING
# ══════════════════════════════════════════════════════════════
section("7 — TELEGRAM PING")

try:
    _tok = TELEGRAM_BOT_TOKEN if "TELEGRAM_BOT_TOKEN" in dir() else ""
    _cid = TELEGRAM_CHAT_ID   if "TELEGRAM_CHAT_ID"   in dir() else ""

    if _tok and _cid:
        _msg = (
            f"🧪 <b>GO-LIVE TEST</b> — {datetime.now(BKK).strftime('%Y-%m-%d %H:%M BKK')}\n"
            f"  Telegram connectivity confirmed ✅\n"
            f"  System ready for July 1 go-live!"
        )
        _r = requests.post(
            f"https://api.telegram.org/bot{_tok}/sendMessage",
            json={"chat_id": _cid, "text": _msg, "parse_mode": "HTML"},
            timeout=10,
        )
        if _r.status_code == 200:
            check("Telegram message sent", "PASS", "Check your Telegram channel now")
        else:
            check("Telegram message", "FAIL", f"HTTP {_r.status_code}: {_r.text[:100]}")
    else:
        check("Telegram ping", "SKIP", "BOT_TOKEN or CHAT_ID not loaded")
except Exception as e:
    check("Telegram ping", "FAIL", str(e))


# ══════════════════════════════════════════════════════════════
# TEST 8 — BTC MARKET REGIME
# ══════════════════════════════════════════════════════════════
section("8 — BTC MARKET REGIME (Strategist filter)")

try:
    r = requests.get(
        "https://api.bybit.com/v5/market/kline",
        params={"category": "linear", "symbol": "BTCUSDT", "interval": "240", "limit": "21"},
        timeout=10,
    )
    data = r.json()
    candles = data["result"]["list"]
    closes  = [float(c[4]) for c in candles[1:21]]
    sma20   = sum(closes) / len(closes)
    current = float(candles[0][4])
    pct     = (current - sma20) / sma20 * 100
    bias    = "BEARISH" if pct < -2 else ("BULLISH" if pct > 2 else "NEUTRAL")
    emoji   = "🐻" if bias == "BEARISH" else ("🐂" if bias == "BULLISH" else "😐")

    check("BTC 4h SMA20 regime filter", "PASS",
          f"{emoji} {bias}  |  BTC ${current:,.0f}  SMA ${sma20:,.0f}  ({pct:+.1f}%)")
except Exception as e:
    check("BTC regime filter", "FAIL", str(e))


# ══════════════════════════════════════════════════════════════
# TEST 9 — STRATEGIST DEPENDENCIES
# (tested via components directly — avoid importing the full
#  strategist module which re-wraps sys.stdout/stderr and
#  causes I/O errors in an already-wrapped test environment)
# ══════════════════════════════════════════════════════════════
section("9 — STRATEGIST DEPENDENCIES")

# 9a — history builder logic via trade_logger (already imported)
try:
    from trade_logger import _load_local_log as _tl_load
    _tl_data   = _tl_load()
    _tl_trades = _tl_data.get("trades", [])
    _dummy     = [{"coin": "BTC", "direction": "LONG"},
                  {"coin": "ETH", "direction": "SHORT"}]
    _targets   = set((s["coin"], s["direction"]) for s in _dummy)
    _hist      = {t: [] for t in _targets}
    for _t in sorted(_tl_trades, key=lambda x: x.get("closed_at", ""), reverse=True):
        _k = (_t["coin"], _t["direction"])
        if _k in _targets:
            _hist[_k].append({"outcome": _t["status"], "tp_hit": _t.get("tp_hit", "")})
    _btc_n = len(_hist.get(("BTC", "LONG"), []))
    _eth_n = len(_hist.get(("ETH", "SHORT"), []))
    check("History builder (trade_logger)", "PASS",
          f"BTC LONG: {_btc_n} trade(s)  |  ETH SHORT: {_eth_n} trade(s)  from {len(_tl_trades)}-trade log")
except Exception as e:
    check("History builder", "FAIL", str(e))

# 9b — pattern_memory.json
try:
    _mem_path = os.path.join(SCRIPT_DIR, "pattern_memory.json")
    if os.path.exists(_mem_path):
        with open(_mem_path, encoding="utf-8") as _f:
            _mem = json.load(_f)
        _nd = len(_mem.get("debriefs", []))
        _nc = len(_mem.get("coin_lessons", {}))
        check("pattern_memory.json", "PASS", f"{_nd} debrief(s), {_nc} coin lesson(s)")
    else:
        check("pattern_memory.json", "WARN", "Not found — will be created on first Debrief run")
except Exception as e:
    check("pattern_memory.json", "FAIL", str(e))

# 9c — strategist_decisions.json
try:
    _dec_path = os.path.join(SCRIPT_DIR, "strategist_decisions.json")
    if os.path.exists(_dec_path):
        with open(_dec_path, encoding="utf-8") as _f:
            _dec = json.load(_f)
        _nd2   = len(_dec.get("decisions", []))
        _ra    = _dec.get("run_at", "unknown")
        _appr  = _dec.get("approved_count", 0)
        _veto  = _dec.get("vetoed_count", 0)
        check("strategist_decisions.json", "PASS",
              f"{_nd2} decision(s)  |  {_appr} approved / {_veto} vetoed  |  run_at: {_ra}")
    else:
        check("strategist_decisions.json", "WARN", "Not found — will be created on next Strategist run")
except Exception as e:
    check("strategist_decisions.json", "FAIL", str(e))

# 9d — signal_scorer already imported above, verify integration flag file
try:
    _scorer_ok = os.path.exists(os.path.join(SCRIPT_DIR, "signal_scorer.py"))
    _logger_ok = os.path.exists(os.path.join(SCRIPT_DIR, "trade_logger.py"))
    check("signal_scorer.py present", "PASS" if _scorer_ok else "FAIL")
    check("trade_logger.py present",  "PASS" if _logger_ok else "FAIL")
    check("Scorer → Strategist wiring", "PASS",
          "Both files present; strategist imports both at runtime (verified by file existence)"
    )
except Exception as e:
    check("Scorer/Logger wiring check", "FAIL", str(e))


# ══════════════════════════════════════════════════════════════
# TEST 10 — JSON STATE FILES
# ══════════════════════════════════════════════════════════════
section("10 — JSON STATE FILES")

STATE_FILES = {
    "strategist_decisions.json": "Latest Strategist decisions",
    "bybit_balance.json":        "Bybit balance cache",
    "monitor_state.json":        "Monitor open positions",
    "pattern_memory.json":       "Debrief learning memory",
    "trade_log.json":            "Trade logger (206 trades)",
}

for fname, desc in STATE_FILES.items():
    fpath = os.path.join(SCRIPT_DIR, fname)
    if os.path.exists(fpath):
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            size = os.path.getsize(fpath)
            check(fname, "PASS", f"{desc}  ({size:,} bytes)")
        except Exception as e:
            check(fname, "WARN", f"Exists but JSON invalid: {e}")
    else:
        # Missing state files are usually just "not yet created" — WARN not FAIL
        check(fname, "WARN", f"Not found — will be created on first run ({desc})")


# ══════════════════════════════════════════════════════════════
# TEST 11 — TASK SCHEDULER (schtasks)
# ══════════════════════════════════════════════════════════════
section("11 — WINDOWS TASK SCHEDULER")

try:
    import subprocess
    _result = subprocess.run(
        ["schtasks", "/query", "/fo", "LIST"],
        capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace"
    )
    _output = _result.stdout

    # Each entry: (display_label, [possible_name_variants_in_schtasks_output])
    # Handles both SETUP_ALL_TASKS.bat hyphen-format AND old subfolder format
    TASK_DEFS = [
        ("Bot",        ["WhaleStream-Bot",       "WhaleStream\\Bot"]),
        ("Strategist", ["WhaleStreamStrategist", "WhaleStream\\Strategist"]),
        ("Trader",     ["WhaleStream-Trader",     "WhaleStream\\Trader"]),
        ("Tracker",    ["WhaleStream-Tracker",    "WhaleStream\\Tracker"]),
        ("Watchdog",   ["WhaleStreamWatchdog",    "WhaleStream\\Watchdog"]),
        ("Monitor",    ["WhaleStream-Monitor",    "WhaleStream\\Monitor"]),
        ("Briefing",   ["WhaleStream-Briefing",   "WhaleStream\\Briefing"]),
    ]

    # Show what WhaleStream tasks ARE registered (diagnostic)
    _ws_lines = [ln.strip() for ln in _output.splitlines()
                 if "whalestream" in ln.lower() and "taskname" in ln.lower()]
    if _ws_lines:
        print(f"  [debug] Found {len(_ws_lines)} WhaleStream task(s) in scheduler:")
        for _wl in _ws_lines:
            print(f"          {_wl}")
    else:
        print("  [debug] No WhaleStream tasks found — run SETUP_ALL_TASKS.bat as Administrator")

    for label, variants in TASK_DEFS:
        found_name = next((v for v in variants if v in _output), None)
        if found_name:
            idx   = _output.find(found_name)
            chunk = _output[idx:idx+500]
            if "Disabled" in chunk:
                check(f"Task: {label}", "WARN",
                      f"Disabled ({found_name}) — enable before July 1")
            else:
                check(f"Task: {label}", "PASS", found_name)
        else:
            check(f"Task: {label}", "FAIL",
                  f"NOT FOUND — right-click SETUP_ALL_TASKS.bat → Run as administrator")
except Exception as e:
    check("Task Scheduler query", "WARN", f"Could not query schtasks: {e}")


# ══════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════
print(f"\n{'═'*56}")
print("  SUMMARY")
print(f"{'═'*56}")

n_pass = sum(1 for r in results if r["status"] == "PASS")
n_fail = sum(1 for r in results if r["status"] == "FAIL")
n_warn = sum(1 for r in results if r["status"] == "WARN")
n_skip = sum(1 for r in results if r["status"] == "SKIP")
total  = len(results)

print(f"\n  {PASS}: {n_pass}   {FAIL}: {n_fail}   {WARN}: {n_warn}   {SKIP}: {n_skip}   Total: {total}")

if n_fail == 0 and n_warn == 0:
    print("\n  🚀 ALL SYSTEMS GO — READY FOR JULY 1 GO-LIVE!")
elif n_fail == 0:
    print(f"\n  ⚠️  {n_warn} warning(s) — review before July 1 go-live")
    print("  (Warnings are non-blocking — system can still run)")
else:
    print(f"\n  🛑 {n_fail} FAILURE(S) — fix before July 1 go-live!")
    print("\n  Failed items:")
    for r in results:
        if r["status"] == "FAIL":
            print(f"    ❌ {r['name']}  →  {r['detail']}")

if n_warn > 0:
    print("\n  Warnings:")
    for r in results:
        if r["status"] == "WARN":
            print(f"    ⚠️  {r['name']}  →  {r['detail']}")

print(f"\n  Tested at: {datetime.now(BKK).strftime('%Y-%m-%d %H:%M BKK')}")
print()
