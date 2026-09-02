"""Durable append-only SQLite event ledger."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Mapping
from uuid import uuid4


class SQLiteLedger:
    def __init__(self, path: str = "data/vanguard.db") -> None:
        self.path = path
        self._lock = Lock()
        db_path = Path(path)
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "event_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, event_type TEXT NOT NULL, "
            "aggregate_id TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL UNIQUE, "
            "idempotency_key TEXT UNIQUE)"
        )
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(events)").fetchall()}
        if "idempotency_key" not in columns:
            self._conn.execute("ALTER TABLE events ADD COLUMN idempotency_key TEXT")
        self._conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_idempotency ON events(idempotency_key) "
            "WHERE idempotency_key IS NOT NULL"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events(aggregate_id, created_at)")
        self._conn.commit()

    def append(self, event_type: str, aggregate_id: str, payload: Mapping[str, object]) -> str:
        event_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = sha256(body.encode()).hexdigest()
        with self._lock:
            self._conn.execute(
                "INSERT INTO events(event_id, created_at, event_type, aggregate_id, payload_json, payload_hash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, created_at, event_type, aggregate_id, body, digest),
            )
            self._conn.commit()
        return event_id

    def append_once(
        self,
        event_type: str,
        aggregate_id: str,
        payload: Mapping[str, object],
        idempotency_key: str,
    ) -> str:
        """Append an event exactly once for the supplied idempotency key.

        Reusing a key returns the original event ID. A reused key with a
        different event payload/type/aggregate is rejected rather than silently
        conflating two distinct operations.
        """
        if not idempotency_key:
            raise ValueError("idempotency_key must be non-empty")
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = sha256(body.encode()).hexdigest()
        with self._lock:
            existing = self._conn.execute(
                "SELECT event_id, event_type, aggregate_id, payload_hash "
                "FROM events WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                event_id, existing_type, existing_aggregate, existing_hash = existing
                if (existing_type, existing_aggregate, existing_hash) != (
                    event_type,
                    aggregate_id,
                    digest,
                ):
                    raise ValueError("idempotency_key already identifies a different event")
                return str(event_id)

            event_id = str(uuid4())
            created_at = datetime.now(timezone.utc).isoformat()
            try:
                self._conn.execute(
                    "INSERT INTO events(event_id, created_at, event_type, aggregate_id, payload_json, payload_hash, idempotency_key) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (event_id, created_at, event_type, aggregate_id, body, digest, idempotency_key),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.rollback()
                existing = self._conn.execute(
                    "SELECT event_id, event_type, aggregate_id, payload_hash "
                    "FROM events WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing is None:
                    raise
                existing_id, existing_type, existing_aggregate, existing_hash = existing
                if (existing_type, existing_aggregate, existing_hash) != (
                    event_type,
                    aggregate_id,
                    digest,
                ):
                    raise ValueError("idempotency_key already identifies a different event")
                return str(existing_id)
            return event_id

    def events(self, aggregate_id: str | None = None) -> list[dict[str, object]]:
        query = "SELECT event_id, created_at, event_type, aggregate_id, payload_json, payload_hash FROM events"
        params: tuple[object, ...] = ()
        if aggregate_id is not None:
            query += " WHERE aggregate_id = ?"
            params = (aggregate_id,)
        query += " ORDER BY created_at, event_id"
        rows = self._conn.execute(query, params).fetchall()
        return [
            {
                "event_id": r[0],
                "created_at": r[1],
                "event_type": r[2],
                "aggregate_id": r[3],
                "payload": json.loads(r[4]),
                "payload_hash": r[5],
            }
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()
