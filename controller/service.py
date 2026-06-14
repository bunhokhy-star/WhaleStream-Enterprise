from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from controller.lifecycle import ServiceStatus


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ServiceHealth:
    name: str
    status: str
    healthy: bool
    message: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Service:
    name: str = "service"
    critical: bool = True

    def __init__(self, name: Optional[str] = None, critical: bool = True) -> None:
        self.name = name or self.name
        self.critical = critical
        self._status = ServiceStatus.CREATED
        self._message = "Created"
        self._context = None

    def initialize(self, context: Any = None) -> None:
        self._context = context
        self._status = ServiceStatus.INITIALIZING
        self._message = "Initialized"

    def start(self) -> None:
        self._status = ServiceStatus.RUNNING
        self._message = "Running"

    def update(self) -> None:
        self._message = "Updated"

    def stop(self) -> None:
        self._status = ServiceStatus.STOPPED
        self._message = "Stopped"

    def fail(self, message: str) -> None:
        self._status = ServiceStatus.FAILED
        self._message = message

    def degrade(self, message: str) -> None:
        self._status = ServiceStatus.DEGRADED
        self._message = message

    def status(self) -> str:
        return self._status.value

    def health(self) -> ServiceHealth:
        healthy = self._status in {ServiceStatus.RUNNING, ServiceStatus.STOPPED}
        return ServiceHealth(
            name=self.name,
            status=self.status(),
            healthy=healthy,
            message=self._message,
            updated_at=utc_now_iso(),
        )
