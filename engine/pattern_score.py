from data.binance_klines import get_klines


def get_pattern_score(symbol, direction):

    candles = get_klines(
        symbol,
        "4h",
        20
    )

    highs = [
        float(c[2])
        for c in candles
    ]

    lows = [
        float(c[3])
        for c in candles
    ]

    recent_high = max(
        highs[-5:]
    )

    previous_high = max(
        highs[-10:-5]
    )

    recent_low = min(
        lows[-5:]
    )

    previous_low = min(
        lows[-10:-5]
    )

    score = 0

    pattern = "NEUTRAL"

    # ======================
    # LONG PATTERNS
    # ======================

    if direction == "LONG":

        if recent_high > previous_high:
            score += 10

        if recent_low > previous_low:
            score += 10

        if score >= 20:
            pattern = "BULLISH_BREAKOUT"

        elif score == 10:
            pattern = "HIGHER_LOW"

        else:
            pattern = "NEUTRAL"

    # ======================
    # SHORT PATTERNS
    # ======================

    else:

        if recent_high < previous_high:
            score += 10

        if recent_low < previous_low:
            score += 10

        if score >= 20:
            pattern = "BEARISH_BREAKDOWN"

        elif score == 10:
            pattern = "LOWER_HIGH"

        else:
            pattern = "NEUTRAL"

    return {
        "pattern": pattern,
        "score": score
    }