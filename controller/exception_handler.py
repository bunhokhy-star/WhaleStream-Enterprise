from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ControllerException:
    error_type: str
    message: str
    handled_at: str

    def to_dict(self) -> Dict:
        return asdict(self)


class ExceptionHandler:
    def handle(self, exc: Exception) -> ControllerException:
        return ControllerException(exc.__class__.__name__, str(exc), utc_now_iso())
