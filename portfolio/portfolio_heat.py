from __future__ import annotations

from portfolio.portfolio import PortfolioSnapshot


def calculate_portfolio_heat(
    snapshot: PortfolioSnapshot,
    new_trade_risk_percent: float = 0.0
) -> float:
    return round(snapshot.total_risk_percent + float(new_trade_risk_percent), 6)
