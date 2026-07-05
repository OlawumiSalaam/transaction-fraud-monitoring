"""Disposition service: the human decision boundary (FR-16, FR-17, FR-18, FR-20).

The analyst is the sole decider. This service enforces the engagement floor (a
reason code is mandatory), the rationale-graduation policy (richer rationale for
escalate / deviation), computes the deviation flag, routes the case as a **state
change only** (no financial action), and writes the **complete decision snapshot**
to the append-only audit log at write time (FR-20; the demo depends on this).

Spec references: FR-16, FR-17, FR-18, FR-20; §11.2; Addendum §2.4, §4.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from tfm.api.schemas import DispositionResponse
from tfm.audit.log import AuditEventType, AuditWriter
from tfm.config.settings import DISPOSITION_ACTIONS, AppConfig
from tfm.persistence.models import Case as CaseModel
from tfm.persistence.models import Disposition as DispositionModel
from tfm.services.errors import (
    CaseAlreadyDispositioned,
    CaseNotFound,
    InvalidAction,
    RationaleFloorRequired,
    RationaleRequiredForAction,
)

_ROUTING = {
    "clear": ("cleared", "closed"),
    "hold": ("pending", "pending review"),
    "escalate": ("escalated", "escalation"),
}
_OPEN_STATUSES = ("queued", "pending")


def record_disposition(
    session: Session,
    config: AppConfig,
    audit_writer: AuditWriter,
    *,
    case_id: str,
    action: str,
    reason_code: str,
    rationale: str | None,
    follow_up: str | None,
    analyst_id: str,
) -> DispositionResponse:
    """Record the analyst's disposition, route the case, and audit the full snapshot."""
    if action not in DISPOSITION_ACTIONS:
        raise InvalidAction(f"unknown disposition action: {action}", {"action": action})

    # Engagement floor (architectural): a disposition cannot exist without a reason code.
    if not reason_code or not reason_code.strip():
        raise RationaleFloorRequired("a reason code is required for every disposition")

    case = session.get(CaseModel, case_id)
    if case is None:
        raise CaseNotFound(f"case not found: {case_id}", {"case_id": case_id})
    if case.status not in _OPEN_STATUSES:
        raise CaseAlreadyDispositioned(
            f"case already dispositioned: {case_id} (status={case.status})",
            {"case_id": case_id, "status": case.status},
        )

    deviated = action != case.recommendation_action
    needs_rationale = action in config.governance.richer_rationale_required_for_actions or (
        deviated and config.governance.richer_rationale_required_on_deviation
    )
    if needs_rationale and (rationale is None or not rationale.strip()):
        raise RationaleRequiredForAction(
            f"a rationale is required for '{action}' (escalate or deviation)",
            {"action": action, "deviated_from_recommendation": deviated},
        )

    status, routed_to = _ROUTING[action]
    resolved_follow_up = follow_up if action == "hold" else None
    now = datetime.now(UTC)

    case.status = status
    disposition = DispositionModel(
        disposition_id=str(uuid.uuid4()),
        case_id=case_id,
        action=action,
        reason_code=reason_code,
        rationale=rationale,
        deviated_from_recommendation=deviated,
        follow_up=resolved_follow_up,
        analyst_id=analyst_id,
        created_at=now,
    )
    session.add(disposition)

    # Complete decision snapshot at write time (FR-20). A decision is reconstructable
    # from this single record: evidence shown, score status, recommendation, the
    # disposition + rationale + deviation, explanation pathway, identity, timestamp.
    payload: dict[str, object] = {
        "case_id": case_id,
        "evidence_shown": case.evidence,
        "score_status": {
            "available": case.score is not None,
            "score_band": case.score_band,
            "score": float(case.score) if case.score is not None else None,
        },
        "recommendation": {
            "action": case.recommendation_action,
            "confidence": case.recommendation_confidence,
            "basis": case.recommendation_basis,
            "uncertainty_flag": case.uncertainty_flag,
        },
        "disposition": {
            "action": action,
            "reason_code": reason_code,
            "rationale": rationale,
            "deviated_from_recommendation": deviated,
            "follow_up": resolved_follow_up,
        },
        "explanation_pathway": case.explanation_pathway,
        "analyst_id": analyst_id,
        "recorded_at": now.isoformat(),
    }
    audit_writer.append(session, case_id, AuditEventType.DISPOSITION_RECORDED, payload)
    session.flush()

    return DispositionResponse(
        disposition_id=disposition.disposition_id,
        case_id=case_id,
        action=action,
        deviated_from_recommendation=deviated,
        routed_to=routed_to,
        status=status,
        recorded_at=now,
    )
