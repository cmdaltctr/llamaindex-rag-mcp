"""MCP-over-HTTP state, the MCP token, the saved web port and the upload limit.

``PUT /v1/mcp``, the token routes, ``PUT /v1/settings/web-port`` and
``PUT /v1/settings/upload-limit`` need a browser session: a bearer
credential, including the MCP token, never passes. Every body is
validated before it changes anything. The three settings live in
``omrg.jsonc`` (ADR-087): every read returns the file ``revision``, every
save may send it back, and a file that changed since then gives 409.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from ....config.settings_file import SettingsFile
from ....config.settings_file_write import SettingsFileError
from ....integrations.workspace_sqlite.settings import (
    MAX_UPLOAD_LIMIT_MIB,
    MAX_WEB_PORT,
    MIN_UPLOAD_LIMIT_MIB,
    MIN_WEB_PORT,
)
from ..engine_access import ReadScope, RuntimeDep, require_session
from ..errors import error_response
from ..lifespan import WebRuntime
from ..live_settings import CONFIG_FILE, DEFAULT, upload_limit
from ..mcp_http import McpHttp
from ..security import Principal
from ..settings_store import refusal_response
from ..uploads import DEFAULT_MAX_UPLOAD_BYTES, MIB
from .graphs import ok

router = APIRouter(prefix="/v1")

ManageScope = Annotated[Principal, Depends(require_session("manage"))]
CredentialsScope = Annotated[Principal, Depends(require_session("credentials"))]


Revision = Annotated[str, Field(max_length=128)] | None
PORT_RULE = f"The port must be a whole number from {MIN_WEB_PORT} to {MAX_WEB_PORT}."
LIMIT_RULE = (
    f"The upload limit must be a whole number of MiB from {MIN_UPLOAD_LIMIT_MIB} "
    f"to {MAX_UPLOAD_LIMIT_MIB}."
)


def _in_range(value: Any, low: int, high: int) -> bool:
    """Return whether *value* is a whole number (not a boolean) from *low* to *high*."""
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


class McpEnabledBody(BaseModel):
    """Body of ``PUT /v1/mcp``."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool
    revision: Revision = None


class WebPortBody(BaseModel):
    """Body of ``PUT /v1/settings/web-port``; ``null`` clears the file port."""

    model_config = ConfigDict(extra="forbid")

    port: Annotated[StrictInt, Field(ge=MIN_WEB_PORT, le=MAX_WEB_PORT)] | None
    revision: Revision = None

    @field_validator("port", mode="before")
    @classmethod
    def _rule(cls, value: Any) -> Any:
        if value is not None and not _in_range(value, MIN_WEB_PORT, MAX_WEB_PORT):
            raise ValueError(PORT_RULE)  # names the range, never the value
        return value


class UploadLimitBody(BaseModel):
    """Body of ``PUT /v1/settings/upload-limit``; ``null`` clears the file limit."""

    model_config = ConfigDict(extra="forbid")

    max_mib: Annotated[StrictInt, Field(ge=MIN_UPLOAD_LIMIT_MIB, le=MAX_UPLOAD_LIMIT_MIB)] | None
    revision: Revision = None

    @field_validator("max_mib", mode="before")
    @classmethod
    def _rule(cls, value: Any) -> Any:
        if value is not None and not _in_range(value, MIN_UPLOAD_LIMIT_MIB, MAX_UPLOAD_LIMIT_MIB):
            raise ValueError(LIMIT_RULE)
        return value


def _http(request: Request) -> McpHttp:
    return request.app.state.mcp_http


def _source(file: SettingsFile, key: str) -> str:
    return CONFIG_FILE if key in file.values else DEFAULT


async def _state(http: McpHttp) -> Response:
    token = await run_in_threadpool(http.tokens.describe)
    file = await run_in_threadpool(http.store.read)
    return ok(
        {
            "revision": file.revision,
            "enabled": http.enabled,
            "source": _source(file, "mcp_http_enabled"),
            "url": http.url,
            "token": token,
        }
    )


