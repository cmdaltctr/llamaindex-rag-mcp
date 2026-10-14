"""Run routes: submission, inspection, cancellation, retry and events.

Submission admits the revision at once (``Engine.validate_pipeline`` with
the inputs) and queues the frozen snapshot on the workspace run service.
An invalid graph or input never reaches execution: it gets 422 with the
structured issues. A full queue gets 429.

Events are committed before subscribers wake. Clients follow them by
JSON polling (``GET .../events?after_sequence=N``) or by server-sent
events (``GET .../events/stream``). The stream replays committed events
after ``Last-Event-ID`` (or ``?after=N``), writes each event's sequence on
its ``id:`` line so clients can deduplicate, and ends when the run ends or
the server stops admitting work. A closed browser connection only stops
the stream; the run continues until an explicit cancel.

Scopes: reads and streams need ``read``; submit, cancel and retry need
``run``. Document-job runs are served by ``/v1/jobs`` only. Previewed
workspace cleanup needs the session-only ``manage`` scope.

Experiment runs (design D10): a submission may name an approved
``experiment_context``. The experiment admission guard runs before any
run record exists and a refusal gets 403 with its stable ``code``. A
bearer credential bound to a context is refused on the live library and
sees only its own context's runs; other runs read as unknown (404).
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ...core.experiments import (
    ExperimentAdmissionError,
    ExperimentPathError,
    check_credential_target,
)
from ...core.pipelines import PipelineValidationError
from ...core.workspace import (
    TERMINAL_RUN_STATUSES,
    CleanupRejected,
    CleanupSelector,
    QueueFullError,
    RunStateError,
    ServiceClosedError,
    UnsafeInputError,
)
from .engine_access import ReadScope, RuntimeDep, require_session
from .errors import API_HEADERS, error_response
from .lifespan import WebRuntime
from .routes_graphs import ok, validation_failure
from .runs_wiring import RunsDep, RunTarget, WorkspaceRuns, describe_operations
from .security import Principal, require_scope

router = APIRouter(prefix="/v1")

RunScope = Annotated[Principal, Depends(require_scope("run"))]
ManageScope = Annotated[Principal, Depends(require_session("manage"))]

#: Most events one polling request returns.
MAX_EVENT_PAGE = 500
#: Reconnection delay the stream advises, in milliseconds.
STREAM_RETRY_MS = 3000


class SubmitBody(BaseModel):
    """Body of ``POST /v1/runs``."""

    model_config = ConfigDict(extra="forbid")

    revision_id: str = Field(min_length=1, max_length=64)
    inputs: dict[str, Any] = Field(default_factory=dict)
    origin: Literal["submit", "repeat"] = "submit"
    experiment_context: str | None = Field(default=None, min_length=1, max_length=64)


def run_context(run: Any) -> str | None:
    """Return the experiment context id a run record names, if any."""
    experiment = (run.get("resources") or {}).get("experiment")
    return experiment.get("context_id") if isinstance(experiment, dict) else None


def _visible(principal: Principal, run: Any) -> bool:
    """A context-bound credential sees only its own context's runs."""
    bound = principal.experiment_context
    return bound is None or run_context(run) == bound


def _graph_run(runs: WorkspaceRuns, run_id: str, principal: Principal) -> dict[str, Any] | None:
    """Return a visible graph run, or ``None`` for an unknown, hidden or job run."""
    repository = runs.service.repository
    try:
        run = dict(repository.get_run(run_id))
    except KeyError:
        return None
    if runs.is_task_pipeline(repository.get_pipeline(run["pipeline_id"])):
        return None
    return run if _visible(principal, run) else None


def _unknown_run() -> Response:
    return error_response(404, "Unknown run.")


def experiment_refusal(exc: ExperimentAdmissionError | ExperimentPathError) -> Response:
    """Return 403 with the stable experiment refusal payload."""
    return JSONResponse(exc.to_dict(), status_code=403, headers=API_HEADERS)


