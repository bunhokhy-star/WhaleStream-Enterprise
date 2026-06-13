from __future__ import annotations

import json
from pathlib import Path

from recovery.models import RecoveryState


class StateSaver:
    def __init__(self, path: str = "history/recovery_state.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state: RecoveryState) -> str:
        self.path.write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return str(self.path)
