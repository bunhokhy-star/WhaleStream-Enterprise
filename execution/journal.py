import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any


ROOT = Path(__file__).resolve().parents[1]
JOURNAL_PATH = ROOT / "history" / "execution_journal.csv"

FIELDNAMES = [
    "timestamp_utc",
    "event",
    "symbol",
    "side",
    "qty",
    "price",
    "order_id",
    "order_link_id",
    "status",
    "message"
]


def ensure_journal() -> None:

    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not JOURNAL_PATH.exists():
        with JOURNAL_PATH.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
            writer.writeheader()


def log_execution_event(
    event: str,
    symbol: str = "",
    side: str = "",
    qty: str = "",
    price: str = "",
    order_id: str = "",
    order_link_id: str = "",
    status: str = "",
    message: str = ""
) -> Dict[str, Any]:

    ensure_journal()

    row = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": price,
        "order_id": order_id,
        "order_link_id": order_link_id,
        "status": status,
        "message": message
    }

    with JOURNAL_PATH.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writerow(row)

    return row