def _refusal(exc: Exception, redactor: Callable[[str], str] | None = None) -> Response:
    """Map a run-service or admission refusal to its HTTP response.

    *redactor* is ``Engine.redact``; it removes provider credential values.
    """
    if isinstance(exc, ExperimentAdmissionError | ExperimentPathError):
        return experiment_refusal(exc)
    if isinstance(exc, PipelineValidationError):
        return validation_failure(exc, redactor)
    if isinstance(exc, QueueFullError):
        return error_response(429, f"The run queue is full: {exc.limit} runs are waiting.")
    if isinstance(exc, ServiceClosedError):
        return error_response(503, "The server is shutting down.")
    if isinstance(exc, RunStateError):
        return error_response(409, str(exc))
    if isinstance(exc, UnsafeInputError):
        return error_response(400, "Run inputs must not hold credentials.")
    return error_response(400, f"Invalid run inputs: {exc}", error_type="validation")


_REFUSALS = (
    ExperimentAdmissionError,
    PipelineValidationError,
    QueueFullError,
    ServiceClosedError,
    RunStateError,
    UnsafeInputError,
    ValueError,
)


async def _warm_catalogue(runtime: WebRuntime, target: RunTarget) -> None:
    """Build the catalogue (and a context Engine) off the event loop before admission.

    The credential check runs first, so a refused caller never causes a
    context Engine build.

    Raises:
        ExperimentAdmissionError: The caller may not reach the target.
        ExperimentPathError: The context workspace moved.
    """
    context_id = target.experiment_context
    if context_id is None or runtime.experiments is None:
        await run_in_threadpool(describe_operations, runtime.engine)
        return
    check_credential_target(
        bound_context=target.bound_context, target_context=context_id, session=target.session
    )
    engine = await run_in_threadpool(runtime.experiments.engine, context_id)
    await run_in_threadpool(describe_operations, engine)


async def _admit(runtime: WebRuntime, runs: WorkspaceRuns, target: RunTarget, admit: Any) -> Any:
    """Warm the target Engine, then run *admit* for *target*; map refusals."""
    try:
        await _warm_catalogue(runtime, target)
        with runs.targeting(target):
            run = admit()
    except _REFUSALS as exc:
        return _refusal(exc, runtime.engine.redact)
    return ok({"run": run}, 202)


# ── Submission and control ───────────────────────────────────────────────


@router.post("/runs", status_code=202, operation_id="submitRun")
async def submit_run(
    principal: RunScope, body: SubmitBody, runtime: RuntimeDep, runs: RunsDep
) -> Response:
    """Admit a saved revision with its inputs and queue the run.

    With ``experiment_context`` the run uses that approved context's Engine.
    """
    repository = runs.service.repository
    try:
        revision = repository.get_revision(body.revision_id)
        hidden = runs.is_task_pipeline(repository.get_pipeline(revision["pipeline_id"]))
    except KeyError:
        hidden = True
    if hidden:
        return error_response(404, "Unknown revision.")
    target = RunTarget.for_principal(principal, body.experiment_context)
    return await _admit(
        runtime,
        runs,
        target,
        lambda: runs.service.submit(body.revision_id, inputs=body.inputs, origin=body.origin),
    )


@router.post("/runs/{run_id}/cancel", operation_id="cancelRun")
async def cancel_run(principal: RunScope, run_id: str, runs: RunsDep) -> Response:
    """Cancel a queued run, or ask the active run to stop at a safe boundary."""
    if _graph_run(runs, run_id, principal) is None:
        return _unknown_run()
    try:
        return ok({"run": runs.service.cancel(run_id)})
    except RunStateError as exc:
        return _refusal(exc)


@router.post("/runs/{run_id}/retry", status_code=202, operation_id="retryRun")
async def retry_run(
    principal: RunScope, run_id: str, runtime: RuntimeDep, runs: RunsDep
) -> Response:
    """Repeat a failed, cancelled or interrupted run as a new run.

    The new run uses the stored revision, inputs and experiment context
    with fresh admission; the source run does not change.
    """
    source = _graph_run(runs, run_id, principal)
    if source is None:
        return _unknown_run()
    target = RunTarget.for_principal(principal, run_context(source))
    return await _admit(runtime, runs, target, lambda: runs.service.retry(run_id))


