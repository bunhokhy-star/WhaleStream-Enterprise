def calculate_quantity_from_risk(account_equity, risk_percent, entry_price, stop_loss):
    risk_amount = account_equity * (risk_percent / 100)
    stop_distance = abs(entry_price - stop_loss)

    if stop_distance <= 0:
        return 0

    return risk_amount / stop_distance
