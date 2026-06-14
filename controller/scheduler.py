from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ScheduledTaskResult:
    name: str
    success: bool
    message: str = ""
    ran_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Scheduler:
    def __init__(self) -> None:
        self.tasks: List[tuple[str, Callable[[], Any]]] = []
        self.results: List[ScheduledTaskResult] = []

    def add_task(self, name: str, callback: Callable[[], Any]) -> None:
        self.tasks.append((name, callback))

    def run_once(self) -> List[ScheduledTaskResult]:
        self.results = []
        for name, callback in self.tasks:
            try:
                callback()
                self.results.append(ScheduledTaskResult(name, True, "OK", utc_now_iso()))
            except Exception as exc:
                self.results.append(ScheduledTaskResult(name, False, str(exc), utc_now_iso()))
        return self.results
