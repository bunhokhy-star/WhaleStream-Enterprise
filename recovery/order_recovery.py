from __future__ import annotations

from typing import List

from recovery.exchange_sync import SyncResult
from recovery.models import RecoveredOrder, RecoveryState


class OrderRecovery:
    def recover(self, state: RecoveryState, sync_result: SyncResult) -> List[RecoveredOrder]:
        recovered = []

        existing = {o.key(): o for o in state.orders}

        for order in sync_result.missing_local_orders:
            existing[order.key()] = order
            recovered.append(order)

        state.orders = list(existing.values())

        return recovered
