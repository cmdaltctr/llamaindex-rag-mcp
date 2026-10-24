"""``GET`` and ``PUT /v1/settings/configuration``: every setting, its source and its problems.

The route lists each setting with the value in force, where the value came
from, whether it applies at once or after a restart, and whether a hand edit
of ``omrs.jsonc`` is waiting for a restart. It also lists the problems found in
the file and the handover notice. It reads the file and the keychain, writes
nothing and sends no request to any provider.

A key field never leaves the server: ``value`` is ``null`` and ``last4`` holds
the last four characters (an empty string when the key is shorter than eight
characters). The page treats the presence of ``last4`` as "this is a key". A
value that broke its rule is ignored by the reader, so it never appears.

The launch writes the route's state to ``app.state.configuration`` (see
:class:`ConfigurationState`). A launch that sets nothing still answers, with
the file as it is now and no restart pending.

``PUT`` (edit-settings-from-configuration-page D3) saves one or more settings,
all or none under one revision, and answers with the ``GET`` body. It needs a
browser session with the manage scope. The checks before the write live in
``api/configuration_update.py``. With a running server the save goes through
the provider state, so provider fields, the upload limit and the MCP switch
apply at once; a restart-only key shows ``restart_pending``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ....compose_providers import resolve_keychain_references
from ....config.settings_file import SettingsFile, read_settings_file
from ....config.settings_file_write import SettingsFileError
from ....config.user_config import display_path
from ...settings_view import SettingView, describe_settings
from ..configuration_update import update_refusal
from ..engine_access import ReadScope, admitted, require_session
from ..errors import error_response
from ..live_settings import apply_file_settings
from ..provider_state import EngineRefused
from ..restart_snapshot import capture, pending
from ..security import Principal
from ..settings_handover import HandoverResult
from ..settings_store import SettingsFileStore, refusal_response
from .graphs import ok

if TYPE_CHECKING:
    from ....config import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

ManageScope = Annotated[Principal, Depends(require_session("manage"))]
#: Most changes one save may hold. It is above the number of writable keys.
MAX_CHANGES = 128
READ_FAILED = "The configuration could not be read."
ENGINE_REFUSED = "The running engine cannot take this change. Restart the server to apply it."


class ConfigurationUpdate(BaseModel):
    """Body of ``PUT /v1/settings/configuration``.

    Attributes:
        revision: The ``revision`` the page last read.
        changes: Dotted key to new value. ``null`` removes the key from the file.
    """

    model_config = ConfigDict(extra="forbid")

    revision: Annotated[str, Field(max_length=128)]
    changes: Annotated[dict[str, Any], Field(min_length=1, max_length=MAX_CHANGES)]


@dataclass
class ConfigurationState:
    """What the route needs, kept on ``app.state.configuration`` for one launch.

    Every member has a default, so a test or a partial launch can set only
    what it needs.

    Attributes:
        launch_settings: ``Settings`` as the process launched. Restart-only
            rows show it. ``None`` means the live settings.
        snapshot: The restart-only file values at launch (``capture``). ``None``
            means the file as it is now, so nothing is pending.
        handover: The result of the handover at launch.
        live_settings: Resolves ``Settings`` now, for rows that apply at once.
            ``None`` builds ``Settings()``.
        read_file: Reads ``omrs.jsonc`` now.
        overrides: ``(value, source)`` by file-only key, for a value the
            launch fixed (``--port`` is ``init``, ``WEB_MAX_UPLOAD_MIB`` is ``env``).
    """

    launch_settings: Settings | None = None
    snapshot: Mapping[str, Any] | None = None
    handover: HandoverResult = field(default_factory=lambda: HandoverResult(False, None))
    live_settings: Callable[[], Settings] | None = None
    read_file: Callable[[], SettingsFile] = read_settings_file
    overrides: Mapping[str, tuple[Any, str]] = field(default_factory=dict)


def _resolved(settings: Settings, keychain: Any) -> Settings:
    """Return *settings* with each ``keychain://`` reference resolved."""
    return resolve_keychain_references(settings, store=keychain)[0]


