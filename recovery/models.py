from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RecoveredPosition:
    symbol: str
    side: str
    qty: float
    entry_price: float = 0.0
    unrealized_pnl: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        return f"{self.symbol}:{self.side}".upper()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecoveredOrder:
    symbol: str
    side: str
    order_id: str
    order_type: str = "Limit"
    qty: float = 0.0
    price: float = 0.0
    status: str = "New"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        return str(self.order_id)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecoveryState:
    saved_at: str = field(default_factory=utc_now_iso)
    positions: List[RecoveredPosition] = field(default_factory=list)
    orders: List[RecoveredOrder] = field(default_factory=list)
    portfolio: Dict[str, Any] = field(default_factory=dict)
    kernel: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "saved_at": self.saved_at,
            "positions": [p.to_dict() for p in self.positions],
            "orders": [o.to_dict() for o in self.orders],
            "portfolio": self.portfolio,
            "kernel": self.kernel,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryState":
        return cls(
            saved_at=data.get("saved_at", utc_now_iso()),
            positions=[RecoveredPosition(**p) for p in data.get("positions", [])],
            orders=[RecoveredOrder(**o) for o in data.get("orders", [])],
            portfolio=data.get("portfolio", {}),
            kernel=data.get("kernel", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ExchangeSnapshot:
    positions: List[RecoveredPosition] = field(default_factory=list)
    orders: List[RecoveredOrder] = field(default_factory=list)
    wallet: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "positions": [p.to_dict() for p in self.positions],
            "orders": [o.to_dict() for o in self.orders],
            "wallet": self.wallet,
        }


@dataclass
class RecoveryReport:
    started_at: str = field(default_factory=utc_now_iso)
    completed_at: str = ""
    status: str = "STARTED"
    local_positions: int = 0
    exchange_positions: int = 0
    recovered_positions: int = 0
    local_orders: int = 0
    exchange_orders: int = 0
    recovered_orders: int = 0
    warnings: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)

    def complete(self, status: str = "SUCCESS") -> None:
        self.status = status
        self.completed_at = utc_now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
