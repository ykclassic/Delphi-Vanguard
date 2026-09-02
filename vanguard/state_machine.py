"""Fail-closed trade lifecycle with explicit legal transitions."""
from __future__ import annotations

from enum import Enum
from threading import RLock


class TradeState(str, Enum):
    NO_SIGNAL = "NO_SIGNAL"
    SIGNAL_DETECTED = "SIGNAL_DETECTED"
    RISK_VALIDATED = "RISK_VALIDATED"
    PENDING_HUMAN_APPROVAL = "PENDING_HUMAN_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTION_PENDING = "EXECUTION_PENDING"
    PRE_EXECUTION_REVALIDATION = "PRE_EXECUTION_REVALIDATION"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    POSITION_OPEN = "POSITION_OPEN"
    CLOSED = "CLOSED"
    EMERGENCY_CLOSED = "EMERGENCY_CLOSED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


_ALLOWED = {
    TradeState.NO_SIGNAL: {TradeState.SIGNAL_DETECTED},
    TradeState.SIGNAL_DETECTED: {TradeState.RISK_VALIDATED, TradeState.REJECTED, TradeState.EXPIRED, TradeState.FAILED},
    TradeState.RISK_VALIDATED: {TradeState.PENDING_HUMAN_APPROVAL, TradeState.REJECTED, TradeState.EXPIRED, TradeState.FAILED},
    TradeState.PENDING_HUMAN_APPROVAL: {TradeState.APPROVED, TradeState.REJECTED, TradeState.EXPIRED},
    TradeState.APPROVED: {TradeState.EXECUTION_PENDING, TradeState.EXPIRED, TradeState.REJECTED},
    TradeState.EXECUTION_PENDING: {TradeState.PRE_EXECUTION_REVALIDATION, TradeState.FAILED, TradeState.EXPIRED},
    TradeState.PRE_EXECUTION_REVALIDATION: {TradeState.ORDER_SUBMITTED, TradeState.REJECTED, TradeState.EXPIRED, TradeState.FAILED},
    TradeState.ORDER_SUBMITTED: {TradeState.ORDER_CONFIRMED, TradeState.FAILED},
    TradeState.ORDER_CONFIRMED: {TradeState.POSITION_OPEN, TradeState.CLOSED, TradeState.FAILED},
    TradeState.POSITION_OPEN: {TradeState.CLOSED, TradeState.EMERGENCY_CLOSED, TradeState.FAILED},
    TradeState.REJECTED: set(), TradeState.CLOSED: set(), TradeState.EMERGENCY_CLOSED: set(),
    TradeState.EXPIRED: set(), TradeState.FAILED: set(),
}


class InvalidTransition(ValueError):
    pass


class TradeStateMachine:
    def __init__(self) -> None:
        self._state = TradeState.NO_SIGNAL
        self._lock = RLock()

    @property
    def state(self) -> TradeState:
        with self._lock:
            return self._state

    def transition(self, new_state: TradeState) -> TradeState:
        with self._lock:
            if new_state not in _ALLOWED[self._state]:
                raise InvalidTransition(f"{self._state.value} -> {new_state.value} is not allowed")
            self._state = new_state
            return self._state

    def reset(self) -> None:
        with self._lock:
            self._state = TradeState.NO_SIGNAL
