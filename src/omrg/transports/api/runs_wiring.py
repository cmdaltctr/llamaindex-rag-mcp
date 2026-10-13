"""Compose the workspace run service for the web application (design D6, D7).

:func:`run_service_factory` builds one :class:`WorkspaceRuns` per launch:
the SQLite workspace repository, private artefacts, the admission step
and the executor around the Engine that the lifespan owns. One consumer
and one bounded queue serve graph runs and the document jobs
(ingestion and codebase maps).

* Graph runs are admitted at submission with ``Engine.validate_pipeline``
  (with inputs). The executor runs that frozen ``AdmissionSnapshot``; it
  never admits the revision again.
* Document jobs are runs of a reserved per-kind workspace pipeline. Only
  :meth:`WorkspaceRuns.submit_task` can admit one, so a graph submission
  or a retry of a job revision fails graph validation instead.
* Experiment runs (design D10) name an approved experiment context. The
  submit route states the caller and the target with
  :meth:`WorkspaceRuns.targeting`. Admission runs the experiment
  admission guard (credential binding, context state, graph checks)
  before the run record exists; a live-library request from an
  experiment-bound credential is refused the same way. The run records
  ``ExperimentAdmission.provenance()`` under ``resources["experiment"]``.
  The context lease is held only while the run executes: the run service
  can drop a queued job (cancel or shutdown) without calling back, so a
  lease taken at submission could never be returned. The executor takes
  a fresh lease, which fails cleanly when the context was revoked while
  the run waited.

"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from typing import Annotated, Any

from fastapi import Depends, HTTPException

from ...core.experiments import ExperimentAdmissionError, check_credential_target
from ...core.pipelines import PipelineResult, RunStatus
from ...core.workspace import (
    Admission,
    ArtefactStore,
    RunJob,
    RunRecord,
    RunService,
    WorkspaceCleanup,
    WorkspaceLayout,
)
from ...integrations.workspace_sqlite import SqliteWorkspaceRepository
from .lifespan import WebRuntime, get_runtime

#: Layout key that marks a reserved document-job pipeline.
TASK_LAYOUT_KEY = "omrg_task"

TaskWorkFn = Callable[[], Awaitable[Any]]


# ── Admission and execution ──────────────────────────────────────────────


@dataclass(frozen=True)
class TaskWork:
    """A document job admitted by :meth:`WorkspaceRuns.submit_task`."""

    kind: str
    work: TaskWorkFn


@dataclass(frozen=True)
class RunTarget:
    """Who submits a graph run and which library it targets.

    Attributes:
        experiment_context: Target experiment context, or ``None`` for the
            live library.
        bound_context: Context bound to the caller's bearer credential.
        session: Whether the caller is the browser session.
    """

    experiment_context: str | None = None
    bound_context: str | None = None
    session: bool = True

    @classmethod
    def for_principal(cls, principal: Any, experiment_context: str | None) -> RunTarget:
        """Return the target of a request by *principal*."""
        return cls(experiment_context, principal.experiment_context, principal.kind == "session")


@dataclass(frozen=True)
class ExperimentJob:
    """An admitted experiment graph; the executor runs its frozen snapshot."""

    admission: Any


def public_outputs(result: PipelineResult) -> PipelineResult:
    """Replace context bundles in the outputs with their public search rows.

    A ``ContextBundle`` output is stored as the rows ``Engine.search``
    returns (``public_rows()``), not as an opaque text form.
    """
    outputs = dict(result.outputs)
    changed = False
    for name, value in outputs.items():
        public_rows = getattr(value, "public_rows", None)
        if callable(public_rows):
            outputs[name] = public_rows()
            changed = True
    return result.model_copy(update={"outputs": outputs}) if changed else result


def snapshot_provenance(snapshot: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the settings and resource identities to record for a snapshot.

    The run service redacts both before storage.
    """
    settings = {
        item.name: {
            "profile": item.profile_name,
            "profile_origin": item.profile_origin,
            "settings": item.settings.model_dump(mode="json"),
        }
        for item in snapshot.collections
    }
    resources = {
        "graph_identity": snapshot.graph_identity,
        "schema_version": snapshot.schema_version,
        "operations": {node.node_id: f"{node.operation}@{node.version}" for node in snapshot.nodes},
    }
    return settings, resources


