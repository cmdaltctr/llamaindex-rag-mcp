"""Error envelope for the local HTTP runtime.

Every API error uses the MCP error-dict shape declared as ``Error`` in
``openapi.yaml``: ``{"status": "error", "message": "..."}``. Messages
never contain stack traces or credential values.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .security import redact

logger = logging.getLogger(__name__)

#: Headers sent on every API response. ``no-store`` keeps credential
#: responses out of the browser cache.
API_HEADERS: dict[str, str] = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


def error_response(
    status_code: int,
    message: str,
    *,
    error_type: str | None = None,
    headers: dict[str, str] | None = None,
    redactor: Callable[[str], str] | None = None,
) -> JSONResponse:
    """Build an error envelope response.

    Args:
        status_code: HTTP status code.
        message: Human-readable message. It is redacted before it is sent.
        error_type: Optional ``Error.error_type`` category from the contract.
        headers: Extra response headers.
        redactor: ``Engine.redact``. It removes provider credential values
            before the OMRS token redaction runs.

    Returns:
        A JSON response with the status/message envelope.
    """
    body: dict[str, Any] = {
        "status": "error",
        "message": redact(redactor(message) if redactor else message),
    }
    if error_type is not None:
        body["error_type"] = error_type
    return JSONResponse(body, status_code=status_code, headers={**API_HEADERS, **(headers or {})})


def engine_redactor(request: Request) -> Callable[[str], str] | None:
    """Return the running Engine's redactor, or ``None`` before startup."""
    runtime = getattr(request.app.state, "runtime", None)
    engine = getattr(runtime, "engine", None)
    return getattr(engine, "redact", None)


def _validation_message(exc: RequestValidationError) -> str:
    """Summarise validation errors by location and reason, never by value."""
    parts = []
    for error in exc.errors()[:5]:
        location = ".".join(str(item) for item in error.get("loc", ()) if item != "body")
        parts.append(f"{location or 'request'}: {error.get('msg', 'invalid value')}")
    return "Invalid request. " + "; ".join(parts)


def install_error_handlers(app: FastAPI) -> None:
    """Register envelope handlers for framework, validation and unexpected errors.

    Args:
        app: The application to configure.
    """

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(
            exc.status_code,
            str(exc.detail),
            headers=exc.headers,
            redactor=engine_redactor(request),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            400,
            _validation_message(exc),
            error_type="validation",
            redactor=engine_redactor(request),
        )

    @app.exception_handler(Exception)
    async def _internal_error(request: Request, exc: Exception) -> JSONResponse:
        # The redacting log filter scrubs the traceback; the client gets
        # no detail at all.
        logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return error_response(500, "Internal server error.", error_type="internal")
