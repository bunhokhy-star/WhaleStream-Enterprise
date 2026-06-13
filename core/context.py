from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class KernelContext:
    mode: str = "demo"
    require_approval: bool = True
    min_confidence: float = 80.0
    min_rr: float = 3.0
    max_open_positions: int = 5
    max_open_orders: int = 20
    risk_per_trade: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def demo_default(cls) -> "KernelContext":
        return cls(mode="demo", require_approval=True)
