from __future__ import annotations

from core.trade_ticket import TradeTicket


class ApprovalDecision:
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PASSED = "PASSED"


class ApprovalEngine:
    def __init__(self, interactive: bool = True) -> None:
        self.interactive = interactive

    def request_approval(self, ticket: TradeTicket) -> str:
        if not self.interactive:
            return ApprovalDecision.PASSED

        print()
        print("=" * 54)
        print("WHALESTREAM TRADE APPROVAL")
        print("=" * 54)
        print(f"Trade ID   : {ticket.trade_id}")
        print(f"Symbol     : {ticket.symbol}")
        print(f"Side       : {ticket.side}")
        print(f"Confidence : {ticket.confidence}%")
        print(f"Entry      : {ticket.entry_low} - {ticket.entry_high}")
        print(f"Stop Loss  : {ticket.stop_loss}")
        print(f"Targets    : {ticket.targets}")
        print(f"Risk %     : {ticket.risk_percent}")
        print(f"Regime     : {ticket.market_regime}")
        print("=" * 54)
        print("[Y] Approve   [N] Reject   [P] Pass")
        decision = input("> ").strip().upper()

        if decision == "Y":
            return ApprovalDecision.APPROVED
        if decision == "N":
            return ApprovalDecision.REJECTED
        return ApprovalDecision.PASSED
