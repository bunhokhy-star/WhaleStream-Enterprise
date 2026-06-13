from engine.trade_builder import build_long_trade

trade = build_long_trade(
    "BTCUSDT"
)

print(trade)