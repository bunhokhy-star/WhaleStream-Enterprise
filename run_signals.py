from data.coingecko import get_market_data
from data.funding import get_funding_rate

from engine.whale_stream import analyze
from engine.signal_builder_v2 import build_signal_v2
from engine.telegram_formatter_v3 import format_signal
from engine.risk_manager import validate_trade

from telegram_sender import send_message
from backtest.logger import log_signal


print()
print("===================================")
print("WHALE STREAM SIGNAL CENTER")
print("===================================")
print()

coins = get_market_data()

longs, shorts = analyze(coins)

# ==================================
# TOP LONG SIGNALS
# ==================================

print("======================")
print("TOP LONG SIGNALS")
print("======================")
print()

for coin in longs:

    symbol = coin["symbol"] + "USDT"

    try:

        funding = get_funding_rate(symbol)

        signal = build_signal_v2(
            symbol,
            "LONG",
            funding_rate=funding,
            oi_change=0
        )

        risk = validate_trade(signal)

        if not risk["passed"]:

            print(
                "REJECTED:",
                symbol,
                risk["reasons"]
            )

            continue

        signal["risk_reward"] = risk["rr"]
        signal["sl_percent"] = risk["sl_percent"]

        log_signal(signal)

        message = format_signal(signal)

        print(message)

        send_message(message)

        print()
        print("Telegram Sent:", symbol)
        print()

    except Exception as e:

        print(
            "FAILED:",
            symbol,
            str(e)
        )

# ==================================
# TOP SHORT SIGNALS
# ==================================

print("======================")
print("TOP SHORT SIGNALS")
print("======================")
print()

for coin in shorts:

    symbol = coin["symbol"] + "USDT"

    try:

        funding = get_funding_rate(symbol)

        signal = build_signal_v2(
            symbol,
            "SHORT",
            funding_rate=funding,
            oi_change=0
        )

        risk = validate_trade(signal)

        if not risk["passed"]:

            print(
                "REJECTED:",
                symbol,
                risk["reasons"]
            )

            continue

        signal["risk_reward"] = risk["rr"]
        signal["sl_percent"] = risk["sl_percent"]

        log_signal(signal)

        message = format_signal(signal)

        print(message)

        send_message(message)

        print()
        print("Telegram Sent:", symbol)
        print()

    except Exception as e:

        print(
            "FAILED:",
            symbol,
            str(e)
        )