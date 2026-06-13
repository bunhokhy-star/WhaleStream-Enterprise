from data.binance_klines import get_klines


def get_retest_zone(symbol):

    candles = get_klines(
        symbol,
        "1h",
        30
    )

    lows = []

    highs = []

    for candle in candles[-10:]:

        highs.append(
            float(candle[2])
        )

        lows.append(
            float(candle[3])
        )

    support = min(lows)

    resistance = max(highs)

    return {
        "entry_low": round(
            support * 1.002,
            4
        ),
        "entry_high": round(
            support * 1.008,
            4
        ),
        "resistance": round(
            resistance,
            4
        )
    }