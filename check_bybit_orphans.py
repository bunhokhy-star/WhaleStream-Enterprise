"""
WHALE-STREAM Bybit Position Orphan Detector
Cross-references open Bybit Demo positions against OPEN signals in Google Sheets.

ORPHAN TYPE A (Critical): Position open on Bybit but NO matching OPEN row in sheet
  → Real money deployed, tracker not monitoring it. Must investigate immediately.

ORPHAN TYPE B (Info): OPEN signal in sheet but no matching Bybit position
  → Signal was logged but order was never placed (or already closed by Bybit).
  → Normal for signals the trader skipped; only concerning if recent.

Run: python check_bybit_orphans.py
Output: check_bybit_orphans.txt + Telegram alert if Type A orphans found.
"""

import os, sys, json, hmac, hashlib, time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

SCRIPT_DIR              = os.path.dirname(os.path.abspath(__file__))
GOOGLE_SHEET_ID         = "1R21mkduSpbki2HmlNJMHM95-LkGS0q-AKHE1HVIfMmI"
GOOGLE_CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, "google_credentials.json")
OUT_FILE                = os.path.join(SCRIPT_DIR, "check_bybit_orphans.txt")

# ── Bybit Demo API credentials — loaded from local_config.py (gitignored) ─────
try:
    from local_config import BYBIT_API_KEY, BYBIT_API_SECRET
except ImportError:
    import os as _os
    BYBIT_API_KEY    = _os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET = _os.getenv("BYBIT_API_SECRET", "")
BYBIT_BASE_URL   = "https://api-demo.bybit.com"
BYBIT_CATEGORY   = "linear"

try:
    from local_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    import os as _os
    TELEGRAM_BOT_TOKEN = _os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = _os.getenv("TELEGRAM_CHAT_ID", "")


# ─────────────────────────────────────────────────────────────
# BYBIT AUTHENTICATION (copied exactly from whale_stream_trader.py)
# ─────────────────────────────────────────────────────────────

def bybit_request(method, endpoint, params=None, body=None):
    """
    Authenticated Bybit V5 API request.
    Adds X-BAPI-DEMO-TRADING: 1 header for demo account.
    """
    import requests

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


def get_bybit_open_positions():
    """Returns dict: symbol -> {side, size, unrealisedPnl, avgPrice, markPrice}"""
    result = bybit_request("GET", "/v5/position/list",
                           {"category": BYBIT_CATEGORY, "settleCoin": "USDT"})
    positions = {}
    if result.get("retCode") == 0:
        for pos in result["result"].get("list", []):
            if float(pos.get("size", 0)) > 0:
                sym = pos["symbol"]
                positions[sym] = {
                    "side":          pos.get("side", "?"),
                    "size":          float(pos.get("size", 0)),
                    "avgPrice":      float(pos.get("avgPrice", 0)),
                    "unrealisedPnl": float(pos.get("unrealisedPnl", 0)),
                    "markPrice":     float(pos.get("markPrice", 0)),
                }
    return positions


