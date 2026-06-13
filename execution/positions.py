from typing import Dict, Any, List, Optional

from execution.bybit_client import session
from execution.utils import assert_ok, safe_float


def get_positions(symbol: Optional[str] = None, category: str = "linear", settle_coin: str = "USDT") -> Dict[str, Any]:
    params = {"category": category, "settleCoin": settle_coin}

    if symbol:
        params["symbol"] = symbol

    response = session.get_positions(**params)
    return assert_ok(response, "Get positions")


def list_open_positions(category: str = "linear", settle_coin: str = "USDT") -> List[Dict[str, Any]]:
    response = get_positions(category=category, settle_coin=settle_coin)
    positions = response.get("result", {}).get("list", [])

    open_positions = []

    for pos in positions:
        if safe_float(pos.get("size")) > 0:
            open_positions.append(pos)

    return open_positions


def get_position_size(symbol: str) -> float:
    response = get_positions(symbol=symbol)
    positions = response.get("result", {}).get("list", [])

    if not positions:
        return 0.0

    return safe_float(positions[0].get("size"))
