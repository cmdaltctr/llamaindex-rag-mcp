"""Routes of the llama.cpp server that ``omrg web`` starts and owns (design D12).

``GET`` reports the state and the settings (read from ``omrg.jsonc``, with its
``revision``). ``PUT`` writes the program, the model, the context window and the
idle sleep to the file; it may send the ``revision`` it read. ``POST`` start, stop
and restart control the one process the server owns. Every write and control route needs the browser
session. Changing the program or the model also needs the ``credentials``
scope. No route returns the log file or any text of the child process.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .... import compose
from ....config.settings_file_write import SettingsFileError
from ....core.providers.llm import llamacpp_rules as rules
from ..engine_access import ReadScope, RuntimeDep, admitted
from ..errors import error_response
from ..llamacpp_server import LaunchConfig, LlamacppServer, ServerStatus
from ..provider_state import EngineRefused, validate_int
from ..settings_store import refusal_response
from .experiments import ManageScope
from .graphs import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

BINARY_RULE = (
    "The program must be the absolute path of an executable file named llama-server "
    "(llama-server.exe on Windows)."
)
MODEL_RULE = (
    "The model must be the absolute path of an existing .gguf file, or a Hugging Face id "
    "such as org/name or org/name:tag."
)
CREDENTIALS_RULE = "Changing the program or the model needs the credentials scope."
_REFUSED = "The running engine cannot take this change. Restart the server to apply it."
_WINDOW = next(spec for spec in rules.LLAMACPP_SERVER_FIELDS if spec.id == "context_window")
_IDLE = next(spec for spec in rules.LLAMACPP_SERVER_FIELDS if spec.id == "idle_sleep")
#: Request key to the ``Settings`` field (and so the ``omrg.jsonc`` key) it writes.
_FIELD_IDS = {
    "binary": "llamacpp_server_binary",
    "model": "llamacpp_server_model",
    "context_window": "llamacpp_context_window",
    "idle_sleep": "llamacpp_idle_sleep_seconds",
}


class ServerBody(BaseModel):
    """Body of ``PUT /v1/llamacpp/server``. A key that is absent stays as it is; ``null`` clears."""

    model_config = ConfigDict(extra="forbid")

    binary: str | None = Field(None, max_length=2048)
    model: str | None = Field(None, max_length=2048)
    context_window: int | float | str | None = None
    idle_sleep: int | float | str | None = None
    revision: Annotated[str, Field(max_length=128)] | None = None


def _manager(request: Request) -> LlamacppServer:
    return request.app.state.llamacpp_server  # type: ignore[no-any-return]


def _values(runtime: Any) -> Any:
    return runtime.providers.values if runtime.providers else None


def _launch_config(view: dict[str, Any]) -> LaunchConfig:
    return LaunchConfig(
        binary=str(view["binary"]["value"] or ""),
        model=str(view["model"]["value"] or ""),
        context_window=int(view["context_window"]["value"]),
        chat_url=str(view["chat_url"]),
        idle_sleep=int(view["idle_sleep"]["value"]),
    )


def _revision(runtime: Any) -> str:
    return runtime.providers.revision if runtime.providers else "absent"


def _body(view: dict[str, Any], status: ServerStatus, revision: str) -> dict[str, Any]:
    """Return the response body: state, reason, running values, pending restart and saved values."""
    started = status.started_with
    saved = _launch_config(view)
    pending = started is not None and (
        (started.binary, started.model, started.context_window, started.idle_sleep)
        != (saved.binary, saved.model, saved.context_window, saved.idle_sleep)
    )
    return {
        "revision": revision,
        "state": status.state,
        "reason": status.reason,
        "exit_code": status.exit_code,
        "pid_running": status.pid_running,
        "running_with": None
        if started is None
        else {"context_window": started.context_window, "model_kind": started.model_kind},
        "pending_restart": pending,
        "saved": {key: view[key] for key in ("binary", "model", "context_window", "idle_sleep")},
    }


async def _respond(runtime: Any, status: ServerStatus) -> Response:
    view = await run_in_threadpool(compose.llamacpp_server_settings, _values(runtime))
    return ok(_body(view, status, _revision(runtime)))


@router.get("/llamacpp/server", operation_id="getLlamacppServer")
async def get_server(_: ReadScope, request: Request, runtime: RuntimeDep) -> Response:
    """Return the state, the values the process started with and the saved settings."""
    async with admitted(runtime):
        return await _respond(runtime, _manager(request).status())


def _check(key: str, value: object) -> tuple[str | None, str | None]:
    """Check one value. Returns ``(text to save or None to clear, rule broken or None)``."""
    if value is None:
        return None, None
    if key == "context_window":
        return validate_int(_WINDOW, value)
    if key == "idle_sleep":
        return validate_int(_IDLE, value)
    text = str(value).strip()
    if key == "binary":
        return (text, None) if rules.check_binary(text) else (None, BINARY_RULE)
    return (text, None) if rules.model_kind(text) else (None, MODEL_RULE)


@router.put("/llamacpp/server", operation_id="saveLlamacppServer")
async def save_server(
    principal: ManageScope, body: ServerBody, request: Request, runtime: RuntimeDep
) -> Response:
    """Save the program, the model and the context window.

    400 for a broken rule (the message names the rule, never the value), 403
    when the body sets the program or the model and the session lacks the
    ``credentials`` scope, 409 for a locked field. A running server keeps running.
    """
    keys = [k for k in _FIELD_IDS if k in body.model_fields_set]
    if not keys:
        return error_response(
            400, "Send at least one of binary, model, context_window or idle_sleep."
        )
    if {"binary", "model"} & set(keys) and "credentials" not in principal.scopes:
        return error_response(403, CREDENTIALS_RULE)
    updates: dict[str, str | int | None] = {}
    for key in keys:
        text, rule = _check(key, getattr(body, key))
        if rule:
            return error_response(400, rule)
        whole = key in ("context_window", "idle_sleep") and text
        updates[_FIELD_IDS[key]] = int(text) if whole else text
    state = runtime.providers
    if state is None:
        return error_response(404, "Provider settings are not available.")
    async with admitted(runtime), state.lock:
        view = await run_in_threadpool(compose.llamacpp_server_settings, state.values)
        for key in keys:
            if view[key]["locked"]:
                return error_response(409, view[key]["lock_reason"] or "This field is locked.")
        try:
            await run_in_threadpool(state.save_fields, runtime.engine, updates, body.revision)
        except SettingsFileError as exc:
            return refusal_response(exc)
        except EngineRefused:
            return error_response(409, _REFUSED)
        return await _respond(runtime, _manager(request).status())


@router.post("/llamacpp/server/start", operation_id="startLlamacppServer")
async def start_server(_: ManageScope, request: Request, runtime: RuntimeDep) -> Response:
    """Start the server with the saved values. A refusal is state `failed` with one fixed reason."""
    async with admitted(runtime):
        view = await run_in_threadpool(compose.llamacpp_server_settings, _values(runtime))
        status = await _manager(request).start(_launch_config(view))
        return ok(_body(view, status, _revision(runtime)))


@router.post("/llamacpp/server/stop", operation_id="stopLlamacppServer")
async def stop_server(_: ManageScope, request: Request, runtime: RuntimeDep) -> Response:
    """Stop the process this server started. With none owned, nothing is signalled."""
    async with admitted(runtime):
        return await _respond(runtime, await _manager(request).stop())


@router.post("/llamacpp/server/restart", operation_id="restartLlamacppServer")
async def restart_server(_: ManageScope, request: Request, runtime: RuntimeDep) -> Response:
    """Stop the owned process, then start it with the saved values."""
    async with admitted(runtime):
        view = await run_in_threadpool(compose.llamacpp_server_settings, _values(runtime))
        status = await _manager(request).restart(_launch_config(view))
        return ok(_body(view, status, _revision(runtime)))
