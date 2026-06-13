from data.binance_futures import (
    get_funding_rates,
    get_open_interest
)

WATCHLIST_FILE = "watchlist.txt"


def load_watchlist():

    symbols = []

    with open(WATCHLIST_FILE, "r") as f:

        for line in f:

            symbol = line.strip().upper()

            if symbol:
                symbols.append(symbol)

    return symbols


def get_funding_map():

    funding_data = get_funding_rates()

    funding_map = {}

    for row in funding_data:

        try:

            funding_map[row["symbol"]] = float(
                row["lastFundingRate"]
            )

        except:
            pass

    return funding_map


def get_status(funding):

    if funding > 0.003:
        return "STRONG SHORT WATCH"

    if funding > 0.001:
        return "SHORT WATCH"

    if funding < -0.001:
        return "LONG WATCH"

    return "NEUTRAL"


print("\n===================================")
print("WHALE WATCHLIST V2")
print("===================================\n")

symbols = load_watchlist()

funding_map = get_funding_map()

for symbol in symbols:

    try:

        funding = funding_map.get(symbol, 0)

        oi = get_open_interest(symbol)

        print(
            symbol,
            "\nFunding:", round(funding, 6),
            "\nOI:", oi["openInterest"],
            "\nSignal:", get_status(funding),
            "\n"
        )

    except Exception as e:

        print(symbol, "ERROR")