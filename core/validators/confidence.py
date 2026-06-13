from core.context import KernelContext
from core.trade_ticket import TradeTicket
from core.validators.base import ValidationResult, Validator


class ConfidenceValidator(Validator):
    name = "confidence"

    def validate(self, ticket: TradeTicket, context: KernelContext) -> ValidationResult:
        if ticket.confidence < context.min_confidence:
            return ValidationResult(False, f"Confidence {ticket.confidence} < minimum {context.min_confidence}", self.name)
        return ValidationResult(True, "Confidence accepted", self.name)
