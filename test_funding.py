from data.binance_futures import (
    get_funding_rates
)

from engine.funding_filter import (
    analyze_funding
)

funding_data = get_funding_rates()

positive, negative = analyze_funding(
    funding_data
)

print("\nTOP POSITIVE FUNDING\n")

for row in positive:

    print(
        row["symbol"],
        row["funding"]
    )

print("\nTOP NEGATIVE FUNDING\n")

for row in negative:

    print(
        row["symbol"],
        row["funding"]
    )