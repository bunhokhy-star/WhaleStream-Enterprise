"""
WHALE-STREAM Open Signal Audit
Reads all OPEN signals from Google Sheets and produces a health report.
Groups by age: healthy (<24h), at-risk (24-48h), expiring (<24h left before 72h timeout), critical (>72h).
Flags duplicate coins (same coin open multiple times).
Read-only — does NOT modify the sheet.
Output saved to: audit_open_signals.txt
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict

SCRIPT_DIR              = os.path.dirname(os.path.abspath(__file__))
GOOGLE_SHEET_ID         = "1R21mkduSpbki2HmlNJMHM95-LkGS0q-AKHE1HVIfMmI"
GOOGLE_CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, "google_credentials.json")
OUT_FILE                = os.path.join(SCRIPT_DIR, "audit_open_signals.txt")
TRADE_TIMEOUT_HOURS     = 72

COL_COIN      = 0
COL_SIGNAL    = 1
COL_CONF      = 2
COL_ENTRY     = 3
COL_SL        = 4
COL_TP1       = 5
COL_TIMESTAMP = 10
COL_STATUS    = 11

def main():
    import subprocess
    for mod, pkg in [("gspread", "gspread"), ("google.oauth2", "google-auth")]:
        try:
            __import__(mod)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

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
    print(f"  Loaded {len(data)} rows.")

    bkk_now = datetime.now(timezone(timedelta(hours=7)))

    open_signals = []
    for row in data:
        while len(row) < 17:
            row.append("")
        if row[COL_STATUS].strip() != "OPEN":
            continue
        coin      = row[COL_COIN].strip()
        signal    = row[COL_SIGNAL].strip()
        conf      = row[COL_CONF].strip()
        entry     = row[COL_ENTRY].strip()
        sl        = row[COL_SL].strip()
        tp1       = row[COL_TP1].strip()
        ts_str    = row[COL_TIMESTAMP].strip()
        direction = "LONG" if "Long" in signal or "🟢" in signal else "SHORT"

        age_hours = None
        try:
            trade_dt  = datetime.strptime(ts_str, "%Y-%m-%d %H:%M").replace(
                tzinfo=timezone(timedelta(hours=7))
            )
            age_hours = (bkk_now - trade_dt).total_seconds() / 3600
        except Exception:
            pass

        open_signals.append({
            "coin": coin, "signal": signal, "direction": direction,
            "conf": conf, "entry": entry, "sl": sl, "tp1": tp1,
            "ts": ts_str, "age_h": age_hours,
        })

    lines = []
    def p(s=""):
        lines.append(s)
        print(s)

    p("=" * 65)
    p("  WHALE-STREAM OPEN SIGNAL AUDIT")
    p(f"  Run at: {bkk_now.strftime('%Y-%m-%d %H:%M')} BKK")
    p(f"  Total OPEN signals: {len(open_signals)}")
    p("=" * 65)
    p()

    # ── Age buckets ────────────────────────────────────────────
    healthy   = [r for r in open_signals if r["age_h"] is not None and r["age_h"] < 24]
    at_risk   = [r for r in open_signals if r["age_h"] is not None and 24 <= r["age_h"] < 48]
    expiring  = [r for r in open_signals if r["age_h"] is not None and 48 <= r["age_h"] < TRADE_TIMEOUT_HOURS]
    critical  = [r for r in open_signals if r["age_h"] is not None and r["age_h"] >= TRADE_TIMEOUT_HOURS]
    no_ts     = [r for r in open_signals if r["age_h"] is None]

    p(f"── AGE SUMMARY {'─'*47}")
    p(f"  ✅ Healthy    (<24h)  : {len(healthy):3d} signals")
    p(f"  🟡 At risk   (24-48h): {len(at_risk):3d} signals")
    p(f"  ⚠️  Expiring  (48-72h): {len(expiring):3d} signals  ← <24h before auto-expire")
    p(f"  🚨 Critical  (>72h)  : {len(critical):3d} signals  ← SHOULD HAVE BEEN EXPIRED")
    p(f"  ❓ No timestamp      : {len(no_ts):3d} signals")
    p()

    # ── Duplicate coins ────────────────────────────────────────
    coin_counts = defaultdict(list)
    for r in open_signals:
        coin_counts[r["coin"]].append(r)
    dupes = {c: rs for c, rs in coin_counts.items() if len(rs) > 1}
    if dupes:
        p(f"── DUPLICATE OPEN COINS (same coin, multiple OPEN signals) {'─'*5}")
        for coin, rs in sorted(dupes.items(), key=lambda x: -len(x[1])):
            dirs = " + ".join(r["direction"] for r in rs)
            ages = " / ".join(f"{r['age_h']:.0f}h" if r["age_h"] else "?" for r in rs)
            p(f"  ⚠️  {coin:10s}: {len(rs)} open  ({dirs})  ages: {ages}")
        p()
    else:
        p("── DUPLICATE COINS: None ✅")
        p()

    # ── Detail by bucket ───────────────────────────────────────
    def print_bucket(label, bucket):
        if not bucket:
            return
        p(f"── {label} {'─'*(60-len(label))}")
        p(f"  {'AGE':6s} {'COIN':10s} {'DIR':6s} {'CONF':6s} {'ENTRY':18s} {'TP1':12s} TIMESTAMP")
        p("  " + "─" * 62)
        for r in sorted(bucket, key=lambda x: -(x["age_h"] or 0)):
            age_str = f"{r['age_h']:.1f}h" if r["age_h"] else "  ?h"
            p(f"  {age_str:6s} {r['coin']:10s} {r['direction']:6s} {r['conf']:6s} {r['entry']:18s} {r['tp1']:12s} {r['ts']}")
        p()

    print_bucket("⚠️  EXPIRING SOON — REVIEW THESE (48-72h)", expiring)
    print_bucket("🚨 CRITICAL — OVERDUE (>72h, tracker missed these)", critical)
    print_bucket("🟡 AT RISK (24-48h)", at_risk)
    print_bucket("✅ HEALTHY (<24h)", healthy)

    # ── Direction summary ──────────────────────────────────────
    n_long  = sum(1 for r in open_signals if r["direction"] == "LONG")
    n_short = sum(1 for r in open_signals if r["direction"] == "SHORT")
    p(f"── DIRECTION SPLIT {'─'*44}")
    p(f"  LONG:  {n_long}")
    p(f"  SHORT: {n_short}  {'(⚠️  SHORTs should be 0 — REPAIR MODE active)' if n_short > 0 else '✅ (REPAIR MODE — no SHORT opens expected)'}")
    p()
    p("=" * 65)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nAudit saved to: {OUT_FILE}")

if __name__ == "__main__":
    main()
