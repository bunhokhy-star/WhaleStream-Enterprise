from dataclasses import dataclass, asdict
from typing import Dict, List

from controller.service import ServiceHealth


@dataclass
class HealthReport:
    healthy: bool
    total_services: int
    healthy_services: int
    failed_services: List[str]
    degraded_services: List[str]

    def to_dict(self) -> Dict:
        return asdict(self)


class HealthMonitor:
    def evaluate(self, service_health: List[ServiceHealth]) -> HealthReport:
        failed = [h.name for h in service_health if h.status == "FAILED"]
        degraded = [h.name for h in service_health if h.status == "DEGRADED"]
        healthy_services = len([h for h in service_health if h.healthy])
        return HealthReport(
            healthy=len(failed) == 0,
            total_services=len(service_health),
            healthy_services=healthy_services,
            failed_services=failed,
            degraded_services=degraded,
        )
