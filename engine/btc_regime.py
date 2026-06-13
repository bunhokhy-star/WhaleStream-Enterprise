from engine.trend_matrix import trend_matrix


def get_btc_regime():

    trend = trend_matrix("BTCUSDT")

    score = 0

    weights = {
        "15m": 10,
        "30m": 10,
        "1h": 20,
        "4h": 30,
        "1d": 30
    }

    for tf, weight in weights.items():

        state = trend[tf]

        if state == "BULLISH":
            score += weight

        elif state == "BEARISH":
            score -= weight

    if score >= 40:
        regime = "BULLISH"

    elif score <= -40:
        regime = "BEARISH"

    else:
        regime = "NEUTRAL"

    return {

        "regime": regime,

        "score": score,

        "15m": trend["15m"],
        "30m": trend["30m"],
        "1h": trend["1h"],
        "4h": trend["4h"],
        "1d": trend["1d"]

    }