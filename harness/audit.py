"""Hash-chained append-only audit log.

Every event the harness emits is appended to a single table with a
SHA-256 hash chain. Each row's hash includes the previous row's hash,
which means a regulator (or an internal auditor) can verify the chain
end-to-end without trusting the database administrator.

The chain alignment is deliberate: EU AI Act Article 12 requires
high-risk systems to "automatically record events" over their lifetime
and to make those logs available for inspection. A hash-chained log is
the cheapest way to make that record tamper-evident.

The schema is intentionally narrow. The richer payload lives in the
`payload` JSONB column rather than columns-per-field so the harness can
evolve event shapes without migrations. The trade-off is that ad-hoc
SQL on the audit log is less ergonomic; we accept that because the log
is for after-the-fact investigation, not real-time querying.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def _canonical_json(payload: dict[str, Any]) -> bytes:
    """Stable JSON serialisation for hashing.

    Hashing requires byte-identical input across runs. We sort keys and
    use the JSON ``separators`` form to remove ambiguous whitespace.
    Trade-off: we lose the ability to embed pretty-printed payloads in
    the column, but the chain integrity is more important.
    """

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")


def chain_hash(previous_hash: str, payload: dict[str, Any]) -> str:
    """Compute the next hash in the chain.

    SHA-256 chosen over BLAKE3 etc. for ubiquity in regulator tooling.
    32-byte output is enough collision resistance for an audit log.
    """

    h = hashlib.sha256()
    h.update(previous_hash.encode("ascii"))
    h.update(_canonical_json(payload))
    return h.hexdigest()


GENESIS_HASH = "0" * 64
"""All-zero hash that anchors the start of a fresh chain. Anyone verifying
the log can recognise the genesis row and start hashing forward from it."""


class AuditEvent(BaseModel):
    """One row in the audit log.

    ``run_id`` ties events together within a single agent invocation;
    queries that reconstruct a run filter on ``run_id`` ordered by
    ``sequence``.
    """

    run_id: str
    sequence: int = Field(ge=0)
    timestamp: datetime
    event_type: str
    payload: dict[str, Any]
    previous_hash: str
    hash: str

    @classmethod
    def new(
        cls,
        run_id: str,
        sequence: int,
        event_type: str,
        payload: dict[str, Any],
        previous_hash: str,
    ) -> "AuditEvent":
        ts = datetime.now(tz=timezone.utc)
        body_for_hash = {
            "run_id": run_id,
            "sequence": sequence,
            "timestamp": ts.isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        h = chain_hash(previous_hash, body_for_hash)
        return cls(
            run_id=run_id,
            sequence=sequence,
            timestamp=ts,
            event_type=event_type,
            payload=payload,
            previous_hash=previous_hash,
            hash=h,
        )


class AuditWriter:
    """Abstract writer interface.

    Two implementations ship: ``InMemoryAuditWriter`` (for tests and the
    quickstart) and ``PostgresAuditWriter`` (for production). Sites can
    add their own (e.g. S3-backed, Kafka-backed) by subclassing.
    """

    def append(self, event: AuditEvent) -> None:
        raise NotImplementedError

    def latest_hash(self, run_id: str) -> str:
        raise NotImplementedError


class InMemoryAuditWriter(AuditWriter):
    """In-memory writer. Not durable. Useful for tests and demos."""

    def __init__(self):
        self._events: dict[str, list[AuditEvent]] = {}

    def append(self, event: AuditEvent) -> None:
        self._events.setdefault(event.run_id, []).append(event)

    def latest_hash(self, run_id: str) -> str:
        events = self._events.get(run_id, [])
        return events[-1].hash if events else GENESIS_HASH

    def events(self, run_id: str) -> list[AuditEvent]:
        return list(self._events.get(run_id, []))


def verify_chain(events: list[AuditEvent]) -> bool:
    """Verify a sequence of events forms a valid hash chain.

    Returns True if every event's ``hash`` matches the recomputed value
    and the ``previous_hash`` references match. Returns False on the
    first mismatch. Sites use this both during routine audits and during
    incident investigation.
    """

    expected_prev = GENESIS_HASH
    for ev in events:
        if ev.previous_hash != expected_prev:
            return False
        body = {
            "run_id": ev.run_id,
            "sequence": ev.sequence,
            "timestamp": ev.timestamp.isoformat(),
            "event_type": ev.event_type,
            "payload": ev.payload,
        }
        recomputed = chain_hash(expected_prev, body)
        if ev.hash != recomputed:
            return False
        expected_prev = ev.hash
    return True


class AuditLogger:
    """Convenience wrapper that maintains run state.

    Callers usually instantiate one logger per run, pass it through the
    harness, and let the logger manage sequence numbers and chain heads.
    """

    def __init__(self, run_id: str, writer: AuditWriter):
        self._run_id = run_id
        self._writer = writer
        self._sequence = 0

    def emit(self, event_type: str, payload: dict[str, Any]) -> AuditEvent:
        prev = self._writer.latest_hash(self._run_id)
        event = AuditEvent.new(
            run_id=self._run_id,
            sequence=self._sequence,
            event_type=event_type,
            payload=payload,
            previous_hash=prev,
        )
        self._writer.append(event)
        self._sequence += 1
        return event
