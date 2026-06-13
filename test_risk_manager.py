from engine.signal_builder_v2 import build_signal_v2

from engine.risk_manager import validate_trade

signal = build_signal_v2(

    "BTCUSDT",

    "LONG",

    funding_rate=0,

    oi_change=0

)

result = validate_trade(
    signal
)

print()

print(result)