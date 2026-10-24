"""Integration catalogue and install routes (design D7; ``install-integrations-from-the-app``).

``GET /v1/integrations`` shows which optional integrations the running
server can use, its install type, and whether the app can install each
extra. It reads the runtime probes and the install receipt only.

``POST /v1/integrations/{extra}/install`` starts the one install job for an
allowed extra, and ``GET /v1/integrations/install`` reads its state. Both
need the browser session with the ``manage`` scope; a bearer credential
never passes. The path value only selects a catalogue entry: an unknown
value gets 404 and starts no process, and no request text reaches the
install command.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi import Path as PathParam
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from ..engine_access import ReadScope, RuntimeDep, admitted, require_session
from ..errors import API_HEADERS, error_response
from ..install_environment import InstallEnvironment
from ..install_job import InstallJob
from ..integrations_catalogue import Integration, describe_entry, describe_integrations
from ..integrations_catalogue import find_integration as find_extra
from ..lifespan import WebRuntime
from ..security import Principal, redact
from .graphs import ok

router = APIRouter(prefix="/v1")

ManageScope = Annotated[Principal, Depends(require_session("manage"))]
ExtraParam = Annotated[str, PathParam(max_length=64)]

UNKNOWN_EXTRA = "This extra is not in the integrations list."

#: Plain-English message for each 409 reason.
REASONS: dict[str, str] = {
    "not-installable-here": "The app does not install this extra. Use the command on its entry.",
    "status-unknown": (
        "The server could not check whether this extra is installed. "
        "Use the command on its entry instead."
    ),
    "already-installed": "This extra is already installed.",
    "no-requirements": "This extra adds no packages, so there is nothing to install.",
    "not-uv-tool": (
        "This server does not run as a uv tool install, so the app cannot install into it. "
        "Use the command on the entry, then restart the server."
    ),
    "uv-not-found": "The uv program was not found. Use the command on the entry instead.",
    "install-running": "Another install is running. Wait until it finishes, then try again.",
}


async def _settings(runtime: WebRuntime) -> Any:
    try:
        return runtime.engine.resolve_settings()
    except Exception:
        return None


def _catalogue(settings: Any, job: InstallJob) -> tuple[InstallEnvironment, list[dict[str, Any]]]:
    environment = job.detect()
    entries = describe_integrations(settings, environment, job.restart_needed, job.requirements)
    return environment, entries


def _one(
    item: Integration, settings: Any, job: InstallJob
) -> tuple[InstallEnvironment, dict[str, Any]]:
    environment = job.detect()
    entry = describe_entry(item, settings, environment, job.restart_needed, job.requirements)
    return environment, entry


def _conflict(reason: str) -> JSONResponse:
    body = {"status": "error", "message": redact(REASONS[reason]), "reason": reason}
    return JSONResponse(body, status_code=409, headers=API_HEADERS)


@router.get("/integrations", operation_id="listIntegrations")
async def list_integrations(_: ReadScope, runtime: RuntimeDep) -> Response:
    """List every installable integration with its availability in this launch.

    The probes may import optional packages, so they run off the event
    loop. A probe that fails gives the ``unknown`` state for that entry.
    """
    async with admitted(runtime):
        settings = await _settings(runtime)
        environment, entries = await run_in_threadpool(_catalogue, settings, runtime.installs)
    return ok({"install_type": environment.install_type, "integrations": entries})


@router.get("/integrations/install", operation_id="getIntegrationInstall")
async def get_install(_: ManageScope, runtime: RuntimeDep) -> Response:
    """Report the running or last install of this launch."""
    return ok({"install": runtime.installs.snapshot()})


@router.post("/integrations/{extra}/install", operation_id="installIntegration")
async def install_integration(_: ManageScope, extra: ExtraParam, runtime: RuntimeDep) -> Response:
    """Start installing an allowed extra into this server's own environment."""
    item = find_extra(extra)
    if item is None or item.extra is None:
        return error_response(404, UNKNOWN_EXTRA)
    job = runtime.installs
    async with admitted(runtime):
        settings = await _settings(runtime)
        environment, entry = await run_in_threadpool(_one, item, settings, job)
    reason = entry["install_reason"] or ("install-running" if job.running else None)
    if reason is not None or environment.uv is None:
        return _conflict(reason or "uv-not-found")
    redactor = getattr(runtime.engine, "redact", None)
    job.start(item.extra, environment.uv, entry["packages"], redactor=redactor)
    return ok({"install": job.snapshot()}, 202)
