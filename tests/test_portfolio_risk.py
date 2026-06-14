from core.trade_ticket import TradeTicket, generate_trade_id
from portfolio.policy import PortfolioRiskPolicy
from portfolio.portfolio import PortfolioPosition, PortfolioSnapshot
from portfolio.portfolio_manager import PortfolioManager


def build_ticket(symbol="BTCUSDT", risk_percent=0.5):
    return TradeTicket(
        trade_id=generate_trade_id(),
        symbol=symbol,
        side="Buy",
        entry_low=64000,
        entry_high=64100,
        stop_loss=61800,
        targets=[65000, 66000, 68000, 70000],
        confidence=90,
        risk_percent=risk_percent,
        strategy="WhaleStream",
        market_regime="BULLISH",
    )


def main():
    print()
    print("=" * 44)
    print("WHALESTREAM PORTFOLIO RISK TEST")
    print("=" * 44)

    snapshot = PortfolioSnapshot(
        equity=1000.0,
        available_balance=800.0,
        positions=[
            PortfolioPosition(
                symbol="ETHUSDT",
                side="Buy",
                notional=200.0,
                risk_percent=1.0,
            )
        ],
        daily_realized_pnl=0.0,
        consecutive_losses=0,
    )

    policy = PortfolioRiskPolicy(
        max_open_positions=5,
        max_portfolio_heat_percent=5.0,
        max_risk_per_trade_percent=1.0,
        max_daily_loss_percent=3.0,
        max_consecutive_losses=3,
        allow_duplicate_symbol=False,
        min_available_balance_percent=10.0,
    )

    manager = PortfolioManager(snapshot=snapshot, policy=policy)

    accepted_ticket = build_ticket(symbol="BTCUSDT", risk_percent=0.5)
    result = manager.validate_trade(accepted_ticket)

    print()
    print("Accepted Check:", result.passed)
    print("Reason:", result.reason)
    print("Checks:", result.checks)

    if not result.passed:
        raise SystemExit("ACCEPTED TRADE TEST FAILED")

    manager.add_position_from_ticket(accepted_ticket, notional=150.0)

    duplicate_ticket = build_ticket(symbol="BTCUSDT", risk_percent=0.5)
    duplicate_result = manager.validate_trade(duplicate_ticket)

    print()
    print("Duplicate Check:", duplicate_result.passed)
    print("Reason:", duplicate_result.reason)

    if duplicate_result.passed:
        raise SystemExit("DUPLICATE SYMBOL TEST FAILED")

    hot_snapshot = PortfolioSnapshot(
        equity=1000.0,
        available_balance=800.0,
        positions=[
            PortfolioPosition("ETHUSDT", "Buy", 200.0, 2.5),
            PortfolioPosition("SOLUSDT", "Buy", 200.0, 2.0),
        ],
    )

    hot_manager = PortfolioManager(snapshot=hot_snapshot, policy=policy)
    hot_ticket = build_ticket(symbol="XRPUSDT", risk_percent=1.0)
    hot_result = hot_manager.validate_trade(hot_ticket)

    print()
    print("Portfolio Heat Check:", hot_result.passed)
    print("Reason:", hot_result.reason)

    if hot_result.passed:
        raise SystemExit("PORTFOLIO HEAT TEST FAILED")

    loss_snapshot = PortfolioSnapshot(
        equity=1000.0,
        available_balance=800.0,
        positions=[],
        daily_realized_pnl=-35.0,
        consecutive_losses=0,
    )

    loss_manager = PortfolioManager(snapshot=loss_snapshot, policy=policy)
    loss_result = loss_manager.validate_trade(build_ticket(symbol="LINKUSDT", risk_percent=0.5))

    print()
    print("Daily Loss Check:", loss_result.passed)
    print("Reason:", loss_result.reason)

    if loss_result.passed:
        raise SystemExit("DAILY LOSS GUARD TEST FAILED")

    print()
    print("STATUS: PORTFOLIO RISK TEST PASSED")


if __name__ == "__main__":
    main()
