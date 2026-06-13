import requests


def get_klines(symbol, interval="1h", limit=200):

    url = (
        "https://fapi.binance.com/fapi/v1/klines"
    )

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json()