from core.context import KernelContext
from core.trade_ticket import TradeTicket
from core.validators.base import ValidationResult, Validator


class DuplicateValidator(Validator):
    name = "duplicate"

    def validate(self, ticket: TradeTicket, context: KernelContext) -> ValidationResult:
        return ValidationResult(True, "Duplicate check deferred", self.name)
