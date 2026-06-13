from pathlib import Path
import shutil

from recovery.crash_detector import CrashDetector
from recovery.models import ExchangeSnapshot, RecoveredOrder, RecoveredPosition, RecoveryState
from recovery.recovery_engine import RecoveryEngine
from recovery.recovery_report import RecoveryReportWriter
from recovery.restart_manager import RestartManager
from recovery.state_loader import StateLoader
from recovery.state_saver import StateSaver


TMP = Path("history/test_recovery")


def clean():
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True, exist_ok=True)


def main():
    print()
    print("=" * 44)
    print("WHALESTREAM RECOVERY ENGINE TEST")
    print("=" * 44)

    clean()

    state_path = TMP / "recovery_state.json"
    report_path = TMP / "recovery_report.json"
    lock_path = TMP / "runtime.lock"

    local_state = RecoveryState(
        positions=[
            RecoveredPosition(
                symbol="BTCUSDT",
                side="Buy",
                qty=0.001,
                entry_price=64000,
            )
        ],
        orders=[
            RecoveredOrder(
                symbol="BTCUSDT",
                side="Buy",
                order_id="ORDER-LOCAL-001",
                qty=0.001,
                price=62000,
            )
        ],
    )

    saver = StateSaver(str(state_path))
    loader = StateLoader(str(state_path))
    crash_detector = CrashDetector(str(lock_path))
    restart_manager = RestartManager(crash_detector)
    report_writer = RecoveryReportWriter(str(report_path))

    saver.save(local_state)
    print("✓ State Saved")

    loaded = loader.load()
    print("✓ State Loaded")

    if len(loaded.positions) != 1 or len(loaded.orders) != 1:
        raise SystemExit("STATE LOAD TEST FAILED")

    restart_manager.mark_started()

    exchange_snapshot = ExchangeSnapshot(
        positions=[
            RecoveredPosition(
                symbol="BTCUSDT",
                side="Buy",
                qty=0.001,
                entry_price=64000,
            ),
            RecoveredPosition(
                symbol="ETHUSDT",
                side="Sell",
                qty=0.01,
                entry_price=3200,
            ),
        ],
        orders=[
            RecoveredOrder(
                symbol="BTCUSDT",
                side="Buy",
                order_id="ORDER-LOCAL-001",
                qty=0.001,
                price=62000,
            ),
            RecoveredOrder(
                symbol="ETHUSDT",
                side="Sell",
                order_id="ORDER-EXCHANGE-002",
                qty=0.01,
                price=3300,
            ),
        ],
    )

    engine = RecoveryEngine(
        state_loader=loader,
        state_saver=saver,
        restart_manager=restart_manager,
        report_writer=report_writer,
    )

    report = engine.recover(exchange_snapshot)

    print("✓ Exchange Sync")
    print("✓ Position Recovery")
    print("✓ Order Recovery")
    print("✓ Restart Simulation")
    print("✓ Recovery Report")

    if report.recovered_positions != 1:
        raise SystemExit("POSITION RECOVERY TEST FAILED")

    if report.recovered_orders != 1:
        raise SystemExit("ORDER RECOVERY TEST FAILED")

    if not report_path.exists():
        raise SystemExit("RECOVERY REPORT TEST FAILED")

    recovered_state = loader.load()

    if len(recovered_state.positions) != 2:
        raise SystemExit("RECOVERED STATE POSITION COUNT FAILED")

    if len(recovered_state.orders) != 2:
        raise SystemExit("RECOVERED STATE ORDER COUNT FAILED")

    print()
    print("Report Status:", report.status)
    print("Recovered Positions:", report.recovered_positions)
    print("Recovered Orders:", report.recovered_orders)
    print()
    print("STATUS: RECOVERY ENGINE TEST PASSED")


if __name__ == "__main__":
    main()