class RunAdmitter:
    """Admission for the run service: a graph snapshot, or a pending job."""

    def __init__(self, engine: Any, experiments: Any | None = None) -> None:
        """Admit against *engine*, or against an experiment context Engine.

        Args:
            engine: The live Engine.
            experiments: The launch's ``ExperimentEngines``, if any.
        """
        self._engine = engine
        self._experiments = experiments
        self._pending: TaskWork | None = None
        self._target: RunTarget | None = None

    def __call__(self, revision: Mapping[str, Any], inputs: Mapping[str, Any]) -> Admission:
        """Return the admission for one submission or retry.

        Raises:
            PipelineValidationError: The graph or its inputs are invalid.
            ExperimentAdmissionError: The caller may not reach the target.
        """
        task, self._pending = self._pending, None
        if task is not None:
            return Admission(settings={}, resources={"task": task.kind}, payload=task)
        target = self._target or RunTarget()
        if target.experiment_context is not None:
            return self._admit_experiment(target, revision, inputs)
        check_credential_target(
            bound_context=target.bound_context, target_context=None, session=target.session
        )
        snapshot = self._engine.validate_pipeline(revision["document"], inputs=dict(inputs))
        settings, resources = snapshot_provenance(snapshot)
        return Admission(settings=settings, resources=resources, payload=snapshot)

    def _admit_experiment(
        self, target: RunTarget, revision: Mapping[str, Any], inputs: Mapping[str, Any]
    ) -> Admission:
        context_id = target.experiment_context
        if self._experiments is None:
            check_credential_target(
                bound_context=target.bound_context,
                target_context=context_id,
                session=target.session,
            )
            raise ExperimentAdmissionError(
                "experiment_context_unknown", "No experiment context has this id.", context_id
            )
        admission = self._experiments.admit(
            context_id,
            revision["document"],
            inputs=dict(inputs),
            bound_context=target.bound_context,
            session=target.session,
        )
        # The executor takes its own lease (see the module docstring).
        admission.release()
        settings, resources = snapshot_provenance(admission.snapshot)
        resources["experiment"] = admission.provenance()
        return Admission(settings=settings, resources=resources, payload=ExperimentJob(admission))

    @contextlib.contextmanager
    def targeting(self, target: RunTarget) -> Iterator[None]:
        """Admit the one synchronous submission or retry in this block for *target*."""
        self._target = target
        try:
            yield
        finally:
            self._target = None

    @contextlib.contextmanager
    def task(self, work: TaskWork) -> Iterator[None]:
        """Admit *work* for the one synchronous submission in this block."""
        self._pending = work
        try:
            yield
        finally:
            self._pending = None


async def _run_task(job: RunJob, task: TaskWork) -> PipelineResult:
    """Run a document job; finish the Engine call even if shutdown cancels us."""
    inner = asyncio.ensure_future(task.work())
    try:
        value = await asyncio.shield(inner)
    except asyncio.CancelledError:
        # Shutdown cancelled the consumer. The Engine closes after this
        # returns, so let the ingestion or map call reach its end first.
        await asyncio.wait({inner})
        raise
    return PipelineResult(
        run_id=job.run_id,
        status=RunStatus.SUCCEEDED,
        graph_identity=job.graph_hash,
        outputs={"result": value},
    )


async def _run_experiment(
    experiments: Any, job: RunJob, payload: ExperimentJob, on_event: Any, cancellation: Any
) -> PipelineResult:
    """Run an admitted experiment snapshot under a fresh context lease.

    Raises:
        ExperimentAdmissionError: The context was revoked while the run
            waited; the context Engine does not run.
    """
    admission = payload.admission
    lease = experiments.registry.acquire(admission.context.context_id)
    outcome = await experiments.execute(
        replace(admission, lease=lease), on_event=on_event, cancellation=cancellation
    )
    return outcome.result.model_copy(update={"run_id": job.run_id})


def build_executor(
    engine: Any, experiments: Any | None = None
) -> Callable[..., Awaitable[PipelineResult]]:
    """Return the run-service executor around *engine* and the experiment engines."""

    async def execute(job: RunJob, *, on_event: Any, cancellation: Any) -> PipelineResult:
        if isinstance(job.payload, TaskWork):
            return await _run_task(job, job.payload)
        if isinstance(job.payload, ExperimentJob):
            result = await _run_experiment(experiments, job, job.payload, on_event, cancellation)
        else:
            result = await engine.run_pipeline(
                job.payload, on_event=on_event, cancellation=cancellation, run_id=job.run_id
            )
        return public_outputs(result)

    return execute


# ── Service façade ───────────────────────────────────────────────────────


