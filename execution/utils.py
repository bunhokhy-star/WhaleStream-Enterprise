from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict

from execution.exceptions import BybitAPIError


def assert_ok(response: Dict[str, Any], action: str = "Bybit request") -> Dict[str, Any]:
    """Validate Bybit V5 REST response."""

    if not isinstance(response, dict):
        raise BybitAPIError(f"{action} failed: response is not a dictionary")

    ret_code = response.get("retCode")

    if ret_code != 0:
        ret_msg = response.get("retMsg", "Unknown error")
        raise BybitAPIError(f"{action} failed: retCode={ret_code}, retMsg={ret_msg}")

    return response


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def round_down(value: float, precision: int) -> str:
    """Round down to a fixed decimal precision and return as string for API params."""

    q = Decimal("1") if precision <= 0 else Decimal("1") / (Decimal("10") ** precision)
    return str(Decimal(str(value)).quantize(q, rounding=ROUND_DOWN))
