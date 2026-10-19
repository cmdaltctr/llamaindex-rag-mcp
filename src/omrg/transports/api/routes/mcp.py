"""MCP-over-HTTP state, the MCP token, the saved web port and the upload limit.

``PUT /v1/mcp``, the token routes, ``PUT /v1/settings/web-port`` and
``PUT /v1/settings/upload-limit`` need a browser session: a bearer
credential, including the MCP token, never passes. Every body is
validated before it changes anything.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from ....integrations.workspace_sqlite.settings import (
    MAX_UPLOAD_LIMIT_MIB,
    MAX_WEB_PORT,
    MIN_UPLOAD_LIMIT_MIB,
    MIN_WEB_PORT,
)
from ..engine_access import ReadScope, RuntimeDep, require_session
from ..errors import API_HEADERS, error_response
from ..lifespan import WebRuntime
from ..mcp_http import McpHttp
from ..security import Principal
from ..uploads import DEFAULT_MAX_UPLOAD_BYTES, MIB

router = APIRouter(prefix="/v1")

ManageScope = Annotated[Principal, Depends(require_session("manage"))]
CredentialsScope = Annotated[Principal, Depends(require_session("credentials"))]


class McpEnabledBody(BaseModel):
    """Body of ``PUT /v1/mcp``."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool


class WebPortBody(BaseModel):
    """Body of ``PUT /v1/settings/web-port``; ``null`` clears the saved port."""

    model_config = ConfigDict(extra="forbid")

    port: Annotated[StrictInt, Field(ge=MIN_WEB_PORT, le=MAX_WEB_PORT)] | None


class UploadLimitBody(BaseModel):
    """Body of ``PUT /v1/settings/upload-limit``; ``null`` clears the saved limit."""

    model_config = ConfigDict(extra="forbid")

    max_mib: Annotated[StrictInt, Field(ge=MIN_UPLOAD_LIMIT_MIB, le=MAX_UPLOAD_LIMIT_MIB)] | None


def _http(request: Request) -> McpHttp:
    return request.app.state.mcp_http


async def _state(http: McpHttp) -> dict[str, Any]:
    token = await run_in_threadpool(http.tokens.describe)
    return {"status": "ok", "enabled": http.enabled, "url": http.url, "token": token}


@router.get("/mcp", operation_id="getMcpState")
async def get_mcp_state(_: ReadScope, runtime: RuntimeDep, request: Request) -> dict[str, Any]:
    """Return whether MCP over HTTP is on, its URL and whether a token exists."""
    return await _state(_http(request))


@router.put("/mcp", operation_id="setMcpEnabled")
async def set_mcp_enabled(
    _: ManageScope, body: McpEnabledBody, runtime: RuntimeDep, request: Request
) -> dict[str, Any]:
    """Turn MCP over HTTP on or off. The database is written before the gate changes."""
    http = _http(request)
    await run_in_threadpool(http.settings.set_mcp_http_enabled, body.enabled)
    http.enabled = body.enabled
    return await _state(http)


@router.post("/mcp/token", status_code=201, operation_id="rotateMcpToken")
async def rotate_mcp_token(
    _: CredentialsScope, runtime: RuntimeDep, request: Request
) -> dict[str, Any]:
    """Create or replace the MCP token. The value is in this response only."""
    http = _http(request)
    created = await run_in_threadpool(http.tokens.create)
    return {"status": "ok", "token": created.token, "created_at": created.created_at}


@router.delete("/mcp/token", operation_id="revokeMcpToken")
async def revoke_mcp_token(
    _: CredentialsScope, runtime: RuntimeDep, request: Request
) -> dict[str, Any]:
    """Delete the MCP token. Clients that hold it get 401 at their next request."""
    http = _http(request)
    revoked = await run_in_threadpool(http.tokens.revoke)
    return {"status": "ok", "revoked": revoked}


def _port_state(http: McpHttp, saved: int | None) -> dict[str, Any]:
    return {"status": "ok", "saved": saved, "bound": http.port}


@router.get("/settings/web-port", operation_id="getWebPort")
async def get_web_port(_: ReadScope, runtime: RuntimeDep, request: Request) -> dict[str, Any]:
    """Return the saved port (used at the next launch) and the bound port."""
    http = _http(request)
    return _port_state(http, await run_in_threadpool(http.settings.get_web_port))


@router.put("/settings/web-port", operation_id="setWebPort")
async def set_web_port(
    _: ManageScope, body: WebPortBody, runtime: RuntimeDep, request: Request
) -> dict[str, Any]:
    """Save the port for later launches. The running server does not rebind."""
    http = _http(request)
    await run_in_threadpool(http.settings.set_web_port, body.port)
    return _port_state(http, body.port)


#: Refusal while a launch option sets the limit.
LAUNCH_LOCKED = (
    "The upload limit was set when the server started. Remove --max-upload-mib or "
    "WEB_MAX_UPLOAD_MIB and restart to change it here."
)


def _limit_state(runtime: WebRuntime, saved: int | None) -> dict[str, Any]:
    return {
        "status": "ok",
        "max_bytes": runtime.uploads.max_bytes,
        "source": runtime.upload_limit_source,
        "saved_mib": saved,
        "default_mib": DEFAULT_MAX_UPLOAD_BYTES // MIB,
        "min_mib": MIN_UPLOAD_LIMIT_MIB,
        "max_mib": MAX_UPLOAD_LIMIT_MIB,
    }


@router.get("/settings/upload-limit", operation_id="getUploadLimit")
async def get_upload_limit(_: ReadScope, runtime: RuntimeDep, request: Request) -> dict[str, Any]:
    """Return the per-file upload limit in force, its source, the saved value and the range."""
    saved = await run_in_threadpool(_http(request).settings.get_upload_limit_mib)
    return _limit_state(runtime, saved)


@router.put("/settings/upload-limit", operation_id="setUploadLimit")
async def set_upload_limit(
    _: ManageScope, body: UploadLimitBody, runtime: RuntimeDep, request: Request
) -> Response:
    """Save the upload limit and apply it to new uploads at once.

    The database is written before the running limit changes. A launch
    option locks the limit: the request then gets 409 and changes nothing.
    """
    if runtime.upload_limit_source == "launch":
        return error_response(409, LAUNCH_LOCKED)
    await run_in_threadpool(_http(request).settings.set_upload_limit_mib, body.max_mib)
    if body.max_mib is None:
        runtime.uploads.max_bytes = runtime.config.max_upload_bytes
        runtime.upload_limit_source = "default"
    else:
        runtime.uploads.max_bytes = body.max_mib * MIB
        runtime.upload_limit_source = "saved"
    return JSONResponse(_limit_state(runtime, body.max_mib), headers=API_HEADERS)
