from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import json


@dataclass
class Event:
    event_type: str
    trade_id: Optional[str] = None
    component: str = "core"
    level: str = "INFO"
    message: str = ""
    payload: Dict[str, Any] = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if self.payload is None:
            self.payload = {}
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EventBus:
    def __init__(self, log_path: str = "logs/whalestream_events.jsonl") -> None:
        self.subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        self.subscribers.setdefault(event_type, []).append(handler)

    def publish(self, event: Event) -> None:
        self._write_event(event)

        for handler in self.subscribers.get(event.event_type, []):
            handler(event)

        for handler in self.subscribers.get("*", []):
            handler(event)

    def _write_event(self, event: Event) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
