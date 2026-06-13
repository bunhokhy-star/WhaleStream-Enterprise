from data.binance_symbols import get_binance_symbols

symbols = get_binance_symbols()

print()

print("TOTAL SYMBOLS:", len(symbols))

print()

for s in sorted(list(symbols))[:30]:

    print(s)