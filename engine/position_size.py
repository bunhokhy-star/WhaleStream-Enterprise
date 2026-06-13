def calculate_position_size(
    account_size,
    risk_percent,
    entry,
    stop_loss
):

    risk_amount = account_size * (
        risk_percent / 100
    )

    stop_distance = abs(
        entry - stop_loss
    )

    position = (
        risk_amount /
        stop_distance
    )

    return {

        "risk_amount": round(
            risk_amount,
            2
        ),

        "position_size": round(
            position,
            2
        )

    }