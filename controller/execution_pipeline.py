from dataclasses import dataclass, asdict
from typing import Any, Callable, Dict, List


@dataclass
class ExecutionPipelineResult:
    orders_requested: int
    orders_executed: int
    orders_rejected: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ExecutionPipeline:
    def __init__(self) -> None:
        self.validators: List[Callable[[Dict[str, Any]], bool]] = []

    def add_validator(self, callback: Callable[[Dict[str, Any]], bool]) -> None:
        self.validators.append(callback)

    def execute(self, orders: List[Dict[str, Any]]):
        executed = []
        for order in orders:
            if all(v(order) for v in self.validators):
                executed_order = dict(order)
                executed_order["status"] = "SIMULATED_EXECUTED"
                executed.append(executed_order)
        result = ExecutionPipelineResult(len(orders), len(executed), len(orders) - len(executed))
        return executed, result
