from data.binance_klines import get_klines


def build_short_trade(symbol):

    candles = get_klines(
        symbol,
        "1h",
        30
    )

    highs = [
        float(c[2])
        for c in candles[-10:]
    ]

    resistance = max(highs)

    entry_high = round(
        resistance * 0.998,
        4
    )

    entry_low = round(
        resistance * 0.992,
        4
    )

    entry = (
        entry_high + entry_low
    ) / 2

    stop_loss = round(
        entry * 1.035,
        4
    )

    risk = stop_loss - entry

    tp1 = round(
        entry - risk,
        4
    )

    tp2 = round(
        entry - risk * 2,
        4
    )

    tp3 = round(
        entry - risk * 3,
        4
    )

    tp4 = round(
        entry - risk * 4,
        4
    )

    price = float(
        candles[-1][4]
    )

    return {
        "symbol": symbol,
        "price": price,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "tp4": tp4
    }