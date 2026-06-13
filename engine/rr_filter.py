def valid_rr(
    entry,
    stop_loss,
    target
):

    risk = (
        entry - stop_loss
    )

    reward = (
        target - entry
    )

    if risk <= 0:
        return False

    rr = reward / risk

    return rr >= 2