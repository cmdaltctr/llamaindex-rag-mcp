"""Shared helpers for the document route modules (design D8).

Route modules validate input, delegate to the Engine that the lifespan
owns, and format output. This module keeps the few shared pieces in
one place: the runtime dependency, admission for engine work, the
session-only dependency for destructive actions, and read access to the
Engine's store and profile resolver.

:func:`engine_store` and :func:`engine_resolver` read the Engine's
public read-only ``store`` and ``profile_resolver`` properties.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, HTTPException

from .lifespan import AdmissionClosed, WebRuntime, get_runtime
from .security import Principal, require_scope

logger = logging.getLogger(__name__)

RuntimeDep = Annotated[WebRuntime, Depends(get_runtime)]
ReadScope = Annotated[Principal, Depends(require_scope("read"))]
FilesScope = Annotated[Principal, Depends(require_scope("files"))]


def engine_store(engine: Any) -> Any:
    """Return the vector store the Engine owns.

    Args:
        engine: The runtime Engine.

    Returns:
        The Engine's store.

    Raises:
        HTTPException: 503 when the Engine holds no open store.
    """
    try:
        store = engine.store
    except RuntimeError:
        store = None
    if store is None:
        raise HTTPException(503, "The engine has no open vector store.")
    return store


def engine_resolver(engine: Any) -> Any | None:
    """Return the Engine's profile resolver, or ``None`` when it has none."""
    return engine.profile_resolver


@asynccontextmanager
async def admitted(runtime: WebRuntime) -> AsyncIterator[None]:
    """Hold runtime admission so shutdown waits before it closes the Engine.

    Raises:
        HTTPException: 503 when shutdown has begun.
    """
    try:
        async with runtime.admission.enter():
            yield
    except AdmissionClosed:
        raise HTTPException(503, "The server is shutting down.") from None


def require_session(scope: str) -> Callable[..., Any]:
    """Return a dependency that needs *scope* and a browser session.

    Bearer credentials for notebook clients never pass, whatever scopes
    they hold. Destructive actions use this dependency.

    Args:
        scope: The scope the session must hold.

    Returns:
        An async FastAPI dependency that returns the :class:`Principal`.
    """
    scoped = require_scope(scope)

    # A default value, not ``Annotated``: postponed annotations cannot see
    # the local ``scoped`` when FastAPI resolves the signature.
    async def dependency(principal: Principal = Depends(scoped)) -> Principal:  # noqa: B008
        if principal.kind != "session":
            raise HTTPException(
                403, "This action needs the browser session; notebook credentials cannot run it."
            )
        return principal

    dependency.omrg_scope = scope  # type: ignore[attr-defined]
    dependency.omrg_session_only = True  # type: ignore[attr-defined]
    return dependency


def failure_text(exc: BaseException) -> str:
    """Return a short failure description without raw detail.

    Only the exception type is returned. Raw messages can hold paths or
    provider detail, and the redacting log filter keeps the full text.
    """
    return f"{type(exc).__name__}."
