"""Audit Writer (scaffold).

Responsibilities: write an append-only per-case record to
``audit_log``. This scaffold provides the append mechanism and the append-only
guarantee at the application layer. It deliberately does NOT construct audit
payloads: what a record contains (evidence shown, score, rule hits,
recommendation, disposition, rationale, explanation pathway, identity,
timestamps) is assembled by the milestones that produce those artifacts
and passed in here.

Invariants:
* Append-only. This class exposes ``append`` and nothing else — no update, no
  delete. Postgres additionally enforces this with a trigger (initial migration),
  and production revokes UPDATE/DELETE at the database role level.
* A decision must be reconstructable from ``audit_log`` alone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.orm import Session

from tfm.persistence.models import AuditLog


class AuditEventType(StrEnum):
    """The per-case audit events written along the online path."""

    CASE_ASSEMBLED = "case_assembled"
    EXPLANATION_GENERATED = "explanation_generated"
    DISPOSITION_RECORDED = "disposition_recorded"


class AuditWriter:
    """Insert-only writer for the append-only audit log."""

    def append(
        self,
        session: Session,
        case_id: str,
        event_type: AuditEventType,
        payload: dict[str, object],
    ) -> AuditLog:
        """Append one audit record. Never updates or deletes."""

        record = AuditLog(
            audit_id=str(uuid.uuid4()),
            case_id=case_id,
            event_type=event_type.value,
            payload=payload,
            created_at=datetime.now(UTC),
        )
        session.add(record)
        session.flush()
        return record
