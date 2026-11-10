from typing import Any, Dict, Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.logging import get_logger

logger = get_logger("muscar_mail.exceptions")


class MuscarMailError(Exception):
    """Base exception for all domain and service errors in muscar_mail."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(MuscarMailError):
    """Raised when request lacks valid authentication credentials (HTTP 401)."""

    def __init__(self, message: str = "Invalid or missing API key."):
        super().__init__(message=message, status_code=401)


class InsufficientCreditsError(MuscarMailError):
    """Raised when daily free credits or paid credits are exhausted (HTTP 402)."""

    def __init__(
        self,
        message: str = "Daily verification credit quota exhausted (HTTP 402).",
        reset_on: Optional[str] = None,
    ):
        details = {"reset_on": reset_on} if reset_on else {}
        super().__init__(message=message, status_code=402, details=details)


class BatchLimitExceededError(MuscarMailError):
    """Raised when input batch exceeds the 25-email invariant limit (HTTP 422)."""

    def __init__(
        self,
        received_count: int,
        max_allowed: int = 25,
    ):
        super().__init__(
            message=f"Batch size of {received_count} exceeds maximum allowed limit of {max_allowed} emails.",
            status_code=422,
            details={"received": received_count, "max_allowed": max_allowed},
        )


class UpstreamTimeoutError(MuscarMailError):
    """Raised when upstream Verifalia call exceeds the bounded timeout ceiling (HTTP 504)."""

    def __init__(self, message: str = "Upstream email verification timed out."):
        super().__init__(message=message, status_code=504)


class UpstreamProviderError(MuscarMailError):
    """Raised when upstream Verifalia returns an unrecoverable 5xx error (HTTP 502)."""

    def __init__(self, message: str = "Upstream verification service encountered an error."):
        super().__init__(message=message, status_code=502)


async def muscar_mail_exception_handler(
    request: Request, exc: MuscarMailError
) -> JSONResponse:
    """Translates domain MuscarMailError exceptions into structured JSON responses."""
    content: Dict[str, Any] = {"error": exc.message}
    if exc.details:
        content["details"] = exc.details
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Mounts muscar_mail domain exception handlers onto a FastAPI application instance."""
    app.add_exception_handler(MuscarMailError, muscar_mail_exception_handler)

    @app.exception_handler(Exception)
    async def global_unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled server exception.", exc_info=exc, path=str(request.url))
        return JSONResponse(
            status_code=500,
            content={
                "error": "InternalServerError",
                "message": str(exc),
                "type": type(exc).__name__,
            },
        )
