from __future__ import annotations


class CapitalAllocator:
    def __init__(self, default_risk_percent: float = 0.5) -> None:
        self.default_risk_percent = default_risk_percent

    def calculate_risk_amount(self, equity: float, risk_percent: float = None) -> float:
        pct = self.default_risk_percent if risk_percent is None else risk_percent
        return round(float(equity) * (float(pct) / 100), 8)

    def calculate_position_qty(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
        risk_percent: float = None,
    ) -> float:
        risk_amount = self.calculate_risk_amount(equity, risk_percent)
        risk_per_unit = abs(float(entry_price) - float(stop_loss))

        if risk_per_unit <= 0:
            raise ValueError("Risk per unit must be greater than zero")

        return round(risk_amount / risk_per_unit, 8)
