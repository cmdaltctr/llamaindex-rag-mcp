"""Structured errors for experiment contexts (design D10).

Each error carries a stable ``code`` that transports map to a response.
Messages name no filesystem path from outside the request, no store URI
and no credential.
"""

from __future__ import annotations

from typing import Any


class ExperimentPathError(ValueError):
    """A workspace or root failed a canonical path check.

    Attributes:
        code: Stable reason, for example ``traversal`` or ``symlink_escape``.
    """

    def __init__(self, code: str, message: str) -> None:
        """Keep the code and the operator message."""
        super().__init__(message)
        self.code = code

    def to_dict(self) -> dict[str, Any]:
        """Return the MCP/HTTP-style error payload."""
        return {"status": "error", "code": self.code, "message": str(self)}


class ExperimentAdmissionError(PermissionError):
    """An experiment request was refused before any side effect.

    Attributes:
        code: Stable reason, for example ``live_library_target``.
        context_id: The context the request named, if any.
    """

    def __init__(self, code: str, message: str, context_id: str | None = None) -> None:
        """Keep the code, message and context id."""
        super().__init__(message)
        self.code = code
        self.context_id = context_id

    def to_dict(self) -> dict[str, Any]:
        """Return the MCP/HTTP-style error payload."""
        return {
            "status": "error",
            "code": self.code,
            "message": str(self),
            "context_id": self.context_id,
        }
