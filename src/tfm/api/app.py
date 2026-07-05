"""FastAPI application factory.

Wires the online-path service scaffold: structured logging, validated
configuration (fail-fast at startup), the database session factory, and the
audit writer. No architectural-layer routes are registered yet — only health.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from tfm.api.routes import cases as cases_route
from tfm.api.routes import disposition as disposition_route
from tfm.api.routes import health as health_route
from tfm.api.routes import queue as queue_route
from tfm.audit.log import AuditWriter
from tfm.config.settings import Settings, get_settings, load_config
from tfm.observability.logging import configure_logging, get_logger
from tfm.persistence.db import create_db_engine, create_session_factory
from tfm.services.errors import ServiceError


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


def configure_app(app: FastAPI) -> None:
    """Register routers and the uniform error handler (shared by app + tests)."""
    app.include_router(health_route.router)
    app.include_router(queue_route.router)
    app.include_router(cases_route.router)
    app.include_router(disposition_route.router)

    @app.exception_handler(ServiceError)
    async def _service_error(request: Request, exc: ServiceError) -> JSONResponse:
        # Uniform error body (Addendum §2.5). LLM issues never reach here — they
        # degrade to the templated pathway inside the explainer (NFR-2, FR-12).
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )


def create_app() -> FastAPI:
    app = FastAPI(
        title="Transaction Fraud Monitoring API",
        version="0.0.0",
        lifespan=lifespan,
    )
    configure_app(app)
    return app


app = create_app()
