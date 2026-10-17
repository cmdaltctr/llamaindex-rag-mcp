"""Graph routes: operation catalogue, pipelines, layouts, revisions, validation.

Handlers validate the request, delegate to the Engine (catalogue and
graph validation) or to the workspace repository (records), and format
the result. Core validation decides what a valid graph is; a direct API
submission gets the same structured issues as the canvas.

Scopes: reads need ``read``; saves and validation need ``graph``.
Layout saves never create a revision. Revisions are immutable, and
identical content returns the existing revision (content-hash dedupe).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from ....compose_profiles import ProfileDeletedError, ProfileNotReadyError
from ....core.pipelines import PipelineValidationError, parse_definition
from ....core.workspace import TASK_LAYOUT_KEY, content_hash
from ..engine_access import ReadScope, RuntimeDep, admitted
from ..errors import API_HEADERS, error_response
from ..runs_wiring import RunsDep, WorkspaceRuns, describe_operations
from ..security import Principal, redact, require_scope

router = APIRouter(prefix="/v1")

GraphScope = Annotated[Principal, Depends(require_scope("graph"))]


class LayoutBody(BaseModel):
    """Body of ``PUT /v1/pipelines/{pipeline_id}/layout``."""

    model_config = ConfigDict(extra="forbid")

    layout: dict[str, Any]


class RevisionBody(BaseModel):
    """Body of ``POST /v1/pipelines/{pipeline_id}/revisions``."""

    model_config = ConfigDict(extra="forbid")

    document: dict[str, Any]


class ValidateBody(BaseModel):
    """Body of ``POST /v1/pipelines/validate``."""

    model_config = ConfigDict(extra="forbid")

    document: dict[str, Any]
    inputs: dict[str, Any] | None = None
    collection: str | None = Field(default=None, min_length=1, max_length=128)


def ok(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
    """Return a success body with the API headers."""
    body = jsonable_encoder({"status": "ok", **payload})
    return JSONResponse(body, status_code=status_code, headers=API_HEADERS)


def validation_failure(
    exc: PipelineValidationError, redactor: Callable[[str], str] | None = None
) -> JSONResponse:
    """Return 422 with the error envelope and every structured issue.

    Args:
        exc: The validation failure.
        redactor: ``Engine.redact``; removes provider credential values.
    """

    def clean(text: str) -> str:
        return redact(redactor(text) if redactor else text)

    issues = [{**issue.model_dump(), "message": clean(issue.message)} for issue in exc.issues]
    body: dict[str, Any] = {
        "status": "error",
        "message": clean(str(exc)),
        "error_type": "validation",
        "issues": issues,
    }
    if exc.nodes is not None:
        body["nodes"] = list(exc.nodes)
    return JSONResponse(body, status_code=422, headers=API_HEADERS)


def _pipeline(runs: WorkspaceRuns, pipeline_id: str) -> dict[str, Any] | None:
    try:
        return dict(runs.service.repository.get_pipeline(pipeline_id))
    except KeyError:
        return None


def _unknown_pipeline() -> Response:
    return error_response(404, "Unknown pipeline.")


def _reserved() -> Response:
    return error_response(409, "This pipeline holds workspace jobs and cannot be edited.")


def _reserved_layout(layout: dict[str, Any]) -> Response | None:
    if TASK_LAYOUT_KEY in layout:
        return error_response(400, f"The layout key {TASK_LAYOUT_KEY!r} is reserved.")
    return None


# ── Catalogue ────────────────────────────────────────────────────────────


@router.get("/pipeline-operations", operation_id="listPipelineOperations")
async def list_pipeline_operations(_: ReadScope, runtime: RuntimeDep) -> Response:
    """Return the operation catalogue with availability and reasons."""
    async with admitted(runtime):
        operations = await run_in_threadpool(describe_operations, runtime.engine)
    return ok({"operations": operations})


# ── Pipelines and layouts ────────────────────────────────────────────────


@router.post("/pipelines", operation_id="createPipeline", deprecated=True)
async def create_pipeline(_: GraphScope) -> Response:
    """Withdrawn. Pipelines belong to profiles; create a profile instead."""
    return error_response(410, "Create a profile instead: POST /v1/profiles.")


@router.get("/pipelines", operation_id="listPipelines")
async def list_pipelines(_: ReadScope, runs: RunsDep) -> Response:
    """List pipelines in creation order; reserved job pipelines are hidden."""
    records = [p for p in runs.service.repository.list_pipelines() if not runs.is_task_pipeline(p)]
    return ok({"pipelines": records})


@router.get("/pipelines/{pipeline_id}", operation_id="getPipeline")
async def get_pipeline(
    _: ReadScope, pipeline_id: str, runs: RunsDep, runtime: RuntimeDep
) -> Response:
    """Return a pipeline, its layout, its current revision (or ``null``) and its profile slot.

    ``profile_slot`` names the profile and the slot (``ingest``, ``search`` or
    ``answer``) that the pipeline fills. It is ``null`` for any other pipeline.
    """
    record = _pipeline(runs, pipeline_id)
    if record is None:
        return _unknown_pipeline()
    current = record.get("current_revision_id")
    revision = runs.service.repository.get_revision(current) if current else None
    owner = runtime.profiles.owner_of(pipeline_id) if runtime.profiles is not None else None
    slot = None if owner is None else {"profile_id": owner[0]["profile_id"], "slot": owner[1]}
    return ok({"pipeline": record, "current_revision": revision, "profile_slot": slot})


@router.put("/pipelines/{pipeline_id}/layout", operation_id="savePipelineLayout")
async def save_pipeline_layout(
    _: GraphScope, pipeline_id: str, body: LayoutBody, runs: RunsDep, runtime: RuntimeDep
) -> Response:
    """Replace the presentation layout. No revision is created."""
    record = _pipeline(runs, pipeline_id)
    if record is None:
        return _unknown_pipeline()
    if runs.is_task_pipeline(record):
        return _reserved()
    if (refused := _reserved_layout(body.layout)) is not None:
        return refused
    if runtime.profiles is not None:
        try:
            runtime.profiles.check_slot_editable(pipeline_id)
        except ProfileDeletedError as exc:
            return error_response(409, str(exc))
    return ok({"pipeline": runs.service.repository.save_layout(pipeline_id, body.layout)})


# ── Revisions ────────────────────────────────────────────────────────────


@router.post("/pipelines/{pipeline_id}/revisions", operation_id="savePipelineRevision")
async def save_pipeline_revision(
    _: GraphScope, pipeline_id: str, body: RevisionBody, runs: RunsDep, runtime: RuntimeDep
) -> Response:
    """Store an immutable execution revision and make it current.

    The document must parse as a supported graph document; full checks
    run at validation and admission. A wrapped ``{"graph", "layout"}``
    document stores the graph only. Returns 201 for a new revision and
    200 when identical content already exists.
    """
    record = _pipeline(runs, pipeline_id)
    if record is None:
        return _unknown_pipeline()
    if runs.is_task_pipeline(record):
        return _reserved()
    try:
        graph = parse_definition(body.document).graph
    except PipelineValidationError as exc:
        return validation_failure(exc, runtime.engine.redact)
    document = graph.model_dump(mode="json")
    try:
        async with admitted(runtime):
            revision, created, affected = await run_in_threadpool(
                _store_revision, runs, runtime.profiles, pipeline_id, document, graph.schema_version
            )
    except ProfileNotReadyError as exc:
        failure = {
            "status": "error",
            "message": runtime.engine.redact(str(exc)),
            "error_type": "validation",
            "not_ready_reasons": exc.reasons,
        }
        return JSONResponse(failure, status_code=409, headers=API_HEADERS)
    except ProfileDeletedError as exc:
        return error_response(409, str(exc))
    except ValueError as exc:
        return error_response(400, str(exc), error_type="validation")
    payload: dict[str, Any] = {"revision": revision, "created": created}
    if affected is not None:
        payload["affected_collections"] = affected
    return ok(payload, 201 if created else 200)


def _store_revision(
    runs: WorkspaceRuns,
    profiles: Any,
    pipeline_id: str,
    document: dict[str, Any],
    schema_version: int,
) -> tuple[dict[str, Any], bool, list[str] | None]:
    """Check the slot rules, then save the revision, under the lock that a delete takes.

    Returns:
        The revision, whether it is new, and the collections that the save
        affects (``None`` for a pipeline that belongs to no profile).
    """
    repository = runs.service.repository
    with profiles.lock if profiles is not None else contextlib.nullcontext():
        affected = profiles.check_slot_save(pipeline_id, document) if profiles else None
        known = {rev["content_hash"] for rev in repository.list_revisions(pipeline_id)}
        created = content_hash(document) not in known
        revision = repository.save_revision(pipeline_id, document, schema_version=schema_version)
    return dict(revision), created, affected


@router.get("/pipelines/{pipeline_id}/revisions", operation_id="listPipelineRevisions")
async def list_pipeline_revisions(_: ReadScope, pipeline_id: str, runs: RunsDep) -> Response:
    """List a pipeline's revisions by revision number."""
    if _pipeline(runs, pipeline_id) is None:
        return _unknown_pipeline()
    return ok({"revisions": runs.service.repository.list_revisions(pipeline_id)})


