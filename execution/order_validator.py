from decimal import Decimal, InvalidOperation
from typing import Dict, Any
from uuid import uuid4
from datetime import datetime, timezone

from execution.market import get_price


VALID_SIDES = {"Buy", "Sell"}


def _to_decimal(value: Any, field_name: str) -> Decimal:

    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc

    if decimal_value <= 0:
        raise ValueError(f"{field_name} must be greater than zero")

    return decimal_value


def normalize_side(side: str) -> str:

    value = str(side).strip().lower()

    if value == "buy":
        return "Buy"

    if value == "sell":
        return "Sell"

    raise ValueError("side must be Buy or Sell")


def generate_order_link_id(prefix: str = "WSTEST") -> str:

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:6].upper()

    return f"{prefix}{timestamp}{suffix}"


def validate_limit_order(
    symbol: str,
    side: str,
    qty: str,
    price: str
) -> Dict[str, Any]:

    if not symbol or not str(symbol).endswith("USDT"):
        raise ValueError("symbol must be a USDT perpetual symbol, for example BTCUSDT")

    normalized_side = normalize_side(side)

    qty_decimal = _to_decimal(qty, "qty")
    price_decimal = _to_decimal(price, "price")

    notional = qty_decimal * price_decimal

    return {
        "symbol": str(symbol).upper(),
        "side": normalized_side,
        "qty": str(qty_decimal),
        "price": str(price_decimal),
        "notional": float(notional)
    }


def build_safe_limit_test_order(
    symbol: str = "BTCUSDT",
    side: str = "Buy",
    qty: str = "0.001",
    offset_pct: float = 20.0
) -> Dict[str, Any]:

    normalized_side = normalize_side(side)

    live_price = Decimal(str(get_price(symbol)))

    if normalized_side == "Buy":
        test_price = live_price * (Decimal("1") - Decimal(str(offset_pct)) / Decimal("100"))
    else:
        test_price = live_price * (Decimal("1") + Decimal(str(offset_pct)) / Decimal("100"))

    # BTCUSDT demo futures accepts 0.1 price precision. This keeps the order away from market.
    test_price = test_price.quantize(Decimal("0.1"))

    validated = validate_limit_order(
        symbol=symbol,
        side=normalized_side,
        qty=qty,
        price=str(test_price)
    )

    validated["live_price"] = float(live_price)
    validated["offset_pct"] = offset_pct
    validated["time_in_force"] = "PostOnly"
    validated["order_link_id"] = generate_order_link_id()

    return validated
