from data.coingecko import get_market_data
from engine.whale_stream import analyze

coins = get_market_data()

longs, shorts = analyze(coins)

print("\n======================")
print("WHALE STREAM SCANNER")
print("======================\n")

print("TOP 3 LONG\n")

for coin in longs:
    print(
        coin["symbol"],
        "| Score:", coin["score"],
        "| MCAP:", round(coin["market_cap"] / 1_000_000, 2), "M",
        "| Vol/MCap:", coin["volume_mcap"],
        "| 24h:", str(coin["change24"]) + "%",
        "| 7d:", str(coin["change7"]) + "%"
    )

print("\nTOP 3 SHORT\n")

for coin in shorts:
    print(
        coin["symbol"],
        "| Score:", coin["score"],
        "| MCAP:", round(coin["market_cap"] / 1_000_000, 2), "M",
        "| Vol/MCap:", coin["volume_mcap"],
        "| 24h:", str(coin["change24"]) + "%",
        "| 7d:", str(coin["change7"]) + "%"
    )

print("\nCEO VERDICT:")

if len(longs) > 0:
    print("GO")
else:
    print("STAY OUT")