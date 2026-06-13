from engine.confidence_score import confidence_score

score = confidence_score(
    trend_score=4,
    funding_score=10,
    oi_score=8,
    volume_score=6
)

print(score)