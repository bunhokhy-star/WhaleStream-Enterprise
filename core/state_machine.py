from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set


class InvalidStateTransition(Exception):
    pass


class TradeState:
    NEW = "NEW"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    FILLED = "FILLED"
    OPEN = "OPEN"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    TradeState.NEW: {TradeState.VALIDATED, TradeState.REJECTED, TradeState.FAILED},
    TradeState.VALIDATED: {TradeState.APPROVED, TradeState.REJECTED, TradeState.FAILED},
    TradeState.APPROVED: {TradeState.SUBMITTED, TradeState.CANCELLED, TradeState.FAILED},
    TradeState.SUBMITTED: {TradeState.ACCEPTED, TradeState.FAILED, TradeState.CANCELLED},
    TradeState.ACCEPTED: {TradeState.FILLED, TradeState.CANCELLED, TradeState.FAILED},
    TradeState.FILLED: {TradeState.OPEN, TradeState.CLOSED, TradeState.FAILED},
    TradeState.OPEN: {TradeState.PARTIAL_EXIT, TradeState.CLOSED, TradeState.FAILED},
    TradeState.PARTIAL_EXIT: {TradeState.PARTIAL_EXIT, TradeState.CLOSED, TradeState.FAILED},
    TradeState.CLOSED: {TradeState.ARCHIVED},
    TradeState.REJECTED: {TradeState.ARCHIVED},
    TradeState.CANCELLED: {TradeState.ARCHIVED},
    TradeState.FAILED: {TradeState.ARCHIVED},
    TradeState.ARCHIVED: set(),
}


@dataclass
class TradeStateMachine:
    state: str = TradeState.NEW

    def can_transition(self, new_state: str) -> bool:
        return new_state in ALLOWED_TRANSITIONS.get(self.state, set())

    def transition(self, new_state: str) -> str:
        if not self.can_transition(new_state):
            raise InvalidStateTransition(f"Invalid trade state transition: {self.state} -> {new_state}")
        self.state = new_state
        return self.state
