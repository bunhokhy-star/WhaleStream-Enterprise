"""
WHALE-STREAM Short Win Rate Analysis
Reads all resolved signals from Google Sheets and breaks down win rates
by direction, confidence, coin, and market regime.
Output saved to: analysis_shorts.txt
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ── Config (matches whale_stream_tracker.py) ──────────────────
SCRIPT_DIR              = os.path.dirname(os.path.abspath(__file__))
GOOGLE_SHEET_ID         = "1R21mkduSpbki2HmlNJMHM95-LkGS0q-AKHE1HVIfMmI"
GOOGLE_CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, "google_credentials.json")
OUT_FILE                = os.path.join(SCRIPT_DIR, "analysis_shorts.txt")

# Column indices (0-based), matching whale_stream_tracker.py
COL_COIN      = 0
COL_SIGNAL    = 1
COL_CONF      = 2
COL_ENTRY     = 3
COL_PATTERN   = 9
COL_TIMESTAMP = 10
COL_STATUS    = 11
# Tracker columns
COL_ENTRY_PRICE  = 12
COL_EXIT_PRICE   = 13
COL_TP_HIT       = 14
COL_PNL          = 15
COL_RESOLVED_AT  = 16

# Telegram credentials
try:
    from local_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    import os as _os
    TELEGRAM_BOT_TOKEN = _os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = _os.getenv("TELEGRAM_CHAT_ID", "")

def pct(n, d):
    return f"{n/d*100:.1f}%" if d > 0 else "N/A"

def avg(lst):
    return sum(lst)/len(lst) if lst else 0.0

def main():
    # ── Install deps if missing ────────────────────────────────
    import subprocess
    for mod, pkg in [("gspread","gspread"), ("google.oauth2","google-auth")]:
        try:
            __import__(mod)
        except ImportError:
            subprocess.check_call([sys.executable,"-m","pip","install",pkg,"--quiet"])

    print("Connecting to Google Sheets...")
    # Use google.oauth2 directly — bypasses gspread.auth which fails on some Python 3.14 setups
    from google.oauth2.service_account import Credentials as _GCreds
    from gspread.client import Client as _GClient
    _SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = _GCreds.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=_SCOPES)
    client = _GClient(auth=creds)
    sheet  = client.open_by_key(GOOGLE_SHEET_ID).sheet1
    rows   = sheet.get_all_values()
    data   = rows[1:] if len(rows) > 1 else []
    print(f"  Loaded {len(data)} rows from Sheets.")

    # ── Parse all resolved trades ─────────────────────────────
    resolved       = []
    expired_longs  = []   # EXPIRED LONG signals (status == "EXPIRED")
    for row in data:
        while len(row) < 17:
            row.append("")
        status = row[COL_STATUS].strip()

        # Collect EXPIRED LONGs separately (excluded from WIN/LOSS resolved list)
        if status == "EXPIRED":
            signal_raw = row[COL_SIGNAL].strip().upper()
            direction  = "LONG" if "LONG" in signal_raw or "🟢" in signal_raw else "SHORT"
            if direction == "LONG":
                pnl_str = row[COL_PNL].strip().replace("%", "")
                try:
                    exp_pnl = float(pnl_str)
                except Exception:
                    exp_pnl = None
                # Also capture entry zone for hit-rate analysis (Option C)
                entry_zone_raw = row[COL_ENTRY].strip() if len(row) > COL_ENTRY else ""
                expired_longs.append({
                    "coin":       row[COL_COIN].strip(),
                    "ts":         row[COL_TIMESTAMP].strip(),
                    "tp_hit":     row[COL_TP_HIT].strip() if len(row) > COL_TP_HIT else "",
                    "pnl":        exp_pnl,
                    "entry_zone": entry_zone_raw,
                })

        if status not in ("WIN", "LOSS"):
            continue
        coin      = row[COL_COIN].strip()
        signal    = row[COL_SIGNAL].strip().upper()
        conf_str  = row[COL_CONF].strip().replace("%","")
        pnl_raw   = row[COL_PNL].strip()
        ts_str    = row[COL_TIMESTAMP].strip()
        pattern   = row[COL_PATTERN].strip() if len(row) > COL_PATTERN else ""
        direction = "LONG" if "LONG" in signal or "🟢" in signal else "SHORT"
        # [B] suffix means this P&L was written back from Bybit actual fill (v46.27+)
        is_bybit  = "[B]" in pnl_raw
        try:
            conf = float(conf_str)
        except:
            conf = 0.0
        # Use regex so "[B]" suffix and other annotations don't break parsing
        import re as _re
        _pm = _re.search(r'([+-]?\d+(?:\.\d+)?)', pnl_raw.replace(",", ""))
        pnl = float(_pm.group(1)) if _pm else None

        # ── Sanity check: skip malformed / fake entries ───────────
        # Two types of fake entries exist:
        # 1. Wrong P&L sign: SHORT LOSS with positive P&L (SL below entry)
        # 2. Tiny P&L (abs < 5%): TP/SL within 0.1% of entry — instant fake
        #    resolution. Legitimate trades at 10x leverage always produce
        #    abs(P&L) >= 5% (at least 0.5% raw move × 10x).
        if pnl is not None:
            if direction == "SHORT" and status == "LOSS" and pnl > 0:
                continue  # malformed SHORT — SL was below entry
            if direction == "LONG"  and status == "WIN"  and pnl < 0:
                continue  # malformed LONG  — TP was below entry
            if abs(pnl) < 5:
                continue  # fake instant resolution — TP/SL within noise of entry

        resolved.append({
            "coin":      coin,
            "direction": direction,
            "conf":      conf,
            "status":    status,
            "pnl":       pnl,
            "is_bybit":  is_bybit,   # True if P&L was written back from Bybit actual fill
            "ts":        ts_str,
            "signal":    signal,
            "pattern":   pattern,
            "tp_hit":    row[COL_TP_HIT].strip() if len(row) > COL_TP_HIT else "",
        })

    longs  = [r for r in resolved if r["direction"] == "LONG"]
    shorts = [r for r in resolved if r["direction"] == "SHORT"]

    lw = [r for r in longs  if r["status"] == "WIN"]
    ll = [r for r in longs  if r["status"] == "LOSS"]
    sw = [r for r in shorts if r["status"] == "WIN"]
    sl = [r for r in shorts if r["status"] == "LOSS"]

    lines = []
    def p(s=""):
        lines.append(s)
        print(s)

    # ── SYSTEM HEALTH SUMMARY ────────────────────────────────
    _long_wr_sum = len([r for r in longs if r["status"]=="WIN"]) / len(longs) * 100 if longs else 0
    _short_wr_sum = len([r for r in shorts if r["status"]=="WIN"]) / len(shorts) * 100 if shorts else 0
    _g1_ok = len(resolved) >= 150
    _g3_ok = _short_wr_sum >= 50.0 and len(shorts) >= 20
    _repair_active = os.path.exists(os.path.join(os.path.dirname(__file__), "short_repair.flag"))

    p("═" * 58)
    p("  WHALE-STREAM — SYSTEM HEALTH SUMMARY")
    p("═" * 58)
    p(f"  Total resolved    : {len(resolved):4d}  (WIN+LOSS, excl EXPIRED)")
    p(f"  LONG win rate     : {_long_wr_sum:.1f}%  ({len([r for r in longs if r['status']=='WIN'])}W/{len([r for r in longs if r['status']=='LOSS'])}L)")
    _repair_str = " ⚠️ REPAIR MODE" if _repair_active else ""
    p(f"  SHORT win rate    : {_short_wr_sum:.1f}%{_repair_str}  ({len([r for r in shorts if r['status']=='WIN'])}W/{len([r for r in shorts if r['status']=='LOSS'])}L)")
    p(f"  Expired (72h)     : {len(expired_longs):4d}  (not counted in WR)")
    p(f"  Gate 1            : {'✅ CLEARED' if _g1_ok else f'❌ {len(resolved)}/150'}")
    p(f"  Gate 3 (SHORT WR) : {'✅ PASS' if _g3_ok else f'❌ {_short_wr_sum:.1f}% (need 50%+ over 20 SHORTs)'}")
    p(f"  System status     : {'⚠️ REPAIR MODE — SHORTs blocked' if _repair_active else '✅ FULL MODE — all signals active'}")
    p("═" * 58)
    p()

    p("=" * 60)
    p("  WHALE-STREAM SHORT WIN RATE DEEP ANALYSIS")
    p(f"  Run at: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    p("=" * 60)
    p()

    # ── Overall summary ───────────────────────────────────────
    p("── OVERALL SUMMARY ──────────────────────────────────────")
    p(f"  Total resolved trades : {len(resolved)}")
    p(f"  LONGs  : {len(longs)} total | {len(lw)} WIN | {len(ll)} LOSS | WR: {pct(len(lw),len(longs))}")
    p(f"  SHORTs : {len(shorts)} total | {len(sw)} WIN | {len(sl)} LOSS | WR: {pct(len(sw),len(shorts))}")
    p(f"  SHORT avg conf (WIN)  : {avg([r['conf'] for r in sw]):.1f}%")
    p(f"  SHORT avg conf (LOSS) : {avg([r['conf'] for r in sl]):.1f}%")
    p(f"  LONG  avg conf (WIN)  : {avg([r['conf'] for r in lw]):.1f}%")
    p(f"  LONG  avg conf (LOSS) : {avg([r['conf'] for r in ll]):.1f}%")
    p()

    # ── SHORT breakdown by confidence band ────────────────────
    p("── SHORT WIN RATE BY CONFIDENCE BAND ───────────────────")
    bands = [(95,101), (92,95), (90,92), (88,90), (85,88), (0,85)]
    for lo, hi in bands:
        bucket = [r for r in shorts if lo <= r["conf"] < hi]
        bw     = [r for r in bucket if r["status"] == "WIN"]
        label  = f"{lo}%+" if hi == 101 else f"{lo}-{hi}%"
        p(f"  {label:10s}: {len(bucket):3d} signals | {len(bw):2d} WIN | WR: {pct(len(bw),len(bucket))}")
    p()

    # ── SHORT breakdown by LONG band (for reference) ─────────
    p("── LONG  WIN RATE BY CONFIDENCE BAND ───────────────────")
    for lo, hi in bands:
        bucket = [r for r in longs if lo <= r["conf"] < hi]
        bw     = [r for r in bucket if r["status"] == "WIN"]
        label  = f"{lo}%+" if hi == 101 else f"{lo}-{hi}%"
        p(f"  {label:10s}: {len(bucket):3d} signals | {len(bw):2d} WIN | WR: {pct(len(bw),len(bucket))}")
    p()

    # ── LONG confidence TIER breakdown (validates v46.21 calibration) ─
    p("── LONG WIN RATE BY CONFIDENCE TIER (v46.21) ───────────")
    p("  Tiers defined in v46.21: TIER 1=Elite(92%+), TIER 2=Good(88-91%), TIER 3=Min(85-87%)")
    tier_defs = [
        ("TIER 1 — ELITE  (92%+)",   92, 101),
        ("TIER 2 — GOOD   (88-91%)", 88,  92),
        ("TIER 3 — MIN    (85-87%)", 85,  88),
    ]
    tier_results = []
    for label, lo, hi in tier_defs:
        bucket  = [r for r in longs if lo <= r["conf"] < hi]
        bw_t    = [r for r in bucket if r["status"] == "WIN"]
        bl_t    = [r for r in bucket if r["status"] == "LOSS"]
        pnls_t  = [r["pnl"] for r in bucket  if r["pnl"] is not None]
        wpnls_t = [r["pnl"] for r in bw_t    if r["pnl"] is not None]
        lpnls_t = [r["pnl"] for r in bl_t    if r["pnl"] is not None]
        wr_str  = pct(len(bw_t), len(bucket))
        ap_str  = f"{avg(pnls_t):+.1f}%" if pnls_t  else "  N/A "
        aw_str  = f"{avg(wpnls_t):+.1f}%" if wpnls_t else "  N/A "
        al_str  = f"{avg(lpnls_t):+.1f}%" if lpnls_t else "  N/A "
        tier_results.append((lo, len(bucket), len(bw_t), len(bw_t)/len(bucket) if bucket else 0))
        p(f"  {label:28s}: {len(bucket):3d} trades | WR: {wr_str:6s} | "
          f"avg P&L: {ap_str:8s} | avg WIN: {aw_str:8s} | avg LOSS: {al_str}")
    # Verdict: does TIER 1 outperform TIER 2?
    t1_lo, t1_n, t1_w, t1_wr = tier_results[0]
    t2_lo, t2_n, t2_w, t2_wr = tier_results[1]
    if t1_n >= 3:
        if t1_wr > t2_wr:
            p(f"  ✅ TIER 1 outperforms TIER 2 ({t1_wr*100:.1f}% vs {t2_wr*100:.1f}%) — calibration validated")
        elif t1_wr == t2_wr:
            p(f"  ➡️  TIER 1 matches TIER 2 ({t1_wr*100:.1f}%) — inconclusive, need more data")
        else:
            p(f"  ⚠️  TIER 1 not outperforming TIER 2 ({t1_wr*100:.1f}% vs {t2_wr*100:.1f}%) — review TIER 1 criteria")
    else:
        p(f"  ℹ️  TIER 1 has only {t1_n} trade(s) — need 3+ to evaluate (v46.21 is recent)")
    p()

    # ── LONG confidence recommendation ────────────────────────
    p("── LONG CONFIDENCE RECOMMENDATION ──────────────────────")
    best_long_threshold = None
    long_band_results   = []
    for lo, hi in [(95,101),(92,95),(90,92),(88,90),(85,88),(0,85)]:
        bucket = [r for r in longs if r["conf"] >= lo]
        bw_    = [r for r in bucket if r["status"] == "WIN"]
        wr_    = len(bw_) / len(bucket) if bucket else 0
        long_band_results.append((lo, len(bucket), wr_))
        if wr_ >= 0.60 and len(bucket) >= 5 and best_long_threshold is None:
            best_long_threshold = lo
            p(f"  At conf >= {lo}%: {len(bucket)} LONGs, WR = {wr_*100:.1f}% ✓")

    # Find the lowest threshold that still beats 55% WR (softer fallback)
    fallback_threshold = None
    for lo, n, wr_ in long_band_results:
        if wr_ >= 0.55 and n >= 5:
            fallback_threshold = lo
            break

    # NOTE: Code floor is LONG_MIN_CONF = 88 in whale_stream_bot.py (set v46.62).
    # Recommendations below reflect actual code floor of 88%, not 85%.
    if best_long_threshold is not None and best_long_threshold > 88:
        p(f"  → Recommend raising LONG min confidence from 88% to {best_long_threshold}%")
        p(f"  → This filters out weak setups dragging WR below 60%")
    elif best_long_threshold is not None and best_long_threshold >= 88:
        p(f"  → Code floor already at 88% (LONG_MIN_CONF=88 in bot.py) — no change needed")
        p(f"  → TIER 2 (88-91%) band is the primary acceptable LONG zone")
    else:
        p(f"  → Code floor already at 88% (LONG_MIN_CONF=88 in bot.py) — historical 85-87% trades no longer placed")
        if fallback_threshold:
            p(f"  → At conf >= {fallback_threshold}%: WR = {next(wr for lo,n,wr in long_band_results if lo==fallback_threshold)*100:.1f}%")
    p()

    # ── LONG breakdown by pattern ─────────────────────────────
    p("── LONG WIN RATE BY PATTERN ─────────────────────────────")
    long_patterns = defaultdict(list)
    for r in longs:
        # Normalise pattern: take first 4 words, lowercase
        pat_raw = r.get("pattern", r.get("signal", "unknown"))
        pat_key = " ".join(str(pat_raw).lower().split()[:4])
        long_patterns[pat_key].append(r)
    for pat, trades in sorted(long_patterns.items(), key=lambda x: -len(x[1])):
        pw = [t for t in trades if t["status"] == "WIN"]
        p(f"  {pat[:35]:35s}: {len(trades):3d} trades | {len(pw):2d} WIN | WR: {pct(len(pw), len(trades))}")
    p()

    # ── Gate 2: LONG P&L Deep Dive ────────────────────────────
    p("── GATE 2: LONG P&L DEEP DIVE ──────────────────────────")
    GATE1_TARGET = 150

    long_pnls  = [r["pnl"] for r in longs if r["pnl"] is not None]
    lw_pnls    = [r["pnl"] for r in lw   if r["pnl"] is not None]
    ll_pnls    = [r["pnl"] for r in ll   if r["pnl"] is not None]

    total_long_pnl = sum(long_pnls) if long_pnls else 0.0
    avg_win_pnl    = avg(lw_pnls)
    avg_loss_pnl   = avg(ll_pnls)
    sum_wins_pnl   = sum(lw_pnls) if lw_pnls else 0.0
    sum_loss_pnl   = sum(ll_pnls) if ll_pnls else 0.0  # negative number
    profit_factor  = (sum_wins_pnl / abs(sum_loss_pnl)) if sum_loss_pnl else float("inf")
    ev_per_trade   = total_long_pnl / len(longs) if longs else 0.0

    p(f"  Total LONG trades  : {len(longs)} ({len(lw)} WIN / {len(ll)} LOSS)")
    p(f"  Net LONG P&L       : {total_long_pnl:+.1f}%  (sum of all LONG P&L at 10x)")
    p(f"  Avg WIN  P&L       : {avg_win_pnl:+.1f}%")
    p(f"  Avg LOSS P&L       : {avg_loss_pnl:+.1f}%")
    p(f"  Profit Factor      : {profit_factor:.2f}x  (need > 1.0 to be profitable)")
    p(f"  Expected Value     : {ev_per_trade:+.2f}% per trade")
    p(f"  Gate 1 progress    : {len(longs) + len(shorts)}/{GATE1_TARGET} total resolved trades")

    gate2_pass = total_long_pnl > 0 and profit_factor > 1.0
    if gate2_pass:
        p(f"  ✅ GATE 2 STATUS: PASS — Net LONG P&L is positive, PF={profit_factor:.2f}x")
    else:
        reasons = []
        if total_long_pnl <= 0:
            reasons.append(f"net P&L is {total_long_pnl:+.1f}% (need > 0)")
        if profit_factor <= 1.0:
            reasons.append(f"profit factor {profit_factor:.2f}x (need > 1.0)")
        p(f"  ❌ GATE 2 STATUS: FAIL — {'; '.join(reasons)}")
    p()

    # ── LONG WR month-by-month trend ─────────────────────────
    p("── LONG WIN RATE BY MONTH (trajectory) ─────────────────")
    long_by_month = defaultdict(list)
    for r in longs:
        ts = r.get("ts", "")
        try:
            month_key = datetime.strptime(ts[:7], "%Y-%m").strftime("%Y-%m")
        except Exception:
            month_key = "unknown"
        long_by_month[month_key].append(r)

    month_rows = []
    for month in sorted(long_by_month.keys()):
        trades = long_by_month[month]
        wins   = [t for t in trades if t["status"] == "WIN"]
        wr     = len(wins) / len(trades) * 100 if trades else 0
        pnls   = [t["pnl"] for t in trades if t["pnl"] is not None]
        month_rows.append((month, len(trades), len(wins), wr, avg(pnls) if pnls else None))

    if month_rows:
        p(f"  {'Month':<10} {'Trades':>6} {'Wins':>5} {'WR':>7} {'Avg P&L':>9}  Trend")
        p(f"  {'─'*10} {'─'*6} {'─'*5} {'─'*7} {'─'*9}  {'─'*8}")
        prev_wr = None
        for month, n, w, wr, avg_pnl in month_rows:
            if prev_wr is None:
                trend = "  —"
            elif wr > prev_wr + 2:
                trend = "  ↑ improving"
            elif wr < prev_wr - 2:
                trend = "  ↓ declining"
            else:
                trend = "  → stable"
            pnl_str = f"{avg_pnl:+.1f}%" if avg_pnl is not None else "   N/A"
            wr_icon = "✅" if wr >= 60 else "⚠️" if wr >= 50 else "❌"
            p(f"  {month:<10} {n:>6} {w:>5} {wr_icon} {wr:>4.0f}%  {pnl_str:>9}{trend}")
            prev_wr = wr
        # Summary: is trajectory positive?
        if len(month_rows) >= 2:
            first_wr = month_rows[0][3]
            last_wr  = month_rows[-1][3]
            delta    = last_wr - first_wr
            if delta >= 5:
                p(f"  ✅ Positive trajectory: WR improved {delta:+.0f}pp from {month_rows[0][0]} to {month_rows[-1][0]}")
            elif delta <= -5:
                p(f"  ⚠️  Negative trajectory: WR dropped {delta:+.0f}pp — review recent signal quality")
            else:
                p(f"  ➡️  Stable trajectory: WR delta {delta:+.0f}pp over {len(month_rows)} months")
    else:
        p("  No LONG data with timestamps yet")
    p()

    # ── Actual vs Estimated P&L (Bybit write-back audit) ─────
    p("── ACTUAL vs ESTIMATED P&L (Bybit write-back v46.27+) ──")
    _bybit_longs = [r for r in longs if r.get("is_bybit") and r["pnl"] is not None]
    _est_longs   = [r for r in longs if not r.get("is_bybit") and r["pnl"] is not None]

    if not _bybit_longs:
        p("  No Bybit actual P&L data yet.")
        p("  [B] write-back starts accumulating from v46.27 onwards.")
        p("  Once trades have [B] values, this section shows fill accuracy.")
    else:
        _cov = len(_bybit_longs) / len(longs) * 100 if longs else 0
        p(f"  Coverage : {len(_bybit_longs)}/{len(longs)} LONG trades have Bybit actual P&L "
          f"({_cov:.0f}%)")
        _bw = [r for r in _bybit_longs if r["status"] == "WIN"]
        _bl = [r for r in _bybit_longs if r["status"] == "LOSS"]
        if _bw:
            p(f"  Actual WIN  P&L : avg {avg([r['pnl'] for r in _bw]):+.1f}%"
              f"  ({len(_bw)} trades)")
        if _bl:
            p(f"  Actual LOSS P&L : avg {avg([r['pnl'] for r in _bl]):+.1f}%"
              f"  ({len(_bl)} trades)")
        _avg_act = avg([r["pnl"] for r in _bybit_longs])
        if _est_longs:
            _avg_est = avg([r["pnl"] for r in _est_longs])
            _gap = _avg_act - _avg_est
            _gap_icon = "✅" if _gap >= 0 else "⚠️"
            p(f"  Estimated avg   : {_avg_est:+.1f}%  ({len(_est_longs)} trades, no [B])")
            p(f"  Actual avg      : {_avg_act:+.1f}%  ({len(_bybit_longs)} trades, [B])")
            if _gap > 1:
                _verdict = "actual fills beating estimates — upside bias in TP targeting ✅"
            elif _gap < -1:
                _verdict = "actual fills lagging estimates — slippage / fees eating into P&L ⚠️"
            else:
                _verdict = "estimates closely match actual fills ✅"
            p(f"  {_gap_icon} Gap (actual−est): {_gap:+.1f}pp  ({_verdict})")
        else:
            p(f"  Actual avg P&L  : {_avg_act:+.1f}%  (all {len(_bybit_longs)} trades have [B])")
            p("  (No estimated-only trades remaining to compare against)")
    p()

    # ── LONG WR by coin (full ranked table) ──────────────────
    long_by_coin = defaultdict(list)
    for r in longs:
        long_by_coin[r["coin"]].append(r)

    p("── LONG WIN RATE BY COIN (ranked) ──────────────────────")
    long_coin_table = []
    for coin, trades in long_by_coin.items():
        if len(trades) < 2:
            continue  # need at least 2 trades to be meaningful
        wins = [t for t in trades if t["status"] == "WIN"]
        wr   = len(wins) / len(trades)
        avg_pnl = sum(t["pnl"] for t in trades if t["pnl"] is not None) / len(trades)
        long_coin_table.append((coin, len(trades), len(wins), wr, avg_pnl))
    long_coin_table.sort(key=lambda x: (-x[3], -x[1]))  # sort by WR desc, then trade count desc
    if long_coin_table:
        p(f"  {'COIN':<12} {'TRADES':>6} {'WINS':>5} {'WR':>7} {'AVG P&L':>9}  RATING")
        p(f"  {'─'*12} {'─'*6} {'─'*5} {'─'*7} {'─'*9}  {'─'*8}")
        for coin, n, w, wr, avg_pnl in long_coin_table:
            if wr >= 0.70:
                rating = "⭐ STRONG"
            elif wr >= 0.55:
                rating = "✅ GOOD"
            elif wr >= 0.40:
                rating = "⚠️ WEAK"
            else:
                rating = "❌ POOR"
            pnl_str = f"{avg_pnl:+.1f}%" if avg_pnl is not None else "n/a"
            p(f"  {coin:<12} {n:>6} {w:>5} {wr*100:>6.0f}%  {pnl_str:>9}  {rating}")
    else:
        p("  No coins with 2+ LONG trades yet")
    p()

    # ─── LONG WIN RATE BY PATTERN ─────────────────────────────────
    p("")
    p("═" * 58)
    p("  LONG WIN RATE BY PATTERN (min 2 trades, ranked by WR)")
    p("═" * 58)
    pat_stats = {}
    for r in longs:
        raw_pat = r.get("pattern", "").strip()
        # Key: first 35 chars of pattern, title-cased for grouping
        key = raw_pat[:35].rstrip(" ,-") if raw_pat else "Unknown"
        if key not in pat_stats:
            pat_stats[key] = {"w": 0, "l": 0}
        if r.get("status") == "WIN":
            pat_stats[key]["w"] += 1
        else:
            pat_stats[key]["l"] += 1

    pat_rows = []
    for pat, ps in pat_stats.items():
        total = ps["w"] + ps["l"]
        if total < 2:
            continue
        wr = ps["w"] / total * 100
        pat_rows.append((pat, ps["w"], ps["l"], total, wr))

    if pat_rows:
        pat_rows.sort(key=lambda x: -x[4])
        p(f"  {'Pattern':<36} {'W':>3} {'L':>3} {'Tot':>4} {'WR':>6}")
        p("  " + "-" * 56)
        for pat, w, l, tot, wr in pat_rows:
            if wr >= 75:    icon = "⭐"
            elif wr >= 60:  icon = "✅"
            elif wr >= 45:  icon = "⚠️ "
            else:           icon = "❌"
            p(f"  {icon} {pat:<34} {w:>3} {l:>3} {tot:>4} {wr:>5.0f}%")
        best = pat_rows[0]
        p(f"")
        p(f"  Best pattern: {best[0]} — {best[4]:.0f}% WR ({best[1]}W/{best[2]}L)")
    else:
        p("  Insufficient data (need ≥2 trades per pattern)")
    p("")

    # ── LONG coin blocklist candidates ────────────────────────
    p("── LONG BLOCKLIST CANDIDATES ────────────────────────────")
    long_block_candidates = []
    for coin, trades in long_by_coin.items():
        wins = [t for t in trades if t["status"] == "WIN"]
        if len(trades) >= 3 and len(wins) == 0:
            long_block_candidates.append((coin, len(trades)))
    if long_block_candidates:
        p("  Coins with 0% LONG WR over 3+ trades — consider adding to LONG_COIN_BLOCKLIST:")
        for coin, n in sorted(long_block_candidates, key=lambda x: -x[1]):
            p(f"  ⛔ {coin:12s}: 0 WIN / {n} LONG trades")
        p()
        p("  → Add to LONG_COIN_BLOCKLIST in whale_stream_bot.py to block future LONG signals")
    else:
        p("  ✅ No LONG coins qualify for blocklist (need 0% WR over 3+ trades)")
    p()

    # ── SHORT losses: which coins lost? ──────────────────────
    p("── SHORT LOSSES BY COIN ─────────────────────────────────")
    loss_coins = defaultdict(list)
    for r in sl:
        loss_coins[r["coin"]].append(r)
    for coin, trades in sorted(loss_coins.items(), key=lambda x:-len(x[1])):
        all_s = [r for r in shorts if r["coin"] == coin]
        wins  = [r for r in all_s if r["status"] == "WIN"]
        p(f"  {coin:12s}: {len(trades)} LOSS / {len(all_s)} total  WR: {pct(len(wins),len(all_s))}  "
          f"avg conf: {avg([r['conf'] for r in all_s]):.1f}%")
    p()

    # ── SHORT breakdown by pattern ────────────────────────────
    p("── SHORT WIN RATE BY PATTERN ────────────────────────────")
    short_patterns = defaultdict(list)
    for r in shorts:
        # Normalise pattern: take first 4 words, lowercase
        pat_raw = r.get("pattern", r.get("signal", "unknown"))
        pat_key = " ".join(str(pat_raw).lower().split()[:4])
        short_patterns[pat_key].append(r)
    for pat, trades in sorted(short_patterns.items(), key=lambda x: -len(x[1])):
        pw = [t for t in trades if t["status"] == "WIN"]
        p(f"  {pat[:35]:35s}: {len(trades):3d} trades | {len(pw):2d} WIN | WR: {pct(len(pw), len(trades))}")
    p()

    # ── SHORT wins: which coins won? ────────────────────────
    p("── SHORT WINS BY COIN ───────────────────────────────────")
    win_coins = defaultdict(list)
    for r in sw:
        win_coins[r["coin"]].append(r)
    for coin, trades in sorted(win_coins.items(), key=lambda x:-len(x[1])):
        all_s = [r for r in shorts if r["coin"] == coin]
        p(f"  {coin:12s}: {len(trades)} WIN  / {len(all_s)} total  WR: {pct(len(trades),len(all_s))}  "
          f"avg conf: {avg([r['conf'] for r in all_s]):.1f}%")
    p()

    # ── TP Hit Distribution ───────────────────────────────────
    p("── TP HIT DISTRIBUTION (ACTUAL) ─────────────────────────")
    from collections import Counter as _Counter

    long_tp_hits  = [r["tp_hit"] for r in lw if r.get("tp_hit")]
    short_tp_hits = [r["tp_hit"] for r in sw if r.get("tp_hit")]

    long_wins_pnl  = [r["pnl"] for r in lw if r["pnl"] is not None]
    short_wins_pnl = [r["pnl"] for r in sw if r["pnl"] is not None]

    p("  LONG wins TP exit  (v46.25: TP1=50% partial lock, TP2/TP3=ride remainder):")
    if long_tp_hits:
        lt_counts = _Counter(long_tp_hits)
        for lbl in ["TP1", "TP2", "TP3", "TP4"]:
            n = lt_counts.get(lbl, 0)
            # P&L for this TP level
            tp_pnls = [r["pnl"] for r in lw
                       if r.get("tp_hit") == lbl and r["pnl"] is not None]
            pnl_str = f"  avg P&L: {avg(tp_pnls):+.1f}%" if tp_pnls else ""
            tier_note = "  ← TIER 1 target" if lbl in ("TP3", "TP4") else ""
            p(f"    {lbl}: {n:3d} ({n/len(long_tp_hits)*100:.0f}%){pnl_str}{tier_note}")
        if long_wins_pnl:
            p(f"  Avg LONG win P&L : {avg(long_wins_pnl):+.1f}%")
            p(f"  Max LONG win P&L : {max(long_wins_pnl):+.1f}%")
        # Upside capture check: does TP2+ beat TP1?
        tp1_pnls   = [r["pnl"] for r in lw if r.get("tp_hit") == "TP1" and r["pnl"] is not None]
        tp2up_pnls = [r["pnl"] for r in lw
                      if r.get("tp_hit") in ("TP2","TP3","TP4") and r["pnl"] is not None]
        if tp1_pnls and tp2up_pnls:
            uplift = avg(tp2up_pnls) - avg(tp1_pnls)
            p(f"  TP2+ vs TP1 uplift: {uplift:+.1f}% avg P&L advantage from riding higher TP")
    else:
        p("  No LONG wins with TP data yet.")
    p()
    p("  SHORT wins TP exit:")
    if short_tp_hits:
        st_counts = _Counter(short_tp_hits)
        for lbl in ["TP1", "TP2", "TP3", "TP4"]:
            n = st_counts.get(lbl, 0)
            tp_pnls = [r["pnl"] for r in sw
                       if r.get("tp_hit") == lbl and r["pnl"] is not None]
            pnl_str = f"  avg P&L: {avg(tp_pnls):+.1f}%" if tp_pnls else ""
            p(f"    {lbl}: {n:3d} ({n/len(short_tp_hits)*100:.0f}%){pnl_str}")
        if short_wins_pnl:
            p(f"  Avg SHORT win P&L: {avg(short_wins_pnl):+.1f}%")
    else:
        p("  No SHORT wins with TP data yet.")
    p()

    # ── Signal expiry analysis ────────────────────────────────
    # NOTE: expired_longs is built from raw data (status=="EXPIRED") above,
    # because the main `resolved` / `longs` lists filter out EXPIRED rows.
    p("── SIGNAL EXPIRY ANALYSIS ───────────────────────────────")
    long_wins   = lw   # already built: [r for r in longs if r["status"] == "WIN"]
    long_losses = ll   # already built: [r for r in longs if r["status"] == "LOSS"]
    # SL hits: LOSS with tp_hit containing "SL" or "STOP"
    sl_hits = [r for r in long_losses if str(r.get("tp_hit", "")).upper() in ("SL", "STOP", "SL HIT")]
    # Other LOSS (tp_hit is a TP level or unknown — not an expiry, not a plain SL)
    other_losses = [r for r in long_losses if r not in sl_hits]

    total_resolved = len(longs)
    total_expired  = len(expired_longs)
    total_all      = total_resolved + total_expired   # resolved WIN/LOSS + expired

    if total_all > 0:
        p(f"  Total LONG signals (incl. expired): {total_all}")
        p(f"  TP hit (WIN)        : {len(long_wins):3d}  ({pct(len(long_wins), total_all)})")
        p(f"  SL hit (LOSS)       : {len(sl_hits):3d}  ({pct(len(sl_hits), total_all)})")
        p(f"  Other LOSS          : {len(other_losses):3d}  ({pct(len(other_losses), total_all)})")
        p(f"  Expired 72h         : {total_expired:3d}  ({pct(total_expired, total_all)})")
        p()
        # Expiry rate insight
        expiry_rate = total_expired / total_all
        if expiry_rate > 0.25:
            p(f"  ⚠️  HIGH EXPIRY RATE: {expiry_rate*100:.0f}% of LONGs expire unused.")
            p(f"     Consider: close near-profit positions manually before 72h if dashboard shows gain.")
        elif expiry_rate > 0.10:
            p(f"  ⚡ Moderate expiry rate: {expiry_rate*100:.0f}% of LONGs timeout without resolving.")
        else:
            p(f"  ✅ Low expiry rate: {expiry_rate*100:.0f}% — most LONGs resolve via TP or SL.")

        # Avg P&L on expiries vs SL hits
        exp_pnls = [r["pnl"] for r in expired_longs if r.get("pnl") is not None]
        sl_pnls  = [r["pnl"] for r in sl_hits       if r.get("pnl") is not None]
        if exp_pnls:
            exp_avg = sum(exp_pnls) / len(exp_pnls)
            if sl_pnls:
                sl_avg = sum(sl_pnls) / len(sl_pnls)
                p(f"     Avg expiry P&L: {exp_avg:+.1f}%  |  Avg SL-hit P&L: {sl_avg:+.1f}%")
            else:
                p(f"     Avg expiry P&L: {exp_avg:+.1f}%")
    else:
        p("  No LONG data yet")
    p()

    # ── All SHORT trades in detail ────────────────────────────
    p("── ALL SHORT TRADES (chronological) ────────────────────")
    p(f"  {'DATE':16s} {'COIN':10s} {'CONF':6s} {'STATUS':6s} {'P&L':8s}")
    p("  " + "-"*52)
    for r in sorted(shorts, key=lambda x: x["ts"]):
        pnl_s = f"{r['pnl']:+.1f}%" if r["pnl"] is not None else "   ?"
        p(f"  {r['ts']:16s} {r['coin']:10s} {r['conf']:5.0f}% {r['status']:6s} {pnl_s}")
    p()

    # ── Recommendation ────────────────────────────────────────
    p("── RECOMMENDATION ───────────────────────────────────────")
    # Find the lowest confidence band where SHORT WR >= 50%
    best_threshold = None
    for lo, hi in [(95,101),(92,95),(90,92),(88,90),(85,88),(0,85)]:
        bucket = [r for r in shorts if r["conf"] >= lo]
        bw_    = [r for r in bucket if r["status"] == "WIN"]
        wr_    = len(bw_) / len(bucket) if bucket else 0
        if wr_ >= 0.50 and len(bucket) >= 3:
            best_threshold = lo
            p(f"  At conf >= {lo}%: {len(bucket)} SHORTs, WR = {wr_*100:.1f}% ✓")
            break
    if best_threshold:
        p(f"  → Recommend raising SHORT min confidence to {best_threshold}%")
    else:
        p("  → Insufficient data or no threshold achieves 50% WR for SHORTs")
        p("  → Consider disabling SHORT signals until more data is collected")
    p()
    p("=" * 60)

    # ── SHORT RECOVERY DETECTION ──────────────────────────────
    SCRIPT_DIR_ANALYSIS = os.path.dirname(os.path.abspath(__file__))
    SHORT_REPAIR_FILE   = os.path.join(SCRIPT_DIR_ANALYSIS, "short_repair.flag")
    MIN_SHORTS_FOR_RECOVERY = 20
    MIN_WR_FOR_RECOVERY     = 0.50   # 50%

    # Use the last MIN_SHORTS_FOR_RECOVERY real SHORT trades (already filtered)
    recent_shorts = shorts[-MIN_SHORTS_FOR_RECOVERY:] if len(shorts) >= MIN_SHORTS_FOR_RECOVERY else []
    if recent_shorts:
        recent_sw = [r for r in recent_shorts if r["status"] == "WIN"]
        recent_wr = len(recent_sw) / len(recent_shorts)
    else:
        recent_wr = 0.0

    repair_active = os.path.exists(SHORT_REPAIR_FILE)

    if recent_wr >= MIN_WR_FOR_RECOVERY and len(recent_shorts) >= MIN_SHORTS_FOR_RECOVERY:
        p()
        p("── ✅ SHORT RECOVERY DETECTED ─────────────────────────────")
        p(f"  Last {len(recent_shorts)} real SHORT trades: {len(recent_sw)}W / {len(recent_shorts)-len(recent_sw)}L = {recent_wr*100:.1f}% WR")
        p(f"  GATE 3 CONDITION MET: SHORT WR ≥ {MIN_WR_FOR_RECOVERY*100:.0f}% over {len(recent_shorts)} trades!")
        if repair_active:
            try:
                os.remove(SHORT_REPAIR_FILE)
                p(f"  ✅ short_repair.flag DELETED — SHORTs will resume on next trader run.")
            except Exception as e:
                p(f"  ⚠ Could not delete short_repair.flag: {e}")
                p(f"  → Run LIFT_SHORT_REPAIR.bat manually to resume SHORTs.")
        else:
            p("  SHORT REPAIR MODE was not active — SHORTs already running.")
        # Send Telegram alert
        try:
            import requests as _req
            _msg = (
                f"🎯 <b>SHORT WR RECOVERED — REPAIR MODE LIFTED</b>\n"
                f"  Last {len(recent_shorts)} real SHORTs: {len(recent_sw)}W / {len(recent_shorts)-len(recent_sw)}L = <b>{recent_wr*100:.1f}% WR</b>\n"
                f"  Gate 3 condition MET (≥50% WR over 20+ trades).\n"
                f"  {'short_repair.flag deleted — SHORTs will resume automatically.' if repair_active else 'SHORTs were already active.'}"
            )
            _req.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": _msg, "parse_mode": "HTML"},
                timeout=10,
            )
        except Exception:
            pass
    elif repair_active:
        p()
        p("── ⏸ SHORT REPAIR MODE STATUS ─────────────────────────────")
        if recent_shorts:
            p(f"  Last {len(recent_shorts)} real SHORTs: {len(recent_sw)}W / {len(recent_shorts)-len(recent_sw)}L = {recent_wr*100:.1f}% WR")
            p(f"  Need {MIN_WR_FOR_RECOVERY*100:.0f}%+ WR to resume — currently {recent_wr*100:.1f}%")
            p(f"  Gap: {(MIN_WR_FOR_RECOVERY - recent_wr)*100:.1f}% below target")
        else:
            p(f"  Not enough real SHORT trades yet (need {MIN_SHORTS_FOR_RECOVERY}, have {len(shorts)})")
        p(f"  Run LIFT_SHORT_REPAIR.bat to override manually.")

    # ── SHORT RECOVERY PROGRESS ─────────────────────────────────────────
    p()
    p("═" * 58)
    p("  SHORT RECOVERY PROGRESS — H / FF / CHZ Approved Coins")
    p("═" * 58)

    RECOVERY_COINS = {"H", "FF", "CHZ"}
    # Per-coin table
    p(f"  {'Coin':<6} {'W':>3} {'L':>3} {'Tot':>4} {'WR':>6}  Status")
    p("  " + "-" * 42)
    any_rc_trades = False
    for rc_coin in ["H", "FF", "CHZ"]:
        rc_all = [r for r in shorts if r.get("coin", "").upper() == rc_coin]
        if rc_all:
            any_rc_trades = True
            rc_w = sum(1 for r in rc_all if r["status"] == "WIN")
            rc_l = len(rc_all) - rc_w
            rc_wr = rc_w / len(rc_all) * 100
            icon = "⭐" if rc_wr >= 75 else "✅" if rc_wr >= 50 else "⚠️ "
            p(f"  {icon} {rc_coin:<5} {rc_w:>3} {rc_l:>3} {len(rc_all):>4} {rc_wr:>5.0f}%")
        else:
            p(f"  ─  {rc_coin:<5}   0   0    0     N/A  (no SHORT trades placed yet)")
    p("")

    # Combined recovery coin WR
    rc_combined = [r for r in shorts if r.get("coin", "").upper() in RECOVERY_COINS]
    if rc_combined:
        rc_total_w = sum(1 for r in rc_combined if r["status"] == "WIN")
        rc_total_wr = rc_total_w / len(rc_combined) * 100
        p(f"  Combined H/FF/CHZ: {rc_total_w}W/{len(rc_combined)-rc_total_w}L = {rc_total_wr:.0f}% WR")
    else:
        p("  Combined H/FF/CHZ: 0 trades — SHORTs for these coins are UNLOCKED in REPAIR MODE.")
        p("  → Bot will place H/FF/CHZ SHORTs at ≥93% confidence when next opportunity arises.")

    # Last-20 rolling WR gap to target
    p("")
    _s20 = shorts[-20:] if len(shorts) >= 20 else shorts
    _s20_w = sum(1 for r in _s20 if r["status"] == "WIN")
    _s20_wr = _s20_w / len(_s20) * 100 if _s20 else 0
    _gap_pct = max(0.0, 50.0 - _s20_wr)
    p(f"  Last-{len(_s20)} SHORT WR: {_s20_w}W/{len(_s20)-_s20_w}L = {_s20_wr:.1f}% (target: ≥50.0%)")
    if _s20_wr < 50.0:
        # How many wins needed: need ≥10 in last 20 (or ≥11 if exactly 20)
        _wins_needed = max(0, 10 - _s20_w)
        if len(_s20) < 20:
            _wins_needed = max(0, int(len(_s20) * 0.5) + 1 - _s20_w)
        p(f"  Gap to recovery: {_gap_pct:.1f}% — need {_wins_needed} more win(s) in next trades")
        if any_rc_trades and rc_combined:
            p(f"  At {rc_total_wr:.0f}% WR on recovery coins → each trade is {rc_total_wr:.0f}% likely to be a WIN")
            if rc_total_wr > 0:
                import math as _math
                _eta_trades = _math.ceil(_wins_needed / (rc_total_wr / 100))
                p(f"  ETA: ~{_eta_trades} recovery coin trade(s) to reach target (estimate)")
        else:
            p("  → No recovery coin trades placed yet. H/FF/CHZ SHORTs unlocked — waiting for signals.")
    else:
        p("  ✅ Last-20 WR ≥50% — Gate 3 recovery target MET!")
    p("")

    # ── SIGNAL SCORE TIER WIN RATES (v47.22) ─────────────────────
    p()
    p("═" * 58)
    p("  SIGNAL SCORE TIER WIN RATES (validates scorer)")
    p("  Scores written by Strategist → saved in pattern_memory.json by Debrief")
    p("═" * 58)
    _mem_path = os.path.join(SCRIPT_DIR, "pattern_memory.json")
    if os.path.exists(_mem_path):
        try:
            with open(_mem_path, "r", encoding="utf-8") as _mf:
                _mem = json.load(_mf)
            _sts = _mem.get("score_tier_stats", {})
            _total_scored = sum(
                _sts.get(t, {}).get("wins", 0) + _sts.get(t, {}).get("losses", 0)
                for t in ("0-4", "5-6", "7-8", "9-10")
            )
            if _total_scored == 0:
                p("  No scored debriefs yet — scores will populate as trades resolve.")
                p("  (Requires v47.22+ Debrief and v47.21+ Strategist to write scores)")
            else:
                p(f"  {'Tier':<10} {'W':>4} {'L':>4} {'Tot':>5} {'WR':>7}  Verdict")
                p("  " + "-" * 46)
                _tier_order = [("0-4", "❌ WEAK — below score gate floor"),
                               ("5-6", "⚠️  MARGINAL — passes gate, review"),
                               ("7-8", "✅ GOOD — reliable quality band"),
                               ("9-10","⭐ ELITE — highest conviction")]
                for _tier, _verdict in _tier_order:
                    _tw = _sts.get(_tier, {}).get("wins", 0)
                    _tl = _sts.get(_tier, {}).get("losses", 0)
                    _tt = _tw + _tl
                    _twr = f"{_tw/_tt*100:.1f}%" if _tt > 0 else "N/A"
                    _bar = ""
                    if _tt > 0:
                        _wr_f = _tw / _tt
                        _bar = "🟩" * int(_wr_f * 5) + "🟥" * (5 - int(_wr_f * 5))
                    p(f"  {_tier:<10} {_tw:>4} {_tl:>4} {_tt:>5} {_twr:>7}  {_bar}  {_verdict}")
                p()
                # Validation verdict
                _e9 = _sts.get("9-10", {})
                _e7 = _sts.get("7-8", {})
                _e5 = _sts.get("5-6", {})
                _wr9 = _e9.get("wins",0)/(_e9.get("wins",0)+_e9.get("losses",0)) if (_e9.get("wins",0)+_e9.get("losses",0))>0 else None
                _wr7 = _e7.get("wins",0)/(_e7.get("wins",0)+_e7.get("losses",0)) if (_e7.get("wins",0)+_e7.get("losses",0))>0 else None
                _wr5 = _e5.get("wins",0)/(_e5.get("wins",0)+_e5.get("losses",0)) if (_e5.get("wins",0)+_e5.get("losses",0))>0 else None
                if _wr9 is not None and _wr7 is not None and _wr9 >= _wr7:
                    p(f"  ✅ SCORER VALIDATED: elite tier (9-10) WR {_wr9*100:.1f}% ≥ good tier (7-8) {_wr7*100:.1f}%")
                    p(f"     Higher scores ARE predicting better outcomes — scorer is working.")
                elif _wr9 is not None and _wr7 is not None:
                    p(f"  ⚠️  SCORER NEEDS REVIEW: elite tier (9-10) WR {_wr9*100:.1f}% < good tier (7-8) {_wr7*100:.1f}%")
                    p(f"     Higher scores not consistently outperforming — check scorer dimensions.")
                else:
                    p(f"  ℹ️  Need more scored trades to validate (aim for 5+ per tier)")
        except Exception as _e:
            p(f"  Could not load pattern_memory.json: {_e}")
    else:
        p("  pattern_memory.json not found — run a few cycles to accumulate debriefs.")
    p()

    # ── ENTRY ZONE HIT-RATE: CHRONIC MISS COINS (Option C v47.22) ────────
    p("═" * 58)
    p("  ENTRY ZONE HIT-RATE — CHRONIC MISS COINS")
    p("  Coins where price never reaches our entry zone (signal expires)")
    p("═" * 58)
    if expired_longs or longs:
        # Compute per-coin: expired count + total signals (resolved + expired)
        _expired_by_coin = defaultdict(list)
        for _e in expired_longs:
            _expired_by_coin[_e["coin"]].append(_e)
        _resolved_by_coin = defaultdict(list)
        for _r in longs:
            _resolved_by_coin[_r["coin"]].append(_r)
        _all_coins = set(list(_expired_by_coin.keys()) + list(_resolved_by_coin.keys()))
        _coin_rows = []
        for _cn in _all_coins:
            _exp_n  = len(_expired_by_coin.get(_cn, []))
            _res_n  = len(_resolved_by_coin.get(_cn, []))
            _total  = _exp_n + _res_n
            if _total < 2:
                continue
            _exp_rate = _exp_n / _total
            # Compute avg entry zone width (e.g. "1800-1820" → width = 20 / midpoint = 1.1%)
            _widths = []
            for _ex in _expired_by_coin.get(_cn, []):
                _ez = _ex.get("entry_zone", "")
                import re as _re2
                _prices = [float(x) for x in _re2.findall(r'[\d]+\.?[\d]*', _ez) if float(x) > 0]
                if len(_prices) >= 2:
                    _lo, _hi = min(_prices), max(_prices)
                    _mid = (_lo + _hi) / 2
                    if _mid > 0:
                        _widths.append((_hi - _lo) / _mid * 100)
            _avg_width = sum(_widths) / len(_widths) if _widths else None
            _coin_rows.append((_cn, _exp_n, _res_n, _total, _exp_rate, _avg_width))
        _coin_rows.sort(key=lambda x: -x[4])  # sort by expiry rate desc
        if _coin_rows:
            p(f"  {'COIN':<12} {'Exp':>4} {'Res':>4} {'Tot':>4} {'Exp%':>6}  {'Avg Zone Width':>16}  Verdict")
            p("  " + "-" * 62)
            for _cn, _en, _rn, _tn, _er, _aw in _coin_rows:
                _icon = "🚨" if _er >= 0.70 else ("⚠️ " if _er >= 0.40 else "✅ ")
                _aw_str = f"{_aw:.2f}% wide" if _aw is not None else "zone N/A"
                _verdict = ""
                if _er >= 0.70:
                    _verdict = "CHRONIC MISS — widen entry zone or skip"
                elif _er >= 0.40:
                    _verdict = "High miss rate — consider wider zone"
                else:
                    _verdict = "OK"
                p(f"  {_icon} {_cn:<10} {_en:>4} {_rn:>4} {_tn:>4} {_er*100:>5.0f}%  {_aw_str:>16}  {_verdict}")
            p()
            _chronic = [r for r in _coin_rows if r[4] >= 0.70]
            if _chronic:
                p(f"  → {len(_chronic)} coin(s) have ≥70% expiry rate.")
                p(f"     Prompt guidance: for these coins, widen entry zone by 0.5-1% OR skip generating signals.")
                p(f"     Chronic miss coins: {', '.join(r[0] for r in _chronic)}")
            else:
                p("  ✅ No coins with ≥70% expiry rate — entry zones are adequate.")
        else:
            p("  Not enough data per coin (need 2+ signals each).")
    else:
        p("  No data yet.")
    p()

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nAnalysis saved to: {OUT_FILE}")

if __name__ == "__main__":
    main()
