from __future__ import annotations

from dataclasses import dataclass

from core.context import KernelContext
from core.trade_ticket import TradeTicket


@dataclass
class ValidationResult:
    passed: bool
    reason: str
    validator: str = "unknown"


class Validator:
    name = "base"

    def validate(self, ticket: TradeTicket, context: KernelContext) -> ValidationResult:
        raise NotImplementedError
