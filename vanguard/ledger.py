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
        self._conn.execute("CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, event_type TEXT NOT NULL, aggregate_id TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL UNIQUE)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events(aggregate_id, created_at)")
        self._conn.commit()

    def append(self, event_type: str, aggregate_id: str, payload: Mapping[str, object]) -> str:
        event_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = sha256(body.encode()).hexdigest()
        with self._lock:
            self._conn.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)", (event_id, created_at, event_type, aggregate_id, body, digest))
            self._conn.commit()
        return event_id

    def events(self, aggregate_id: str | None = None) -> list[dict[str, object]]:
        query = "SELECT event_id, created_at, event_type, aggregate_id, payload_json, payload_hash FROM events"
        params: tuple[object, ...] = ()
        if aggregate_id is not None:
            query += " WHERE aggregate_id = ?"
            params = (aggregate_id,)
        query += " ORDER BY created_at, event_id"
        rows = self._conn.execute(query, params).fetchall()
        return [{"event_id": r[0], "created_at": r[1], "event_type": r[2], "aggregate_id": r[3], "payload": json.loads(r[4]), "payload_hash": r[5]} for r in rows]

    def close(self) -> None:
        self._conn.close()
