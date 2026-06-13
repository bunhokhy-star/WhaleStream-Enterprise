from core.context import KernelContext
from core.trade_ticket import TradeTicket
from core.validators.base import ValidationResult, Validator


class WalletValidator(Validator):
    name = "wallet"

    def validate(self, ticket: TradeTicket, context: KernelContext) -> ValidationResult:
        return ValidationResult(True, "Wallet check deferred", self.name)
