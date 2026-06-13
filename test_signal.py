from engine.signal_builder import build_signal

signal = build_signal(
    "BTCUSDT"
)

for k, v in signal.items():
    print(k, "=", v)