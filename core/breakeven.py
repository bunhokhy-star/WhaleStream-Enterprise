from __future__ import annotations

from core.position import Position


class BreakEvenManager:
    def __init__(self, buffer_percent: float = 0.05) -> None:
        self.buffer_percent = buffer_percent

    def breakeven_price(self, position: Position) -> float:
        buffer_value = position.entry_price * (self.buffer_percent / 100)

        if position.direction == "LONG":
            return round(position.entry_price + buffer_value, 8)

        return round(position.entry_price - buffer_value, 8)

    def should_move_to_breakeven(self, position: Position, current_price: float) -> bool:
        if not position.targets:
            return False

        tp1 = position.targets[0]

        if position.direction == "LONG":
            return current_price >= tp1 and position.stop_loss < position.entry_price

        return current_price <= tp1 and position.stop_loss > position.entry_price

    def apply(self, position: Position, current_price: float) -> bool:
        if not self.should_move_to_breakeven(position, current_price):
            return False

        position.stop_loss = self.breakeven_price(position)
        position.metadata["breakeven_applied"] = True
        position.metadata["breakeven_price"] = position.stop_loss
        return True
