from core.position import Position, PositionStatus
from core.position_manager import PositionManager


def main():
    print()
    print("=" * 44)
    print("WHALESTREAM POSITION MANAGER TEST")
    print("=" * 44)

    manager = PositionManager()

    position = Position(
        trade_id="WS-TEST-POSITION-0001",
        symbol="BTCUSDT",
        side="Buy",
        qty=0.004,
        entry_price=64000,
        stop_loss=61760,
        targets=[66000, 68000, 70000, 72000],
        remaining_qty=0.004,
    )

    manager.add_position(position)

    print()
    print("Opened:", position.status)
    print("Initial SL:", position.stop_loss)

    manager.update_price(position.trade_id, 66000)
    p1 = manager.get_position(position.trade_id)

    print()
    print("After TP1")
    print("Status:", p1.status)
    print("Remaining Qty:", p1.remaining_qty)
    print("Stop Loss:", p1.stop_loss)

    if p1.stop_loss <= p1.entry_price:
        raise SystemExit("BREAKEVEN TEST FAILED")

    manager.update_price(position.trade_id, 68000)
    p2 = manager.get_position(position.trade_id)

    print()
    print("After TP2")
    print("Status:", p2.status)
    print("Remaining Qty:", p2.remaining_qty)
    print("Stop Loss:", p2.stop_loss)

    if not p2.metadata.get("trailing_stop_active"):
        raise SystemExit("TRAILING STOP TEST FAILED")

    manager.update_price(position.trade_id, 72000)
    p4 = manager.get_position(position.trade_id)

    print()
    print("After TP4")
    print("Status:", p4.status)
    print("Remaining Qty:", p4.remaining_qty)

    if p4.status != PositionStatus.CLOSED:
        raise SystemExit("POSITION CLOSE TEST FAILED")

    print()
    print("STATUS: POSITION MANAGER TEST PASSED")


if __name__ == "__main__":
    main()
