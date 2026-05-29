from typing import Any


class AppError(Exception):
    """Base class for all domain errors. Maps to a structured JSON response."""

    code: str = "app_error"
    status_code: int = 500

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ValidationError(AppError):
    code = "validation_error"
    status_code = 422


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404


class ConflictError(AppError):
    code = "conflict"
    status_code = 409


class AuthError(AppError):
    """Raised when the caller is not authenticated. Used from Phase 1 onward."""

    code = "auth_error"
    status_code = 401


class TenantAccessError(AppError):
    """Raised when the caller tries to access another tenant's data. Used from Phase 1 onward."""

    code = "tenant_access_error"
    status_code = 403


class ExternalProviderError(AppError):
    """Raised when an external API (FIPE, BACEN) fails or is degraded."""

    code = "external_provider_error"
    status_code = 502

    def __init__(self, message: str, details: Any = None, degraded: bool = False) -> None:
        super().__init__(message, details)
        self.degraded = degraded
