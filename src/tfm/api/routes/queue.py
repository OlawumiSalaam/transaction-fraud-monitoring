"""Triage queue route: prioritised, re-sortable, filterable (FR-14, FR-19).

Spec references: FR-14, FR-19; Addendum §2.3.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from tfm.api.deps import get_config, get_session
from tfm.api.schemas import QueueResponse
from tfm.config.settings import AppConfig
from tfm.services import queue_service

router = APIRouter(prefix="/api", tags=["queue"])


@router.get("/queue")
def get_queue(
    session: Annotated[Session, Depends(get_session)],
    config: Annotated[AppConfig, Depends(get_config)],
    sort: str | None = None,
    level: str | None = None,
    rule: str | None = None,
    min_amount: float | None = None,
) -> QueueResponse:
    return queue_service.list_queue(
        session, config, sort=sort, level=level, rule=rule, min_amount=min_amount
    )
