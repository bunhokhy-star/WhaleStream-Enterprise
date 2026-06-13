from __future__ import annotations

from typing import Optional

from core.event_bus import Event, EventBus
from recovery.exchange_sync import ExchangeSync
from recovery.models import ExchangeSnapshot, RecoveryReport, RecoveryState
from recovery.order_recovery import OrderRecovery
from recovery.position_recovery import PositionRecovery
from recovery.recovery_report import RecoveryReportWriter
from recovery.restart_manager import RestartManager
from recovery.state_loader import StateLoader
from recovery.state_saver import StateSaver


class RecoveryEngine:
    def __init__(
        self,
        state_loader: StateLoader = None,
        state_saver: StateSaver = None,
        exchange_sync: ExchangeSync = None,
        position_recovery: PositionRecovery = None,
        order_recovery: OrderRecovery = None,
        restart_manager: RestartManager = None,
        report_writer: RecoveryReportWriter = None,
        event_bus: EventBus = None,
    ) -> None:
        self.state_loader = state_loader or StateLoader()
        self.state_saver = state_saver or StateSaver()
        self.exchange_sync = exchange_sync or ExchangeSync()
        self.position_recovery = position_recovery or PositionRecovery()
        self.order_recovery = order_recovery or OrderRecovery()
        self.restart_manager = restart_manager or RestartManager()
        self.report_writer = report_writer or RecoveryReportWriter()
        self.event_bus = event_bus or EventBus()

    def save_state(self, state: RecoveryState) -> str:
        path = self.state_saver.save(state)
        self.event_bus.publish(
            Event(
                event_type="RecoveryStateSaved",
                component="RecoveryEngine",
                message=f"Recovery state saved: {path}",
                payload=state.to_dict(),
            )
        )
        return path

    def recover(self, exchange_snapshot: ExchangeSnapshot) -> RecoveryReport:
        report = RecoveryReport()

        unclean_shutdown = self.restart_manager.startup_check()

        state = self.state_loader.load()
        sync_result = self.exchange_sync.compare(state, exchange_snapshot)

        report.local_positions = len(state.positions)
        report.exchange_positions = len(exchange_snapshot.positions)
        report.local_orders = len(state.orders)
        report.exchange_orders = len(exchange_snapshot.orders)

        if unclean_shutdown:
            report.warnings.append("Unclean shutdown detected")
            report.actions.append("Startup recovery mode enabled")

        recovered_positions = self.position_recovery.recover(state, sync_result)
        recovered_orders = self.order_recovery.recover(state, sync_result)

        report.recovered_positions = len(recovered_positions)
        report.recovered_orders = len(recovered_orders)

        for position in recovered_positions:
            report.actions.append(f"Recovered position: {position.symbol} {position.side}")

        for order in recovered_orders:
            report.actions.append(f"Recovered order: {order.order_id} {order.symbol}")

        if sync_result.missing_exchange_positions:
            report.warnings.append(
                f"Local positions not found on exchange: {len(sync_result.missing_exchange_positions)}"
            )

        if sync_result.missing_exchange_orders:
            report.warnings.append(
                f"Local orders not found on exchange: {len(sync_result.missing_exchange_orders)}"
            )

        self.save_state(state)

        status = "SUCCESS" if not report.warnings else "RECOVERED_WITH_WARNINGS"
        report.complete(status=status)
        self.report_writer.write(report)

        self.event_bus.publish(
            Event(
                event_type="RecoveryCompleted",
                component="RecoveryEngine",
                level="INFO" if status == "SUCCESS" else "WARNING",
                message=f"Recovery completed: {status}",
                payload=report.to_dict(),
            )
        )

        return report
