"""Health route.

Liveness and readiness for the online-path service. No business logic; used by
docker-compose, CI, and the Streamlit workspace to confirm the API is reachable
and its configuration validated at startup.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from tfm.api.deps import get_config, get_session, get_settings
from tfm.config.settings import AppConfig, Settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(
    settings: Annotated[Settings, Depends(get_settings)],
    config: Annotated[AppConfig, Depends(get_config)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    """Return service status. Config is validated at startup; DB is pinged here."""

    try:
        session.execute(text("SELECT 1"))
        db_reachable = True
    except Exception:
        db_reachable = False

    return {
        "status": "ok",
        "app_env": settings.app_env,
        "config_loaded": config is not None,
        "db_reachable": db_reachable,
    }
