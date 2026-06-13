from engine.trade_builder import build_long_trade
from engine.trend_matrix import trend_matrix


def build_signal(symbol):

    trade = build_long_trade(symbol)

    matrix = trend_matrix(symbol)

    confidence = 40

    # Trend Contribution

    confidence += matrix["score"] * 12

    # Structure Bonus

    if trade["tp4"] > trade["entry_high"]:
        confidence += 10

    # Risk Reward

    reward = (
        trade["tp4"]
        - trade["entry_high"]
    )

    risk = (
        trade["entry_high"]
        - trade["stop_loss"]
    )

    if risk > 0:

        rr = reward / risk

        if rr >= 4:
            confidence += 20

        elif rr >= 3:
            confidence += 15

        elif rr >= 2:
            confidence += 10

    if confidence > 100:
        confidence = 100

    if confidence < 0:
        confidence = 0

    return {
        "symbol": trade["symbol"],
        "confidence": round(confidence),
        "entry_low": trade["entry_low"],
        "entry_high": trade["entry_high"],
        "stop_loss": trade["stop_loss"],
        "tp1": trade["tp1"],
        "tp2": trade["tp2"],
        "tp3": trade["tp3"],
        "tp4": trade["tp4"],
        "trend_score": matrix["score"],
        "15m": matrix["15m"],
        "30m": matrix["30m"],
        "1h": matrix["1h"],
        "4h": matrix["4h"],
        "1d": matrix["1d"]
    }