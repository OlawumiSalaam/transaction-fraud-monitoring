"""Structured logging configuration test."""

from __future__ import annotations

from tfm.config.settings import Settings
from tfm.observability.logging import configure_logging, get_logger


def test_configure_logging_and_emit(settings: Settings) -> None:
    configure_logging(settings)
    log = get_logger("tfm.test")
    # Should not raise; structured event with bound context.
    log.info("test.event", key="value")
