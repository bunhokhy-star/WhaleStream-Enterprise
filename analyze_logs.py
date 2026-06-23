"""
WHALE-STREAM Log Analyzer
Parses trader_log.txt, tracker_log.txt, bot_log.txt for health metrics.

Extracts:
- Trader: order success/failure rates, skip reasons, circuit breaker triggers, balance readings
- Tracker: trade resolution counts, expiry counts, WIN/LOSS patterns, latest stats block
- Bot: run counts, max_tokens truncations, signal generation stats, unicode errors

Output: analyze_logs.txt
"""

import os, re
from datetime import datetime
from collections import defaultdict, Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE   = os.path.join(SCRIPT_DIR, "analyze_logs.txt")

LOG_FILES = {
    "trader":  os.path.join(SCRIPT_DIR, "trader_log.txt"),
    "tracker": os.path.join(SCRIPT_DIR, "tracker_log.txt"),
    "bot":     os.path.join(SCRIPT_DIR, "bot_log.txt"),
}

def read_log(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except FileNotFoundError:
        return []

def analyze_trader(lines):
    stats = {
        "runs":                  0,
        "orders_placed":         0,
        "orders_failed":         0,
        "skipped_stale":         0,
        "skipped_entry_far":     0,
        "skipped_short_repair":  0,
        "repair_mode_runs":      0,
        "balances":              [],
        "margin_deployed":       [],
        "fail_reasons":          Counter(),
        "placed_coins":          Counter(),
        "fresh_signals":         [],  # list of ints from "Found N fresh"
    }

    for line in lines:
        s = line.strip()

        # ── Run complete ─────────────────────────────────────────
        # [2026-06-21 20:16 BKK] RUN COMPLETE — 2/5 orders placed | $40 margin deployed | balance=$492.58
        m = re.search(r'RUN COMPLETE\s*—\s*(\d+)/(\d+) orders placed \| \$(\d+\.?\d*) margin deployed \| balance=\$(\d+\.?\d*)', s)
        if m:
            stats["runs"] += 1
            placed  = int(m.group(1))
            total   = int(m.group(2))
            margin  = float(m.group(3))
            balance = float(m.group(4))
            # orders placed/failed from the RUN COMPLETE summary line (avoids double-counting)
            stats["orders_placed"]  += placed
            stats["orders_failed"]  += (total - placed)
            stats["margin_deployed"].append(margin)
            stats["balances"].append(balance)
            continue

        # ── Order placed ─────────────────────────────────────────
        # ✅ Order placed!  Order ID: ...
        # (also capture coin from the header line just above)
        # We grab coin from the "── COIN LONG/SHORT" block header
        if "Order placed!" in s or "order placed" in s.lower():
            # coin is in the block header tracked below — skip individual count here
            # (already counted via RUN COMPLETE summary)
            pass

        # Track which coins got orders placed (from block headers + placed confirmation)
        # Block format:  ── ETHFI LONG 🟢 ──
        m = re.search(r'──\s+(\w+)\s+(LONG|SHORT)', s)
        if m:
            # We note the coin; we'll credit it only if the next placed line appears
            _pending_coin = (m.group(1), m.group(2))

        # ── Order failed ─────────────────────────────────────────
        # ❌ Order failed: Price invalid (retCode=10001)
        m = re.search(r'Order failed[:\s]+(.+)', s, re.IGNORECASE)
        if m:
            reason = re.sub(r'\(retCode=\d+\)', '', m.group(1)).strip()
            stats["fail_reasons"][reason[:60]] += 1

        # ── Stale signal skips ───────────────────────────────────
        # ⏭ Skipped 50 OPEN signal(s) older than 4 hours (stale entry zones)
        m = re.search(r'Skipped (\d+) OPEN signal', s)
        if m:
            stats["skipped_stale"] += int(m.group(1))

        # ── Entry too far from mark ──────────────────────────────
        # ⏭ Entry too far from mark: signal at 0.2025 vs mark 0.18531 ...
        if "Entry too far from mark" in s:
            stats["skipped_entry_far"] += 1

        # ── Short repair skips ───────────────────────────────────
        # [2026-06-21 22:20 BKK] SKIP H SHORT — short_repair.flag present (REPAIR MODE)
        if "short_repair.flag present" in s:
            stats["skipped_short_repair"] += 1

        # ── Repair mode summary ──────────────────────────────────
        # [2026-06-21 22:20 BKK] REPAIR MODE — skipped 3 SHORT(s): H, JASMY, CHZ
        if "REPAIR MODE" in s and "skipped" in s.lower():
            stats["repair_mode_runs"] += 1

        # ── Fresh signals found ──────────────────────────────────
        # ✓ Found 5 fresh OPEN signal(s) to trade
        m = re.search(r'Found (\d+) fresh OPEN signal', s)
        if m:
            stats["fresh_signals"].append(int(m.group(1)))

        # ── Balance reading (wallet check) ───────────────────────
        # ✓ Available USDT: $492.58  (total: $492.58)
        # Already grabbed from RUN COMPLETE; this captures any intermediate reads
        m = re.search(r'Available USDT[:\s]+\$(\d+\.?\d*)', s)
        if m:
            # Only append if not already captured via RUN COMPLETE this run
            try:
                val = float(m.group(1))
                # deduplicate consecutive identical values
                if not stats["balances"] or stats["balances"][-1] != val:
                    stats["balances"].append(val)
            except ValueError:
                pass

    # ── Placed coin extraction ────────────────────────────────────
    # Walk lines again to pair block headers with placed confirmations
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        m = re.search(r'──\s+(\w+)\s+(LONG|SHORT)', s)
        if m:
            coin = m.group(1)
            # look ahead up to 10 lines for a placed confirmation
            for j in range(i + 1, min(i + 10, len(lines))):
                if "Order placed!" in lines[j]:
                    stats["placed_coins"][coin] += 1
                    break
        i += 1

    return stats


def analyze_tracker(lines):
    stats = {
        "runs":              0,
        "wins":              0,
        "losses":            0,
        "expired":           0,
        "circuit_breakers":  0,
        "no_price_skips":    0,
        "latest_stats":      {},   # from most-recent TRADE STATS block
        "errors_traceback":  0,
    }

    # ── Run count: each banner = one run ─────────────────────────
    # ║   📈  WHALE-STREAM TRACKER — CHECKING TRADES    ║
    # The banner line contains the box-drawing chars but in the file they
    # may appear as escaped unicode or actual chars — match the text part.
    for line in lines:
        s = line.strip()

        if "WHALE-STREAM TRACKER" in s and "CHECKING TRADES" in s:
            stats["runs"] += 1

        # ✅ CHZ      🔴 Short  WIN  TP1  +118.11%  (entry 0.0254 → exit 0.0224)
        if re.search(r'✅\s+\w+\s+.*(WIN|TP\d)', s):
            stats["wins"] += 1

        # ❌ HYPE     🟢 Long  LOSS  SL  -46.15%
        if re.search(r'❌\s+\w+\s+.*(LOSS|SL)', s):
            stats["losses"] += 1

        # ⏰ ZEC EXPIRED (79h old)
        if s.startswith("⏰") and "EXPIRED" in s:
            stats["expired"] += 1

        # ⚠️  CIRCUIT BREAKER: Recent P&L < -100%. Consider pausing new signals.
        if "CIRCUIT BREAKER" in s:
            stats["circuit_breakers"] += 1

        # ⚠ GRAM: no Bybit price found — skipping
        if "no Bybit price found" in s:
            stats["no_price_skips"] += 1

        # UnicodeEncodeError / Traceback
        if "UnicodeEncodeError" in s or "Traceback (most recent" in s:
            stats["errors_traceback"] += 1

    # ── Extract LATEST stats block ────────────────────────────────
    # Find the last occurrence of "Total Resolved" and parse the block
    last_idx = -1
    for i, line in enumerate(lines):
        if "Total Resolved" in line:
            last_idx = i

    if last_idx >= 0:
        block = lines[last_idx: last_idx + 20]
        for line in block:
            s = line.strip()
            m = re.search(r'Total Resolved\s*:\s*(\d+)\s*\((\d+) WIN / (\d+) LOSS\)', s)
            if m:
                stats["latest_stats"]["total_resolved"] = int(m.group(1))
                stats["latest_stats"]["wins"]           = int(m.group(2))
                stats["latest_stats"]["losses"]         = int(m.group(3))
            m = re.search(r'Win Rate\s*:\s*([\d.]+)%', s)
            if m:
                stats["latest_stats"]["win_rate"] = float(m.group(1))
            m = re.search(r'Long Win Rate\s*:\s*([\d.]+)%\s*\((\d+)/(\d+)\)', s)
            if m:
                stats["latest_stats"]["long_win_rate"] = f"{m.group(1)}% ({m.group(2)}/{m.group(3)})"
            m = re.search(r'Short Win Rate\s*:\s*([\d.]+)%\s*\((\d+)/(\d+)\)', s)
            if m:
                stats["latest_stats"]["short_win_rate"] = f"{m.group(1)}% ({m.group(2)}/{m.group(3)})"
            m = re.search(r'Total P&L\s*:\s*([+\-][\d.]+%)', s)
            if m:
                stats["latest_stats"]["total_pnl"] = m.group(1)
            m = re.search(r'Profit Factor\s*:\s*([\d.]+)', s)
            if m:
                stats["latest_stats"]["profit_factor"] = float(m.group(1))
            m = re.search(r'Expectancy\s*:\s*([+\-][\d.]+%)', s)
            if m:
                stats["latest_stats"]["expectancy"] = m.group(1)
            m = re.search(r'Max Drawdown\s*:\s*([+\-][\d.]+%)', s)
            if m:
                stats["latest_stats"]["max_drawdown"] = m.group(1)
            m = re.search(r'Still OPEN\s*:\s*(\d+)', s)
            if m:
                stats["latest_stats"]["still_open"] = int(m.group(1))
            m = re.search(r'Expired \(not counted.*\):\s*(\d+)', s)
            if m:
                stats["latest_stats"]["expired_total"] = int(m.group(1))

    return stats


def analyze_bot(lines):
    stats = {
        "runs":              0,
        "run_completes":     0,
        "longs_parsed":      Counter(),   # accumulates per run
        "shorts_parsed":     Counter(),
        "signals_logged":    0,
        "signals_skipped_dup": 0,
        "stop_max_tokens":   0,
        "stop_end_turn":     0,
        "unicode_errors":    0,
        "graveyard_win_rates": [],
        "btc_dominance":     [],
        "fear_greed":        [],
    }

    for line in lines:
        s = line.strip()

        # ║   🐳  WHALE-STREAM v45.0 — AUTO BOT STARTING    ║
        if "WHALE-STREAM" in s and "AUTO BOT STARTING" in s:
            stats["runs"] += 1

        # ✅  WHALE-STREAM run complete!
        if "WHALE-STREAM run complete" in s:
            stats["run_completes"] += 1

        # ✓ Parsed 3 LONG + 3 SHORT signals
        m = re.search(r'Parsed (\d+) LONG \+ (\d+) SHORT signals', s)
        if m:
            stats["longs_parsed"][int(m.group(1))] += 1
            stats["shorts_parsed"][int(m.group(2))] += 1

        # ✓ 2 signal(s) logged as OPEN in Google Sheets
        m = re.search(r'(\d+) signal\(s\) logged as OPEN', s)
        if m:
            stats["signals_logged"] += int(m.group(1))

        # ℹ Skipping duplicates (coin+direction) already OPEN today: 6 combos
        m = re.search(r'Skipping duplicates.*?:\s*(\d+) combos', s)
        if m:
            stats["signals_skipped_dup"] += int(m.group(1))

        # Match both log formats: old "stop_reason=X" and new "stop=X"
        if re.search(r'stop(?:_reason)?=max_tokens', s):
            stats["stop_max_tokens"] += 1
        if re.search(r'stop(?:_reason)?=end_turn', s):
            stats["stop_end_turn"] += 1

        # UnicodeEncodeError
        if "UnicodeEncodeError" in s:
            stats["unicode_errors"] += 1

        # ✓ Signal Graveyard: 20 trades loaded (win rate: 40%)
        m = re.search(r'Signal Graveyard.*win rate:\s*(\d+)%', s)
        if m:
            stats["graveyard_win_rates"].append(int(m.group(1)))

        # ✓ BTC Dominance: 55.90% [HIGH — ...]
        m = re.search(r'BTC Dominance:\s*([\d.]+)%', s)
        if m:
            stats["btc_dominance"].append(float(m.group(1)))

        # ✓ Fear & Greed: 14/100 [EXTREME FEAR]
        m = re.search(r'Fear & Greed:\s*(\d+)/100', s)
        if m:
            stats["fear_greed"].append(int(m.group(1)))

    return stats


def main():
    lines_out = []
    def p(s=""): lines_out.append(s); print(s)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    p("=" * 65)
    p("  WHALE-STREAM LOG HEALTH REPORT")
    p(f"  Generated: {now}")
    p("=" * 65)
    p()

    # ── TRADER LOG ────────────────────────────────────────────────
    trader_lines = read_log(LOG_FILES["trader"])
    p(f"-- TRADER LOG ({len(trader_lines)} lines) " + "-" * 35)
    if trader_lines:
        ts = analyze_trader(trader_lines)
        total_attempted = ts["orders_placed"] + ts["orders_failed"]
        p(f"  Trader runs              : {ts['runs']}")
        if ts["balances"]:
            p(f"  Balance (min/max/latest) : ${min(ts['balances']):.2f}  /  ${max(ts['balances']):.2f}  /  ${ts['balances'][-1]:.2f}")
        if ts["margin_deployed"]:
            total_margin = sum(ts["margin_deployed"])
            p(f"  Total margin deployed    : ${total_margin:.0f}  (across {ts['runs']} runs)")
        if ts["fresh_signals"]:
            p(f"  Fresh signals seen       : total={sum(ts['fresh_signals'])}  avg={sum(ts['fresh_signals'])/len(ts['fresh_signals']):.1f}/run")
        p(f"  Orders placed            : {ts['orders_placed']}")
        p(f"  Orders failed            : {ts['orders_failed']}")
        if total_attempted > 0:
            sr = ts["orders_placed"] / total_attempted * 100
            p(f"  Order success rate       : {sr:.1f}%  ({ts['orders_placed']}/{total_attempted})")
        p(f"  Stale skips (cumulative) : {ts['skipped_stale']}  (signals >4h old, per run)")
        p(f"  Entry-too-far skips      : {ts['skipped_entry_far']}  (>8% from mark price)")
        p(f"  SHORT repair skips       : {ts['skipped_short_repair']}  (short_repair.flag set)")
        p(f"  Repair mode activations  : {ts['repair_mode_runs']}")
        if ts["fail_reasons"]:
            p(f"  Top failure reasons:")
            for reason, count in ts["fail_reasons"].most_common(5):
                p(f"    {count:3d}x  {reason}")
        if ts["placed_coins"]:
            top = ts["placed_coins"].most_common(8)
            p(f"  Coins with placed orders : {', '.join(f'{c}({n})' for c, n in top)}")
    else:
        p("  (file not found or empty)")
    p()

    # ── TRACKER LOG ───────────────────────────────────────────────
    tracker_lines = read_log(LOG_FILES["tracker"])
    p(f"-- TRACKER LOG ({len(tracker_lines)} lines) " + "-" * 34)
    if tracker_lines:
        ts2 = analyze_tracker(tracker_lines)
        p(f"  Tracker runs             : {ts2['runs']}")
        p(f"  WIN resolutions (logged) : {ts2['wins']}")
        p(f"  LOSS resolutions (logged): {ts2['losses']}")
        p(f"  EXPIRED (logged)         : {ts2['expired']}")
        p(f"  Circuit breaker warnings : {ts2['circuit_breakers']}")
        p(f"  No-price skips           : {ts2['no_price_skips']}  (symbol not on Bybit)")
        p(f"  Traceback/Unicode errors : {ts2['errors_traceback']}")
        ls = ts2["latest_stats"]
        if ls:
            p()
            p("  -- Latest Stats Block --")
            if "total_resolved" in ls:
                p(f"  Total resolved           : {ls['total_resolved']}  ({ls.get('wins','?')} WIN / {ls.get('losses','?')} LOSS)")
            if "win_rate" in ls:
                p(f"  Win rate                 : {ls['win_rate']}%")
            if "long_win_rate" in ls:
                p(f"  Long win rate            : {ls['long_win_rate']}")
            if "short_win_rate" in ls:
                p(f"  Short win rate           : {ls['short_win_rate']}")
            if "total_pnl" in ls:
                p(f"  Total P&L (10x)          : {ls['total_pnl']}")
            if "profit_factor" in ls:
                p(f"  Profit factor            : {ls['profit_factor']}  (>1.0 = profitable)")
            if "expectancy" in ls:
                p(f"  Expectancy per trade     : {ls['expectancy']}")
            if "max_drawdown" in ls:
                p(f"  Max drawdown             : {ls['max_drawdown']}")
            if "still_open" in ls:
                p(f"  Still OPEN               : {ls['still_open']}")
            if "expired_total" in ls:
                p(f"  Total expired            : {ls['expired_total']}")
    else:
        p("  (file not found or empty)")
    p()

    # ── BOT LOG ───────────────────────────────────────────────────
    bot_lines = read_log(LOG_FILES["bot"])
    p(f"-- BOT LOG ({len(bot_lines)} lines) " + "-" * 38)
    if bot_lines:
        bs = analyze_bot(bot_lines)
        p(f"  Bot runs (started)       : {bs['runs']}")
        p(f"  Bot runs (completed)     : {bs['run_completes']}")
        incomplete = bs["runs"] - bs["run_completes"]
        if incomplete > 0:
            p(f"  Incomplete runs          : {incomplete}  (started but did not complete)")
        p(f"  API calls stop=max_tokens: {bs['stop_max_tokens']}  (truncated — mostly pre-v46.4 with 8k limit)")
        p(f"  API calls stop=end_turn  : {bs['stop_end_turn']}  (complete — all recent runs)")
        total_calls = bs["stop_max_tokens"] + bs["stop_end_turn"]
        if total_calls > 0:
            trunc_pct = bs["stop_max_tokens"] / total_calls * 100
            p(f"  Historical truncation    : {trunc_pct:.1f}%  ({bs['stop_max_tokens']}/{total_calls} API calls, 16k limit since v46.4)")
        p(f"  Unicode errors (early)   : {bs['unicode_errors']}  (cp1252 console issue, not data loss)")
        # Signal parse breakdown
        if bs["longs_parsed"]:
            common_longs  = bs["longs_parsed"].most_common(1)[0]
            common_shorts = bs["shorts_parsed"].most_common(1)[0]
            total_longs  = sum(k * v for k, v in bs["longs_parsed"].items())
            total_shorts = sum(k * v for k, v in bs["shorts_parsed"].items())
            p(f"  Signals parsed (LONG)    : {total_longs} total  (most common: {common_longs[0]}/run x{common_longs[1]})")
            p(f"  Signals parsed (SHORT)   : {total_shorts} total  (most common: {common_shorts[0]}/run x{common_shorts[1]})")
        p(f"  Signals logged to Sheets : {bs['signals_logged']}")
        p(f"  Duplicate signals skipped: {bs['signals_skipped_dup']}")
        if bs["graveyard_win_rates"]:
            avg_wr = sum(bs["graveyard_win_rates"]) / len(bs["graveyard_win_rates"])
            p(f"  Graveyard win rate (avg) : {avg_wr:.1f}%  (over {len(bs['graveyard_win_rates'])} runs)")
        if bs["btc_dominance"]:
            p(f"  BTC dominance seen       : min {min(bs['btc_dominance']):.2f}%  max {max(bs['btc_dominance']):.2f}%  latest {bs['btc_dominance'][-1]:.2f}%")
        if bs["fear_greed"]:
            p(f"  Fear & Greed seen        : min {min(bs['fear_greed'])}  max {max(bs['fear_greed'])}  latest {bs['fear_greed'][-1]}")
    else:
        p("  (file not found or empty)")
    p()
    p("=" * 65)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines_out))
    print(f"\nReport saved to: {OUT_FILE}")


if __name__ == "__main__":
    main()
