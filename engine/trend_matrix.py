from engine.trend_score import get_trend


def trend_matrix(symbol):

    timeframes = [
        "15m",
        "30m",
        "1h",
        "4h",
        "1d"
    ]

    score = 0

    results = {}

    for tf in timeframes:

        trend = get_trend(
            symbol,
            tf
        )

        results[tf] = trend

        if trend == "BULLISH":
            score += 1

        elif trend == "BEARISH":
            score -= 1

    results["score"] = score

    return results


def bullish(symbol):

    result = trend_matrix(symbol)

    return result["score"] >= 2


def bearish(symbol):

    result = trend_matrix(symbol)

    return result["score"] <= -2