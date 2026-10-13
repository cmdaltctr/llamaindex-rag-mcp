"""Long-running document jobs: ingestion, codebase maps and job polling.

These implement the reviewed ``/v1`` operations ``ingestPath``,
``generateCodebaseMap``, ``getJobStatus`` and ``listJobEvents``.
Submission returns 202 and a ``Job`` resource; ``GET /v1/jobs/{jobId}``
polls it, and ``GET /v1/jobs/{jobId}/events`` pages the events of the
run behind the job.

Jobs run on the workspace run service (design D7): the same single
consumer and bounded queue as graph runs, persisted records, interruption
of unfinished jobs at the next start, and cancellation of waiting jobs at
shutdown. A running ingestion or map call has no safe stop point, so
shutdown lets it finish before the Engine closes.

Paths must be absolute and inside an approved root (``omrg web --root``
or the managed upload root). Paths read from indexed metadata never
grant access. Both submissions need the session-only ``files`` scope.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from ...core.workspace import TERMINAL_RUN_STATUSES, QueueFullError, ServiceClosedError
from .engine_access import FilesScope, ReadScope, RuntimeDep, engine_store
from .errors import error_response
from .grants import GrantDenied
from .lifespan import WebRuntime
from .runs_wiring import RunsDep, WorkspaceRuns
from .security import redact

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

#: Run status to ``Job.status``.
_JOB_STATUS = {
    "queued": "queued",
    "running": "running",
    "cancelling": "running",
    "succeeded": "completed",
}


class IngestBody(BaseModel):
    """Body of ``ingestPath`` (schema ``IngestRequest``)."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(max_length=4096)
    collection: str = Field(default="documents", min_length=1, max_length=256)


class CodebaseMapBody(BaseModel):
    """Body of ``generateCodebaseMap`` (schema ``CodebaseMapRequest``)."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(max_length=4096)
    refresh: bool = False


class JobFailed(Exception):
    """A job's Engine call failed; the message is already redacted."""


def _granted(runtime: WebRuntime, path: str) -> str:
    """Return the canonical path when it is inside an approved root."""
    try:
        return str(runtime.grants.check(path))
    except GrantDenied as exc:
        raise HTTPException(403, str(exc)) from None


def _guarded(job: str, work: Callable[[], Awaitable[Any]]) -> Callable[[], Awaitable[Any]]:
    """Redact a failure before the run service records it."""

    async def run() -> Any:
        try:
            return await work()
        except Exception as exc:
            logger.warning("Web %s job failed: %s", job, redact(repr(exc)))
            raise JobFailed(f"{type(exc).__name__}: {redact(str(exc))[:300]}") from None

    return run


def _job_id(run_id: str) -> str:
    return str(uuid.UUID(run_id))


def describe_job(runs: WorkspaceRuns, run: Mapping[str, Any]) -> dict[str, Any]:
    """Return the ``Job`` view of a job run."""
    status = _JOB_STATUS.get(run["status"], "failed")
    result = error = None
    if status == "completed":
        stored = runs.result(run) or {}
        result = (stored.get("outputs") or {}).get("result")
    elif status == "failed":
        failure = run.get("failure") or {}
        error = failure.get("error") or f"The job was {run['status']}."
        error = error.removeprefix(f"{JobFailed.__name__}: ")
    updated = run.get("finished_at") or run.get("started_at") or run["created_at"]
    return {
        "job_id": _job_id(run["run_id"]),
        "status": status,
        "result": result,
        "error": error,
        "created_at": run["created_at"],
        "updated_at": updated,
    }


def _accept(
    runs: WorkspaceRuns, kind: str, inputs: dict[str, Any], work: Callable[[], Awaitable[Any]]
) -> Response:
    try:
        run = runs.submit_task(kind, inputs, _guarded(kind, work))
    except QueueFullError as exc:
        return error_response(429, f"The job queue is full: {exc.limit} jobs are waiting.")
    except ServiceClosedError:
        return error_response(503, "The server is shutting down.")
    return JSONResponse(describe_job(runs, run), status_code=202)


@router.post("/ingestions", status_code=202, operation_id="ingestPath")
async def ingest_path(
    _: FilesScope, body: IngestBody, runtime: RuntimeDep, runs: RunsDep
) -> Response:
    """Queue ingestion of an approved file or directory into a collection."""
    path = _granted(runtime, body.path)
    engine, collection = runtime.engine, body.collection

    async def work() -> dict[str, Any]:
        return await engine.ingest(path, collection_name=collection)

    return _accept(runs, "ingest", {"path": path, "collection": collection}, work)


@router.post("/codebase-maps", status_code=202, operation_id="generateCodebaseMap")
async def generate_codebase_map(
    _: FilesScope, body: CodebaseMapBody, runtime: RuntimeDep, runs: RunsDep
) -> Response:
    """Queue a codebase map of an approved directory.

    The job passes the Engine's own settings and store to the core map
    API explicitly; it never resolves process defaults.
    """
    path = _granted(runtime, body.path)
    engine, refresh = runtime.engine, body.refresh

    async def work() -> dict[str, Any]:
        from ...core.codebase import codebase_map

        settings = engine.resolve_settings()
        text = await asyncio.to_thread(
            codebase_map.get_codebase_map_text,
            path=path,
            refresh=refresh,
            settings=settings,
            store=engine_store(engine),
        )
        return {"map": text}

    return _accept(runs, "codebase_map", {"path": path, "refresh": refresh}, work)


#: Largest event page; the same limit as run event polling.
MAX_JOB_EVENT_PAGE = 500


def _job_run(runs: WorkspaceRuns, job_id: str) -> Mapping[str, Any] | None:
    """Return the run behind a job, or ``None`` for a graph run or unknown id."""
    repository = runs.service.repository
    try:
        run = repository.get_run(uuid.UUID(job_id).hex)
        is_job = runs.is_task_pipeline(repository.get_pipeline(run["pipeline_id"]))
    except (KeyError, ValueError):
        return None
    return run if is_job else None


@router.get("/jobs/{job_id}", operation_id="getJobStatus")
async def get_job_status(_: ReadScope, job_id: str, runs: RunsDep) -> Response:
    """Return the status of one ingestion or codebase-map job."""
    run = _job_run(runs, job_id)
    if run is None:
        return error_response(404, "Unknown job.")
    return JSONResponse(describe_job(runs, run))


@router.get("/jobs/{job_id}/events", operation_id="listJobEvents")
async def list_job_events(
    _: ReadScope,
    job_id: str,
    runs: RunsDep,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_JOB_EVENT_PAGE)] = MAX_JOB_EVENT_PAGE,
) -> Response:
    """Return committed job events after ``after_sequence`` (JSON polling)."""
    run = _job_run(runs, job_id)
    if run is None:
        return error_response(404, "Unknown job.")
    events = runs.service.repository.list_events(
        run["run_id"], after_sequence=after_sequence, limit=limit
    )
    last = events[-1]["sequence"] if events else after_sequence
    complete = run["status"] in TERMINAL_RUN_STATUSES and last >= run["last_sequence"]
    body = {
        "status": "ok",
        "job_id": _job_id(run["run_id"]),
        "job_status": describe_job(runs, run)["status"],
        "events": events,
        "last_sequence": last,
        "complete": complete,
    }
    return JSONResponse(body)