class WorkspaceRuns:
    """The run service of one launch, with document-job support.

    It satisfies the lifespan ``RunServiceHook`` (``start``/``shutdown``).
    """

    def __init__(
        self, service: RunService, admitter: RunAdmitter, cleanup: WorkspaceCleanup
    ) -> None:
        """Wrap *service*; *admitter* must be the service's admission step.

        Args:
            service: The run service.
            admitter: The admission step the service calls.
            cleanup: Previewed cleanup of finished runs in the same workspace.
        """
        self.service = service
        self.cleanup = cleanup
        self._admitter = admitter
        self._task_revisions: dict[str, str] = {}

    async def start(self) -> list[str]:
        """Start the consumer; report runs left unfinished as interrupted."""
        return await self.service.start()

    async def shutdown(self) -> Any:
        """Stop admission, cancel waiting runs, drain the active run."""
        return await self.service.shutdown()

    @staticmethod
    def is_task_pipeline(pipeline: Mapping[str, Any]) -> bool:
        """Return whether *pipeline* is a reserved document-job pipeline."""
        return TASK_LAYOUT_KEY in (pipeline.get("layout") or {})

    def _task_revision(self, kind: str) -> str:
        if kind not in self._task_revisions:
            repository = self.service.repository
            pipeline = next(
                (
                    p
                    for p in repository.list_pipelines()
                    if (p.get("layout") or {}).get(TASK_LAYOUT_KEY) == kind
                ),
                None,
            )
            if pipeline is None:
                pipeline = repository.create_pipeline(
                    f"Workspace job: {kind}", layout={TASK_LAYOUT_KEY: kind}
                )
            revision = repository.save_revision(
                pipeline["pipeline_id"], {"task": kind}, schema_version=1
            )
            self._task_revisions[kind] = revision["revision_id"]
        return self._task_revisions[kind]

    def submit_task(self, kind: str, inputs: Mapping[str, Any], work: TaskWorkFn) -> RunRecord:
        """Queue a document job on the shared consumer.

        Args:
            kind: Job kind, for example ``ingest``.
            inputs: JSON inputs recorded with the run (no credentials).
            work: Coroutine function that does the job and returns its result.

        Raises:
            QueueFullError: The waiting-job limit is reached.
            ServiceClosedError: The service is not accepting runs.
        """
        revision_id = self._task_revision(kind)
        with self._admitter.task(TaskWork(kind, work)):
            return self.service.submit(revision_id, inputs=inputs)

    def targeting(self, target: RunTarget) -> contextlib.AbstractContextManager[None]:
        """Admit the submission or retry in this block for *target*.

        Raises (inside the block):
            ExperimentAdmissionError: Before any run record is written.
        """
        return self._admitter.targeting(target)

    def result(self, run: Mapping[str, Any]) -> Any:
        """Return the stored, redacted result of a finished run, or ``None``."""
        ref = run.get("result_ref")
        if not ref:
            return None
        try:
            return self.service.artefacts.read_json(ref)
        except (OSError, ValueError):
            return None


def build_workspace_runs(runtime: WebRuntime) -> WorkspaceRuns:
    """Build the run service of *runtime* (the ``run_service_factory``).

    Args:
        runtime: The started runtime; its Engine is borrowed, never closed here.

    Returns:
        The service façade; the lifespan starts and shuts it down.
    """
    layout = WorkspaceLayout(runtime.config.workspace)
    repository = SqliteWorkspaceRepository(layout.records)
    admitter = RunAdmitter(runtime.engine, runtime.experiments)
    service = RunService(
        repository=repository,
        executor=build_executor(runtime.engine, runtime.experiments),
        admit=admitter,
        artefacts=ArtefactStore(layout.artefacts),
    )
    return WorkspaceRuns(service, admitter, WorkspaceCleanup.for_layout(repository, layout))


#: The factory ``omrg web`` passes to ``create_app``.
run_service_factory = build_workspace_runs


def get_runs(runtime: Annotated[WebRuntime, Depends(get_runtime)]) -> WorkspaceRuns:
    """Route dependency returning the launch's :class:`WorkspaceRuns`.

    Raises:
        HTTPException: 503 when the server runs without a run service.
    """
    runs = runtime.run_service
    if not isinstance(runs, WorkspaceRuns):
        raise HTTPException(503, "The run service is not available in this server.")
    return runs


RunsDep = Annotated[WorkspaceRuns, Depends(get_runs)]


def describe_operations(engine: Any) -> list[dict[str, Any]]:
    """Return the Engine's operation catalogue with availability reasons."""
    return engine.describe_operations()
