"""
╔══════════════════════════════════════════════════════════════╗
║   WHALE-STREAM TRADE LOGGER v1.0                             ║
║                                                              ║
║  Persistent WIN/LOSS trade log with full stats engine.       ║
║                                                              ║
║  Syncs resolved trades from Google Sheets → trade_log.json   ║
║  Exports to trade_log.csv for Excel analysis.                ║
║                                                              ║
║  Trade categories:                                           ║
║    FULL_WIN    — TP3 or TP4 hit (maximum profit captured)    ║
║    PARTIAL_WIN — TP1 or TP2 hit (partial profit)             ║
║    LOSS        — SL hit before any TP                        ║
║                                                              ║
║  Usage:                                                      ║
║    Standalone:  python trade_logger.py [--sync] [--stats]    ║
║    As module:   from trade_logger import (                   ║
║                     get_win_rate, get_daily_summary,         ║
║                     get_performance_by_coin,                 ║
║                     get_performance_by_pattern,              ║
║                     get_performance_by_hour)                 ║
║                                                              ║
║  Runs automatically after every tracker resolution cycle.    ║
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
import csv
import json
import re
from datetime import datetime, timezone, timedelta

BKK = timezone(timedelta(hours=7))   # Bangkok timezone (UTC+7) — used everywhere

# ── Force UTF-8 output ─────────────────────────────────────────
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# ── Credentials ────────────────────────────────────────────────
try:
    from local_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ══════════════════════════════════════════════════════════════════
# SECTION 1 — CONFIGURATION
# ══════════════════════════════════════════════════════════════════

SCRIPT_DIR           = os.path.dirname(os.path.abspath(__file__))
TRADE_LOG_FILE       = os.path.join(SCRIPT_DIR, "trade_log.json")
TRADE_LOG_CSV        = os.path.join(SCRIPT_DIR, "trade_log.csv")
LOG_FILE             = os.path.join(SCRIPT_DIR, "trade_logger_log.txt")
GOOGLE_SHEET_ID      = "1R21mkduSpbki2HmlNJMHM95-LkGS0q-AKHE1HVIfMmI"
GOOGLE_CREDS_FILE    = "google_credentials.json"

# Google Sheets column indices — must match whale_stream_strategist.py
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


# ══════════════════════════════════════════════════════════════════
# SECTION 2 — HELPERS
# ══════════════════════════════════════════════════════════════════

def log(msg):
    bkk = datetime.now(BKK).strftime("%Y-%m-%d %H:%M BKK")
    line = f"[{bkk}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def send_telegram(msg):
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def safe_float(s, default=None):
    """Parse '+45.20%' or '-3.50%' or '0.685' → float. Returns default on failure."""
    try:
        return float(str(s).replace("%", "").replace("+", "").strip())
    except Exception:
        return default


def _get_sheet_rows() -> list:
    """
    Fetch all rows from Google Sheet using the Sheets REST API v4.
    No gspread dependency — uses google-auth (already installed by other agents).
    Returns list of lists (same format as gspread.get_all_values()).
    """
    import requests as _req
    from google.oauth2.service_account import Credentials as _GCreds
    from google.auth.transport.requests import Request as _GReq

    creds_path = os.path.join(SCRIPT_DIR, GOOGLE_CREDS_FILE)
    _SCOPES    = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds      = _GCreds.from_service_account_file(creds_path, scopes=_SCOPES)
    creds.refresh(_GReq())

    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets"
        f"/{GOOGLE_SHEET_ID}/values/Sheet1"
    )
    resp = _req.get(url, headers={"Authorization": f"Bearer {creds.token}"}, timeout=15)
    resp.raise_for_status()
    return resp.json().get("values", [])


def _categorise(status: str, tp_hit: str, pnl_pct: float) -> str:
    """
    Assign a trade category based on outcome.

    FULL_WIN    — TP3 or TP4 hit
    PARTIAL_WIN — TP1 or TP2 hit, or WIN with unspecified TP
    LOSS        — SL hit before any TP
    """
    st = status.strip().upper()
    tp = tp_hit.strip().upper()

    if st == "WIN":
        if tp in ("TP3", "TP4"):
            return "FULL_WIN"
        return "PARTIAL_WIN"
    # LOSS
    return "LOSS"


def _load_local_log() -> dict:
    """Load trade_log.json, returning empty structure if missing."""
    empty = {
        "version": "1.0",
        "synced_at": "",
        "trades": [],
        "stats": {
            "total_trades": 0,
            "full_wins":    0,
            "partial_wins": 0,
            "losses":       0,
            "total_pnl_usd": 0.0,
        },
    }
    try:
        with open(TRADE_LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure stats key exists (migration safety)
        if "stats" not in data:
            data["stats"] = empty["stats"]
        return data
    except Exception:
        return empty


def _save_local_log(data: dict):
    """Atomic write of trade_log.json."""
    tmp = TRADE_LOG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, TRADE_LOG_FILE)


def _export_csv(trades: list):
    """Write trade_log.csv — overwrite every sync."""
    fieldnames = [
        "id", "coin", "direction", "category",
        "entry_price", "exit_price", "tp_hit", "pnl_pct", "pnl_usd",
        "pattern", "mtf_bias", "signal_score", "opened_at", "closed_at",
        "bybit_order_id", "conf_pct",
    ]
    with open(TRADE_LOG_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    print(f"   ✓ trade_log.csv updated ({len(trades)} rows)")


# ══════════════════════════════════════════════════════════════════
# SECTION 3 — SYNC FROM GOOGLE SHEETS
# ══════════════════════════════════════════════════════════════════

def sync_from_sheets() -> int:
    """
    Pull all resolved trades from Google Sheets and rebuild trade_log.json.
    Returns count of resolved trades synced.
    """
    print("📋 Connecting to Google Sheets...")
    try:
        all_rows = _get_sheet_rows()
    except Exception as e:
        log(f"✗ Sheets connection failed: {e}")
        return 0

    data_rows = all_rows[1:] if len(all_rows) > 1 else []  # skip header
    trades = []

    for i, row in enumerate(data_rows, start=2):   # row 2 = first data row in sheet
        if len(row) <= COL_STATUS:
            continue
        status = row[COL_STATUS].strip().upper()
        if status not in ("WIN", "LOSS"):
            continue  # only resolved trades

        coin       = row[COL_COIN].strip().upper()       if len(row) > COL_COIN        else ""
        _dir_raw   = row[COL_SIGNAL].strip().upper()     if len(row) > COL_SIGNAL      else ""
        direction  = "LONG" if "LONG" in _dir_raw else ("SHORT" if "SHORT" in _dir_raw else _dir_raw)
        conf_raw   = row[COL_CONF].strip()               if len(row) > COL_CONF        else ""
        pattern    = row[COL_PATTERN].strip()            if len(row) > COL_PATTERN     else ""
        # Extract MTF bias embedded in pattern string (e.g. "Bull flag [4H_BULL_1H_PULLBACK]")
        _mtf_m   = re.search(r'\[([A-Z0-9_]{5,30})\]', pattern)
        mtf_bias = _mtf_m.group(1) if _mtf_m and _mtf_m.group(1).startswith(("4H_", "MTF_")) else ""
        opened_at  = row[COL_TIMESTAMP].strip()          if len(row) > COL_TIMESTAMP   else ""
        entry_px   = row[COL_ENTRY_PRICE].strip()        if len(row) > COL_ENTRY_PRICE else ""
        exit_px    = row[COL_EXIT_PRICE].strip()         if len(row) > COL_EXIT_PRICE  else ""
        tp_hit     = row[COL_TP_HIT].strip()             if len(row) > COL_TP_HIT      else ""
        pnl_raw    = row[COL_PNL].strip()                if len(row) > COL_PNL         else ""
        closed_at  = row[COL_RESOLVED_AT].strip()        if len(row) > COL_RESOLVED_AT else ""
        bybit_id   = row[COL_BYBIT_ID].strip()           if len(row) > COL_BYBIT_ID    else ""

        if not coin or direction not in ("LONG", "SHORT"):
            continue

        pnl_pct  = safe_float(pnl_raw, default=0.0)
        conf_pct = safe_float(conf_raw, default=0.0)
        category = _categorise(status, tp_hit, pnl_pct)

        # Estimate USD P&L (margin $20 by default; refined if we know margin)
        margin   = 20.0   # Phase 1 default — future: read from dedicated column
        pnl_usd  = round((pnl_pct / 100.0) * margin, 4) if pnl_pct is not None else 0.0

        # Extract hour from opened_at for time-of-day analysis
        hour = None
        try:
            clean = opened_at.replace(" BKK", "").strip()
            dt    = datetime.strptime(clean, "%Y-%m-%d %H:%M")
            hour  = dt.hour
        except Exception:
            pass

        trade_id = f"{coin}_{direction}_{closed_at}_r{i}".replace(" ", "_").replace(":", "")  # row index prevents same-minute collisions

        trades.append({
            "id":            trade_id,
            "coin":          coin,
            "direction":     direction,
            "category":      category,
            "status":        status,
            "entry_price":   entry_px,
            "exit_price":    exit_px,
            "tp_hit":        tp_hit,
            "pnl_pct":       pnl_pct,
            "pnl_usd":       pnl_usd,
            "conf_pct":      conf_pct,
            "pattern":       pattern,
            "mtf_bias":      mtf_bias,   # e.g. "4H_BULL_1H_PULLBACK" — NEW v47.20
            "signal_score":  None,   # filled by signal_scorer when available
            "opened_at":     opened_at,
            "closed_at":     closed_at,
            "hour_bkk":      hour,
            "bybit_order_id": bybit_id,
            "sheet_row":     i,
        })

    # Recompute aggregate stats
    full_wins    = sum(1 for t in trades if t["category"] == "FULL_WIN")
    partial_wins = sum(1 for t in trades if t["category"] == "PARTIAL_WIN")
    losses       = sum(1 for t in trades if t["category"] == "LOSS")
    total_pnl    = round(sum(t["pnl_usd"] for t in trades), 2)

    data = {
        "version":   "1.0",
        "synced_at": datetime.now(BKK).strftime("%Y-%m-%d %H:%M BKK"),
        "trades":    trades,
        "stats": {
            "total_trades": len(trades),
            "full_wins":    full_wins,
            "partial_wins": partial_wins,
            "losses":       losses,
            "wins":         full_wins + partial_wins,
            "total_pnl_usd": total_pnl,
        },
    }

    _save_local_log(data)
    _export_csv(trades)

    print(f"   ✓ Synced {len(trades)} resolved trades  "
          f"({full_wins} full wins + {partial_wins} partial wins + {losses} losses)")
    print(f"   💰 Total P&L: ${total_pnl:+.2f}")
    log(f"Synced {len(trades)} trades: {full_wins}FW / {partial_wins}PW / {losses}L  PNL=${total_pnl:+.2f}")
    return len(trades)


# ══════════════════════════════════════════════════════════════════
# SECTION 4 — QUERY FUNCTIONS (import by other agents)
# ══════════════════════════════════════════════════════════════════

def get_win_rate(coin: str = None, direction: str = None) -> dict:
    """
    Return win rate stats for a specific coin+direction (or all trades).

    Returns:
        {
          "total": int,
          "wins": int,          # FULL_WIN + PARTIAL_WIN
          "full_wins": int,
          "partial_wins": int,
          "losses": int,
          "win_rate": float,    # 0.0 – 1.0
          "full_win_rate": float,
          "avg_pnl_pct": float,
        }
    """
    data   = _load_local_log()
    trades = data.get("trades", [])

    if coin:
        trades = [t for t in trades if t["coin"] == coin.upper()]
    if direction:
        trades = [t for t in trades if t["direction"] == direction.upper()]

    total    = len(trades)
    fw       = sum(1 for t in trades if t["category"] == "FULL_WIN")
    pw       = sum(1 for t in trades if t["category"] == "PARTIAL_WIN")
    losses   = sum(1 for t in trades if t["category"] == "LOSS")
    wins     = fw + pw
    wr       = wins / total if total > 0 else 0.0
    fwr      = fw / total   if total > 0 else 0.0
    avg_pnl  = (sum(t["pnl_pct"] for t in trades) / total) if total > 0 else 0.0

    return {
        "total":          total,
        "wins":           wins,
        "full_wins":      fw,
        "partial_wins":   pw,
        "losses":         losses,
        "win_rate":       round(wr, 4),
        "full_win_rate":  round(fwr, 4),
        "avg_pnl_pct":   round(avg_pnl, 2),
    }


def get_daily_summary(date_str: str = None) -> dict:
    """
    Return today's (or a specific date's) trading summary.
    date_str format: 'YYYY-MM-DD'. Defaults to today BKK.
    """
    if date_str is None:
        date_str = datetime.now(BKK).strftime("%Y-%m-%d")

    data   = _load_local_log()
    trades = [t for t in data.get("trades", [])
              if t.get("closed_at", "").startswith(date_str)]

    total    = len(trades)
    fw       = sum(1 for t in trades if t["category"] == "FULL_WIN")
    pw       = sum(1 for t in trades if t["category"] == "PARTIAL_WIN")
    losses   = sum(1 for t in trades if t["category"] == "LOSS")
    pnl_usd  = round(sum(t["pnl_usd"] for t in trades), 2)
    wr       = (fw + pw) / total if total > 0 else 0.0

    return {
        "date":          date_str,
        "total_trades":  total,
        "full_wins":     fw,
        "partial_wins":  pw,
        "losses":        losses,
        "win_rate":      round(wr, 4),
        "total_pnl_usd": pnl_usd,
        "trades":        trades,
    }


def get_performance_by_coin() -> list:
    """
    Return per-coin win rate and P&L, sorted by win rate descending.

    Returns list of dicts: [{coin, direction, total, wins, losses, win_rate, avg_pnl_pct, total_pnl_usd}]
    """
    data   = _load_local_log()
    trades = data.get("trades", [])

    # Group by (coin, direction)
    groups = {}
    for t in trades:
        key = (t["coin"], t["direction"])
        groups.setdefault(key, []).append(t)

    results = []
    for (coin, direction), group in groups.items():
        total   = len(group)
        wins    = sum(1 for t in group if t["category"] in ("FULL_WIN", "PARTIAL_WIN"))
        fw      = sum(1 for t in group if t["category"] == "FULL_WIN")
        losses  = sum(1 for t in group if t["category"] == "LOSS")
        wr      = wins / total if total > 0 else 0.0
        avg_pnl = sum(t["pnl_pct"] for t in group) / total if total > 0 else 0.0
        tot_pnl = round(sum(t["pnl_usd"] for t in group), 2)

        results.append({
            "coin":          coin,
            "direction":     direction,
            "total":         total,
            "wins":          wins,
            "full_wins":     fw,
            "losses":        losses,
            "win_rate":      round(wr, 4),
            "avg_pnl_pct":  round(avg_pnl, 2),
            "total_pnl_usd": tot_pnl,
        })

    return sorted(results, key=lambda x: (-x["win_rate"], -x["total"]))


def get_performance_by_pattern() -> list:
    """
    Return win rate and P&L grouped by pattern, sorted by win rate descending.
    """
    data   = _load_local_log()
    trades = data.get("trades", [])

    groups = {}
    for t in trades:
        pat = t.get("pattern", "Unknown") or "Unknown"
        groups.setdefault(pat, []).append(t)

    results = []
    for pattern, group in groups.items():
        total   = len(group)
        wins    = sum(1 for t in group if t["category"] in ("FULL_WIN", "PARTIAL_WIN"))
        losses  = total - wins
        wr      = wins / total if total > 0 else 0.0
        avg_pnl = sum(t["pnl_pct"] for t in group) / total if total > 0 else 0.0

        results.append({
            "pattern":      pattern,
            "total":        total,
            "wins":         wins,
            "losses":       losses,
            "win_rate":     round(wr, 4),
            "avg_pnl_pct":  round(avg_pnl, 2),
        })

    return sorted(results, key=lambda x: (-x["win_rate"], -x["total"]))


def get_performance_by_hour() -> list:
    """
    Return win rate by BKK hour-of-day. Reveals which hours produce best signals.
    """
    data   = _load_local_log()
    trades = [t for t in data.get("trades", []) if t.get("hour_bkk") is not None]

    groups = {}
    for t in trades:
        h = t["hour_bkk"]
        groups.setdefault(h, []).append(t)

    results = []
    for hour, group in sorted(groups.items()):
        total  = len(group)
        wins   = sum(1 for t in group if t["category"] in ("FULL_WIN", "PARTIAL_WIN"))
        losses = total - wins
        wr     = wins / total if total > 0 else 0.0

        results.append({
            "hour_bkk":  hour,
            "label":     f"{hour:02d}:00 BKK",
            "total":     total,
            "wins":      wins,
            "losses":    losses,
            "win_rate":  round(wr, 4),
        })

    return results


def get_streak() -> dict:
    """
    Return current winning/losing streak and longest streaks from trade history.
    Trades ordered by closed_at.
    """
    data   = _load_local_log()
    trades = sorted(
        data.get("trades", []),
        key=lambda t: t.get("closed_at", "")
    )

    if not trades:
        return {"current_streak": 0, "streak_type": "none", "best_win_streak": 0, "worst_loss_streak": 0}

    current_streak     = 1
    best_win_streak    = 0
    worst_loss_streak  = 0
    _win_run           = 0
    _loss_run          = 0

    last_outcome = "WIN" if trades[-1]["category"] in ("FULL_WIN", "PARTIAL_WIN") else "LOSS"

    for t in trades:
        is_win = t["category"] in ("FULL_WIN", "PARTIAL_WIN")
        if is_win:
            _win_run  += 1
            _loss_run  = 0
        else:
            _loss_run += 1
            _win_run   = 0
        best_win_streak   = max(best_win_streak,  _win_run)
        worst_loss_streak = max(worst_loss_streak, _loss_run)

    # Current streak = run at end of list
    current_streak = _win_run if last_outcome == "WIN" else _loss_run

    return {
        "current_streak":    current_streak,
        "streak_type":       last_outcome,
        "best_win_streak":   best_win_streak,
        "worst_loss_streak": worst_loss_streak,
        "last_outcome":      last_outcome,
    }


# ══════════════════════════════════════════════════════════════════
# SECTION 5 — PRINT STATS REPORT
# ══════════════════════════════════════════════════════════════════

def print_stats_report():
    """Print a full performance report to console."""
    data  = _load_local_log()
    stats = data.get("stats", {})
    total = stats.get("total_trades", 0)

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║   📊  WHALE-STREAM TRADE LOG — PERFORMANCE REPORT   ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"   Synced at : {data.get('synced_at', 'never')}")
    print(f"   Total trades: {total}")
    print()

    if total == 0:
        print("   No resolved trades yet.")
        return

    fw    = stats.get("full_wins",    0)
    pw    = stats.get("partial_wins", 0)
    ls    = stats.get("losses",       0)
    wins  = fw + pw
    wr    = wins / total * 100 if total > 0 else 0.0
    pnl   = stats.get("total_pnl_usd", 0.0)

    print("── OVERALL ─────────────────────────────────────────")
    print(f"   Win Rate   : {wr:.1f}%  ({wins}W / {ls}L / {total} total)")
    print(f"   Full Wins  : {fw}  ({fw/total*100:.1f}%)")
    print(f"   Partial W  : {pw}  ({pw/total*100:.1f}%)")
    print(f"   Losses     : {ls}  ({ls/total*100:.1f}%)")
    print(f"   Total P&L  : ${pnl:+.2f}")

    streak = get_streak()
    s_icon = "🔥" if streak["streak_type"] == "WIN" else "❄️"
    print(f"\n── STREAKS ─────────────────────────────────────────")
    print(f"   Current    : {s_icon} {streak['streak_type']} streak of {streak['current_streak']}")
    print(f"   Best win   : {streak['best_win_streak']} consecutive")
    print(f"   Worst loss : {streak['worst_loss_streak']} consecutive")

    by_coin = get_performance_by_coin()
    if by_coin:
        print(f"\n── BY COIN (top 10) ────────────────────────────────")
        print(f"   {'COIN':<8} {'DIR':<6} {'W':<4} {'L':<4} {'WR':>6}  {'AVG P&L':>8}")
        for r in by_coin[:10]:
            bar = "█" * int(r["win_rate"] * 10)
            print(f"   {r['coin']:<8} {r['direction']:<6} "
                  f"{r['wins']:<4} {r['losses']:<4} "
                  f"{r['win_rate']*100:>5.1f}%  "
                  f"{r['avg_pnl_pct']:>+7.2f}%  {bar}")

    by_pattern = get_performance_by_pattern()
    if by_pattern:
        print(f"\n── BY PATTERN (top 8) ──────────────────────────────")
        print(f"   {'PATTERN':<30} {'W':<4} {'L':<4} {'WR':>6}")
        for r in by_pattern[:8]:
            print(f"   {r['pattern'][:30]:<30} {r['wins']:<4} {r['losses']:<4} "
                  f"{r['win_rate']*100:>5.1f}%")

    by_hour = get_performance_by_hour()
    if by_hour:
        print(f"\n── BY HOUR (BKK) ───────────────────────────────────")
        best_hour = max(by_hour, key=lambda x: x["win_rate"])
        for r in by_hour:
            bar = "█" * int(r["win_rate"] * 10)
            star = " ★" if r["hour_bkk"] == best_hour["hour_bkk"] else ""
            print(f"   {r['label']}  WR={r['win_rate']*100:>5.1f}%  {r['total']:>3} trades  {bar}{star}")

    print()


# ══════════════════════════════════════════════════════════════════
# SECTION 6 — MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    """
    Standalone usage:
      python trade_logger.py          → sync + show stats
      python trade_logger.py --sync   → sync only
      python trade_logger.py --stats  → show stats from local log only
    """
    args = sys.argv[1:]

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║   📒  WHALE-STREAM TRADE LOGGER v1.0                ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    stats_only = "--stats" in args
    sync_only  = "--sync"  in args

    if not stats_only:
        n = sync_from_sheets()
        if n == 0 and not sync_only:
            print("   ⚠ No trades synced (check Sheets connection).")

    if not sync_only:
        print_stats_report()


if __name__ == "__main__":
    main()
