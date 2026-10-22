"""Packaged frontend assets with a single-page fallback (design D11).

:class:`FrontendFallback` is installed as the router's *default* app, so it
runs only when no route matched. It never answers an ``/v1`` path with
HTML: unknown API paths get the JSON error envelope. A path with a file
extension that does not exist returns a plain 404, so a missing script is
never replaced by ``index.html``. A page load of the server's own origin
gets ``index.html`` with the workspace sign-in secret (:mod:`.page_secret`).
"""

from __future__ import annotations

from pathlib import Path

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

from .errors import error_response
from .middleware import is_api_path
from .page_secret import PageSecret, inject_page_secret, page_may_carry_secret
from .security import AccessPolicy

MISSING_BUILD_MESSAGE = (
    "The web workspace assets are not built. "
    "Run `npm ci && npm run build` in the web/ directory, then restart `omrs web`."
)


class FrontendFallback:
    """Serve built assets, or ``index.html`` for frontend routes."""

    def __init__(
        self,
        static_dir: Path | None,
        *,
        policy: AccessPolicy | None = None,
        page_secret: PageSecret | None = None,
    ) -> None:
        """Serve from *static_dir* when it holds an ``index.html``.

        Args:
            static_dir: Built asset directory, or ``None`` for API only.
            policy: The launch access policy, which decides who gets the secret.
            page_secret: The workspace sign-in secret, or ``None`` for a page
                without one.
        """
        self._policy = policy
        self._secret = page_secret
        index = static_dir / "index.html" if static_dir is not None else None
        self._index = index if index is not None and index.is_file() else None
        self._files = (
            StaticFiles(directory=static_dir, follow_symlink=False)
            if self._index is not None and static_dir is not None
            else None
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Answer an unmatched request."""
        response = await self._respond(scope)
        await response(scope, receive, send)

    async def _respond(self, scope: Scope) -> Response:
        path: str = scope.get("path", "/")
        if is_api_path(path):
            return error_response(404, "Not Found")
        if scope.get("method") not in {"GET", "HEAD"}:
            return PlainTextResponse("Method Not Allowed", status_code=405)
        if self._files is None or self._index is None:
            return PlainTextResponse(MISSING_BUILD_MESSAGE, status_code=404)
        if path.strip("/") not in {"", "index.html"}:
            try:
                return await self._files.get_response(self._files.get_path(scope), scope)
            except HTTPException:
                pass
            if "." in path.rstrip("/").rsplit("/", 1)[-1]:
                return PlainTextResponse("Not Found", status_code=404)
        if (
            self._secret is not None
            and self._policy is not None
            and page_may_carry_secret(self._policy, Headers(scope=scope))
        ):
            page = inject_page_secret(self._index.read_text(encoding="utf-8"), self._secret)
            return HTMLResponse(page, headers={"Cache-Control": "no-store"})
        return FileResponse(
            self._index, media_type="text/html", headers={"Cache-Control": "no-cache"}
        )
