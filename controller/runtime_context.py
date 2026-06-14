from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RuntimeContext:
    started_at: str = field(default_factory=utc_now_iso)
    config: Dict[str, Any] = field(default_factory=dict)
    state: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    events: list = field(default_factory=list)
    shutdown_requested: bool = False
    trading_enabled: bool = True

    def set(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def emit(self, event_type: str, payload: Dict[str, Any] = None) -> None:
        self.events.append({"time": utc_now_iso(), "event_type": event_type, "payload": payload or {}})

    def request_shutdown(self) -> None:
        self.shutdown_requested = True
        self.emit("ShutdownRequested")

    def disable_trading(self, reason: str) -> None:
        self.trading_enabled = False
        self.emit("TradingDisabled", {"reason": reason})

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
