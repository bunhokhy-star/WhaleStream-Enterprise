from data.binance_futures import get_open_interest
from data.binance_oi_history import (
    load_history,
    save_history
)

symbols = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BEATUSDT",
    "WLDUSDT"
]

history = load_history()

print("\nOI CHANGE TEST\n")

for symbol in symbols:

    try:

        current = float(
            get_open_interest(symbol)["openInterest"]
        )

        previous = history.get(symbol)

        if previous:

            change = (
                (current - previous)
                / previous
            ) * 100

            print(
                symbol,
                "OI Change:",
                round(change, 2),
                "%"
            )

        else:

            print(
                symbol,
                "First Run"
            )

        history[symbol] = current

    except Exception as e:

        print(symbol, "ERROR")

save_history(history)