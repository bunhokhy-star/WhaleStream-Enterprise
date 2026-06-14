from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HeartbeatSnapshot:
    count: int
    status: str
    service_count: int
    healthy_services: int
    time: str

    def to_dict(self) -> Dict:
        return asdict(self)


class Heartbeat:
    def __init__(self) -> None:
        self.count = 0
        self.last_snapshot = None

    def beat(self, controller_status: str, service_health: list) -> HeartbeatSnapshot:
        self.count += 1
        healthy_services = len([h for h in service_health if h.healthy])
        self.last_snapshot = HeartbeatSnapshot(
            count=self.count,
            status=controller_status,
            service_count=len(service_health),
            healthy_services=healthy_services,
            time=utc_now_iso(),
        )
        return self.last_snapshot
