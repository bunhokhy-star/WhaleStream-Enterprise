from engine.trade_builder import build_long_trade
from engine.short_trade_builder import build_short_trade

from engine.market_score import market_score
from engine.pattern_score import get_pattern_score
from engine.trend_matrix import trend_matrix
from engine.btc_regime import get_btc_regime
from engine.decision_engine import calculate_confidence


def build_signal_v2(
    symbol,
    direction,
    funding_rate=0,
    oi_change=0
):

    # ==========================
    # Build Trade
    # ==========================

    if direction == "LONG":
        trade = build_long_trade(symbol)
    else:
        trade = build_short_trade(symbol)

    # ==========================
    # Trend Analysis
    # ==========================

    trend = trend_matrix(symbol)

    # ==========================
    # Pattern Analysis
    # ==========================

    pattern = get_pattern_score(
        symbol,
        direction
    )

    # ==========================
    # BTC Regime
    # ==========================

    btc = get_btc_regime()

    # ==========================
    # Base Market Score
    # ==========================

    base_score = market_score(
        trend["score"],
        funding_rate,
        oi_change
    )

    # ==========================
    # Build Score Components
    # ==========================

    scores = {}

    # Base trend/funding/OI score
    scores["market"] = base_score

    # Pattern
    scores["pattern"] = pattern["score"] / 2

    # BTC Regime
    btc_bonus = 0

    if direction == "LONG":

        if btc["regime"] == "BULLISH":
            btc_bonus = 10

        elif btc["regime"] == "BEARISH":
            btc_bonus = -10

    else:

        if btc["regime"] == "BEARISH":
            btc_bonus = 10

        elif btc["regime"] == "BULLISH":
            btc_bonus = -10

    scores["btc"] = btc_bonus

    # Future components (reserved)

    scores["liquidity"] = 0
    scores["risk_reward"] = 0
    scores["entry"] = 0

    # ==========================
    # Decision Engine
    # ==========================

    decision = calculate_confidence(
        scores
    )

    confidence = decision["confidence"]

    # ==========================
    # Final Signal
    # ==========================

    trade["direction"] = direction

    trade["confidence"] = confidence

    trade["score_breakdown"] = decision["breakdown"]

    trade["pattern"] = pattern["pattern"]

    trade["trend_score"] = trend["score"]

    trade["15m"] = trend["15m"]
    trade["30m"] = trend["30m"]
    trade["1h"] = trend["1h"]
    trade["4h"] = trend["4h"]
    trade["1d"] = trend["1d"]

    trade["funding_rate"] = funding_rate
    trade["oi_change"] = oi_change

    trade["btc_regime"] = btc["regime"]
    trade["btc_score"] = btc["score"]

    return trade