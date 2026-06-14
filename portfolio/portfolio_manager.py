from __future__ import annotations

from typing import Dict, Any

from core.event_bus import Event, EventBus
from core.trade_ticket import TradeTicket
from portfolio.policy import PortfolioRiskPolicy
from portfolio.portfolio import PortfolioPosition, PortfolioSnapshot
from portfolio.risk_engine import PortfolioRiskEngine, PortfolioRiskResult


class PortfolioManager:
    def __init__(
        self,
        snapshot: PortfolioSnapshot,
        policy: PortfolioRiskPolicy = None,
        event_bus: EventBus = None,
    ) -> None:
        self.snapshot = snapshot
        self.policy = policy or PortfolioRiskPolicy()
        self.risk_engine = PortfolioRiskEngine(self.policy)
        self.event_bus = event_bus or EventBus()

    def validate_trade(self, ticket: TradeTicket) -> PortfolioRiskResult:
        result = self.risk_engine.validate(self.snapshot, ticket)

        self.event_bus.publish(
            Event(
                event_type="PortfolioRiskResult",
                trade_id=ticket.trade_id,
                component="PortfolioManager",
                level="INFO" if result.passed else "WARNING",
                message=result.reason,
                payload=result.to_dict(),
            )
        )

        return result

    def add_position_from_ticket(self, ticket: TradeTicket, notional: float) -> PortfolioPosition:
        position = PortfolioPosition(
            symbol=ticket.symbol,
            side=ticket.side,
            notional=float(notional),
            risk_percent=float(ticket.risk_percent),
            metadata={"trade_id": ticket.trade_id},
        )

        self.snapshot.positions.append(position)

        self.event_bus.publish(
            Event(
                event_type="PortfolioPositionAdded",
                trade_id=ticket.trade_id,
                component="PortfolioManager",
                message=f"Added portfolio exposure: {ticket.symbol}",
                payload=position.to_dict(),
            )
        )

        return position

    def report(self) -> Dict[str, Any]:
        return self.snapshot.to_dict()
