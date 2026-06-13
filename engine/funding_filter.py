def analyze_funding(funding_data):

    results = []

    for row in funding_data:

        try:

            symbol = row["symbol"]

            funding = float(
                row["lastFundingRate"]
            )

            results.append({
                "symbol": symbol,
                "funding": funding
            })

        except:

            pass

    positive = sorted(
        results,
        key=lambda x: x["funding"],
        reverse=True
    )

    negative = sorted(
        results,
        key=lambda x: x["funding"]
    )

    return positive[:10], negative[:10]