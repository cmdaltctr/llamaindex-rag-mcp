"""Request guard applied before any route or static file runs.

This pure ASGI middleware checks the ``Host`` header on every request.
On ``/v1`` paths it also rejects foreign ``Origin`` values, cross-site and
same-site fetch metadata, and credentials placed in the query string.
Authentication and scopes are checked by :func:`.security.require_scope`.
Pure ASGI (not ``BaseHTTPMiddleware``) keeps streaming responses intact.
"""

from __future__ import annotations

from urllib.parse import parse_qsl

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import API_HEADERS, error_response
from .security import SECRET_QUERY_KEYS, AccessPolicy, looks_like_credential

#: Headers sent on every response, API or static.
PAGE_HEADERS: dict[str, str] = {
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "frame-ancestors 'none'; base-uri 'none'; object-src 'none'",
}


def is_api_path(path: str) -> bool:
    """Return whether *path* belongs to the ``/v1`` API namespace."""
    return path == "/v1" or path.startswith("/v1/")


class GuardMiddleware:
    """Reject requests that fail the local Host, Origin or query rules."""

    def __init__(self, app: ASGIApp, policy: AccessPolicy) -> None:
        """Wrap *app* with the request guard.

        Args:
            app: The inner ASGI application.
            policy: The launch access policy.
        """
        self.app = app
        self.policy = policy

    def _rejection(self, scope: Scope, headers: Headers) -> tuple[int, str] | None:
        """Return ``(status, message)`` when the request must be refused."""
        if not self.policy.host_allowed(headers.get("host")):
            return 400, "Invalid Host header. Open the workspace with the URL from `omrs web`."
        if not is_api_path(scope["path"]):
            return None
        if headers.get("sec-fetch-site", "same-origin") in {"cross-site", "same-site"}:
            return 403, "Cross-site request rejected."
        origin = headers.get("origin")
        if origin is not None and not self.policy.origin_allowed(origin):
            return 403, "Cross-origin request rejected."
        query = scope.get("query_string", b"").decode("latin-1")
        for key, value in parse_qsl(query, keep_blank_values=True):
            if key.lower() in SECRET_QUERY_KEYS or looks_like_credential(value):
                return 400, "Credentials must not be sent in the query string."
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Apply the guard to HTTP requests; pass other scopes through."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        api = is_api_path(scope["path"])
        extra = {**PAGE_HEADERS, **(API_HEADERS if api else {})}

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw = list(message.get("headers", []))
                present = {name.lower() for name, _ in raw}
                for name, value in extra.items():
                    if name.lower().encode("latin-1") not in present:
                        raw.append((name.lower().encode("latin-1"), value.encode("latin-1")))
                message["headers"] = raw
            await send(message)

        rejection = self._rejection(scope, headers)
        if rejection is not None:
            response = error_response(*rejection)
            await response(scope, receive, send_with_headers)
            return
        await self.app(scope, receive, send_with_headers)
