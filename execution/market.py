from typing import Dict, Any, List

from execution.bybit_client import session
from execution.utils import assert_ok, safe_float


def get_ticker(symbol: str, category: str = "linear") -> Dict[str, Any]:
    response = session.get_tickers(category=category, symbol=symbol)
    response = assert_ok(response, f"Get ticker {symbol}")

    rows = response.get("result", {}).get("list", [])

    if not rows:
        raise ValueError(f"No ticker data returned for {symbol}")

    return rows[0]


def get_price(symbol: str, category: str = "linear") -> float:
    ticker = get_ticker(symbol, category)
    return safe_float(ticker.get("lastPrice"))


def get_orderbook(symbol: str, category: str = "linear", limit: int = 25) -> Dict[str, Any]:
    response = session.get_orderbook(category=category, symbol=symbol, limit=limit)
    return assert_ok(response, f"Get orderbook {symbol}")


def get_klines(symbol: str, interval: str = "60", limit: int = 50, category: str = "linear") -> List[list]:
    response = session.get_kline(category=category, symbol=symbol, interval=interval, limit=limit)
    response = assert_ok(response, f"Get klines {symbol}")
    return response.get("result", {}).get("list", [])
