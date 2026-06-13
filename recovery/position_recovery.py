from __future__ import annotations

from typing import List

from recovery.exchange_sync import SyncResult
from recovery.models import RecoveredPosition, RecoveryState


class PositionRecovery:
    def recover(self, state: RecoveryState, sync_result: SyncResult) -> List[RecoveredPosition]:
        recovered = []

        existing = {p.key(): p for p in state.positions}

        for position in sync_result.missing_local_positions:
            existing[position.key()] = position
            recovered.append(position)

        state.positions = list(existing.values())

        return recovered
