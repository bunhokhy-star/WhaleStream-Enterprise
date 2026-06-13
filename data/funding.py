from data.binance_futures import get_funding_rates


def get_funding_rate(symbol):

    funding_data = get_funding_rates()

    symbol = symbol.upper()

    for row in funding_data:

        if row["symbol"].upper() == symbol:

            return float(
                row["lastFundingRate"]
            )

    return 0.0