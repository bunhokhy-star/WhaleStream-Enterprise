from engine.atr import get_atr

atr = get_atr(
    "BTCUSDT",
    "4h"
)

print("ATR =", atr)