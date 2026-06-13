from engine.btc_regime import get_btc_regime

btc = get_btc_regime()

print()

print("BTC REGIME")

print("----------------")

for k, v in btc.items():

    print(k, "=", v)