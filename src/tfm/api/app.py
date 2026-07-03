"""FastAPI application factory.

Wires the online-path service scaffold: structured logging, validated
configuration (fail-fast at startup), the database session factory, and the
audit writer. No architectural-layer routes are registered yet — only health.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from tfm.api.routes import health as health_route
from tfm.audit.log import AuditWriter
from tfm.config.settings import Settings, get_settings, load_config
from tfm.observability.logging import configure_logging, get_logger
from tfm.persistence.db import create_db_engine, create_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()
    configure_logging(settings)
    log = get_logger("tfm.api")

    # Fail-fast: invalid governance config aborts startup (register risk R13).
    config = load_config(settings)

    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    app.state.settings = settings
    app.state.config = config
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.audit_writer = AuditWriter()

    log.info("api.startup", app_env=settings.app_env, llm_enabled=settings.llm_enabled)
    try:
        yield
    finally:
        engine.dispose()
        log.info("api.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Transaction Fraud Monitoring API",
        version="0.0.0",
        lifespan=lifespan,
    )
    app.include_router(health_route.router)
    return app


app = create_app()
