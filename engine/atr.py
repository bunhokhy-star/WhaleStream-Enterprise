from data.binance_klines import get_klines


def get_atr(symbol, interval="4h", period=14):

    candles = get_klines(
        symbol,
        interval,
        period + 1
    )

    trs = []

    for i in range(1, len(candles)):

        high = float(candles[i][2])
        low = float(candles[i][3])

        prev_close = float(
            candles[i - 1][4]
        )

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )

        trs.append(tr)

    atr = sum(trs) / len(trs)

    return atr