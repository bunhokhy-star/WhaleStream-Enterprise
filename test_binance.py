from data.binance_futures import (
    get_funding_rates
)

print("\nBINANCE FUNDING TEST\n")

data = get_funding_rates()

for row in data[:10]:

    print(
        row["symbol"],
        "Funding:",
        row["lastFundingRate"]
    )