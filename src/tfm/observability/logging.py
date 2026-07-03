"""Structured application logging.

This configures process/application logging only. It is deliberately separate
from the audit log: the audit record [FR-20] is a durable domain artifact written
to the ``audit_log`` table by the Audit Writer, not a log line. Application logs
are operational telemetry and must never be treated as the audit trail.
"""

from __future__ import annotations

import logging
import sys

import structlog

from tfm.config.settings import Settings


def configure_logging(settings: Settings) -> None:
    """Configure structlog for the process. Idempotent."""

    level = getattr(logging, settings.log_level)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structured logger."""

    return structlog.get_logger(name)  # type: ignore[no-any-return]
