from core.context import KernelContext
from core.trade_ticket import TradeTicket
from core.validators.base import ValidationResult, Validator


class MarketValidator(Validator):
    name = "market"

    def validate(self, ticket: TradeTicket, context: KernelContext) -> ValidationResult:
        if not ticket.symbol.endswith("USDT"):
            return ValidationResult(False, "Only USDT linear symbols are supported", self.name)
        return ValidationResult(True, "Market accepted", self.name)
