"""Service-layer errors mapped to the uniform API error contract."""

from __future__ import annotations


class ServiceError(Exception):
    """Base service error carrying the HTTP status + stable error code."""

    http_status: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class CaseNotFound(ServiceError):
    http_status = 404
    code = "NOT_FOUND"


class ElementNotFound(ServiceError):
    http_status = 404
    code = "NOT_FOUND"


class CaseAlreadyDispositioned(ServiceError):
    http_status = 409
    code = "CASE_ALREADY_DISPOSITIONED"


class RationaleFloorRequired(ServiceError):
    http_status = 400
    code = "RATIONALE_FLOOR_REQUIRED"


class RationaleRequiredForAction(ServiceError):
    http_status = 400
    code = "RATIONALE_REQUIRED_FOR_ACTION"


class InvalidAction(ServiceError):
    http_status = 422
    code = "SCHEMA_ERROR"