# ── Inspection ───────────────────────────────────────────────────────────


@router.get("/runs", operation_id="listRuns")
async def list_runs(
    principal: ReadScope,
    runs: RunsDep,
    pipeline_id: str | None = None,
    status: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Response:
    """List graph runs, newest first, optionally by pipeline and status."""
    repository = runs.service.repository
    hidden = {p["pipeline_id"] for p in repository.list_pipelines() if runs.is_task_pipeline(p)}
    try:
        records = repository.list_runs(pipeline_id=pipeline_id, statuses=status or None)
    except ValueError as exc:
        return error_response(400, str(exc), error_type="validation")
    visible = [
        run for run in records if run["pipeline_id"] not in hidden and _visible(principal, run)
    ]
    return ok({"runs": visible[:limit]})


@router.get("/runs/{run_id}", operation_id="getRun")
async def get_run(principal: ReadScope, run_id: str, runs: RunsDep) -> Response:
    """Return one run record: revision, redacted settings, state and failure."""
    run = _graph_run(runs, run_id, principal)
    return _unknown_run() if run is None else ok({"run": run})


@router.get("/runs/{run_id}/result", operation_id="getRunResult")
async def get_run_result(principal: ReadScope, run_id: str, runs: RunsDep) -> Response:
    """Return the stored, redacted result of a finished run."""
    run = _graph_run(runs, run_id, principal)
    if run is None:
        return _unknown_run()
    result = runs.result(run)
    if result is None:
        return error_response(404, "This run has no stored result.")
    return ok({"run_id": run_id, "result": result})


@router.get("/runs/{run_id}/events", operation_id="listRunEvents")
async def list_run_events(
    principal: ReadScope,
    run_id: str,
    runs: RunsDep,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_EVENT_PAGE)] = MAX_EVENT_PAGE,
) -> Response:
    """Return committed events after ``after_sequence`` (polling fallback)."""
    run = _graph_run(runs, run_id, principal)
    if run is None:
        return _unknown_run()
    events = runs.service.repository.list_events(run_id, after_sequence=after_sequence, limit=limit)
    last = events[-1]["sequence"] if events else after_sequence
    return ok(
        {
            "run_id": run_id,
            "run_status": run["status"],
            "events": events,
            "last_sequence": last,
            "complete": run["status"] in TERMINAL_RUN_STATUSES and last >= run["last_sequence"],
        }
    )


# ── Server-sent events ───────────────────────────────────────────────────


def _frame(event: str, data: Any, event_id: int | None = None) -> str:
    lines = [] if event_id is None else [f"id: {event_id}"]
    lines += [f"event: {event}", "data: " + json.dumps(data, separators=(",", ":"))]
    return "\n".join(lines) + "\n\n"


def _start_sequence(last_event_id: str | None, after: int | None) -> int | Response:
    """Return the sequence to replay after; ``Last-Event-ID`` wins."""
    if last_event_id is not None and last_event_id.strip():
        try:
            value = int(last_event_id.strip())
        except ValueError:
            return error_response(400, "Last-Event-ID must be a run event sequence number.")
        if value < 0:
            return error_response(400, "Last-Event-ID must not be negative.")
        return value
    return after or 0


async def _event_stream(
    runtime: WebRuntime, runs: WorkspaceRuns, run_id: str, after: int
) -> AsyncIterator[str]:
    """Yield SSE frames until the run ends, admission closes or the client leaves.

    Leaving (generator cancellation or close) only detaches the
    subscription; the run is never cancelled here.
    """
    events = runs.service.subscribe(run_id, after_sequence=after)
    closed = asyncio.ensure_future(runtime.admission.wait_closed())
    following: asyncio.Future[Any] | None = None
    try:
        yield f"retry: {STREAM_RETRY_MS}\n\n"
        while True:
            following = asyncio.ensure_future(anext(events))
            done, _ = await asyncio.wait({following, closed}, return_when=asyncio.FIRST_COMPLETED)
            if following not in done:
                following.cancel()
                with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                    await following
                yield _frame("server.closing", {"reason": "The server is shutting down."})
                return
            try:
                event = following.result()
            except StopAsyncIteration:
                break
            finally:
                following = None
            yield _frame(event["kind"], event, event["sequence"])
        run = runs.service.repository.get_run(run_id)
        yield _frame("run.end", {"status": run["status"], "last_sequence": run["last_sequence"]})
    finally:
        closed.cancel()
        if following is not None and not following.done():
            # The client left during a wait. Cancelling the pending read
            # closes the subscription; the run itself is not touched.
            following.cancel()
        else:
            await events.aclose()


