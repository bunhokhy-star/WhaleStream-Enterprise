from __future__ import annotations   # PEP 563 — lazy annotations, Python 3.7+ compatible
"""
╔══════════════════════════════════════════════════════════════╗
║   WHALE-STREAM SIGNAL SCORER v47.19                          ║
║                                                              ║
║  Pre-scores every signal 0–10 BEFORE sending to Strategist.  ║
║  Deterministic — no API calls, instant evaluation.           ║
║                                                              ║
║  Scoring dimensions (2 pts each, base max 10):               ║
║    [1] Bot confidence alignment    (0–2)                     ║
║    [2] Market regime match         (0–2)                     ║
║    [3] Coin historical win rate    (0–2)                     ║
║    [4] Portfolio correlation       (0–2)                     ║
║    [5] Pattern strength            (0–2)                     ║
║  MTF bias adjustment (applied after, clamped 0–10):          ║
║    [6] MTF structure alignment     (-2 to +2)                ║
║       +2 = ideal entry (4H_BULL+1H_PULLBACK or mirror)      ║
║       +1 = 4H trend confirms direction                       ║
║        0 = no MTF bias or neutral                            ║
║       -1 = 4H trend opposes direction (counter-trend)        ║
║       -2 = 4H_SIDEWAYS (structural indecision, VETO risk)   ║
║                                                              ║
║  Verdict thresholds:                                         ║
║    Score ≥ 7  → STRONG  (send to Claude for final review)    ║
║    Score 4–6  → REVIEW  (send to Claude, flag low score)     ║
║    Score < 4  → SKIP    (auto-reject, save Claude tokens)    ║
║                                                              ║
║  Imported by whale_stream_strategist.py — no direct run.     ║
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

# ── Pattern strength tables ────────────────────────────────────
# Score +2: proven high-probability setups
STRONG_PATTERNS = {
    "bull flag", "bear flag",
    "breakout", "breakdown",
    "double bottom", "double top",
    "support bounce", "resistance break", "support break",
    "cup and handle",
    "ascending triangle", "descending triangle",
    "bull pennant", "bear pennant",
    "wyckoff accumulation", "wyckoff distribution",
    "golden cross", "death cross",
    "rsi divergence", "bullish divergence", "bearish divergence",
    "inverse head and shoulders", "head and shoulders",
    "falling wedge", "rising wedge",
    "higher high higher low", "lower high lower low",
}

# Score +1: moderate-probability setups
MODERATE_PATTERNS = {
    "momentum", "trend following", "trend continuation",
    "rsi oversold", "rsi overbought",
    "macd bullish", "macd bearish", "macd cross",
    "volume spike", "volume breakout",
    "ema cross", "ma cross", "sma cross",
    "higher high", "lower low", "higher low", "lower high",
    "support hold", "resistance hold",
    "consolidation breakout", "range breakout",
    "pullback", "retest", "bounce",
    "fib retracement", "fibonacci", "fib level",
    "order block", "fair value gap", "fvg",
}

# Verdict thresholds (names match verdicts: STRONG_MIN = floor for STRONG, REVIEW_MIN = floor for REVIEW)
STRONG_MIN  = 7   # score ≥ 7 → STRONG (high priority, send to Claude)
REVIEW_MIN  = 4   # score ≥ 4 → REVIEW (send to Claude, flag low score); below 4 → SKIP

# ── MTF bias classification tables ────────────────────────────
# Ideal LONG entry: 4H bullish structure, 1H pulling back (best timing)
MTF_IDEAL_LONG  = {"4H_BULL_1H_PULLBACK", "4H_BULL_1H_RANGE", "4H_BULL_1H_BOT"}
# Ideal SHORT entry: 4H bearish structure, 1H bouncing up (best timing)
MTF_IDEAL_SHORT = {"4H_BEAR_1H_BOUNCE",   "4H_BEAR_1H_RANGE", "4H_BEAR_1H_TOP"}


def _extract_mtf_bias(pattern_str: str) -> str:
    """Extract MTF bias like '4H_BULL_1H_PULLBACK' from pattern '[4H_BULL_1H_PULLBACK]'."""
    import re as _re
    m = _re.search(r'\[([A-Z0-9_]{5,30})\]', str(pattern_str))
    if m:
        candidate = m.group(1)
        if candidate.startswith(("4H_", "MTF_")):
            return candidate
    return ""


def _score_mtf_bias(direction: str, pattern: str) -> tuple[int, str]:
    """
    MTF structure alignment adjustment (-2 to +2).
    Applied to base score after all 5 dimensions; final score clamped 0-10.

    +2 — ideal entry: 4H trend confirmed, 1H pulling back into it (best timing)
    +1 — basic alignment: 4H trend confirms direction
     0 — no MTF data or neutral structure
    -1 — counter-trend: 4H opposes direction
    -2 — 4H_SIDEWAYS: structural indecision, Strategist VETO likely
    """
    bias = _extract_mtf_bias(pattern)
    if not bias:
        return 0, "MTF no bias found ±0"

    direction_up = direction.upper()

    # Ideal entries — 4H trend + 1H setting up entry timing
    if bias in MTF_IDEAL_LONG and direction_up == "LONG":
        return 2, f"MTF ideal LONG ({bias}) +2"
    if bias in MTF_IDEAL_SHORT and direction_up == "SHORT":
        return 2, f"MTF ideal SHORT ({bias}) +2"

    # Sideways = no structural edge (Strategist VETO rule already exists)
    if "SIDEWAYS" in bias:
        return -2, f"MTF sideways ({bias}) no trend edge -2"

    # 4H confirms direction (not ideal timing but aligned)
    if bias.startswith("4H_BULL") and direction_up == "LONG":
        return 1, f"MTF 4H bull, LONG aligned ({bias}) +1"
    if bias.startswith("4H_BEAR") and direction_up == "SHORT":
        return 1, f"MTF 4H bear, SHORT aligned ({bias}) +1"

    # Counter-trend — 4H opposes trade direction
    if bias.startswith("4H_BULL") and direction_up == "SHORT":
        return -1, f"MTF 4H bull but SHORT — counter-trend ({bias}) -1"
    if bias.startswith("4H_BEAR") and direction_up == "LONG":
        return -1, f"MTF 4H bear but LONG — counter-trend ({bias}) -1"

    return 0, f"MTF {bias} neutral alignment ±0"


def _score_confidence(confidence: float) -> tuple[int, str]:
    """
    Dimension 1: Bot confidence alignment.
    Bot assigns confidence 0–100. Higher = more certain.
    """
    if confidence >= 88:
        return 2, f"conf {confidence:.0f}% (≥88) +2"
    elif confidence >= 70:
        return 1, f"conf {confidence:.0f}% (≥70) +1"
    else:
        return 0, f"conf {confidence:.0f}% (<70) +0"


def _score_regime(direction: str, market_bias: str) -> tuple[int, str]:
    """
    Dimension 2: Market regime match.
    Trading WITH BTC trend adds conviction; against it is penalised.
    """
    direction    = direction.upper()
    market_bias  = (market_bias or "NEUTRAL").upper()

    if market_bias == "NEUTRAL":
        return 1, f"regime NEUTRAL +1"
    elif (direction == "LONG"  and market_bias == "BULLISH") or \
         (direction == "SHORT" and market_bias == "BEARISH"):
        return 2, f"regime {market_bias} matches {direction} +2"
    else:
        # Fighting the trend — partial penalisation (0 pts, not negative)
        return 0, f"regime {market_bias} opposes {direction} +0"


def _score_win_rate(coin: str, direction: str, history: dict) -> tuple[int, str]:
    """
    Dimension 3: Coin's historical win rate on this direction.
    history: {(coin, direction): [{"outcome": "WIN"/"LOSS", ...}]}
    """
    key    = (coin.upper(), direction.upper())
    trades = history.get(key, [])

    if len(trades) < 3:
        # Insufficient history — uncertain, not penalised
        return 1, f"history <3 samples ({len(trades)}) +1"

    wins   = sum(1 for t in trades if t.get("outcome", "") == "WIN")
    wr     = wins / len(trades)

    if wr >= 0.65:
        return 2, f"WR {wr*100:.0f}% ({wins}W/{len(trades)-wins}L ≥65%) +2"
    elif wr >= 0.50:
        return 1, f"WR {wr*100:.0f}% ({wins}W/{len(trades)-wins}L ≥50%) +1"
    else:
        return 0, f"WR {wr*100:.0f}% ({wins}W/{len(trades)-wins}L <50%) +0"


def _score_correlation(coin: str, direction: str, positions: dict) -> tuple[int, str]:
    """
    Dimension 4: Portfolio correlation / concentration risk.
    Penalise if same coin already open, or if too many positions overall.

    positions: {symbol: {"side": "Buy"/"Sell", ...}}
    """
    coin_upper = coin.upper()
    open_count = len(positions)

    # Check if same coin is already open
    for sym, pos in positions.items():
        sym_coin = sym.replace("USDT", "").upper()
        if sym_coin == coin_upper:
            pos_side  = pos.get("side", "").upper()
            same_dir  = (direction == "LONG"  and pos_side == "BUY") or \
                        (direction == "SHORT" and pos_side == "SELL")
            if same_dir:
                return 0, f"{coin} already open same direction +0"
            else:
                return 1, f"{coin} open opposite direction (hedge) +1"

    # Too many open positions = concentration risk
    if open_count >= 4:
        return 1, f"{open_count} positions open (≥4) +1"

    return 2, f"no correlated open position, {open_count} open +2"


def _score_pattern(pattern: str) -> tuple[int, str]:
    """
    Dimension 5: Pattern strength classification.
    """
    if not pattern:
        return 0, "no pattern specified +0"

    pat_lower = pattern.lower()

    # Check strong patterns (pattern must CONTAIN the strong keyword, not vice versa)
    for strong in STRONG_PATTERNS:
        if strong in pat_lower:
            return 2, f"pattern '{pattern}' (strong) +2"

    # Check moderate patterns
    for moderate in MODERATE_PATTERNS:
        if moderate in pat_lower:
            return 1, f"pattern '{pattern}' (moderate) +1"

    return 0, f"pattern '{pattern}' (unrecognised) +0"


def score_signal(signal: dict, market_bias: str, history: dict, positions: dict) -> dict:
    """
    Score a single signal across all 5 dimensions.

    Args:
        signal:      dict with keys: coin, direction, confidence, pattern, entry
        market_bias: "BULLISH" | "BEARISH" | "NEUTRAL"
        history:     {(coin, direction): [trade_dicts]} from build_coin_history()
        positions:   {symbol: pos_dict} from load_portfolio_state()

    Returns:
        {
          "score":     int (0–10),
          "verdict":   "STRONG" | "REVIEW" | "SKIP",
          "breakdown": {
              "confidence": (pts, reason),
              "regime":     (pts, reason),
              "win_rate":   (pts, reason),
              "correlation":(pts, reason),
              "pattern":    (pts, reason),
          },
          "summary": str,   # one-line human-readable summary
        }
    """
    coin      = signal.get("coin", "UNKNOWN").upper()
    direction = signal.get("direction", "LONG").upper()
    conf      = float(signal.get("confidence", 0) or 0)
    pattern   = signal.get("pattern", "") or ""

    d1_pts, d1_reason = _score_confidence(conf)
    d2_pts, d2_reason = _score_regime(direction, market_bias)
    d3_pts, d3_reason = _score_win_rate(coin, direction, history)
    d4_pts, d4_reason = _score_correlation(coin, direction, positions)
    d5_pts, d5_reason = _score_pattern(pattern)
    d6_pts, d6_reason = _score_mtf_bias(direction, pattern)   # MTF adjustment (-2 to +2)

    base_score  = d1_pts + d2_pts + d3_pts + d4_pts + d5_pts
    total_score = max(0, min(10, base_score + d6_pts))   # clamp to 0-10 after MTF adj

    if total_score >= STRONG_MIN:
        verdict = "STRONG"
    elif total_score >= REVIEW_MIN:
        verdict = "REVIEW"
    else:
        verdict = "SKIP"

    breakdown = {
        "confidence":  (d1_pts, d1_reason),
        "regime":      (d2_pts, d2_reason),
        "win_rate":    (d3_pts, d3_reason),
        "correlation": (d4_pts, d4_reason),
        "pattern":     (d5_pts, d5_reason),
        "mtf_bias":    (d6_pts, d6_reason),   # signed: can be negative
    }

    mtf_sign = f"+{d6_pts}" if d6_pts >= 0 else str(d6_pts)
    summary = (
        f"{coin} {direction} — Score {total_score}/10 [{verdict}] | "
        f"Conf:{d1_pts} Regime:{d2_pts} WR:{d3_pts} Corr:{d4_pts} Pat:{d5_pts} MTF:{mtf_sign}"
    )

    return {
        "score":     total_score,
        "verdict":   verdict,
        "breakdown": breakdown,
        "summary":   summary,
    }


def score_all_signals(
    signals:     list,
    market_bias: str,
    history:     dict,
    positions:   dict,
) -> tuple[list, list, list]:
    """
    Score all signals and split into three buckets.

    Returns:
        strong  — score ≥ 7 (send to Claude, high priority)
        review  — score 4–6 (send to Claude, flag low score)
        skipped — score < 4 (auto-rejected, never sent to Claude)
    """
    strong, review, skipped = [], [], []

    for sig in signals:
        result = score_signal(sig, market_bias, history, positions)
        sig["score"]          = result["score"]
        sig["score_verdict"]  = result["verdict"]
        sig["score_breakdown"]= result["breakdown"]
        sig["score_summary"]  = result["summary"]

        if result["verdict"] == "STRONG":
            strong.append(sig)
        elif result["verdict"] == "REVIEW":
            review.append(sig)
        else:
            skipped.append(sig)

    return strong, review, skipped


def format_score_for_prompt(signal: dict) -> str:
    """
    Return a compact one-line score annotation to inject into the Claude prompt.
    Example: "Score: 8/10 [STRONG] | Conf:+2 Regime:+2 WR:+2 Corr:+1 Pat:+1"
    """
    score    = signal.get("score", "?")
    verdict  = signal.get("score_verdict", "?")
    bd       = signal.get("score_breakdown", {})

    if not bd:
        return f"Score: {score}/10 [{verdict}]"

    pts     = lambda key: bd.get(key, (0, ""))[0]
    mtf_raw = pts('mtf_bias')
    mtf_fmt = f"+{mtf_raw}" if mtf_raw >= 0 else str(mtf_raw)
    return (
        f"Score: {score}/10 [{verdict}] | "
        f"Conf:+{pts('confidence')} "
        f"Regime:+{pts('regime')} "
        f"WR:+{pts('win_rate')} "
        f"Corr:+{pts('correlation')} "
        f"Pat:+{pts('pattern')} "
        f"MTF:{mtf_fmt}"
    )


# ── Self-test (run directly for verification) ──────────────────
if __name__ == "__main__":
    import io, sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    elif hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

    print("\n🧪 SIGNAL SCORER — Self Test\n")

    _test_signals = [
        {"coin": "BTC",  "direction": "LONG",  "confidence": 90, "pattern": "Bull Flag",   "entry": "105000"},
        {"coin": "ETH",  "direction": "SHORT", "confidence": 75, "pattern": "Bear Flag",   "entry": "2500"},
        {"coin": "SOL",  "direction": "LONG",  "confidence": 60, "pattern": "momentum",    "entry": "180"},
        {"coin": "DOGE", "direction": "LONG",  "confidence": 50, "pattern": "",            "entry": "0.15"},
    ]
    _test_history = {
        ("BTC",  "LONG"):  [{"outcome": "WIN"}] * 7 + [{"outcome": "LOSS"}] * 3,
        ("ETH",  "SHORT"): [{"outcome": "WIN"}] * 5 + [{"outcome": "LOSS"}] * 5,
        ("SOL",  "LONG"):  [{"outcome": "WIN"}] * 2 + [{"outcome": "LOSS"}] * 4,
        ("DOGE", "LONG"):  [],
    }
    _test_positions = {}  # no open positions
    _test_bias      = "BULLISH"

    strong, review, skipped = score_all_signals(
        _test_signals, _test_bias, _test_history, _test_positions
    )

    print(f"Market Bias: {_test_bias}\n")
    for bucket_name, bucket in [("STRONG", strong), ("REVIEW", review), ("SKIP", skipped)]:
        for s in bucket:
            print(f"  [{bucket_name}] {s['score_summary']}")
            bd = s.get("score_breakdown", {})
            for dim, (pts, reason) in bd.items():
                print(f"           {dim:<12}: +{pts}  {reason}")
            print()

    print(f"Results — STRONG: {len(strong)}  REVIEW: {len(review)}  SKIP: {len(skipped)}")
