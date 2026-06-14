from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PortfolioRiskPolicy:
    max_open_positions: int = 5
    max_portfolio_heat_percent: float = 5.0
    max_risk_per_trade_percent: float = 1.0
    max_daily_loss_percent: float = 3.0
    max_consecutive_losses: int = 3
    allow_duplicate_symbol: bool = False
    min_available_balance_percent: float = 10.0
