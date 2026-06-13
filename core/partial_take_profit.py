from __future__ import annotations

from dataclasses import dataclass
from typing import List

from core.position import Position, PositionStatus


@dataclass
class PartialCloseEvent:
    target_index: int
    target_price: float
    closed_qty: float
    remaining_qty: float


class PartialTakeProfitManager:
    def __init__(self, close_percentages: List[float] = None) -> None:
        self.close_percentages = close_percentages or [25, 25, 25, 25]

    def reached_targets(self, position: Position, current_price: float) -> List[int]:
        reached = []
        already_closed = set(position.metadata.get("closed_target_indexes", []))

        for i, target in enumerate(position.targets):
            if i in already_closed:
                continue

            if position.direction == "LONG" and current_price >= target:
                reached.append(i)

            if position.direction == "SHORT" and current_price <= target:
                reached.append(i)

        return reached

    def apply(self, position: Position, current_price: float) -> List[PartialCloseEvent]:
        events = []
        closed_indexes = position.metadata.setdefault("closed_target_indexes", [])

        for idx in self.reached_targets(position, current_price):
            if position.remaining_qty <= 0:
                break

            percent = self.close_percentages[min(idx, len(self.close_percentages) - 1)]
            close_qty = round(position.qty * (percent / 100), 8)

            if close_qty > position.remaining_qty:
                close_qty = position.remaining_qty

            position.remaining_qty = round(position.remaining_qty - close_qty, 8)
            closed_indexes.append(idx)

            event = PartialCloseEvent(
                target_index=idx,
                target_price=position.targets[idx],
                closed_qty=close_qty,
                remaining_qty=position.remaining_qty,
            )
            events.append(event)

            if position.remaining_qty <= 0:
                position.status = PositionStatus.CLOSED
            else:
                position.status = PositionStatus.PARTIAL

        return events
