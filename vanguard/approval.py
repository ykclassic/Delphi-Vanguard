"""Explicit human approval records with expiry and single-use semantics."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from secrets import token_urlsafe
from threading import Lock

from vanguard.interfaces import RiskDecision, SignalProposal


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    signal_id: str
    expires_at: datetime
    risk: RiskDecision


@dataclass(frozen=True)
class ApprovalDecision:
    approval_id: str
    signal_id: str
    approver: str
    approved: bool
    decided_at: datetime


class ApprovalStore:
    def __init__(self) -> None:
        self._pending: dict[str, ApprovalRequest] = {}
        self._used: set[str] = set()
        self._lock = Lock()

    def create(self, proposal: SignalProposal, risk: RiskDecision) -> ApprovalRequest:
        if not risk.approved:
            raise ValueError("cannot request approval for a failed risk decision")
        request = ApprovalRequest(token_urlsafe(18), proposal.signal_id, proposal.expires_at, risk)
        with self._lock:
            self._pending[request.approval_id] = request
        return request

    def decide(self, approval_id: str, approver: str, approved: bool, now: datetime | None = None) -> ApprovalDecision:
        now = now or datetime.now(timezone.utc)
        if not approver.strip():
            raise ValueError("approver identity is required")
        with self._lock:
            request = self._pending.get(approval_id)
            if request is None or approval_id in self._used:
                raise ValueError("approval is missing or already consumed")
            if request.expires_at <= now:
                self._pending.pop(approval_id, None)
                self._used.add(approval_id)
                raise ValueError("approval has expired")
            self._pending.pop(approval_id)
            self._used.add(approval_id)
        return ApprovalDecision(approval_id, request.signal_id, approver, approved, now)

    def get(self, approval_id: str) -> ApprovalRequest:
        with self._lock:
            request = self._pending.get(approval_id)
            if request is None or approval_id in self._used:
                raise ValueError("approval is missing or already consumed")
            return request
