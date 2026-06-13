from typing import Dict, Any

from execution.journal import log_execution_event
from execution.order_validator import build_safe_limit_test_order
from execution.orders import place_limit_order, cancel_order


def prepare_safe_test_order(
    symbol: str = "BTCUSDT",
    side: str = "Buy",
    qty: str = "0.001",
    offset_pct: float = 20.0
) -> Dict[str, Any]:

    return build_safe_limit_test_order(
        symbol=symbol,
        side=side,
        qty=qty,
        offset_pct=offset_pct
    )


def place_and_cancel_safe_test_order(
    symbol: str = "BTCUSDT",
    side: str = "Buy",
    qty: str = "0.001",
    offset_pct: float = 20.0
) -> Dict[str, Any]:

    order = prepare_safe_test_order(
        symbol=symbol,
        side=side,
        qty=qty,
        offset_pct=offset_pct
    )

    log_execution_event(
        event="TEST_ORDER_PREPARED",
        symbol=order["symbol"],
        side=order["side"],
        qty=order["qty"],
        price=order["price"],
        order_link_id=order["order_link_id"],
        status="PREPARED",
        message="Safe post-only limit test order prepared"
    )

    placed = place_limit_order(
        symbol=order["symbol"],
        side=order["side"],
        qty=order["qty"],
        price=order["price"],
        time_in_force=order["time_in_force"],
        order_link_id=order["order_link_id"]
    )

    result = placed.get("result", {})
    order_id = result.get("orderId", "")

    log_execution_event(
        event="TEST_ORDER_PLACED",
        symbol=order["symbol"],
        side=order["side"],
        qty=order["qty"],
        price=order["price"],
        order_id=order_id,
        order_link_id=order["order_link_id"],
        status="PLACED",
        message="Safe test order accepted by Bybit Demo"
    )

    cancelled = cancel_order(
        symbol=order["symbol"],
        order_id=order_id
    )

    log_execution_event(
        event="TEST_ORDER_CANCELLED",
        symbol=order["symbol"],
        side=order["side"],
        qty=order["qty"],
        price=order["price"],
        order_id=order_id,
        order_link_id=order["order_link_id"],
        status="CANCELLED",
        message="Safe test order cancelled"
    )

    return {
        "prepared_order": order,
        "placed_response": placed,
        "cancelled_response": cancelled
    }
