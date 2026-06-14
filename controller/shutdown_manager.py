from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ShutdownReport:
    requested: bool
    graceful: bool
    stopped_services: int
    message: str
    time: str

    def to_dict(self) -> Dict:
        return asdict(self)


class ShutdownManager:
    def __init__(self) -> None:
        self.requested = False

    def request(self) -> None:
        self.requested = True

    def shutdown(self, registry) -> ShutdownReport:
        self.requested = True
        services = registry.all()
        registry.stop_all_reverse()
        return ShutdownReport(True, True, len(services), "Graceful shutdown complete", utc_now_iso())
