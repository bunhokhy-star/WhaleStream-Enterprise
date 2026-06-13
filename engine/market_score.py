def market_score(
    trend_score,
    funding_rate,
    oi_change
):

    # Trend becomes the foundation

    score = 50 + (trend_score * 8)

    # Funding

    if funding_rate < 0:
        score += 5

    elif funding_rate > 0.001:
        score -= 5

    # OI

    if oi_change > 2:
        score += 10

    elif oi_change > 0:
        score += 5

    elif oi_change < -2:
        score -= 10

    elif oi_change < 0:
        score -= 5

    # Clamp

    if score > 100:
        score = 100

    if score < 0:
        score = 0

    return round(score)