from config_strategy import *


def validate_trade(signal):

    reasons = []

    passed = True

    # ==========================
    # Entry Price
    # ==========================

    entry = (
        signal["entry_low"] +
        signal["entry_high"]
    ) / 2

    sl = signal["stop_loss"]

    direction = signal["direction"]

    # ==========================
    # Stop Loss %
    # ==========================

    if direction == "LONG":

        sl_percent = (
            (entry - sl) / entry
        ) * 100

    else:

        sl_percent = (
            (sl - entry) / entry
        ) * 100

    if sl_percent < MIN_SL_PERCENT:

        passed = False

        reasons.append(
            f"SL < {MIN_SL_PERCENT}%"
        )

    if sl_percent > MAX_SL_PERCENT:

        passed = False

        reasons.append(
            f"SL > {MAX_SL_PERCENT}%"
        )

    # ==========================
    # Risk Reward
    # ==========================

    tp4 = signal["tp4"]

    if direction == "LONG":

        reward = tp4 - entry
        risk = entry - sl

    else:

        reward = entry - tp4
        risk = sl - entry

    rr = reward / risk if risk > 0 else 0

    if rr < MIN_RR:

        passed = False

        reasons.append(
            f"RR < {MIN_RR}"
        )

    # ==========================
    # Confidence
    # ==========================

    if signal["confidence"] < MIN_CONFIDENCE:

        passed = False

        reasons.append(
            f"Confidence < {MIN_CONFIDENCE}"
        )

    # ==========================
    # Entry Distance
    # ==========================

    distance = 0

    if "price" in signal:

        distance = abs(
            signal["price"] - entry
        ) / entry * 100

        if distance > MAX_ENTRY_DISTANCE:

            print()
            print("========== ENTRY DISTANCE ==========")
            print("Symbol   :", signal["symbol"])
            print("Direction:", direction)
            print("Price    :", signal["price"])
            print("Entry    :", round(entry, 6))
            print("Distance :", round(distance, 2), "%")
            print("Allowed  :", MAX_ENTRY_DISTANCE, "%")
            print("====================================")
            print()

            passed = False

            reasons.append(
                f"Entry Distance > {MAX_ENTRY_DISTANCE}%"
            )

    # ==========================
    # Result
    # ==========================

    return {

        "passed": passed,

        "rr": round(rr, 2),

        "sl_percent": round(
            sl_percent,
            2
        ),

        "entry_distance": round(
            distance,
            2
        ),

        "reasons": reasons

    }