def _row(view: SettingView) -> dict[str, Any]:
    row: dict[str, Any] = {
        "key": view.key,
        "value": view.value,
        "source": view.source,
        "applies": view.applies,
        "restart_pending": view.restart_pending,
        "saved": view.saved,
        "editable": view.editable,
        "read_only_reason": view.read_only_reason,
        "kind": view.kind,
        "choices": None if view.choices is None else list(view.choices),
        "min": view.min,
        "max": view.max,
        "nullable": view.nullable,
    }
    if view.last4 is not None:
        row["last4"] = view.last4
    return row


def build_configuration(state: ConfigurationState | None, keychain: Any) -> dict[str, Any]:
    """Return the body of ``GET /v1/settings/configuration``.

    Args:
        state: The launch state, or ``None`` for a launch that set none.
        keychain: The keychain store (``app.state.keychain``).

    Returns:
        The response body without ``status``. It holds no key and no refused value.
    """
    state = state or ConfigurationState()
    file = state.read_file()
    if state.live_settings is not None:
        live = state.live_settings()
    else:
        from ....config import Settings  # the build resolves; it is not a singleton

        live = Settings()
    live = _resolved(live, keychain)
    launch = live if state.launch_settings is None else _resolved(state.launch_settings, keychain)
    snapshot = capture(file) if state.snapshot is None else state.snapshot
    views = describe_settings(
        launch=launch,
        live=live,
        file=file,
        snapshot=snapshot,
        pending=pending(snapshot, file),
        overrides=state.overrides,
    )
    return {
        "path": display_path(file.path),
        "revision": file.revision,
        "settings": [_row(view) for view in views],
        "problems": [
            {"key": problem.key, "kind": problem.kind, "message": problem.message}
            for problem in file.problems
        ],
        "handover": {"pending": state.handover.pending, "folder": state.handover.folder},
    }


async def _configuration(request: Request) -> Response:
    state = getattr(request.app.state, "configuration", None)
    keychain = getattr(request.app.state, "keychain", None)
    try:
        body = await run_in_threadpool(build_configuration, state, keychain)
    except Exception:
        logger.exception("The configuration list could not be built.")
        return error_response(500, READ_FAILED)
    return ok(body)


@router.get("/settings/configuration", operation_id="getSettingsConfiguration")
async def get_configuration(_: ReadScope, request: Request) -> Response:
    """List every setting with its source, its restart state and the problems in the file."""
    return await _configuration(request)


def _launch(state: ConfigurationState | None) -> Settings:
    """Return the launch ``Settings`` of *state*, or the settings as resolved now."""
    state = state or ConfigurationState()
    if state.launch_settings is not None:
        return state.launch_settings
    if state.live_settings is not None:
        return state.live_settings()
    from ....config import Settings  # the build resolves; it is not a singleton

    return Settings()


async def _save(request: Request, body: ConfigurationUpdate) -> Response | None:
    """Write the changes; return an error response, or ``None`` when the write passed."""
    runtime = getattr(request.app.state, "runtime", None)
    providers = getattr(runtime, "providers", None)
    try:
        if providers is None:
            http = getattr(request.app.state, "mcp_http", None)
            store = getattr(http, "store", None) or SettingsFileStore()
            await run_in_threadpool(store.write, body.changes, body.revision)
            return None
        async with admitted(runtime), providers.lock:
            await run_in_threadpool(
                providers.save_fields, runtime.engine, body.changes, body.revision
            )
            file = await run_in_threadpool(providers.store.read)
            apply_file_settings(request.app, runtime, file)
    except SettingsFileError as exc:
        return refusal_response(exc)
    except EngineRefused:
        return error_response(409, ENGINE_REFUSED)
    return None


@router.put("/settings/configuration", operation_id="setSettingsConfiguration")
async def set_configuration(
    _: ManageScope, body: ConfigurationUpdate, request: Request
) -> Response:
    """Save one or more settings to ``omrs.jsonc``, all or none, and return the list."""
    state = getattr(request.app.state, "configuration", None)
    overrides = state.overrides if state is not None else {}
    try:
        launch = await run_in_threadpool(_launch, state)
    except Exception:
        logger.exception("The launch settings could not be resolved.")
        return error_response(500, READ_FAILED)
    refusal = await run_in_threadpool(update_refusal, body.changes, launch, overrides)
    if refusal is not None:
        return error_response(*refusal)
    failed = await _save(request, body)
    return failed if failed is not None else await _configuration(request)
