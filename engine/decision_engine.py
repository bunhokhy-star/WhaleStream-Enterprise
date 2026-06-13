from config_strategy import MAX_CONFIDENCE


def calculate_confidence(scores):

    total = 0

    breakdown = {}

    for name, value in scores.items():

        total += value

        breakdown[name] = round(value, 2)

    # ==========================
    # Confidence Limits
    # ==========================

    if total > MAX_CONFIDENCE:

        total = MAX_CONFIDENCE

    if total < 0:

        total = 0

    # ==========================
    # Result
    # ==========================

    return {

        "confidence": round(total),

        "breakdown": breakdown

    }