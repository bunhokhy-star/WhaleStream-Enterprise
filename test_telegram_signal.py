from engine.signal_builder_v2 import build_signal_v2
from engine.telegram_formatter_v3 import format_signal

signal = build_signal_v2(
    "CRVUSDT",
    funding_rate=-0.0002,
    oi_change=1.5
)

print(
    format_signal(signal)
)