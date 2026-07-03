"""Audit Writer scaffold tests.

Verifies the append mechanism and the append-only guarantee at the application
layer. Append-only is additionally enforced in Postgres by a trigger (initial
migration) and in production by revoking UPDATE/DELETE at the role level.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tfm.audit.log import AuditEventType, AuditWriter
from tfm.persistence.models import Account, AuditLog, Case, Counterparty, Transaction


def _make_case(session: Session, case_id: str = "case-1") -> Case:
    """Insert the minimal parent chain so the audit FK is satisfied."""

    now = datetime.now(UTC)
    session.add(Account(account_id="A1", is_merchant=False))
    session.add(Counterparty(counterparty_id="C1", is_merchant=False))
    session.add(
        Transaction(
            txn_id="T1",
            step=1,
            event_ts=now,
            type="TRANSFER",
            amount=100.0,
            account_id="A1",
            counterparty_id="C1",
            direction="outbound",
            sim_flagged=False,
            label=False,
        )
    )
    case = Case(
        case_id=case_id,
        txn_id="T1",
        score=0.5,
        score_band="borderline",
        recommendation_action="hold",
        recommendation_confidence="low",
        recommendation_basis={"score_band": "borderline", "rule_ids": []},
        uncertainty_flag=True,
        evidence={"placeholder": True},
        status="queued",
        queue_priority=0.5,
        created_at=now,
    )
    session.add(case)
    session.flush()
    return case


def test_append_writes_and_roundtrips(session: Session) -> None:
    _make_case(session)
    writer = AuditWriter()

    payload = {"score": 0.5, "recommendation": "hold", "analyst_id": "demo-analyst"}
    record = writer.append(session, "case-1", AuditEventType.DISPOSITION_RECORDED, payload)
    session.commit()

    rows = session.execute(select(AuditLog).where(AuditLog.case_id == "case-1")).scalars().all()
    assert len(rows) == 1
    assert rows[0].audit_id == record.audit_id
    assert rows[0].event_type == "disposition_recorded"
    assert rows[0].payload == payload  # record-level reconstructability


def test_multiple_appends_accumulate(session: Session) -> None:
    _make_case(session)
    writer = AuditWriter()
    writer.append(session, "case-1", AuditEventType.CASE_ASSEMBLED, {"n": 1})
    writer.append(session, "case-1", AuditEventType.EXPLANATION_GENERATED, {"n": 2})
    session.commit()

    count = len(
        session.execute(select(AuditLog).where(AuditLog.case_id == "case-1")).scalars().all()
    )
    assert count == 2


def test_writer_is_append_only() -> None:
    """The writer exposes append and nothing that mutates or deletes records."""

    writer = AuditWriter()
    public = {name for name in dir(writer) if not name.startswith("_")}
    assert public == {"append"}
    for forbidden in ("update", "delete", "remove", "edit"):
        assert not hasattr(writer, forbidden)
