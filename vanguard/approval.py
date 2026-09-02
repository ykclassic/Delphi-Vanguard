"""Durable human approval records with expiry, atomic consumption, and replay protection."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_urlsafe
from threading import Lock

from vanguard.interfaces import RiskContext, RiskDecision, SignalProposal, Side


def _encode(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Side):
        return value.value
    return value


def _dump(value: object) -> str:
    return json.dumps(value, default=_encode, sort_keys=True, separators=(",", ":"))


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


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
    """SQLite-backed approval store; state survives process and worker restarts."""

    def __init__(self, path: str = "data/vanguard.db") -> None:
        self.path = path
        self._lock = Lock()
        db_path = Path(path)
        if path != ":memory:" and db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            signal_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            risk_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED','EXPIRED')),
            approver TEXT,
            decided_at TEXT
        )""")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_approvals_signal ON approvals(signal_id)")

    def create(self, proposal: SignalProposal, risk: RiskDecision) -> ApprovalRequest:
        if not risk.approved:
            raise ValueError("cannot request approval for a failed risk decision")
        request = ApprovalRequest(token_urlsafe(18), proposal.signal_id, proposal.expires_at, risk)
        with self._lock:
            self._conn.execute(
                "INSERT INTO approvals(approval_id,signal_id,expires_at,risk_json,status) VALUES(?,?,?,?,?)",
                (request.approval_id, request.signal_id, request.expires_at.isoformat(), _dump(asdict(risk)), "PENDING"),
            )
        return request

    def get(self, approval_id: str) -> ApprovalRequest:
        row = self._conn.execute("SELECT approval_id,signal_id,expires_at,risk_json,status FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        if row is None or row[4] != "PENDING":
            raise ValueError("approval is missing or already consumed")
        return ApprovalRequest(row[0], row[1], _dt(row[2]), self._risk_from_json(row[3]))

    def get_decision(self, approval_id: str) -> ApprovalDecision:
        row = self._conn.execute("SELECT approval_id,signal_id,status,approver,decided_at FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        if row is None or row[2] not in {"APPROVED", "REJECTED"} or not row[3] or not row[4]:
            raise ValueError("approval decision is unavailable")
        return ApprovalDecision(row[0], row[1], row[3], row[2] == "APPROVED", _dt(row[4]))

    def get_decision_record(self, approval_id: str) -> ApprovalRequest:
        row = self._conn.execute("SELECT approval_id,signal_id,expires_at,risk_json,status FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        if row is None or row[4] not in {"APPROVED", "REJECTED"}:
            raise ValueError("approval decision record is unavailable")
        return ApprovalRequest(row[0], row[1], _dt(row[2]), self._risk_from_json(row[3]))

    def decide(self, approval_id: str, approver: str, approved: bool, now: datetime | None = None) -> ApprovalDecision:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("decision timestamp must be timezone-aware")
        if not approver.strip():
            raise ValueError("approver identity is required")
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute("SELECT signal_id,expires_at,status FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
                if row is None or row[2] != "PENDING":
                    raise ValueError("approval is missing or already consumed")
                if _dt(row[1]) <= now:
                    self._conn.execute("UPDATE approvals SET status='EXPIRED' WHERE approval_id=? AND status='PENDING'", (approval_id,))
                    self._conn.execute("COMMIT")
                    raise ValueError("approval has expired")
                status = "APPROVED" if approved else "REJECTED"
                updated = self._conn.execute("UPDATE approvals SET status=?,approver=?,decided_at=? WHERE approval_id=? AND status='PENDING'", (status, approver.strip(), now.isoformat(), approval_id))
                if updated.rowcount != 1:
                    raise ValueError("approval was consumed concurrently")
                self._conn.execute("COMMIT")
                return ApprovalDecision(approval_id, row[0], approver.strip(), approved, now)
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                raise

    def _risk_from_json(self, raw: str) -> RiskDecision:
        data = json.loads(raw)
        return RiskDecision(
            approved=bool(data["approved"]),
            reason_codes=tuple(data["reason_codes"]),
            volume=float(data["volume"]),
            risk_amount=float(data["risk_amount"]),
            stop_distance=float(data["stop_distance"]),
            reward_distance=float(data["reward_distance"]),
            risk_reward=float(data["risk_reward"]),
            quote_timestamp=_dt(data["quote_timestamp"]),
            context=RiskContext(**data["context"]),
        )

    def close(self) -> None:
        self._conn.close()
