from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.approval import ApprovalDecision, ApprovalEngine
from core.context import KernelContext
from core.event_bus import Event, EventBus
from core.state_machine import TradeState, TradeStateMachine
from core.trade_ticket import TradeTicket
from core.validators.base import ValidationResult, Validator
from core.validators.confidence import ConfidenceValidator
from core.validators.duplicate import DuplicateValidator
from core.validators.market import MarketValidator
from core.validators.risk import RiskRewardValidator
from core.validators.wallet import WalletValidator


class TradingKernel:
    def __init__(
        self,
        context: Optional[KernelContext] = None,
        validators: Optional[List[Validator]] = None,
        approval_engine: Optional[ApprovalEngine] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.context = context or KernelContext.demo_default()
        self.validators = validators or [
            MarketValidator(),
            ConfidenceValidator(),
            RiskRewardValidator(),
            DuplicateValidator(),
            WalletValidator(),
        ]
        self.approval_engine = approval_engine or ApprovalEngine(interactive=True)
        self.event_bus = event_bus or EventBus()

    def create_ticket(self, signal: Dict[str, Any]) -> TradeTicket:
        ticket = TradeTicket.from_signal(signal, risk_percent=self.context.risk_per_trade)
        self.event_bus.publish(
            Event(
                event_type="TradeTicketCreated",
                trade_id=ticket.trade_id,
                component="TradingKernel",
                message=f"Created ticket for {ticket.symbol}",
                payload=ticket.to_dict(),
            )
        )
        return ticket

    def validate_ticket(self, ticket: TradeTicket) -> List[ValidationResult]:
        results = []

        for validator in self.validators:
            result = validator.validate(ticket, self.context)
            results.append(result)

            self.event_bus.publish(
                Event(
                    event_type="ValidationResult",
                    trade_id=ticket.trade_id,
                    component=validator.name,
                    level="INFO" if result.passed else "WARNING",
                    message=result.reason,
                    payload={"passed": result.passed, "validator": result.validator},
                )
            )

            if not result.passed:
                break

        return results

    def process_signal(self, signal: Dict[str, Any]) -> TradeTicket:
        ticket = self.create_ticket(signal)
        state = TradeStateMachine(ticket.status)

        validation_results = self.validate_ticket(ticket)
        failed = [r for r in validation_results if not r.passed]

        if failed:
            ticket.status = state.transition(TradeState.REJECTED)
            ticket.metadata["validation"] = [r.__dict__ for r in validation_results]
            self.event_bus.publish(
                Event(
                    event_type="TradeRejected",
                    trade_id=ticket.trade_id,
                    component="TradingKernel",
                    level="WARNING",
                    message=failed[0].reason,
                    payload=ticket.to_dict(),
                )
            )
            return ticket

        ticket.status = state.transition(TradeState.VALIDATED)
        ticket.metadata["validation"] = [r.__dict__ for r in validation_results]

        self.event_bus.publish(
            Event(
                event_type="TradeValidated",
                trade_id=ticket.trade_id,
                component="TradingKernel",
                message="Trade ticket validated",
                payload=ticket.to_dict(),
            )
        )

        decision = self.approval_engine.request_approval(ticket)
        ticket.metadata["approval_decision"] = decision

        if decision == ApprovalDecision.APPROVED:
            ticket.status = state.transition(TradeState.APPROVED)
            self.event_bus.publish(
                Event(
                    event_type="TradeApproved",
                    trade_id=ticket.trade_id,
                    component="TradingKernel",
                    message="Trade ticket approved",
                    payload=ticket.to_dict(),
                )
            )
        else:
            ticket.status = state.transition(TradeState.REJECTED)
            self.event_bus.publish(
                Event(
                    event_type="TradeRejected",
                    trade_id=ticket.trade_id,
                    component="ApprovalEngine",
                    level="WARNING",
                    message=f"Trade not approved: {decision}",
                    payload=ticket.to_dict(),
                )
            )

        return ticket
