from dataclasses import dataclass, asdict
from typing import Any, Callable, Dict, List


@dataclass
class SignalPipelineResult:
    signals_seen: int
    signals_approved: int
    signals_rejected: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SignalPipeline:
    def __init__(self) -> None:
        self.filters: List[Callable[[Dict[str, Any]], bool]] = []

    def add_filter(self, callback: Callable[[Dict[str, Any]], bool]) -> None:
        self.filters.append(callback)

    def process(self, signals: List[Dict[str, Any]]):
        approved = []
        for signal in signals:
            if all(f(signal) for f in self.filters):
                approved.append(signal)
        result = SignalPipelineResult(len(signals), len(approved), len(signals) - len(approved))
        return approved, result
