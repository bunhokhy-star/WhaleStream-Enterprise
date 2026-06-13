import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.account import get_usdt_balance
from execution.trade_executor import prepare_safe_test_order, place_and_cancel_safe_test_order


CONFIRMATION_TEXT = "YES_PLACE_TEST_ORDER"


def main():

    parser = argparse.ArgumentParser(
        description="WhaleStream Sprint 2 safe Bybit Demo order test"
    )

    parser.add_argument("--execute", action="store_true", help="Actually place and cancel a safe demo limit order")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--side", default="Buy", choices=["Buy", "Sell", "buy", "sell"])
    parser.add_argument("--qty", default="0.001")
    parser.add_argument("--offset-pct", type=float, default=20.0)

    args = parser.parse_args()

    print()
    print("====================================")
    print("WHALESTREAM SAFE ORDER TEST")
    print("====================================")
    print()

    balance = get_usdt_balance()
    print("✓ Wallet OK")
    print(balance)
    print()

    order = prepare_safe_test_order(
        symbol=args.symbol.upper(),
        side=args.side,
        qty=args.qty,
        offset_pct=args.offset_pct
    )

    print("✓ Safe test order prepared")
    print("Symbol       :", order["symbol"])
    print("Side         :", order["side"])
    print("Qty          :", order["qty"])
    print("Live Price   :", order["live_price"])
    print("Test Price   :", order["price"])
    print("Offset       :", str(order["offset_pct"]) + "%")
    print("TimeInForce  :", order["time_in_force"])
    print("Order Link ID:", order["order_link_id"])
    print()

    if not args.execute:
        print("DRY RUN ONLY — no order was placed.")
        print("To place and immediately cancel this demo order, run:")
        print("python execution\\test_order.py --execute")
        print()
        print("STATUS: DRY RUN PASSED")
        return

    print("WARNING: This will place a Bybit DEMO PostOnly limit order and immediately cancel it.")
    print("Type exactly this to continue:", CONFIRMATION_TEXT)
    confirmation = input("> ").strip()

    if confirmation != CONFIRMATION_TEXT:
        print("Cancelled by user. No order placed.")
        return

    result = place_and_cancel_safe_test_order(
        symbol=args.symbol.upper(),
        side=args.side,
        qty=args.qty,
        offset_pct=args.offset_pct
    )

    placed_order_id = result["placed_response"].get("result", {}).get("orderId")

    print()
    print("✓ Order placed")
    print("Order ID:", placed_order_id)
    print("✓ Order cancelled")
    print("✓ Journal saved to history\\execution_journal.csv")
    print()
    print("STATUS: SAFE ORDER TEST PASSED")


if __name__ == "__main__":
    main()
