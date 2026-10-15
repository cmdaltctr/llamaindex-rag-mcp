"""Experiment context routes (design D10, task 8.5).

The browser session registers an experiment workspace below an approved
experiment root (``omrg web --experiment-root``), lists and inspects the
approval records, and revokes a context. Every route needs the
session-only ``manage`` scope: a bearer credential never approves or
revokes a workspace.

Contexts live in memory for one launch, like bearer credentials. A new
launch starts with no context. Registration builds no Engine; the
context Engine is built on its first admitted run.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from ...core.experiments import (
    ExperimentAdmissionError,
    ExperimentPathError,
    create_folder,
    folder_tree,
)
from .engine_access import RuntimeDep, require_session
from .errors import API_HEADERS, error_response
from .routes_graphs import ok
from .security import Principal

router = APIRouter(prefix="/v1")

ManageScope = Annotated[Principal, Depends(require_session("manage"))]

#: Shown wherever an experiment or a notebook editor is approved or opened.
TRUST_NOTICE = (
    "Notebook Python runs with your user account's filesystem and network "
    "permissions. A dependency environment is not an operating-system sandbox. "
    "Open only notebooks you trust."
)

_NO_ROOTS = (
    "No experiment root is approved for this server. Restart it with "
    "`omrg web --experiment-root <directory>` to register experiment workspaces."
)


class ExperimentRequest(BaseModel):
    """Body of ``POST /v1/experiments``."""

    model_config = ConfigDict(extra="forbid")

    workspace: str = Field(min_length=1, max_length=4096)
    name: str = Field(default="", max_length=80)
    actions: list[str] | None = Field(default=None, min_length=1, max_length=2)
    store_backend: str = Field(default="lancedb", min_length=1, max_length=32)
    declared_factors: list[str] = Field(default_factory=list, max_length=8)


class ExperimentFolderRequest(BaseModel):
    """Body of ``POST /v1/experiment-folders``."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=4096)
    root: str | None = Field(default=None, min_length=1, max_length=4096)


def refusal(exc: ExperimentAdmissionError | ExperimentPathError, status_code: int) -> Response:
    """Return the stable experiment error payload with *status_code*."""
    return JSONResponse(exc.to_dict(), status_code=status_code, headers=API_HEADERS)


def _entry(experiments: Any, context: Any) -> dict[str, Any]:
    return {
        "experiment": context.record(),
        "identity": experiments.identity(context.context_id).provenance(),
    }


@router.post("/experiments", status_code=201, operation_id="createExperiment")
async def create_experiment(
    _: ManageScope, body: ExperimentRequest, runtime: RuntimeDep
) -> Response:
    """Approve an experiment workspace below an approved root.

    Returns the approval record and the backend and index identity of the
    context store (below ``<workspace>/output/``). Nothing is built yet.
    """
    experiments = runtime.experiments
    if experiments is None:
        return error_response(409, _NO_ROOTS)
    options: dict[str, Any] = {
        "name": body.name,
        "store_backend": body.store_backend,
        "declared_factors": body.declared_factors,
    }
    if body.actions is not None:
        options["actions"] = body.actions
    try:
        context = experiments.registry.register(body.workspace, **options)
    except ExperimentPathError as exc:
        return refusal(exc, 400)
    return ok({**_entry(experiments, context), "trust_notice": TRUST_NOTICE}, 201)


@router.post("/experiment-folders", status_code=201, operation_id="createExperimentFolder")
async def create_experiment_folder(
    _: ManageScope, body: ExperimentFolderRequest, runtime: RuntimeDep
) -> Response:
    """Create a folder below an approved experiment root.

    The path is relative, has at most four levels and no ``..`` part, and
    no part may be a link. A refused path creates nothing. Register a
    sub-experiment in the folder with ``POST /v1/experiments``.
    """
    experiments = runtime.experiments
    if experiments is None:
        return error_response(409, _NO_ROOTS)
    registry = experiments.registry
    try:
        created = await run_in_threadpool(
            create_folder, registry.approved_roots, body.path, root=body.root
        )
    except ExperimentPathError as exc:
        return refusal(exc, 409 if exc.code == "exists" else 400)
    root = next(item for item in registry.approved_roots if created.is_relative_to(item))
    return ok(
        {
            "folder": {
                "root": str(root),
                "path": created.relative_to(root).as_posix(),
                "name": created.name,
                "workspace": str(created),
            }
        },
        201,
    )


@router.get("/experiments", operation_id="listExperiments")
async def list_experiments(_: ManageScope, runtime: RuntimeDep) -> Response:
    """List the approved roots, their folder trees and every context of this launch."""
    experiments = runtime.experiments
    if experiments is None:
        return ok({"roots": [], "folders": [], "experiments": [], "trust_notice": TRUST_NOTICE})
    registry = experiments.registry
    contexts = registry.contexts()
    folders = [
        {"root": str(root), "tree": await run_in_threadpool(folder_tree, root, contexts)}
        for root in registry.approved_roots
    ]
    return ok(
        {
            "roots": [str(root) for root in registry.approved_roots],
            "folders": folders,
            "experiments": [_entry(experiments, item) for item in contexts],
            "trust_notice": TRUST_NOTICE,
        }
    )


@router.get("/experiments/{context_id}", operation_id="getExperiment")
async def get_experiment(_: ManageScope, context_id: str, runtime: RuntimeDep) -> Response:
    """Return one approval record and its backend and index identity."""
    try:
        context = _context(runtime, context_id)
    except ExperimentAdmissionError as exc:
        return refusal(exc, 404)
    return ok(_entry(runtime.experiments, context))


@router.delete("/experiments/{context_id}", operation_id="revokeExperiment")
async def revoke_experiment(_: ManageScope, context_id: str, runtime: RuntimeDep) -> Response:
    """Revoke a context.

    Later admissions fail with ``experiment_context_revoked``; a queued run
    fails before its Engine runs. A run that already started finishes; use
    ``POST /v1/runs/{run_id}/cancel`` to stop it. Bound credentials stay
    valid but cannot run anything. Workspace files are not touched.
    """
    try:
        _context(runtime, context_id)
        context = runtime.experiments.revoke(context_id)
    except ExperimentAdmissionError as exc:
        return refusal(exc, 404)
    return ok({"experiment": context.record()})


def _context(runtime: Any, context_id: str) -> Any:
    """Return a known context.

    Raises:
        ExperimentAdmissionError: ``experiment_context_unknown``.
    """
    if runtime.experiments is None:
        raise ExperimentAdmissionError(
            "experiment_context_unknown", "No experiment context has this id.", context_id
        )
    return runtime.experiments.registry.get(context_id)
