from data.binance_klines import get_klines


def get_structure(symbol, interval="4h"):

    candles = get_klines(
        symbol,
        interval,
        100
    )

    highs = []
    lows = []

    for candle in candles:

        highs.append(
            float(candle[2])
        )

        lows.append(
            float(candle[3])
        )

    resistance = max(
        highs[-50:]
    )

    support = min(
        lows[-50:]
    )

    return {
        "support": support,
        "resistance": resistance
    }