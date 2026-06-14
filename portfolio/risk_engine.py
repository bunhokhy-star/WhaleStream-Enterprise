from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict

from core.trade_ticket import TradeTicket
from portfolio.policy import PortfolioRiskPolicy
from portfolio.portfolio import PortfolioSnapshot
from portfolio.portfolio_heat import calculate_portfolio_heat


@dataclass
class PortfolioRiskResult:
    passed: bool
    reason: str
    checks: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PortfolioRiskEngine:
    def __init__(self, policy: PortfolioRiskPolicy = None) -> None:
        self.policy = policy or PortfolioRiskPolicy()

    def validate(self, snapshot: PortfolioSnapshot, ticket: TradeTicket) -> PortfolioRiskResult:
        checks: Dict[str, Any] = {}

        new_trade_risk = float(ticket.risk_percent)
        checks["new_trade_risk_percent"] = new_trade_risk

        if new_trade_risk > self.policy.max_risk_per_trade_percent:
            return PortfolioRiskResult(
                False,
                f"Trade risk {new_trade_risk}% exceeds max {self.policy.max_risk_per_trade_percent}%",
                checks,
            )

        open_positions_after = snapshot.open_positions_count + 1
        checks["open_positions_after"] = open_positions_after

        if open_positions_after > self.policy.max_open_positions:
            return PortfolioRiskResult(
                False,
                f"Open positions {open_positions_after} exceeds max {self.policy.max_open_positions}",
                checks,
            )

        heat_after = calculate_portfolio_heat(snapshot, new_trade_risk)
        checks["portfolio_heat_after"] = heat_after

        if heat_after > self.policy.max_portfolio_heat_percent:
            return PortfolioRiskResult(
                False,
                f"Portfolio heat {heat_after}% exceeds max {self.policy.max_portfolio_heat_percent}%",
                checks,
            )

        daily_loss_percent = 0.0
        if snapshot.equity > 0 and snapshot.daily_realized_pnl < 0:
            daily_loss_percent = abs(snapshot.daily_realized_pnl) / snapshot.equity * 100

        checks["daily_loss_percent"] = round(daily_loss_percent, 6)

        if daily_loss_percent >= self.policy.max_daily_loss_percent:
            return PortfolioRiskResult(
                False,
                f"Daily loss {daily_loss_percent:.2f}% exceeds max {self.policy.max_daily_loss_percent}%",
                checks,
            )

        checks["consecutive_losses"] = snapshot.consecutive_losses

        if snapshot.consecutive_losses >= self.policy.max_consecutive_losses:
            return PortfolioRiskResult(
                False,
                f"Consecutive losses {snapshot.consecutive_losses} exceeds max {self.policy.max_consecutive_losses}",
                checks,
            )

        checks["duplicate_symbol"] = ticket.symbol in set(snapshot.symbols())

        if not self.policy.allow_duplicate_symbol and ticket.symbol in set(snapshot.symbols()):
            return PortfolioRiskResult(
                False,
                f"Duplicate symbol exposure blocked: {ticket.symbol}",
                checks,
            )

        available_pct = 0.0
        if snapshot.equity > 0:
            available_pct = snapshot.available_balance / snapshot.equity * 100

        checks["available_balance_percent"] = round(available_pct, 6)

        if available_pct < self.policy.min_available_balance_percent:
            return PortfolioRiskResult(
                False,
                f"Available balance {available_pct:.2f}% below minimum {self.policy.min_available_balance_percent}%",
                checks,
            )

        return PortfolioRiskResult(True, "Portfolio risk accepted", checks)
