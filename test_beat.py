from data.binance_futures import (
    get_funding_rates,
    get_open_interest
)

print("\nBEAT CHECK\n")

funding_data = get_funding_rates()

for row in funding_data:

    if row["symbol"] == "BEATUSDT":

        print(
            "Funding:",
            row["lastFundingRate"]
        )

        break

oi = get_open_interest("BEATUSDT")

print(
    "Open Interest:",
    oi["openInterest"]
)