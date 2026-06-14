from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any


@dataclass
class PortfolioPosition:
    symbol: str
    side: str
    notional: float
    risk_percent: float
    unrealized_pnl: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def direction(self) -> str:
        side = self.side.upper()
        if side in {"BUY", "LONG"}:
            return "LONG"
        if side in {"SELL", "SHORT"}:
            return "SHORT"
        return side

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PortfolioSnapshot:
    equity: float
    available_balance: float
    positions: List[PortfolioPosition] = field(default_factory=list)
    daily_realized_pnl: float = 0.0
    consecutive_losses: int = 0

    @property
    def open_positions_count(self) -> int:
        return len(self.positions)

    @property
    def total_risk_percent(self) -> float:
        return round(sum(p.risk_percent for p in self.positions), 6)

    @property
    def total_notional(self) -> float:
        return round(sum(p.notional for p in self.positions), 6)

    def symbols(self) -> List[str]:
        return [p.symbol for p in self.positions]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "equity": self.equity,
            "available_balance": self.available_balance,
            "daily_realized_pnl": self.daily_realized_pnl,
            "consecutive_losses": self.consecutive_losses,
            "open_positions_count": self.open_positions_count,
            "total_risk_percent": self.total_risk_percent,
            "total_notional": self.total_notional,
            "positions": [p.to_dict() for p in self.positions],
        }
