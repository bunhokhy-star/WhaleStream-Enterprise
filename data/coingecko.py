import requests

def get_market_data():

    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        "?vs_currency=usd"
        "&order=market_cap_desc"
        "&per_page=250"
        "&page=1"
        "&sparkline=false"
        "&price_change_percentage=24h,7d"
    )

    response = requests.get(url, timeout=30)

    response.raise_for_status()

    return response.json()