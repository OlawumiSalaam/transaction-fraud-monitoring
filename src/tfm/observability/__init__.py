"""Observability: structured application logging (distinct from the audit log)."""

from tfm.observability.logging import configure_logging, get_logger

__all__ = ["configure_logging", "get_logger"]
