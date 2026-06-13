from engine.trend_score import get_trend

symbol = "BTCUSDT"

for tf in [
    "15m",
    "30m",
    "1h",
    "4h",
    "1d"
]:

    trend = get_trend(
        symbol,
        tf
    )

    print(
        tf,
        trend
    )