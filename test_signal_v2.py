from engine.signal_builder_v2 import build_signal_v2

coins = [
    "BTCUSDT",
    "CRVUSDT",
    "NEARUSDT"
]

for coin in coins:

    signal = build_signal_v2(
        coin,
        funding_rate=-0.0002,
        oi_change=1.5
    )

    print(
        "\n",
        coin,
        signal["confidence"],
        signal["pattern"]
    )