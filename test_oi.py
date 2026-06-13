from data.binance_futures import get_open_interest

symbols = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BEATUSDT",
    "WLDUSDT"
]

print("\nOPEN INTEREST TEST\n")

for symbol in symbols:

    try:

        data = get_open_interest(symbol)

        print(
            symbol,
            data["openInterest"]
        )

    except Exception as e:

        print(
            symbol,
            "ERROR"
        )