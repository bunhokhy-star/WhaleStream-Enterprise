from typing import Any, Dict, List

from controller.controller_report import ControllerReport
from controller.execution_pipeline import ExecutionPipeline
from controller.health_monitor import HealthMonitor
from controller.heartbeat import Heartbeat
from controller.lifecycle import ControllerStatus
from controller.runtime_context import RuntimeContext
from controller.scheduler import Scheduler
from controller.service import Service
from controller.service_registry import ServiceRegistry
from controller.shutdown_manager import ShutdownManager
from controller.signal_pipeline import SignalPipeline


class LiveController:
    def __init__(
        self,
        context: RuntimeContext | None = None,
        registry: ServiceRegistry | None = None,
        scheduler: Scheduler | None = None,
        heartbeat: Heartbeat | None = None,
        health_monitor: HealthMonitor | None = None,
        signal_pipeline: SignalPipeline | None = None,
        execution_pipeline: ExecutionPipeline | None = None,
        shutdown_manager: ShutdownManager | None = None,
    ) -> None:
        self.context = context or RuntimeContext()
        self.registry = registry or ServiceRegistry()
        self.scheduler = scheduler or Scheduler()
        self.heartbeat = heartbeat or Heartbeat()
        self.health_monitor = health_monitor or HealthMonitor()
        self.signal_pipeline = signal_pipeline or SignalPipeline()
        self.execution_pipeline = execution_pipeline or ExecutionPipeline()
        self.shutdown_manager = shutdown_manager or ShutdownManager()
        self.status = ControllerStatus.CREATED
        self.report = ControllerReport()

    def register_service(self, service: Service) -> None:
        self.registry.register(service)

    def initialize(self) -> None:
        self.status = ControllerStatus.INITIALIZING
        self.context.emit("ControllerInitializing")
        self.registry.initialize_all(self.context)
        self.report.services_registered = len(self.registry.all())

    def start(self) -> None:
        self.registry.start_all()
        self.status = ControllerStatus.RUNNING
        self.context.emit("ControllerStarted")

    def run_cycle(
        self,
        signals: List[Dict[str, Any]] | None = None,
        orders: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        if self.status != ControllerStatus.RUNNING:
            raise RuntimeError("Controller must be RUNNING before run_cycle")

        signals = signals or []
        orders = orders or []

        self.registry.update_all()
        approved_signals, signal_result = self.signal_pipeline.process(signals)
        executed_orders, execution_result = self.execution_pipeline.execute(orders)

        service_health = self.registry.health_all()
        health_report = self.health_monitor.evaluate(service_health)
        heartbeat_snapshot = self.heartbeat.beat(self.status.value, service_health)

        if not health_report.healthy:
            self.status = ControllerStatus.DEGRADED
            self.context.disable_trading("Service health failure")

        self.report.cycles_completed += 1
        self.report.heartbeats = self.heartbeat.count

        result = {
            "signals": signal_result.to_dict(),
            "execution": execution_result.to_dict(),
            "health": health_report.to_dict(),
            "heartbeat": heartbeat_snapshot.to_dict(),
            "approved_signals": approved_signals,
            "executed_orders": executed_orders,
        }
        self.context.emit("ControllerCycleCompleted", result)
        return result

    def stop(self) -> ControllerReport:
        self.status = ControllerStatus.STOPPING
        shutdown_report = self.shutdown_manager.shutdown(self.registry)
        self.status = ControllerStatus.STOPPED
        self.context.emit("ControllerStopped", shutdown_report.to_dict())
        self.report.events = list(self.context.events)
        self.report.complete("STOPPED")
        return self.report
