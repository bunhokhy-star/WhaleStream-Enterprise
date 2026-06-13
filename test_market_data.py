from data.market_data import MarketData

market = MarketData()

coins = market.load_coins()

market.load_funding()

symbols = []

for coin in coins[:10]:

    symbols.append(
        coin["symbol"].upper() + "USDT"
    )

market.load_oi(symbols)

print()

for symbol in symbols:

    print(
        symbol,
        market.funding_rate(symbol),
        market.open_interest(symbol)
    )