"""Case routes: the assembled case view, evidence drill-down, and audit read."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from tfm.api.deps import get_session, get_settings
from tfm.api.schemas import CaseView, DrillDownResponse
from tfm.config.settings import Settings
from tfm.persistence.models import AuditLog
from tfm.services import case_service

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("/{case_id}")
def get_case(
    case_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CaseView:
    return case_service.get_case_view(session, case_id, llm_enabled=settings.llm_enabled)


@router.get("/{case_id}/evidence/{element_id}")
def get_evidence(
    case_id: str,
    element_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> DrillDownResponse:
    return case_service.drill_down(session, case_id, element_id)


@router.get("/{case_id}/audit")
def get_audit(
    case_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, object]]:
    records = session.scalars(
        select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.created_at)
    ).all()
    return [
        {"event_type": r.event_type, "payload": r.payload, "created_at": r.created_at.isoformat()}
        for r in records
    ]
