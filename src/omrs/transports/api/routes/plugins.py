"""Notebook plugin administration and editor routes (design D10, task 8.6).

Every route needs the session-only ``plugins`` scope: a bearer credential
never registers, probes, opens or stops anything.

* Registration is an explicit trust decision (``approved: true``). The
  manifest must be an approved file: the shipped marimo manifest or a
  file below ``<workspace>/plugins/``. The executable must sit in a
  directory of the server's ``PATH`` at launch or below
  ``<workspace>/plugins/``, and its file name must be the manifest's
  executable name. Registration runs no process.
* A recheck runs only the manifest probe recipe.
* Opening an editor needs ``consent: true``, an active experiment
  context and a notebook path relative to that context's workspace. The
  supervisor rechecks compatibility first. The editor access token is
  returned once, in the response body; it is never logged and never part
  of a URL.
* Each open also issues a NEW bearer credential bound to the experiment
  context (scopes ``graph``, ``read``, ``run``). The launcher writes it to
  a private token file (0o600) in the editor's private launch directory,
  beside a private connection file (``omrs_connection.json``) that holds
  the API address, the context id and the token file path. The editor
  gets the connection file path in ``OMRS_CONNECTION_FILE``. The response
  never holds this credential. Stop, a failed open and application
  shutdown revoke it; removing the launch directory deletes both files.
* OMRS installs and updates nothing. Stop, update outside OMRS, recheck,
  then open again.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ....core.experiments import ExperimentAdmissionError
from ....core.plugins import (
    ManifestError,
    PluginConsentError,
    PluginLaunchError,
    PluginTrustError,
    parse_manifest,
)
from ....core.plugins.editor import EditorConnection
from ..engine_access import RuntimeDep
from ..errors import error_response
from ..lifespan import PluginHost
from ..security import AccessPolicy, Principal, require_scope
from .experiments import TRUST_NOTICE, refusal
from .graphs import ok

router = APIRouter(prefix="/v1")

PluginsScope = Annotated[Principal, Depends(require_scope("plugins"))]

#: Scopes of the bearer credential that an opened notebook receives.
EDITOR_CREDENTIAL_SCOPES: frozenset[str] = frozenset({"graph", "read", "run"})

INSTALL_HINT = (
    "Install the notebook editor outside OMRS (for example `uv tool install marimo`), "
    "then register its manifest and executable here and run a compatibility check. "
    "OMRS never installs or updates it."
)


class RegisterPluginBody(BaseModel):
    """Body of ``POST /v1/plugins``."""

    model_config = ConfigDict(extra="forbid")

    manifest_path: str = Field(min_length=1, max_length=4096)
    executable_path: str = Field(min_length=1, max_length=4096)
    approved: bool


class OpenEditorBody(BaseModel):
    """Body of ``POST /v1/plugins/{name}/editors``."""

    model_config = ConfigDict(extra="forbid")

    notebook: str = Field(min_length=1, max_length=1024)
    experiment_context: str = Field(min_length=1, max_length=64)
    consent: bool


def _host(runtime: Any) -> PluginHost:
    return runtime.plugins


def _state(state: Any) -> dict[str, Any]:
    manifest = state.manifest
    return {
        "name": state.name,
        "status": state.status,
        "message": state.message,
        "executable": state.executable,
        "version": state.version,
        "launchable": state.launchable,
        "display_name": manifest.display_name if manifest else None,
        "tool": manifest.tool_name if manifest else None,
    }


def _editor(host: PluginHost, session: Any) -> dict[str, Any]:
    return {
        "launch_id": session.launch_id,
        "plugin": session.plugin,
        "notebook": str(session.notebook),
        "experiment_context": host.editor_contexts.get(session.launch_id),
        "url_without_token": f"http://{session.host}:{session.port}/",
    }


def _real(path: Path) -> Path:
    return Path(os.path.realpath(path))


def _manifest_problem(host: PluginHost, raw: str) -> str | None:
    """Return why *raw* is not an approved manifest location, or ``None``."""
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        return "Give the manifest as an absolute path without '..' parts."
    real = _real(path)
    approved = {_real(item) for item in host.manifests}
    if real in approved or real.is_relative_to(_real(host.manifest_dir)):
        return None
    return (
        f"This manifest is not in an approved location. Use the shipped marimo manifest "
        f"or copy the manifest below {host.manifest_dir} after you review it."
    )


def _executable_problem(host: PluginHost, raw: str, expected: str) -> tuple[int, str] | None:
    """Return ``(status, message)`` when *raw* is not an approved executable."""
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        return 400, "Give the executable as an absolute path without '..' parts."
    parent = _real(path.parent)
    dirs = [_real(item) for item in host.executable_dirs]
    if parent not in dirs and not parent.is_relative_to(_real(host.manifest_dir)):
        return 403, (
            "This executable is not in an approved location: use one on the server's PATH "
            f"or below {host.manifest_dir}."
        )
    if path.name != expected:
        return 400, f"The manifest names the executable {expected!r}, not {path.name!r}."
    return None


# ── Registrations ────────────────────────────────────────────────────────


@router.get("/plugins", operation_id="listPlugins")
async def list_plugins(_: PluginsScope, runtime: RuntimeDep) -> Response:
    """List plugin states and running editors. Runs no process."""
    host = _host(runtime)
    states = await run_in_threadpool(host.registry.list_states)
    return ok(
        {
            "plugins": [_state(state) for state in states],
            "editors": [_editor(host, session) for session in host.editors.sessions()],
            "install_hint": INSTALL_HINT,
            "trust_notice": TRUST_NOTICE,
        }
    )


@router.post("/plugins", status_code=201, operation_id="registerPlugin")
async def register_plugin(
    _: PluginsScope, body: RegisterPluginBody, runtime: RuntimeDep
) -> Response:
    """Record an approved manifest and executable. Runs no process."""
    host = _host(runtime)
    if not body.approved:
        return error_response(
            403, "Registering a plugin needs your explicit approval (approved: true)."
        )
    problem = _manifest_problem(host, body.manifest_path)
    if problem is not None:
        return error_response(403, problem)
    try:
        manifest = parse_manifest(Path(body.manifest_path).read_bytes())
    except ManifestError as exc:
        return error_response(400, str(exc), error_type="validation")
    except OSError:
        return error_response(400, "The manifest file cannot be read.", error_type="validation")
    refused = _executable_problem(host, body.executable_path, manifest.executable_name)
    if refused is not None:
        return error_response(refused[0], refused[1])
    try:
        await run_in_threadpool(
            host.registry.register,
            Path(body.manifest_path),
            Path(body.executable_path),
            approved=True,
        )
    except PluginTrustError as exc:
        return error_response(403, str(exc))
    except (ManifestError, OSError) as exc:
        return error_response(400, str(exc), error_type="validation")
    state = await run_in_threadpool(host.registry.state, manifest.plugin_id)
    return ok({"plugin": _state(state), "trust_notice": TRUST_NOTICE}, 201)


@router.post("/plugins/{name}/recheck", operation_id="recheckPlugin")
async def recheck_plugin(_: PluginsScope, name: str, runtime: RuntimeDep) -> Response:
    """Run the manifest probe recipe against the registered executable."""
    try:
        state = await run_in_threadpool(_host(runtime).registry.recheck, name)
    except KeyError:
        return error_response(404, "Unknown plugin.")
    return ok({"plugin": _state(state)})


@router.delete("/plugins/{name}", operation_id="unregisterPlugin")
async def unregister_plugin(_: PluginsScope, name: str, runtime: RuntimeDep) -> Response:
    """Remove a registration. Stop its editors first. Files are not touched."""
    host = _host(runtime)
    if any(session.plugin == name for session in host.editors.sessions()):
        return error_response(409, "An editor of this plugin is running. Stop it first.")
    try:
        await run_in_threadpool(host.repository.unregister_plugin, name)
    except KeyError:
        return error_response(404, "Unknown plugin.")
    return ok({"name": name, "unregistered": True})


# ── Editors ──────────────────────────────────────────────────────────────


def _notebook_path(workspace: Path, raw: str) -> tuple[int, str] | Path:
    """Return the notebook inside *workspace*, or ``(status, message)``."""
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".py":
        return 400, "Give the notebook as a relative .py path inside the experiment workspace."
    path = _real(workspace / relative)
    if not path.is_relative_to(_real(workspace)):
        return 400, "The notebook resolves outside the experiment workspace."
    if not path.is_file():
        return 404, "The notebook does not exist in the experiment workspace."
    return path


def _editor_connection(policy: AccessPolicy, context_id: str) -> tuple[EditorConnection, str]:
    """Issue a new context-bound credential; return the connection and the credential id."""
    issued = policy.issue_bearer(
        EDITOR_CREDENTIAL_SCOPES, "notebook editor", experiment_context=context_id
    )
    host = f"[{policy.host}]" if ":" in policy.host else policy.host
    api_url = f"http://{host}:{policy.port}"
    return EditorConnection(api_url, context_id, issued.token), issued.id


def _end_editor(host: PluginHost, launch_id: str) -> None:
    """Forget a stopped editor and revoke its notebook credential."""
    host.editor_contexts.pop(launch_id, None)
    cleanup = host.editor_cleanups.pop(launch_id, None)
    if cleanup is not None:
        cleanup()


@router.post("/plugins/{name}/editors", status_code=201, operation_id="openPluginEditor")
async def open_plugin_editor(
    _: PluginsScope, name: str, body: OpenEditorBody, runtime: RuntimeDep, request: Request
) -> Response:
    """Recheck the plugin, then open a notebook in a separate local editor.

    The response carries the editor access token once
    (``token_delivery.token``); the URL never holds it. The notebook API
    credential reaches the editor only through its private connection file.
    """
    host = _host(runtime)
    if not body.consent:
        return error_response(
            403, "Opening a notebook runs its Python with your permissions; consent is required."
        )
    try:
        if runtime.experiments is None:
            raise ExperimentAdmissionError(
                "experiment_context_unknown",
                "No experiment context has this id.",
                body.experiment_context,
            )
        context = runtime.experiments.registry.require_active(body.experiment_context)
    except ExperimentAdmissionError as exc:
        return refusal(exc, 400)
    notebook = _notebook_path(context.workspace, body.notebook)
    if isinstance(notebook, tuple):
        return error_response(notebook[0], notebook[1])
    policy: AccessPolicy = request.app.state.access_policy
    connection, credential_id = _editor_connection(policy, context.context_id)
    revoke = functools.partial(policy.revoke_bearer, credential_id)
    try:
        session = await run_in_threadpool(
            functools.partial(
                host.editors.open, name, notebook, consent=True, connection=connection
            )
        )
    except KeyError:
        revoke()
        return error_response(404, "Unknown plugin.")
    except PluginConsentError as exc:
        revoke()
        return error_response(403, str(exc))
    except PluginLaunchError as exc:
        revoke()
        return error_response(409, str(exc))
    except BaseException:
        revoke()  # nothing may keep a credential that no editor holds
        raise
    host.editor_contexts[session.launch_id] = context.context_id
    host.editor_cleanups[session.launch_id] = revoke
    return ok(
        {
            **_editor(host, session),
            "token_delivery": {"method": "response_body_once", "token": session.token},
            "trust_notice": TRUST_NOTICE,
        },
        201,
    )


@router.delete("/plugin-editors/{launch_id}", operation_id="stopPluginEditor")
async def stop_plugin_editor(_: PluginsScope, launch_id: str, runtime: RuntimeDep) -> Response:
    """Stop one owned editor: graceful first, then bounded escalation.

    Notebook files are not touched. The editor's notebook credential is
    revoked, and its private launch directory (with the connection and
    token files) is removed.
    """
    host = _host(runtime)
    try:
        await run_in_threadpool(host.editors.stop, launch_id)
    except KeyError:
        return error_response(404, "Unknown editor launch.")
    finally:
        _end_editor(host, launch_id)
    return ok({"launch_id": launch_id, "stopped": True})
