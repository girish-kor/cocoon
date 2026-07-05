"""Audit repository. DOCUMENT.md §3.

Mirrors the append-only JSONL audit stream into SQLite for queryable
forensic reconstruction. Both sinks carry the same monotonic `seq`.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from cocoon.persistence.db import Database
from cocoon.persistence.models import AuditEvent


class AuditRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def next_seq(self) -> int:
        with self._db.session() as s:
            current = s.scalar(select(func.max(AuditEvent.seq)))
            return int(current or 0) + 1

    def append(self, *, seq: int, ts_unix_ms: int, event_type: str, payload: dict) -> int:
        with self._db.session() as s:
            event = AuditEvent(
                seq=seq,
                ts_unix_ms=ts_unix_ms,
                event_type=event_type,
                payload=payload,
            )
            s.add(event)
            s.flush()
            return int(event.id)

    def tail(self, n: int = 100) -> list[dict[str, Any]]:
        with self._db.session() as s:
            rows = s.scalars(
                select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(n)
            ).all()
            return [
                {
                    "seq": r.seq,
                    "ts_unix_ms": r.ts_unix_ms,
                    "event_type": r.event_type,
                    "payload": r.payload,
                }
                for r in reversed(rows)
            ]

    def by_type(self, event_type: str, n: int = 100) -> list[dict[str, Any]]:
        with self._db.session() as s:
            rows = s.scalars(
                select(AuditEvent)
                .where(AuditEvent.event_type == event_type)
                .order_by(AuditEvent.seq.desc())
                .limit(n)
            ).all()
            return [
                {
                    "seq": r.seq,
                    "ts_unix_ms": r.ts_unix_ms,
                    "event_type": r.event_type,
                    "payload": r.payload,
                }
                for r in reversed(rows)
            ]