@router.get("/runs/{run_id}/events/stream", operation_id="streamRunEvents")
async def stream_run_events(
    principal: ReadScope,
    run_id: str,
    runtime: RuntimeDep,
    runs: RunsDep,
    after: Annotated[int | None, Query(ge=0)] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> Response:
    """Stream run events as ``text/event-stream`` with replay after a sequence."""
    if _graph_run(runs, run_id, principal) is None:
        return _unknown_run()
    start = _start_sequence(last_event_id, after)
    if isinstance(start, Response):
        return start
    headers = {**API_HEADERS, "Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        _event_stream(runtime, runs, run_id, start),
        media_type="text/event-stream",
        headers=headers,
    )


# ── Workspace cleanup ────────────────────────────────────────────────────


class CleanupSelectorBody(BaseModel):
    """Which finished runs a cleanup selects; every given criterion must hold."""

    model_config = ConfigDict(extra="forbid")

    older_than_days: float | None = Field(default=None, ge=0)
    statuses: list[str] = Field(default_factory=list, max_length=8)
    run_id: str | None = Field(default=None, min_length=1, max_length=64)


class CleanupPreviewBody(BaseModel):
    """Body of ``POST /v1/workspace/cleanup/preview``."""

    model_config = ConfigDict(extra="forbid")

    selector: CleanupSelectorBody


class CleanupApplyBody(BaseModel):
    """Body of ``POST /v1/workspace/cleanup``."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=128)
    selector: CleanupSelectorBody | None = None


def _selector(body: CleanupSelectorBody) -> CleanupSelector:
    """Build the core selector. Raises ``ValueError`` for an invalid one."""
    return CleanupSelector(
        older_than_days=body.older_than_days, statuses=tuple(body.statuses), run_id=body.run_id
    )


@router.post("/workspace/cleanup/preview", operation_id="previewWorkspaceCleanup")
async def preview_workspace_cleanup(
    _: ManageScope, body: CleanupPreviewBody, runs: RunsDep
) -> Response:
    """List the finished runs, events and artefacts a cleanup would remove.

    Returns a single-use confirmation token bound to this exact state.
    Vectors, sources, uploads, notebooks and experiment outputs are never
    in scope.
    """
    try:
        selector = _selector(body.selector)
    except ValueError as exc:
        return error_response(422, f"Invalid cleanup selector: {exc}", error_type="validation")
    try:
        preview = await run_in_threadpool(runs.cleanup.preview_cleanup, selector)
    except KeyError:
        return error_response(404, "Unknown run.")
    return ok({"preview": preview.as_dict()})


@router.post("/workspace/cleanup", operation_id="applyWorkspaceCleanup")
async def apply_workspace_cleanup(
    _: ManageScope, body: CleanupApplyBody, runs: RunsDep
) -> Response:
    """Remove exactly what the token's preview listed, if nothing changed since."""
    try:
        selector = None if body.selector is None else _selector(body.selector)
    except ValueError as exc:
        return error_response(422, f"Invalid cleanup selector: {exc}", error_type="validation")
    try:
        result = await run_in_threadpool(runs.cleanup.apply_cleanup, body.token, selector=selector)
    except CleanupRejected as exc:
        return error_response(
            409, f"The cleanup preview is no longer valid ({exc.reason}). Preview again."
        )
    return ok({"result": dataclasses.asdict(result)})
