def confidence_score(
    trend_score,
    funding_score,
    oi_score,
    volume_score
):

    score = 50

    score += trend_score * 8

    score += funding_score

    score += oi_score

    score += volume_score

    if score > 100:
        score = 100

    if score < 0:
        score = 0

    return round(score)