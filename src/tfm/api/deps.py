"""FastAPI dependency wiring.

Provides the shared infrastructure dependencies (settings, validated config, a
DB session, the audit writer) read from ``app.state``. Architectural-layer
services (scorer, rule engine, assembler, recommendation policy, explainer,
grounding gate, disposition service) are injected here as they are implemented in
their milestones. None exist yet.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from tfm.audit.log import AuditWriter
from tfm.config.settings import AppConfig, Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_config(request: Request) -> AppConfig:
    return request.app.state.config  # type: ignore[no-any-return]


def get_audit_writer(request: Request) -> AuditWriter:
    return request.app.state.audit_writer  # type: ignore[no-any-return]


def get_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
