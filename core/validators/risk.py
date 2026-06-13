from core.context import KernelContext
from core.trade_ticket import TradeTicket
from core.validators.base import ValidationResult, Validator


class RiskRewardValidator(Validator):
    name = "risk_reward"

    def validate(self, ticket: TradeTicket, context: KernelContext) -> ValidationResult:
        if not ticket.targets:
            return ValidationResult(False, "No targets available", self.name)

        entry = ticket.entry_mid
        final_target = float(ticket.targets[-1])
        sl = float(ticket.stop_loss)

        if ticket.direction == "LONG":
            risk = entry - sl
            reward = final_target - entry
        else:
            risk = sl - entry
            reward = entry - final_target

        if risk <= 0:
            return ValidationResult(False, "Invalid risk distance", self.name)

        rr = reward / risk

        if rr < context.min_rr:
            return ValidationResult(False, f"RR {rr:.2f} < minimum {context.min_rr}", self.name)

        return ValidationResult(True, f"RR accepted: {rr:.2f}", self.name)
