import requests

def get_funding_rates():

    url = "https://fapi.binance.com/fapi/v1/premiumIndex"

    response = requests.get(url, timeout=30)

    response.raise_for_status()

    return response.json()


def get_open_interest(symbol):

    url = (
        "https://fapi.binance.com/fapi/v1/openInterest"
        f"?symbol={symbol}"
    )

    response = requests.get(url, timeout=30)

    response.raise_for_status()

    return response.json()