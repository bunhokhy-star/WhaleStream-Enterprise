from __future__ import annotations

from core.position import Position


class TrailingStopManager:
    def __init__(self, trail_percent: float = 1.25, activation_target_index: int = 1) -> None:
        self.trail_percent = trail_percent
        self.activation_target_index = activation_target_index

    def is_active(self, position: Position, current_price: float) -> bool:
        if len(position.targets) <= self.activation_target_index:
            return False

        activation_price = position.targets[self.activation_target_index]

        if position.direction == "LONG":
            return current_price >= activation_price

        return current_price <= activation_price

    def calculate_stop(self, position: Position, current_price: float) -> float:
        trail_value = current_price * (self.trail_percent / 100)

        if position.direction == "LONG":
            return round(current_price - trail_value, 8)

        return round(current_price + trail_value, 8)

    def apply(self, position: Position, current_price: float) -> bool:
        if not self.is_active(position, current_price):
            return False

        proposed_stop = self.calculate_stop(position, current_price)

        if position.direction == "LONG" and proposed_stop > position.stop_loss:
            position.stop_loss = proposed_stop
            position.metadata["trailing_stop_active"] = True
            return True

        if position.direction == "SHORT" and proposed_stop < position.stop_loss:
            position.stop_loss = proposed_stop
            position.metadata["trailing_stop_active"] = True
            return True

        return False