@router.get("/pipelines/{pipeline_id}/revisions/{revision_id}", operation_id="getPipelineRevision")
async def get_pipeline_revision(
    _: ReadScope, pipeline_id: str, revision_id: str, runs: RunsDep
) -> Response:
    """Return one revision of a pipeline."""
    try:
        revision = runs.service.repository.get_revision(revision_id)
    except KeyError:
        revision = None
    if revision is None or revision["pipeline_id"] != pipeline_id:
        return error_response(404, "Unknown revision.")
    return ok({"revision": revision})


# ── Validation ───────────────────────────────────────────────────────────


def _admitted_view(snapshot: Any) -> dict[str, Any]:
    return {
        "admitted": True,
        "graph_identity": snapshot.graph_identity,
        "order": list(snapshot.order),
        "collections": [
            {"name": c.name, "profile": c.profile_name, "profile_origin": c.profile_origin}
            for c in snapshot.collections
        ],
        "nodes": [
            {
                "node_id": n.node_id,
                "operation": n.operation,
                "version": n.version,
                "enabled": n.enabled,
                "collection": n.collection,
                "controls": [control.model_dump(mode="json") for control in n.controls],
            }
            for n in snapshot.nodes
        ],
    }


def _draft_view(report: Any) -> dict[str, Any]:
    return {
        "admitted": False,
        "order": list(report.order),
        "resolved_versions": dict(report.resolved_versions),
        "collections": dict(report.collections),
        "nodes": list(report.nodes),
    }


@router.post("/pipelines/validate", operation_id="validatePipeline")
async def validate_pipeline(_: GraphScope, body: ValidateBody, runtime: RuntimeDep) -> Response:
    """Validate a graph with the Engine; no node, model call or write runs.

    Without ``inputs`` this is the draft check. With ``inputs`` it is the
    admission check that a run submission applies.
    """
    engine = runtime.engine
    try:
        async with admitted(runtime):
            checked = await run_in_threadpool(
                engine.validate_pipeline,
                body.document,
                inputs=body.inputs,
                collection=body.collection,
            )
    except PipelineValidationError as exc:
        return validation_failure(exc, runtime.engine.redact)
    view = _draft_view(checked) if body.inputs is None else _admitted_view(checked)
    return ok({"valid": True, **view})