def get_sheet_signals():
    """
    Returns (opens, recent_wins):
      opens       — all OPEN rows
      recent_wins — WIN rows resolved within the last 24h (for TP2 pursuit detection)
    Since v46.19, the trader targets TP2 in Bybit orders. The tracker may mark WIN/TP1
    while the Bybit position is still alive chasing TP2. We need recent WIN rows so the
    orphan checker can classify these as TYPE C (TP2 Pursuit) instead of TYPE A (Critical).
    """
    import subprocess
    for mod, pkg in [("gspread", "gspread"), ("google.oauth2", "google-auth")]:
        try:
            __import__(mod)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])
    from google.oauth2.service_account import Credentials
    import gspread
    creds  = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    sheet  = client.open_by_key(GOOGLE_SHEET_ID).sheet1
    rows   = sheet.get_all_values()[1:]

    opens       = []
    recent_wins = []  # WIN rows resolved in last 24h
    bkk_now     = datetime.now(timezone(timedelta(hours=7)))

    for row in rows:
        while len(row) < 17:
            row.append("")
        status = row[11].strip()
        signal = row[1].strip()
        coin   = row[0].strip()

        if status == "OPEN":
            opens.append({
                "coin":      coin,
                "signal":    signal,
                "direction": "LONG" if "Long" in signal or "🟢" in signal else "SHORT",
                "conf":      row[2].strip(),
                "ts":        row[10].strip(),
            })
        elif status == "WIN":
            # Check resolved_at (col 16) to see if this WIN is recent enough to have
            # an active Bybit TP2 order still running
            resolved_at_str = row[16].strip() if len(row) > 16 else ""
            if resolved_at_str:
                try:
                    resolved_dt = datetime.strptime(
                        resolved_at_str[:16], "%Y-%m-%d %H:%M"
                    ).replace(tzinfo=timezone(timedelta(hours=7)))
                    age_h = (bkk_now - resolved_dt).total_seconds() / 3600
                    # 72h window — partial close positions (50%@TP1 + 50%@TP2/TP3)
                    # can stay open on Bybit 2-3 days after TP1 resolve. 24h was
                    # too short and would flip these back to TYPE A false alarms.
                    if age_h <= 72:
                        recent_wins.append({
                            "coin":        coin,
                            "resolved_at": resolved_at_str,
                            "age_h":       age_h,
                        })
                except Exception:
                    pass

    return opens, recent_wins


def send_telegram(msg):
    try:
        import urllib.request
        data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Telegram failed: {e}")


