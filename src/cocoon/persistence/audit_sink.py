"""Audit sink bridge. DOCUMENT.md §3; README "Bridge the audit sink" TODO.

Mirrors every audit record into SQLite (AuditRepository) in addition to the
append-only JSONL stream, so `cocoon report session/daily/export` can query
what actually happened. The JSONL file remains the authoritative forensic
artifact; the DB mirror is best-effort and must never break the trading
loop — a failed mirror write logs a warning and moves on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cocoon.core.logging.audit import AuditLogger
from cocoon.core.logging.setup import get_logger
from cocoon.persistence.db import Database
from cocoon.persistence.repositories import AuditRepository

_logger = get_logger(__name__)


class DbMirroredAuditLogger(AuditLogger):
    def __init__(self, audit_log_path: str | Path, db: Database) -> None:
        super().__init__(audit_log_path)
        self._repo = AuditRepository(db)
        # Continue from whichever sink is further ahead so seq stays a
        # single monotonic series across both.
        self._seq = max(self._seq, self._repo.next_seq() - 1)

    def record(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        entry = super().record(event_type, payload)
        try:
            self._repo.append(
                seq=entry["seq"],
                ts_unix_ms=entry["ts_unix_ms"],
                event_type=event_type,
                # Round-trip through json so non-serializable values are
                # coerced the same way the JSONL sink coerces them.
                payload=json.loads(json.dumps(payload, default=str)),
            )
        except Exception as exc:
            _logger.warning("audit_db_mirror_failed", error=str(exc))
        return entry
