from __future__ import annotations

import json
from pathlib import Path

from recovery.models import RecoveryReport


class RecoveryReportWriter:
    def __init__(self, path: str = "history/recovery_report.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, report: RecoveryReport) -> str:
        self.path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return str(self.path)
