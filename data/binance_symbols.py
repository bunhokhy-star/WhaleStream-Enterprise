import requests


def get_binance_symbols():

    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"

    data = requests.get(
        url,
        timeout=10
    ).json()

    symbols = set()

    for item in data["symbols"]:

        if (
            item["status"] == "TRADING"
            and item["contractType"] == "PERPETUAL"
        ):

            symbols.add(
                item["symbol"]
            )

    return symbols