from engine.retest_entry import get_retest_zone
from data.binance_klines import get_klines


def build_long_trade(symbol):

    zone = get_retest_zone(symbol)

    candles = get_klines(
        symbol,
        "1h",
        5
    )

    current_price = float(
        candles[-1][4]
    )

    entry_low = zone["entry_low"]
    entry_high = zone["entry_high"]

    entry = (
        entry_low + entry_high
    ) / 2

    # Fixed 3.5% stop for 10x model

    stop_loss = round(
        entry * 0.965,
        4
    )

    risk = (
        entry - stop_loss
    )

    tp1 = round(
        entry + risk,
        4
    )

    tp2 = round(
        entry + risk * 2,
        4
    )

    tp3 = round(
        entry + risk * 3,
        4
    )

    tp4 = round(
        entry + risk * 4,
        4
    )

    return {
        "symbol": symbol,
        "price": current_price,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "tp4": tp4
    }