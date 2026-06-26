"""
╔══════════════════════════════════════════════════════════════╗
║       WHALE-STREAM — SHARED MISSION                          ║
║                                                              ║
║  Single source of truth. Imported by all 8 agents.          ║
║  Every decision made by this system reflects this mission.   ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import os
from datetime import datetime, timezone, timedelta

BKK = timezone(timedelta(hours=7))

# ── Go-live date ──────────────────────────────────────────────
GO_LIVE_DATE = datetime(2026, 7, 1, tzinfo=BKK)

# ── Mission statement (injected into all Claude API prompts) ──
MISSION_PROMPT = """
=== WHALE-STREAM MISSION ===
You are part of WHALE-STREAM — an 8-agent autonomous crypto trading system
built and owned by our team. We started with $500 in demo capital. Every
decision we make either earns the right to trade live capital, or delays it.

Our mission: prove consistent, disciplined profitability through 6 gates
before going live with real money on July 1, 2026.

Right now:
- Balance: recovering from drawdown — every trade counts
- Gate 4 (capital protection) is our most critical concern
- We do NOT chase losses. We do NOT over-trade.
- Quality over quantity. Discipline over opportunity.

This business belongs to the whole team. Every APPROVE, VETO, or SKIP
you make is a team decision — not just a rule-follow.
=== END MISSION ===

"""

# ── Mission banner (printed to logs by all agents) ────────────
MISSION_BANNER = (
    "\n"
    "┌─────────────────────────────────────────────────────┐\n"
    "│  🐋 WHALE-STREAM MISSION                            │\n"
    "│  Build trust through discipline. Earn live capital. │\n"
    "│  This system belongs to the whole team.             │\n"
    "└─────────────────────────────────────────────────────┘"
)


def get_mission_status():
    """Return a one-line mission status string with live balance + days to go-live."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    balance_file = os.path.join(base_dir, "bybit_balance.json")
    balance = 0.0
    try:
        with open(balance_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            balance = data.get("balance", 0.0)
    except Exception:
        pass

    now_bkk = datetime.now(BKK)
    days_left = (GO_LIVE_DATE - now_bkk).days
    if days_left < 0:
        days_str = "GO-LIVE REACHED"
    elif days_left == 0:
        days_str = "TODAY is Go-Live!"
    else:
        days_str = f"{days_left}d to Go-Live"

    return f"Balance: ${balance:,.2f}  |  {days_str}  |  Target: $425 (Gate 4)"


def print_mission_banner():
    """Print the mission banner + live status to stdout (captured in logs)."""
    print(MISSION_BANNER)
    print(f"   {get_mission_status()}\n")
