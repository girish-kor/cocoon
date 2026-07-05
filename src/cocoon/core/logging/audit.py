"""Audit log. Authoritative source: DOCUMENT.md §3 (NFR Auditability).

"Every order, every signal, every config value in effect at decision
time must be reconstructable from logs alone." This is a distinct
append-only JSONL stream from the general application log
(`logging.app_log_path` vs `logging.audit_log_path`, §8.3) because the
audit trail must not be interleaved with, rotated against, or filtered
by ordinary DEBUG/INFO application chatter — it is a compliance/forensic
artifact, not a debugging aid.

Every record includes a monotonically increasing `seq` in addition to a
wall-clock timestamp: wall-clock time alone is not restart-safe evidence
of ordering (NTP adjustment, clock skew across a crash/restart boundary)
and NFR "Determinism" (§3) forbids wall-clock-dependent branching in the
compute path, so record ordering as read back from the file must not
depend on the reader trusting timestamp monotonicity.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, audit_log_path: str | Path) -> None:
        self._path = Path(audit_log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = self._recover_seq()

    def _recover_seq(self) -> int:
        if not self._path.exists():
            return 0
        last_seq = 0
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    last_seq = max(last_seq, int(record.get("seq", 0)))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        return last_seq

    def record(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            entry = {
                "seq": self._seq,
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "ts_unix_ms": int(time.time() * 1000),
                "event_type": event_type,
                "payload": payload,
            }
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str, sort_keys=True))
                fh.write("\n")
                fh.flush()
            return entry

    def record_order(self, order_context: dict[str, Any]) -> dict[str, Any]:
        return self.record("ORDER", order_context)

    def record_signal(self, signal_context: dict[str, Any]) -> dict[str, Any]:
        return self.record("SIGNAL", signal_context)

    def record_config_snapshot(self, resolved_config: dict[str, Any]) -> dict[str, Any]:
        return self.record("CONFIG_SNAPSHOT", resolved_config)

    def record_state_transition(
        self, *, from_state: str, to_state: str, event: str, action: str
    ) -> dict[str, Any]:
        return self.record(
            "STATE_TRANSITION",
            {
                "from_state": from_state,
                "to_state": to_state,
                "event": event,
                "action": action,
            },
        )

    def record_error(self, error_log_record: dict[str, Any]) -> dict[str, Any]:
        return self.record("ERROR", error_log_record)

    def tail(self, n: int = 100) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        with self._path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
        out: list[dict[str, Any]] = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
