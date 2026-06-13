from __future__ import annotations

from typing import Dict, List

from core.breakeven import BreakEvenManager
from core.event_bus import Event, EventBus
from core.partial_take_profit import PartialCloseEvent, PartialTakeProfitManager
from core.position import Position, PositionStatus
from core.trailing_stop import TrailingStopManager


class PositionManager:
    def __init__(
        self,
        event_bus: EventBus = None,
        breakeven: BreakEvenManager = None,
        trailing: TrailingStopManager = None,
        partial_tp: PartialTakeProfitManager = None,
    ) -> None:
        self.positions: Dict[str, Position] = {}
        self.event_bus = event_bus or EventBus()
        self.breakeven = breakeven or BreakEvenManager()
        self.trailing = trailing or TrailingStopManager()
        self.partial_tp = partial_tp or PartialTakeProfitManager()

    def add_position(self, position: Position) -> Position:
        position.status = PositionStatus.OPEN
        self.positions[position.trade_id] = position
        self.event_bus.publish(
            Event(
                event_type="PositionOpened",
                trade_id=position.trade_id,
                component="PositionManager",
                message=f"Position opened: {position.symbol}",
                payload=position.to_dict(),
            )
        )
        return position

    def get_position(self, trade_id: str) -> Position:
        return self.positions[trade_id]

    def update_price(self, trade_id: str, current_price: float) -> Position:
        position = self.get_position(trade_id)
        position.current_price = current_price

        partial_events = self.partial_tp.apply(position, current_price)
        for event in partial_events:
            self._publish_partial(position, event)

        if position.status != PositionStatus.CLOSED:
            if self.breakeven.apply(position, current_price):
                self.event_bus.publish(
                    Event(
                        event_type="StopMovedToBreakeven",
                        trade_id=position.trade_id,
                        component="PositionManager",
                        message=f"Stop moved to breakeven: {position.stop_loss}",
                        payload=position.to_dict(),
                    )
                )

            if self.trailing.apply(position, current_price):
                self.event_bus.publish(
                    Event(
                        event_type="TrailingStopUpdated",
                        trade_id=position.trade_id,
                        component="PositionManager",
                        message=f"Trailing stop updated: {position.stop_loss}",
                        payload=position.to_dict(),
                    )
                )

        if position.status == PositionStatus.CLOSED:
            self.event_bus.publish(
                Event(
                    event_type="PositionClosed",
                    trade_id=position.trade_id,
                    component="PositionManager",
                    message="Position fully closed by targets",
                    payload=position.to_dict(),
                )
            )

        return position

    def _publish_partial(self, position: Position, event: PartialCloseEvent) -> None:
        self.event_bus.publish(
            Event(
                event_type="PartialTakeProfit",
                trade_id=position.trade_id,
                component="PositionManager",
                message=f"TP{event.target_index + 1} partial close",
                payload={
                    "position": position.to_dict(),
                    "partial_close": event.__dict__,
                },
            )
        )
