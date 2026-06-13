from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_trade_id(prefix: str = "WS") -> str:
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    short_id = uuid4().hex[:8].upper()
    return f"{prefix}-{stamp}-{short_id}"


@dataclass
class TradeTicket:
    trade_id: str
    symbol: str
    side: str
    entry_low: float
    entry_high: float
    stop_loss: float
    targets: List[float]
    confidence: float
    risk_percent: float
    strategy: str = "WhaleStream"
    market_regime: str = "UNKNOWN"
    status: str = "NEW"
    created_at: str = field(default_factory=utc_now_iso)
    approved_at: Optional[str] = None
    executed_at: Optional[str] = None
    closed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def entry_mid(self) -> float:
        return (float(self.entry_low) + float(self.entry_high)) / 2

    @property
    def direction(self) -> str:
        side = self.side.upper()
        if side in {"BUY", "LONG"}:
            return "LONG"
        if side in {"SELL", "SHORT"}:
            return "SHORT"
        return side

    @classmethod
    def from_signal(cls, signal: Dict[str, Any], risk_percent: float = 0.5, strategy: str = "WhaleStream") -> "TradeTicket":
        symbol = signal.get("symbol")
        if not symbol:
            raise ValueError("Signal missing symbol")

        direction = signal.get("direction") or signal.get("side")
        if not direction:
            raise ValueError("Signal missing direction/side")

        side = "Buy" if str(direction).upper() == "LONG" else "Sell"

        targets = []
        for key in ("tp1", "tp2", "tp3", "tp4"):
            if key in signal and signal[key] is not None:
                targets.append(float(signal[key]))

        if not targets:
            raise ValueError("Signal missing targets")

        return cls(
            trade_id=generate_trade_id(),
            symbol=str(symbol).upper(),
            side=side,
            entry_low=float(signal["entry_low"]),
            entry_high=float(signal["entry_high"]),
            stop_loss=float(signal["stop_loss"]),
            targets=targets,
            confidence=float(signal.get("confidence", 0)),
            risk_percent=float(signal.get("risk_percent", risk_percent)),
            strategy=str(signal.get("strategy", strategy)),
            market_regime=str(signal.get("btc_regime", signal.get("market_regime", "UNKNOWN"))),
            metadata={
                "pattern": signal.get("pattern"),
                "funding_rate": signal.get("funding_rate"),
                "oi_change": signal.get("oi_change"),
                "trend_score": signal.get("trend_score"),
                "raw_signal": signal,
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
