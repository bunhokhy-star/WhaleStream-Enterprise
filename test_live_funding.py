from data.funding import get_funding_rate

coins = [

    "BTCUSDT",
    "ETHUSDT",
    "ATOMUSDT",
    "CRVUSDT",
    "RENDERUSDT",
    "TONUSDT"

]

for coin in coins:

    funding = get_funding_rate(
        coin
    )

    print(
        coin,
        funding
    )