def main():
    lines = []
    def p(s=""): lines.append(s); print(s)

    bkk_now = datetime.now(timezone(timedelta(hours=7)))
    p("=" * 65)
    p("  WHALE-STREAM BYBIT ORPHAN DETECTOR")
    p(f"  Run at: {bkk_now.strftime('%Y-%m-%d %H:%M')} BKK")
    p("=" * 65)
    p()

    print("Fetching Bybit open positions...")
    bybit_positions = get_bybit_open_positions()
    p(f"  Bybit open positions : {len(bybit_positions)}")
    for sym, data in sorted(bybit_positions.items()):
        pnl_str = f"{data['unrealisedPnl']:+.2f} USDT"
        p(f"  {sym:15s} {data['side']:5s} size={data['size']}  entry={data['avgPrice']}  uPnL={pnl_str}")
    p()

    print("Fetching Google Sheets signals...")
    sheet_opens, recent_wins = get_sheet_signals()
    sheet_open_coins      = {r["coin"].upper() for r in sheet_opens}
    sheet_recent_win_coins = {r["coin"].upper() for r in recent_wins}
    p(f"  Sheet OPEN signals   : {len(sheet_opens)}")
    p(f"  Recent WIN rows (24h): {len(recent_wins)}  (potential TP2 pursuits)")
    p()

    # ── Bybit symbols → coin names (strip USDT suffix) ────────────
    bybit_coins = {}
    for sym in bybit_positions:
        coin = sym.replace("USDT", "").replace("PERP", "").upper()
        bybit_coins[coin] = sym

    # ── Type A orphans: Bybit position, no OPEN or recent WIN row ──
    # (True orphans — unknown position with no tracking context)
    type_a = [
        (coin, sym) for coin, sym in bybit_coins.items()
        if coin not in sheet_open_coins and coin not in sheet_recent_win_coins
    ]

    # ── Type B orphans: OPEN sheet row but no Bybit position ───────
    type_b = [r for r in sheet_opens if r["coin"].upper() not in bybit_coins]

    # ── Type C (new): Bybit position found, sheet shows recent WIN ──
    # Since v46.19 the trader targets TP2. Tracker resolves WIN/TP1 first,
    # but the Bybit order may still be live pursuing TP2. This is EXPECTED.
    type_c = [
        (coin, sym) for coin, sym in bybit_coins.items()
        if coin not in sheet_open_coins and coin in sheet_recent_win_coins
    ]

    # ── Report ─────────────────────────────────────────────────────
    if type_a:
        p(f"── TYPE A ORPHANS — {len(type_a)} BYBIT POSITIONS NOT IN SHEET ─")
        for coin, sym in sorted(type_a):
            pos = bybit_positions[sym]
            p(f"  [CRITICAL] {coin:10s} ({sym}) — {pos['side']} size={pos['size']} uPnL={pos['unrealisedPnl']:+.2f}")
        p("  -> These positions have real margin at risk but NO tracking row!")
        p("  -> Investigate: was the sheet row deleted? Did logging fail?")
        p()
    else:
        p("── TYPE A ORPHANS: NONE — All Bybit positions have sheet rows ──")
        p()

    if type_c:
        p(f"── TYPE C — {len(type_c)} TP2 PURSUIT(S) — Bybit chasing TP2 after TP1 WIN ─")
        for coin, sym in sorted(type_c):
            pos    = bybit_positions[sym]
            win_r  = next((r for r in recent_wins if r["coin"].upper() == coin), {})
            age_h  = win_r.get("age_h", 0)
            p(f"  [INFO] {coin:10s} ({sym}) — {pos['side']} size={pos['size']}  "
              f"uPnL={pos['unrealisedPnl']:+.2f}  TP1 resolved {age_h:.1f}h ago")
        p("  -> Sheet shows WIN/TP1 but Bybit order still targeting TP2.")
        p("  -> This is EXPECTED since v46.19. Let it run or close manually.")
        p()

    if type_b:
        # Only flag recent ones (< 48h) as potentially concerning
        concerning = []
        for r in type_b:
            try:
                dt = datetime.strptime(r["ts"], "%Y-%m-%d %H:%M").replace(
                    tzinfo=timezone(timedelta(hours=7)))
                age_h = (bkk_now - dt).total_seconds() / 3600
                if age_h < 48:
                    concerning.append((r, age_h))
            except Exception:
                pass
        p(f"── TYPE B: {len(type_b)} OPEN SHEET SIGNALS WITH NO BYBIT POSITION ─")
        p(f"  ({len(type_b) - len(concerning)} are >48h old — likely skipped by trader, normal)")
        if concerning:
            p(f"  WARNING: {len(concerning)} recent signals (<48h) with no Bybit position:")
            for r, age_h in sorted(concerning, key=lambda x: x[1]):
                p(f"     {r['coin']:10s} {r['direction']:6s} {r['conf']:6s} {r['ts']}  ({age_h:.1f}h old)")
        p()
    else:
        p("── TYPE B: All OPEN sheet signals have matching Bybit positions ──")
        p()

    p("=" * 65)

    # ── Telegram alerts ────────────────────────────────────────────
    # TYPE A only → CRITICAL (real unknown orphan)
    if type_a:
        msg = (
            f"<b>⚠️ ORPHANED BYBIT POSITIONS DETECTED</b>\n"
            f"  {len(type_a)} position(s) open on Bybit with NO tracking row in sheet:\n"
        )
        for coin, sym in type_a:
            pos = bybit_positions[sym]
            msg += f"  - {coin} {pos['side']} uPnL={pos['unrealisedPnl']:+.2f} USDT\n"
        msg += "  Check Google Sheets immediately."
        send_telegram(msg)

    # TYPE C → INFO only (TP2 pursuits — expected since v46.19)
    if type_c:
        msg = (
            f"<b>ℹ️ TP2 PURSUIT(S) ACTIVE</b> — {len(type_c)} position(s) chasing TP2:\n"
        )
        for coin, sym in type_c:
            pos   = bybit_positions[sym]
            win_r = next((r for r in recent_wins if r["coin"].upper() == coin), {})
            msg  += f"  - {coin} {pos['side']} uPnL={pos['unrealisedPnl']:+.2f} USDT  (TP1 resolved {win_r.get('age_h',0):.1f}h ago)\n"
        msg += "  These are intentional — Bybit targeting TP2, tracker already marked TP1 WIN."
        send_telegram(msg)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nReport saved to: {OUT_FILE}")


if __name__ == "__main__":
    main()
