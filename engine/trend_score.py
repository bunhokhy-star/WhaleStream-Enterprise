from data.binance_klines import get_klines


def get_trend(symbol, interval):

    candles = get_klines(
        symbol,
        interval,
        50
    )

    closes = []

    for candle in candles:

        closes.append(
            float(candle[4])
        )

    latest = closes[-1]

    sma20 = sum(
        closes[-20:]
    ) / 20

    sma50 = sum(
        closes[-50:]
    ) / 50

    if latest > sma20 > sma50:

        return "BULLISH"

    if latest < sma20 < sma50:

        return "BEARISH"

    return "NEUTRAL"