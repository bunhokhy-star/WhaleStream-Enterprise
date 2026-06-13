import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.account import get_usdt_balance, get_wallet
from execution.market import get_price
from execution.orders import get_open_orders
from execution.positions import list_open_positions


def main():
    print()
    print("====================================")
    print("WHALESTREAM BYBIT TEST")
    print("====================================")
    print()

    try:
        wallet = get_wallet()
        print("✓ Connected")
        print("✓ Wallet response OK")
    except Exception as exc:
        print("✗ Wallet / connection failed")
        print(exc)
        return

    try:
        balance = get_usdt_balance()
        print("✓ USDT Balance")
        print(balance)
    except Exception as exc:
        print("✗ Balance parse failed")
        print(exc)

    try:
        price = get_price("BTCUSDT")
        print("✓ BTC Price")
        print(price)
    except Exception as exc:
        print("✗ Market price failed")
        print(exc)

    try:
        positions = list_open_positions()
        print("✓ Open Positions")
        print(len(positions))
    except Exception as exc:
        print("✗ Positions failed")
        print(exc)

    try:
        orders = get_open_orders()
        print("✓ Open Orders")
        rows = orders.get("result", {}).get("list", [])
        print(len(rows))
    except Exception as exc:
        print("✗ Open orders failed")
        print(exc)

    print()
    print("STATUS: READY FOR SPRINT 2 IF ALL CHECKS ABOVE PASSED")
    print()


if __name__ == "__main__":
    main()
