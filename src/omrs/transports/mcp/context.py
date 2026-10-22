"""Per-server context the MCP lifespan yields to every tool handler (design D2).

A handler reads it from ``ctx.request_context.lifespan_context``. It holds
the Engine, the file-path policy of the transport and the admission hook,
so handlers read no process default.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

#: Returns an async context manager held for the length of one tool call.
Admit = Callable[[], AbstractAsyncContextManager[None]]


class PathDenied(PermissionError):
    """A path is outside every approved root.

    The message never names the path, so a denial does not disclose what
    exists outside the roots.
    """


class _Grants(Protocol):
    """The part of the web API's ``RootGrants`` the policy needs."""

    def check(self, path: Path | str) -> Path:
        """Return the canonical path, or raise ``PermissionError``."""
        ...


@dataclass(frozen=True)
class PathPolicy:
    """Decides which file paths a tool may read.

    Attributes:
        grants: Approved roots, or ``None`` to allow every path (stdio).
    """

    grants: _Grants | None = None

    @classmethod
    def allow_all(cls) -> PathPolicy:
        """Policy for stdio: the client already runs as the user."""
        return cls(None)

    @classmethod
    def from_grants(cls, grants: _Grants) -> PathPolicy:
        """Policy for HTTP: only paths inside the operator's ``--root`` set."""
        return cls(grants)

    def check(self, path: str) -> str:
        """Return the path a tool may read.

        Args:
            path: Path text from the client.

        Returns:
            *path* unchanged when every path is allowed, else its canonical
            form (symlinks followed) inside an approved root.

        Raises:
            PathDenied: The path is relative, outside every root, resolves
                outside through a symlink, or does not exist.
        """
        if self.grants is None:
            return path
        try:
            return str(self.grants.check(path))
        except PermissionError:
            raise PathDenied("Path is outside the approved roots.") from None


@asynccontextmanager
async def no_admission() -> AsyncIterator[None]:
    """Admission hook for stdio: nothing to wait for at shutdown."""
    yield


@dataclass(frozen=True)
class McpContext:
    """What the MCP lifespan yields.

    Attributes:
        engine: The Engine tools run on (an ``omrs.Engine``).
        paths: File-path policy of this transport.
        admit: Admission hook held around each tool call.
        profiles: The web server's profile service, or ``None`` on stdio. The
            service lists user profiles with their readiness and binds them to
            collections. Stdio has no service: it lists from the read-only
            catalogue of the Engine and cannot bind a user profile.
    """

    engine: Any
    paths: PathPolicy
    admit: Admit
    profiles: Any | None = None


def mcp_context(ctx: Any) -> McpContext:
    """Return the :class:`McpContext` the lifespan yielded for this request."""
    return ctx.request_context.lifespan_context
