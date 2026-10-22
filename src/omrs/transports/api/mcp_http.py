"""MCP over streamable HTTP on the web server (design D3, D4).

:func:`build_mcp_http` builds a second MCP server whose lifespan yields the
web runtime's Engine, mounts it at ``/mcp`` behind :class:`McpGate`, and
returns the :class:`McpHttp` that the routes and the lifespan share.

The gate sits in front of the SDK and runs three checks in order: the
endpoint is on (else 404), the ``Origin`` is not foreign (else 403) and the
bearer token matches the stored hash (else 401). Only then does the SDK see
the request. Because the gate checks every request, turning MCP off ends
open sessions at their next request.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings
from starlette.datastructures import Headers
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from ...core.workspace import WorkspaceLayout
from ...integrations.workspace_sqlite import SqliteWorkspaceRepository
from ...integrations.workspace_sqlite.tokens import McpTokenStore
from ..mcp import create_mcp_server
from ..mcp.context import McpContext, PathPolicy
from .errors import error_response
from .lifespan import WebConfig
from .security import AccessPolicy
from .settings_store import SettingsFileStore

MCP_PATH = "/mcp"


class McpGate:
    """Pure ASGI gate in front of the SDK's streamable HTTP app."""

    def __init__(self, app: ASGIApp, http: McpHttp, policy: AccessPolicy) -> None:
        """Wrap *app*; *http* holds the on/off flag and the token store."""
        self.app = app
        self.http = http
        self.policy = policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Refuse the request in gate order, or pass it to the SDK."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        refusal = self._refusal(Headers(scope=scope))
        if refusal is not None:
            await refusal(scope, receive, send)
            return
        await self.app(_inner_scope(scope), receive, send)

    def _refusal(self, headers: Headers) -> Any | None:
        if not self.http.enabled:
            return error_response(404, "MCP over HTTP is off.")
        origin = headers.get("origin")
        if origin is not None and not self.policy.origin_allowed(origin):
            return error_response(403, "Cross-origin request rejected.")
        authorization = headers.get("authorization", "")
        scheme, _, candidate = authorization.partition(" ")
        if scheme.lower() != "bearer" or not self.http.tokens.verify(candidate.strip()):
            return error_response(
                401, "A valid MCP token is required.", headers={"WWW-Authenticate": "Bearer"}
            )
        return None


def _inner_scope(scope: Scope) -> Scope:
    """Return a scope whose path is ``/`` below the ``/mcp`` mount point."""
    path = scope["path"]
    if path == MCP_PATH:
        return {**scope, "path": "/", "root_path": scope.get("root_path", "") + MCP_PATH}
    return scope


@dataclass
class McpHttp:
    """Shared state of the HTTP MCP endpoint for one launch.

    Attributes:
        host: Bound loopback address.
        port: Bound port.
        records: The workspace database file.
        enabled: In-memory copy of the ``mcp_http_enabled`` switch in ``omrs.jsonc``.
            ``PUT /v1/mcp`` updates it after the file write and a hand edit
            updates it at the next request; the gate reads it on every request.
        store: The ``omrs.jsonc`` store (ADR-087).
        tokens: MCP token store.
        session_manager: The SDK session manager, run by the web lifespan.
    """

    host: str
    port: int
    records: Path
    store: SettingsFileStore = field(default_factory=SettingsFileStore)
    tokens: McpTokenStore = field(init=False)
    enabled: bool = False
    session_manager: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Create the token store. The database file is opened by :meth:`prepare`."""
        self.tokens = McpTokenStore(self.records)

    @property
    def url(self) -> str:
        """The ``/mcp`` address on the bound host and port."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}{MCP_PATH}"

    def prepare(self) -> None:
        """Create and migrate the workspace database, then read the switch from the file."""
        SqliteWorkspaceRepository(self.records)
        self.enabled = self.store.read().values.get("mcp_http_enabled") is True


def build_mcp_http(app: FastAPI, config: WebConfig, policy: AccessPolicy) -> McpHttp:
    """Mount the gated MCP endpoint on *app* and return its shared state."""
    http = McpHttp(config.host, config.port, WorkspaceLayout(config.workspace).records)

    @asynccontextmanager
    async def lifespan(_server: Any) -> AsyncIterator[McpContext]:
        runtime = app.state.runtime
        yield McpContext(
            runtime.engine,
            PathPolicy.from_grants(runtime.grants),
            runtime.admission.enter,
            profiles=runtime.profiles,
        )

    server = create_mcp_server(lifespan)
    sdk_app = server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=False,
        transport_security=TransportSecuritySettings(
            allowed_hosts=sorted(policy.allowed_hosts),
            allowed_origins=sorted(policy.allowed_origins),
        ),
    )
    http.session_manager = server.session_manager
    gate = McpGate(sdk_app, http, policy)
    app.router.routes.append(Route(MCP_PATH, gate))
    app.router.routes.append(Mount(MCP_PATH, app=gate))
    return http