@router.get("/mcp", operation_id="getMcpState")
async def get_mcp_state(_: ReadScope, runtime: RuntimeDep, request: Request) -> Response:
    """Return whether MCP over HTTP is on, where that comes from, its URL and the token state."""
    return await _state(_http(request))


@router.put("/mcp", operation_id="setMcpEnabled")
async def set_mcp_enabled(
    _: ManageScope, body: McpEnabledBody, runtime: RuntimeDep, request: Request
) -> Response:
    """Turn MCP over HTTP on or off. The file is written before the gate changes."""
    http = _http(request)
    try:
        await run_in_threadpool(http.store.write, {"mcp_http_enabled": body.enabled}, body.revision)
    except SettingsFileError as exc:
        return refusal_response(exc)
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


async def _port_state(http: McpHttp) -> Response:
    file = await run_in_threadpool(http.store.read)
    saved = file.values.get("web_port")
    return ok(
        {
            "revision": file.revision,
            "saved": saved,
            "bound": http.port,
            "differs": saved is not None and saved != http.port,
        }
    )


@router.get("/settings/web-port", operation_id="getWebPort")
async def get_web_port(_: ReadScope, runtime: RuntimeDep, request: Request) -> Response:
    """Return the file port (used at the next launch), the bound port and whether they differ."""
    return await _port_state(_http(request))


@router.put("/settings/web-port", operation_id="setWebPort")
async def set_web_port(
    _: ManageScope, body: WebPortBody, runtime: RuntimeDep, request: Request
) -> Response:
    """Write `web_port` to `omrg.jsonc` for later launches. The running server does not rebind."""
    http = _http(request)
    try:
        await run_in_threadpool(http.store.write, {"web_port": body.port}, body.revision)
    except SettingsFileError as exc:
        return refusal_response(exc)
    return await _port_state(http)


#: Refusal while a launch option sets the limit.
LAUNCH_LOCKED = (
    "The upload limit was set when the server started. Remove --max-upload-mib or "
    "WEB_MAX_UPLOAD_MIB and restart to change it here."
)


def _limit_state(runtime: WebRuntime, file: SettingsFile) -> Response:
    saved = file.values.get("web_max_upload_mib")
    return ok(
        {
            "revision": file.revision,
            "max_bytes": runtime.uploads.max_bytes,
            "source": runtime.upload_limit_source,
            "saved_mib": saved,
            "default_mib": DEFAULT_MAX_UPLOAD_BYTES // MIB,
            "min_mib": MIN_UPLOAD_LIMIT_MIB,
            "max_mib": MAX_UPLOAD_LIMIT_MIB,
        }
    )


@router.get("/settings/upload-limit", operation_id="getUploadLimit")
async def get_upload_limit(_: ReadScope, runtime: RuntimeDep, request: Request) -> Response:
    """Return the per-file upload limit in force, its source, the file value and the range."""
    return _limit_state(runtime, await run_in_threadpool(_http(request).store.read))


@router.put("/settings/upload-limit", operation_id="setUploadLimit")
async def set_upload_limit(
    _: ManageScope, body: UploadLimitBody, runtime: RuntimeDep, request: Request
) -> Response:
    """Write `web_max_upload_mib` to `omrg.jsonc` and apply it to new uploads at once.

    The file is written before the running limit changes. A launch option
    locks the limit: the request then gets 409 and changes nothing.
    """
    if runtime.upload_limit_source == "launch":
        return error_response(409, LAUNCH_LOCKED)
    store = _http(request).store
    try:
        await run_in_threadpool(store.write, {"web_max_upload_mib": body.max_mib}, body.revision)
    except SettingsFileError as exc:
        return refusal_response(exc)
    file = await run_in_threadpool(store.read)
    runtime.uploads.max_bytes, runtime.upload_limit_source = upload_limit(
        runtime.config, file.values.get("web_max_upload_mib")
    )
    return _limit_state(runtime, file)
