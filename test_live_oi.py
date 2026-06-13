from data.oi import get_oi

coins = [

    "BTCUSDT",
    "ETHUSDT",
    "ATOMUSDT",
    "TONUSDT",
    "INJUSDT",
    "AVAXUSDT"

]

for coin in coins:

    oi = get_oi(
        coin
    )

    print(
        coin,
        oi
    )