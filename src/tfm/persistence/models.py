"""Relational models mapping the approved DB schema (Addendum §3) to the
Canonical Evidence Schema (§6.2).

These are table/column definitions only. They contain no scoring, rule,
assembly, recommendation, or workflow logic. Two architectural invariants are
expressed at this layer:

* ``dispositions.reason_code`` is ``NOT NULL`` — the rationale engagement floor.
* ``audit_log`` is append-only — enforced additionally by the insert-only Audit
  Writer and, in Postgres, a trigger created by the initial migration.

JSON columns use ``JSONB`` on Postgres and portable ``JSON`` on SQLite so the
same models back both the running app and the test suite.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSONB on Postgres, JSON elsewhere (e.g. SQLite for tests).
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class Account(Base):
    """Canonical entity: Account (the entity whose behaviour is judged)."""

    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    first_seen_step: Mapped[int | None] = mapped_column(nullable=True)
    # PaySim: merchant destinations ('M' prefix) carry no balance signal.
    is_merchant: Mapped[bool] = mapped_column(Boolean, default=False)


class Counterparty(Base):
    """Canonical entity: Counterparty / beneficiary (the other side)."""

    __tablename__ = "counterparties"

    counterparty_id: Mapped[str] = mapped_column(String, primary_key=True)
    is_merchant: Mapped[bool] = mapped_column(Boolean, default=False)


class Transaction(Base):
    """Canonical entity: Transaction (the core event)."""

    __tablename__ = "transactions"

    txn_id: Mapped[str] = mapped_column(String, primary_key=True)
    step: Mapped[int] = mapped_column(nullable=False)
    event_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric, nullable=False)

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False)
    counterparty_id: Mapped[str] = mapped_column(
        ForeignKey("counterparties.counterparty_id"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String, nullable=False)

    bal_orig_before: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    bal_orig_after: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    bal_dest_before: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    bal_dest_after: Mapped[float | None] = mapped_column(Numeric, nullable=True)

    # PaySim isFlaggedFraud: ingested for provenance, EXCLUDED from features (§6.5, §9).
    sim_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    label: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        # Account-linked, time-ordered history: the load-bearing structural
        # requirement of the canonical schema (§6.2).
        Index("ix_transactions_account_ts", "account_id", "event_ts"),
        Index("ix_transactions_counterparty", "counterparty_id"),
        Index("ix_transactions_event_ts", "event_ts"),
    )


class ModelVersion(Base):
    """Model provenance. Only a leakage-gate-passing version is eligible (FR-4)."""

    __tablename__ = "model_versions"

    model_version_id: Mapped[str] = mapped_column(String, primary_key=True)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    feature_set: Mapped[str | None] = mapped_column(String, nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)  # FR-22
    calibration: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)  # FR-23
    leakage_verdict: Mapped[str | None] = mapped_column(String, nullable=True)  # FR-26
    df1_result: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)  # DF-1
    artifact_path: Mapped[str | None] = mapped_column(String, nullable=True)


class Case(Base):
    """The assembled case record and its operational state."""

    __tablename__ = "cases"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    txn_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.txn_id"), nullable=False, unique=True
    )
    model_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_versions.model_version_id"), nullable=True
    )

    score: Mapped[float] = mapped_column(Numeric, nullable=False)
    score_band: Mapped[str] = mapped_column(String, nullable=False)
    recommendation_action: Mapped[str] = mapped_column(String, nullable=False)
    recommendation_confidence: Mapped[str] = mapped_column(String, nullable=False)
    recommendation_basis: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    uncertainty_flag: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Assembled evidence snapshot = "evidence shown" for the audit trail (FR-2, FR-20).
    evidence: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)

    explanation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation_pathway: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, nullable=False)  # queued|pending|cleared|escalated
    queue_priority: Mapped[float] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    rule_hits: Mapped[list[RuleHit]] = relationship(back_populates="case")
    dispositions: Mapped[list[Disposition]] = relationship(back_populates="case")

    __table_args__ = (
        Index("ix_cases_status_priority", "status", "queue_priority"),
        Index("ix_cases_score", "score"),
    )


class RuleHit(Base):
    """A deterministic rule firing, preserved as auditable evidence."""

    __tablename__ = "rule_hits"

    rule_hit_id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    rule_id: Mapped[str] = mapped_column(String, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    case: Mapped[Case] = relationship(back_populates="rule_hits")

    __table_args__ = (Index("ix_rule_hits_case", "case_id"),)


class Disposition(Base):
    """The human decision record. The human is the sole decider (FR-16)."""

    __tablename__ = "dispositions"

    disposition_id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)  # clear|hold|escalate

    # Engagement FLOOR (architectural): a disposition cannot exist without a
    # reason code. Additionally enforced in the Disposition Service. [FR-17 elevated]
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    deviated_from_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    follow_up: Mapped[str | None] = mapped_column(Text, nullable=True)

    analyst_id: Mapped[str] = mapped_column(String, nullable=False)  # FR-20
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    case: Mapped[Case] = relationship(back_populates="dispositions")

    __table_args__ = (Index("ix_dispositions_case", "case_id"),)


class AuditLog(Base):
    """Append-only audit record. A decision must be reconstructable from this
    table alone (FR-20, NFR-3). Append-only is additionally enforced by the
    insert-only Audit Writer and a Postgres trigger (initial migration)."""

    __tablename__ = "audit_log"

    audit_id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (Index("ix_audit_log_case_created", "case_id", "created_at"),)
