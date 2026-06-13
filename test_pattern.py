from engine.pattern_score import get_pattern_score

coins = [
    "BTCUSDT",
    "ETHUSDT",
    "CRVUSDT",
    "ATOMUSDT",
    "NEARUSDT"
]

for coin in coins:

    result = get_pattern_score(
        coin
    )

    print(
        coin,
        result
    )