from data.binance_klines import get_klines

data = get_klines(
    "BTCUSDT",
    "1h",
    5
)

print(data)