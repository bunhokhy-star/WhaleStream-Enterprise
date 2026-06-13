from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from recovery.models import RecoveryState


class StateLoader:
    def __init__(self, path: str = "history/recovery_state.json") -> None:
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> RecoveryState:
        if not self.path.exists():
            return RecoveryState(metadata={"state_found": False})

        data = json.loads(self.path.read_text(encoding="utf-8"))
        state = RecoveryState.from_dict(data)
        state.metadata["state_found"] = True
        return state
