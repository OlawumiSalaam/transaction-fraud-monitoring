"""Decision reconstruction from the audit log alone (M8, NFR-3).

``reconstruct_decision`` reads a single ``disposition_recorded`` row and validates
its ``DecisionSnapshot`` payload back into typed objects. It is **pure
deserialization**: it invokes no rule engine, recommendation policy, explanation
generation, grounding gate, or configuration — and reads no operational table
(``cases``, ``dispositions``, ``transactions``, ``rule_hits``). The audit log is
the sole source, which is what makes a decision reconstructable after the fact even
if that decision logic later changes.

Spec references: FR-20, NFR-3; Addendum §3; Release Plan §M8.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from tfm.audit.log import AuditEventType
from tfm.audit.snapshot import (
    DecisionSnapshot,
    DispositionSnapshot,
    Provenance,
    RoutingSnapshot,
)
from tfm.explanation.explainer import Explanation
from tfm.persistence.models import AuditLog
from tfm.recommendation.policy import Recommendation
from tfm.schema.evidence import EvidencePackage


class DecisionNotReconstructable(Exception):
    """No ``disposition_recorded`` event exists for the case."""


class ReconstructedDecision(BaseModel):
    """The decision rebuilt from the audit log — the five reproduced objects.

    The case's *current* status, the canonical transaction/account rows, and the
    configuration are intentionally NOT here: they are live references, not part
    of the frozen decision.
    """

    model_config = ConfigDict(frozen=True)

    case_id: str
    txn_id: str
    analyst_id: str
    recorded_at: str
    evidence: EvidencePackage
    recommendation: Recommendation
    explanation: Explanation
    disposition: DispositionSnapshot
    routing: RoutingSnapshot
    provenance: Provenance


def reconstruct_decision(session: Session, case_id: str) -> ReconstructedDecision:
    """Rebuild a decision from the ``disposition_recorded`` audit event alone.

    Reads only ``audit_log``. Raises ``DecisionNotReconstructable`` if the case has
    no recorded disposition. Performs no recomputation of any decision component.
    """
    record = session.scalars(
        select(AuditLog)
        .where(
            AuditLog.case_id == case_id,
            AuditLog.event_type == AuditEventType.DISPOSITION_RECORDED.value,
        )
        .order_by(AuditLog.created_at.desc())
    ).first()
    if record is None:
        raise DecisionNotReconstructable(case_id)

    # Pure deserialization — no decision logic, no config, no operational tables.
    snapshot = DecisionSnapshot.model_validate(record.payload)
    return ReconstructedDecision(
        case_id=snapshot.case_id,
        txn_id=snapshot.txn_id,
        analyst_id=snapshot.analyst_id,
        recorded_at=snapshot.recorded_at,
        evidence=snapshot.evidence,
        recommendation=snapshot.recommendation,
        explanation=snapshot.explanation,
        disposition=snapshot.disposition,
        routing=snapshot.routing,
        provenance=snapshot.provenance,
    )
