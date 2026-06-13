from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PositionStatus:
    NEW = "NEW"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


@dataclass
class Position:
    trade_id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    stop_loss: float
    targets: List[float]
    remaining_qty: float
    status: str = PositionStatus.NEW
    opened_at: str = field(default_factory=utc_now_iso)
    closed_at: Optional[str] = None
    current_price: Optional[float] = None
    realized_r: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def direction(self) -> str:
        side = self.side.upper()
        if side in {"BUY", "LONG"}:
            return "LONG"
        if side in {"SELL", "SHORT"}:
            return "SHORT"
        return side

    @property
    def risk_per_unit(self) -> float:
        if self.direction == "LONG":
            return self.entry_price - self.stop_loss
        return self.stop_loss - self.entry_price

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
