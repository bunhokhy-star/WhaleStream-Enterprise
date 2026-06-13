from __future__ import annotations

from dataclasses import dataclass
from typing import List

from recovery.models import ExchangeSnapshot, RecoveredOrder, RecoveredPosition, RecoveryState


@dataclass
class SyncResult:
    matched_positions: int
    missing_local_positions: List[RecoveredPosition]
    missing_exchange_positions: List[RecoveredPosition]
    matched_orders: int
    missing_local_orders: List[RecoveredOrder]
    missing_exchange_orders: List[RecoveredOrder]

    @property
    def is_clean(self) -> bool:
        return (
            not self.missing_local_positions
            and not self.missing_exchange_positions
            and not self.missing_local_orders
            and not self.missing_exchange_orders
        )


class ExchangeSync:
    def compare(self, local: RecoveryState, exchange: ExchangeSnapshot) -> SyncResult:
        local_pos = {p.key(): p for p in local.positions}
        ex_pos = {p.key(): p for p in exchange.positions}

        local_orders = {o.key(): o for o in local.orders}
        ex_orders = {o.key(): o for o in exchange.orders}

        matched_positions = len(set(local_pos.keys()) & set(ex_pos.keys()))
        matched_orders = len(set(local_orders.keys()) & set(ex_orders.keys()))

        missing_local_positions = [ex_pos[k] for k in ex_pos.keys() - local_pos.keys()]
        missing_exchange_positions = [local_pos[k] for k in local_pos.keys() - ex_pos.keys()]

        missing_local_orders = [ex_orders[k] for k in ex_orders.keys() - local_orders.keys()]
        missing_exchange_orders = [local_orders[k] for k in local_orders.keys() - ex_orders.keys()]

        return SyncResult(
            matched_positions=matched_positions,
            missing_local_positions=missing_local_positions,
            missing_exchange_positions=missing_exchange_positions,
            matched_orders=matched_orders,
            missing_local_orders=missing_local_orders,
            missing_exchange_orders=missing_exchange_orders,
        )
