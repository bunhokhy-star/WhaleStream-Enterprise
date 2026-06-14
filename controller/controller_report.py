from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ControllerReport:
    started_at: str = field(default_factory=utc_now_iso)
    completed_at: str = ""
    status: str = "CREATED"
    cycles_completed: int = 0
    heartbeats: int = 0
    services_registered: int = 0
    warnings: List[str] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def complete(self, status: str) -> None:
        self.status = status
        self.completed_at = utc_now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
