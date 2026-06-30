"""
╔══════════════════════════════════════════════════════════════╗
║   WHALE-STREAM WEEKLY SCORECARD  v47.44                      ║
║                                                              ║
║  Runs every Monday 07:00 BKK                                 ║
║  Compares this week vs last week:                            ║
║    - Balance growth                                          ║
║    - Win rate trend                                          ║
║    - Best / worst coin                                       ║
║    - ONE recommendation (block coin / adjust floor)          ║
║                                                              ║
║  Recommendation stored in pending_recommendation.json        ║
║  User replies YES/NO in Telegram → telegram_commands.py acts ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import io
import json
import requests
from datetime import datetime, timezone, timedelta

# ── UTF-8 safe output ─────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BKK = timezone(timedelta(hours=7))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TRADE_LOG_FILE  = os.path.join(SCRIPT_DIR, "trade_log.json")
BALANCE_FILE    = os.path.join(SCRIPT_DIR, "bybit_balance.json")
HISTORY_FILE    = os.path.join(SCRIPT_DIR, "weekly_history.json")
PENDING_FILE    = os.path.join(SCRIPT_DIR, "pending_recommendation.json")

# ── Telegram config ───────────────────────────────────────────
try:
    from local_config import TELEGRAM_BOT_TOKEN
except ImportError:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

TELEGRAM_CHAT_ID = ""
for _attr in ("TELEGRAM_CHAT_ID_OPS", "TELEGRAM_CHAT_ID"):
    try:
        from local_config import __dict__ as _lc
        _v = _lc.get(_attr, "")
        if _v:
            TELEGRAM_CHAT_ID = _v
            break
    except Exception:
        pass
if not TELEGRAM_CHAT_ID:
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID_OPS", "") or os.getenv("TELEGRAM_CHAT_ID", "")

# Re-import cleanly
try:
    from local_config import TELEGRAM_CHAT_ID_OPS
    TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID_OPS
except ImportError:
    try:
        from local_config import TELEGRAM_CHAT_ID as _tc
        TELEGRAM_CHAT_ID = _tc
    except ImportError:
        pass


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def bkk_now():
    return datetime.now(BKK)


def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] No token/chat_id — printing only")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=15,
        )
        if not r.ok:
            print(f"[Telegram] Error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[Telegram] Exception: {e}")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def parse_ts(ts_str):
    """Parse ISO timestamp string → aware datetime (BKK if naive)."""
    if not ts_str:
        return None
    try:
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=BKK)
        return ts
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════
# CORE LOGIC
# ══════════════════════════════════════════════════════════════

def get_window(resolved, days_ago_start, days_ago_end):
    """Trades resolved between days_ago_start and days_ago_end days ago."""
    now = bkk_now()
    result = []
    for t in resolved:
        ts = parse_ts(t.get("resolved_at") or t.get("ts"))
        if ts is None:
            continue
        age = (now - ts).total_seconds() / 86400
        if days_ago_start <= age < days_ago_end:
            result.append(t)
    return result


def compute_stats(trades):
    wins   = sum(1 for t in trades if t.get("status") == "WIN")
    losses = len(trades) - wins
    wr     = (wins / len(trades) * 100) if trades else 0.0
    pnl    = sum(float(t.get("pnl_usd") or 0) for t in trades)

    # Per coin+direction breakdown
    by_coin = {}
    for t in trades:
        coin = str(t.get("coin", "?")).upper()
        dirn = str(t.get("direction", "?")).upper()
        key  = f"{coin} {dirn}"
        by_coin.setdefault(key, {"wins": 0, "losses": 0, "pnl": 0.0})
        if t.get("status") == "WIN":
            by_coin[key]["wins"] += 1
        else:
            by_coin[key]["losses"] += 1
        by_coin[key]["pnl"] += float(t.get("pnl_usd") or 0)

    return {
        "wins": wins, "losses": losses, "wr": wr,
        "pnl": pnl, "total": len(trades), "by_coin": by_coin,
    }


def pick_recommendation(this_stats, all_resolved):
    """
    Priority order:
    1. Coin with 2+ losses this week AND <50% all-time WR → BLOCK
    2. Overall LONG WR this week <45% → raise confidence floor
    3. Balance growing + WR >58% → keep going
    4. Default → monitor
    """
    by_coin = this_stats["by_coin"]

    # Priority 1 — block a chronic loser
    block_candidates = []
    for key, stats in by_coin.items():
        if stats["losses"] < 2:
            continue
        parts = key.split(" ", 1)
        if len(parts) != 2:
            continue
        coin, dirn = parts
        all_dir = [t for t in all_resolved
                   if str(t.get("coin", "")).upper() == coin
                   and str(t.get("direction", "")).upper() == dirn]
        if len(all_dir) < 3:
            continue
        all_wins = sum(1 for t in all_dir if t.get("status") == "WIN")
        all_wr = all_wins / len(all_dir) * 100
        if all_wr < 50:
            block_candidates.append({
                "type":        "block_coin",
                "coin":        coin,
                "direction":   dirn,
                "week_losses": stats["losses"],
                "week_wins":   stats["wins"],
                "week_pnl":    round(stats["pnl"], 2),
                "all_wr":      round(all_wr, 1),
                "all_trades":  len(all_dir),
                "status":      "pending",
                "created":     bkk_now().isoformat(),
            })

    if block_candidates:
        # Pick worst P&L this week
        return sorted(block_candidates, key=lambda x: x["week_pnl"])[0]

    # Priority 2 — LONG WR declining this week
    long_trades = [t for t in this_stats.get("_raw", [])
                   if str(t.get("direction", "")).upper() == "LONG"]
    # Compute from by_coin instead
    long_wins   = sum(v["wins"]   for k, v in by_coin.items() if k.endswith(" LONG"))
    long_losses = sum(v["losses"] for k, v in by_coin.items() if k.endswith(" LONG"))
    long_total  = long_wins + long_losses
    long_wr     = (long_wins / long_total * 100) if long_total >= 4 else None

    if long_wr is not None and long_wr < 45:
        return {
            "type":    "raise_floor",
            "message": f"LONG WR only {long_wr:.0f}% this week ({long_wins}W/{long_losses}L). Consider raising LONG confidence floor to 92%.",
            "status":  "pending",
            "created": bkk_now().isoformat(),
        }

    # Priority 3 — positive
    return {
        "type":    "keep_going",
        "message": "System is performing within range. Keep accumulating trades.",
        "status":  "info",
        "created": bkk_now().isoformat(),
    }


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print()
    print("=" * 60)
    print("  WHALE-STREAM WEEKLY SCORECARD")
    print(f"  {bkk_now().strftime('%Y-%m-%d %H:%M BKK')}")
    print("=" * 60)

    # ── Load trades ───────────────────────────────────────────
    all_trades = load_json(TRADE_LOG_FILE, [])
    resolved   = [t for t in all_trades if t.get("status") in ("WIN", "LOSS")]
    print(f"  Loaded {len(resolved)} resolved trades")

    this_week = get_window(resolved, 0,  7)
    last_week = get_window(resolved, 7, 14)
    print(f"  This week: {len(this_week)} trades | Last week: {len(last_week)} trades")

    this_stats = compute_stats(this_week)
    last_stats = compute_stats(last_week)

    # ── Balance ───────────────────────────────────────────────
    balance_data     = load_json(BALANCE_FILE, {})
    balance_now      = float(balance_data.get("balance_usd") or
                             balance_data.get("balance") or
                             balance_data.get("total_equity") or 0)

    history              = load_json(HISTORY_FILE, {})
    balance_last_week    = float(history.get("balance_eow") or 500.0)
    balance_delta        = balance_now - balance_last_week
    balance_pct          = (balance_delta / balance_last_week * 100) if balance_last_week else 0

    # Save for next week
    history["balance_eow"]      = balance_now
    history["last_scorecard"]   = bkk_now().isoformat()
    history["trades_all_time"]  = len(resolved)
    save_json(HISTORY_FILE, history)

    # ── Trend arrows ──────────────────────────────────────────
    bal_arrow = "📈" if balance_delta > 0 else ("📉" if balance_delta < 0 else "➡️")
    wr_delta  = this_stats["wr"] - last_stats["wr"]
    wr_arrow  = "↑" if wr_delta >  1 else ("↓" if wr_delta < -1 else "→")

    # ── Best / worst coin this week ───────────────────────────
    by_coin   = this_stats["by_coin"]
    best_key  = max(by_coin, key=lambda k: by_coin[k]["pnl"]) if by_coin else None
    worst_key = min(by_coin, key=lambda k: by_coin[k]["pnl"]) if by_coin else None

    # ── Recommendation ────────────────────────────────────────
    rec = pick_recommendation(this_stats, resolved)
    if rec.get("type") == "block_coin":
        save_json(PENDING_FILE, rec)
        print(f"  Recommendation: BLOCK {rec['coin']} {rec['direction']} — saved to pending_recommendation.json")
    else:
        # Clear any stale pending
        if os.path.exists(PENDING_FILE):
            os.remove(PENDING_FILE)

    # ── Build Telegram message ────────────────────────────────
    week_str      = bkk_now().strftime("%b %d")
    next_monday   = (bkk_now() + timedelta(days=7)).strftime("%b %d")

    lines = [
        f"📊 <b>WEEKLY SCORECARD — {week_str}</b>",
        "",
        "💰 <b>BALANCE</b>",
        f"  Now:       <b>${balance_now:.0f}</b>  {bal_arrow} ${balance_delta:+.0f} ({balance_pct:+.1f}%)",
        f"  Last week: ${balance_last_week:.0f}",
        "",
        "📈 <b>WIN RATE</b>",
        f"  This week:  <b>{this_stats['wr']:.0f}%</b>  ({this_stats['wins']}W/{this_stats['losses']}L · {this_stats['total']} trades)",
        f"  Last week:  {last_stats['wr']:.0f}%  ({last_stats['wins']}W/{last_stats['losses']}L · {last_stats['total']} trades)",
        f"  Trend: {wr_arrow} {wr_delta:+.0f}pp",
        "",
        "💵 <b>P&amp;L THIS WEEK</b>",
        f"  {this_stats['pnl']:+.2f} USDT",
    ]

    if best_key and by_coin[best_key]["pnl"] > 0:
        b = by_coin[best_key]
        lines += [
            "",
            "🏆 <b>BEST COIN</b>",
            f"  {best_key} — {b['wins']}W/{b['losses']}L  ({b['pnl']:+.2f} USDT)",
        ]

    if worst_key and by_coin[worst_key]["pnl"] < 0:
        w = by_coin[worst_key]
        lines += [
            "",
            "🔴 <b>WORST COIN</b>",
            f"  {worst_key} — {w['wins']}W/{w['losses']}L  ({w['pnl']:+.2f} USDT)",
        ]

    lines += ["", "─" * 22]

    if rec["type"] == "block_coin":
        lines += [
            "⚡ <b>RECOMMENDATION</b>",
            f"  Block <b>{rec['coin']} {rec['direction']}</b> permanently",
            f"  This week: {rec['week_losses']}L/{rec['week_wins']}W  |  All-time: {rec['all_wr']}% WR ({rec['all_trades']} trades)",
            f"  Cost this week: {rec['week_pnl']:+.2f} USDT",
            "",
            "  Reply <b>YES</b> → auto-block next cycle",
            "  Reply <b>NO</b>  → keep watching",
        ]
    elif rec["type"] == "raise_floor":
        lines += [
            "⚡ <b>RECOMMENDATION</b>",
            f"  {rec['message']}",
            "",
            "  Reply <b>YES</b> → raise floor to 92% next cycle",
            "  Reply <b>NO</b>  → keep current floor",
        ]
    else:
        lines += [
            "✅ <b>THIS WEEK</b>",
            f"  {rec['message']}",
            "  No changes needed.",
        ]

    lines += [
        "─" * 22,
        f"All-time trades: {len(resolved)}",
        f"Next scorecard: Mon {next_monday} 07:00 BKK",
        "🐳 WHALE-STREAM v47.44",
    ]

    msg = "\n".join(lines)
    print()
    print(msg)
    print()
    send_telegram(msg)
    print("✅ Weekly scorecard sent.")


if __name__ == "__main__":
    main()
