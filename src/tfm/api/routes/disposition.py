"""Disposition route: record the analyst's decision + route + audit (M7).

The analyst is the sole decider; identity comes from the ``X-Analyst-Id`` header
(default from settings) purely to populate the audit trail (Addendum §2.2).

Spec references: FR-16, FR-17, FR-18, FR-20; Addendum §2.3, §2.4.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from tfm.api.deps import get_audit_writer, get_config, get_session, get_settings
from tfm.api.schemas import DispositionRequest, DispositionResponse
from tfm.audit.log import AuditWriter
from tfm.config.settings import AppConfig, Settings
from tfm.services import disposition_service

router = APIRouter(prefix="/api/cases", tags=["disposition"])


@router.post("/{case_id}/disposition")
def post_disposition(
    case_id: str,
    body: DispositionRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    config: Annotated[AppConfig, Depends(get_config)],
    audit_writer: Annotated[AuditWriter, Depends(get_audit_writer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DispositionResponse:
    analyst_id = request.headers.get("X-Analyst-Id") or settings.default_analyst_id
    return disposition_service.record_disposition(
        session,
        config,
        audit_writer,
        case_id=case_id,
        action=body.action,
        reason_code=body.reason_code,
        rationale=body.rationale,
        follow_up=body.follow_up,
        analyst_id=analyst_id,
    )
