from controller.live_controller import LiveController
from controller.runtime_context import RuntimeContext
from controller.scheduler import Scheduler
from controller.service import Service


class DemoService(Service):
    def __init__(self, name="demo_service", critical=True):
        super().__init__(name=name, critical=critical)
        self.updates = 0

    def update(self):
        self.updates += 1
        self._message = f"Updated {self.updates}"


def main():
    print()
    print("=" * 44)
    print("WHALESTREAM LIVE CONTROLLER TEST")
    print("=" * 44)

    context = RuntimeContext(config={"mode": "test"})
    print("✓ Runtime Context")

    controller = LiveController(context=context)

    controller.register_service(DemoService(name="recovery"))
    controller.register_service(DemoService(name="portfolio"))
    controller.register_service(DemoService(name="execution"))
    print("✓ Service Registry")

    scheduler = Scheduler()
    state = {"ran": False}
    scheduler.add_task("sample_task", lambda: state.update({"ran": True}))
    results = scheduler.run_once()
    if not state["ran"] or not results[0].success:
        raise SystemExit("SCHEDULER TEST FAILED")
    print("✓ Scheduler")

    controller.signal_pipeline.add_filter(lambda signal: signal.get("confidence", 0) >= 80)
    controller.execution_pipeline.add_validator(lambda order: order.get("approved", False) is True)

    controller.initialize()
    controller.start()

    result = controller.run_cycle(
        signals=[
            {"symbol": "BTCUSDT", "confidence": 90},
            {"symbol": "ETHUSDT", "confidence": 70},
        ],
        orders=[
            {"symbol": "BTCUSDT", "approved": True},
            {"symbol": "ETHUSDT", "approved": False},
        ],
    )

    if result["heartbeat"]["count"] != 1:
        raise SystemExit("HEARTBEAT TEST FAILED")
    print("✓ Heartbeat")

    if not result["health"]["healthy"]:
        raise SystemExit("HEALTH MONITOR TEST FAILED")
    print("✓ Health Monitor")

    if result["signals"]["signals_approved"] != 1:
        raise SystemExit("SIGNAL PIPELINE TEST FAILED")
    print("✓ Signal Pipeline")

    if result["execution"]["orders_executed"] != 1:
        raise SystemExit("EXECUTION PIPELINE TEST FAILED")
    print("✓ Execution Pipeline")

    report = controller.stop()
    if report.status != "STOPPED":
        raise SystemExit("GRACEFUL SHUTDOWN TEST FAILED")
    print("✓ Graceful Shutdown")

    if len(context.events) == 0:
        raise SystemExit("RUNTIME EVENT TEST FAILED")
    print("✓ Recovery Integration")
    print("✓ Controller Started")

    print()
    print("Controller Status:", report.status)
    print("Cycles Completed:", report.cycles_completed)
    print("Heartbeats:", report.heartbeats)
    print()
    print("STATUS: LIVE CONTROLLER TEST PASSED")


if __name__ == "__main__":
    main()
