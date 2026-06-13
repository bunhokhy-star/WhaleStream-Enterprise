from core.approval import ApprovalDecision, ApprovalEngine
from core.context import KernelContext
from core.trading_kernel import TradingKernel


class AutoApproval(ApprovalEngine):
    def __init__(self, decision: str):
        super().__init__(interactive=False)
        self.decision = decision

    def request_approval(self, ticket):
        return self.decision


def build_sample_signal(confidence=90):
    return {
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "entry_low": 64000,
        "entry_high": 64100,
        "stop_loss": 61800,
        "tp1": 65000,
        "tp2": 66200,
        "tp3": 67500,
        "tp4": 70500,
        "confidence": confidence,
        "pattern": "TEST_PATTERN",
        "btc_regime": "BULLISH",
        "funding_rate": 0.0,
        "oi_change": 0.0,
        "trend_score": 50,
    }


def main():
    print()
    print("=" * 40)
    print("WHALESTREAM KERNEL TEST")
    print("=" * 40)

    context = KernelContext.demo_default()
    context.min_confidence = 80
    context.min_rr = 2.0

    kernel = TradingKernel(context=context, approval_engine=AutoApproval(ApprovalDecision.APPROVED))
    ticket = kernel.process_signal(build_sample_signal(confidence=90))

    print()
    print("Trade ID :", ticket.trade_id)
    print("Symbol   :", ticket.symbol)
    print("Side     :", ticket.side)
    print("Status   :", ticket.status)

    if ticket.status != "APPROVED":
        raise SystemExit("KERNEL APPROVAL TEST FAILED")

    rejected_kernel = TradingKernel(context=context, approval_engine=AutoApproval(ApprovalDecision.APPROVED))
    rejected_ticket = rejected_kernel.process_signal(build_sample_signal(confidence=50))

    print()
    print("Rejected Status:", rejected_ticket.status)

    if rejected_ticket.status != "REJECTED":
        raise SystemExit("KERNEL REJECTION TEST FAILED")

    print()
    print("STATUS: KERNEL TEST PASSED")


if __name__ == "__main__":
    main()
