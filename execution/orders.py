from typing import Dict, Any, Optional

from execution.bybit_client import session
from execution.utils import assert_ok


def get_open_orders(
    symbol: Optional[str] = None,
    category: str = "linear",
    settle_coin: str = "USDT"
) -> Dict[str, Any]:

    params = {
        "category": category
    }

    if symbol:
        params["symbol"] = symbol
    else:
        params["settleCoin"] = settle_coin

    response = session.get_open_orders(
        **params
    )

    return assert_ok(
        response,
        "Get open orders"
    )


def cancel_order(
    symbol: str,
    order_id: str,
    category: str = "linear"
) -> Dict[str, Any]:

    response = session.cancel_order(
        category=category,
        symbol=symbol,
        orderId=order_id
    )

    return assert_ok(
        response,
        f"Cancel order {order_id}"
    )


def cancel_order_by_link_id(
    symbol: str,
    order_link_id: str,
    category: str = "linear"
) -> Dict[str, Any]:

    response = session.cancel_order(
        category=category,
        symbol=symbol,
        orderLinkId=order_link_id
    )

    return assert_ok(
        response,
        f"Cancel order link {order_link_id}"
    )


def place_market_order(
    symbol: str,
    side: str,
    qty: str,
    category: str = "linear",
    reduce_only: bool = False,
    order_link_id: Optional[str] = None
) -> Dict[str, Any]:

    params = {
        "category": category,
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": str(qty),
        "reduceOnly": reduce_only
    }

    if order_link_id:
        params["orderLinkId"] = order_link_id

    response = session.place_order(
        **params
    )

    return assert_ok(
        response,
        f"Place market order {symbol} {side}"
    )


def place_limit_order(
    symbol: str,
    side: str,
    qty: str,
    price: str,
    category: str = "linear",
    reduce_only: bool = False,
    time_in_force: str = "GTC",
    order_link_id: Optional[str] = None
) -> Dict[str, Any]:

    params = {
        "category": category,
        "symbol": symbol,
        "side": side,
        "orderType": "Limit",
        "qty": str(qty),
        "price": str(price),
        "timeInForce": time_in_force,
        "reduceOnly": reduce_only
    }

    if order_link_id:
        params["orderLinkId"] = order_link_id

    response = session.place_order(
        **params
    )

    return assert_ok(
        response,
        f"Place limit order {symbol} {side}"
    )
