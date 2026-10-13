"""The local run service: one supervised consumer and a bounded queue.

Lifecycle:

1. ``start()`` marks every ``queued``, ``running`` or ``cancelling`` run
   left by an earlier process as ``interrupted``. It never runs them again.
2. ``submit()`` runs fresh admission, stores a redacted run record and
   queues an immutable job. A full queue rejects the submission before any
   admission or record.
3. The consumer runs one job at a time through the injected executor. Each
   status change and its event commit in one transaction before
   subscribers are woken. A failed job does not stop the consumer.
4. ``cancel()`` ends a queued run at once. For the active run it records
   ``cancelling`` and sets the cooperative cancellation flag.
5. ``shutdown()`` stops admission, cancels queued runs, asks the active run
   to stop, and waits with a time limit. A run that does not stop in time
   is recorded as ``interrupted``.
6. ``retry()`` is the only way to repeat a run. It creates a new run.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import time
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from omrg.core.pipelines import RunCancellation
from omrg.core.workspace.artefacts import ArtefactStore, to_jsonable
from omrg.core.workspace.events import STATUS_EVENT, RunEventLog
from omrg.core.workspace.jobs import (
    ARTEFACT_ROOT_KEY,
    DEFAULT_MAX_WAITING,
    Admitter,
    JobQueue,
    RunExecutor,
    RunJob,
    RunStateError,
    ServiceClosedError,
    UnsafeInputError,
)
from omrg.core.workspace.outcomes import RunRecorder, plain, run_artefacts
from omrg.core.workspace.records import (
    NONTERMINAL_RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    RunEventRecord,
    RunRecord,
    canonical_json,
)
from omrg.core.workspace.redaction import contains_secret
from omrg.core.workspace.repository import WorkspaceRepository

logger = logging.getLogger(__name__)

RETRYABLE_STATUSES: frozenset[str] = frozenset({"failed", "cancelled", "interrupted"})


@dataclass(frozen=True)
class ShutdownReport:
    """What a shutdown did.

    Attributes:
        cancelled_queued: Waiting runs that were cancelled before start.
        active_run_id: Run that was active when shutdown began, if any.
        interrupted: Runs recorded as interrupted because they did not stop
            within the time limit.
    """

    cancelled_queued: tuple[str, ...] = ()
    active_run_id: str | None = None
    interrupted: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Active:
    job: RunJob
    flag: RunCancellation


class RunService:
    """Admit, queue, execute and supervise local pipeline runs.

    Args:
        repository: Workspace records.
        executor: Runs one job (see :class:`RunExecutor`).
        admit: Fresh admission for a revision and inputs.
        artefacts: Private artefact store for results and large previews.
        max_waiting: Waiting-job limit. The active job does not count.
        shutdown_timeout: Default seconds that shutdown waits for the
            active run.
        monotonic: Clock for end-to-end wall time; injected in tests.

    Raises:
        ValueError: If ``max_waiting`` is less than 1.
    """

    def __init__(
        self,
        repository: WorkspaceRepository,
        executor: RunExecutor,
        *,
        admit: Admitter,
        artefacts: ArtefactStore,
        max_waiting: int = DEFAULT_MAX_WAITING,
        shutdown_timeout: float = 30.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a stopped service; call :meth:`start` before submissions."""
        self._repository = repository
        self._executor = executor
        self._admit = admit
        self._artefacts = artefacts
        self._queue = JobQueue(max_waiting)
        self._log = RunEventLog(repository)
        self._recorder = RunRecorder(repository, self._log, artefacts)
        self._shutdown_timeout = shutdown_timeout
        self._monotonic = monotonic
        self._state = "new"
        self._active: _Active | None = None
        self._consumer: asyncio.Task[None] | None = None
        self._idle = asyncio.Event()
        self._idle.set()
        self._report: ShutdownReport | None = None

    # --- properties --------------------------------------------------------

    @property
    def repository(self) -> WorkspaceRepository:
        """Return the workspace repository."""
        return self._repository

    @property
    def artefacts(self) -> ArtefactStore:
        """Return the private artefact store."""
        return self._artefacts

    def artefacts_for(self, run: RunRecord) -> ArtefactStore:
        """Return the store that holds the artefacts of *run*.

        A run admitted with an artefact root (for example an experiment
        run) keeps its artefacts below that root. Other runs use the
        workspace store.
        """
        return run_artefacts(run, self._artefacts)

    @property
    def max_waiting(self) -> int:
        """Return the waiting-job limit."""
        return self._queue.limit

    @property
    def waiting_count(self) -> int:
        """Return the number of waiting jobs."""
        return len(self._queue)

    @property
    def active_run_id(self) -> str | None:
        """Return the run that is executing now, if any."""
        return self._active.job.run_id if self._active else None

    # --- lifecycle ---------------------------------------------------------

    async def start(self) -> list[str]:
        """Report unfinished runs as interrupted, then start the consumer.

        Returns:
            Identifiers of the runs marked interrupted, oldest first.

        Raises:
            RunStateError: If the service already started.
            ServiceClosedError: If the service was shut down.
        """
        if self._state == "closed":
            raise ServiceClosedError("the run service was shut down")
        if self._state != "new":
            raise RunStateError("the run service already started")
        stale = self._repository.list_runs(statuses=NONTERMINAL_RUN_STATUSES)
        interrupted = [self._recorder.interrupt_stale(run) for run in reversed(stale)]
        self._consumer = asyncio.create_task(self._consume(), name="omrg-run-consumer")
        self._state = "running"
        return interrupted

    async def wait_idle(self) -> None:
        """Wait until no job is waiting or active."""
        await self._idle.wait()

    async def shutdown(self, timeout: float | None = None) -> ShutdownReport:
        """Stop admission, cancel waiting runs and stop the active run.

        Args:
            timeout: Seconds to wait for the active run. Defaults to the
                service ``shutdown_timeout``.

        Returns:
            What the shutdown did. A second call returns the same report.
        """
        if self._report is not None:
            return self._report
        self._state = "closing"
        cancelled = tuple(
            job.run_id
            for job in self._queue.drain()
            if self._recorder.end(job.run_id, "cancelled", {"reason": "workspace shutdown"})
        )
        active = self._active
        if active is None:
            self._idle.set()
        else:
            self._request_cancel(active, "workspace shutdown")
        limit = self._shutdown_timeout if timeout is None else timeout
        timed_out = False
        try:
            await asyncio.wait_for(self._idle.wait(), limit)
        except TimeoutError:
            timed_out = True
        if self._consumer is not None:
            self._consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer
        interrupted: tuple[str, ...] = ()
        if timed_out and active is not None:
            error = "the run did not stop before the shutdown time limit"
            if self._recorder.end(
                active.job.run_id, "interrupted", {"reason": "interrupted", "error": error}
            ):
                interrupted = (active.job.run_id,)
        self._active = None
        self._idle.set()
        self._state = "closed"
        self._report = ShutdownReport(
            cancelled_queued=cancelled,
            active_run_id=active.job.run_id if active else None,
            interrupted=interrupted,
        )
        return self._report

    # --- admission ---------------------------------------------------------

    def submit(
        self, revision_id: str, *, inputs: Mapping[str, Any], origin: str = "submit"
    ) -> RunRecord:
        """Admit and queue a run of a saved revision.

        Args:
            revision_id: Revision to run.
            inputs: JSON-compatible run inputs or input references.
            origin: ``submit``, or ``repeat`` for an explicit repeat of a
                saved revision.

        Returns:
            The queued run record.

        Raises:
            ServiceClosedError: If the service is not accepting runs.
            QueueFullError: If the waiting-job limit is reached.
            UnsafeInputError: If the inputs hold a credential.
            ValueError: If ``origin`` is invalid or the inputs are not JSON.
            KeyError: If the revision does not exist.
        """
        if origin not in {"submit", "repeat"}:
            raise ValueError(f"origin must be 'submit' or 'repeat', not {origin!r}")
        return self._enqueue(revision_id, inputs, origin=origin, source_run_id=None)

    def retry(self, run_id: str) -> RunRecord:
        """Explicitly repeat a failed, cancelled or interrupted run.

        The new run uses the stored revision and inputs, runs fresh admission
        checks, and records the source run. The source run is not changed.

        Raises:
            RunStateError: If the source run cannot be retried.
            KeyError: If the run does not exist.
        """
        source = self._repository.get_run(run_id)
        if source["status"] not in RETRYABLE_STATUSES:
            raise RunStateError(f"run {run_id} is {source['status']} and cannot be retried")
        return self._enqueue(
            source["revision_id"], source["inputs"], origin="retry", source_run_id=run_id
        )

    def _enqueue(
        self,
        revision_id: str,
        inputs: Mapping[str, Any],
        *,
        origin: str,
        source_run_id: str | None,
    ) -> RunRecord:
        if self._state != "running":
            raise ServiceClosedError("the run service is not accepting runs")
        self._queue.check_capacity()
        inputs_json = canonical_json(dict(inputs))
        if contains_secret(inputs):
            raise UnsafeInputError("run inputs hold a credential; use host configuration")
        revision = self._repository.get_revision(revision_id)
        admission = self._admit(revision, to_jsonable(dict(inputs)))
        settings, resources = plain(admission.settings), plain(admission.resources)
        if admission.artefact_root is not None:
            resources[ARTEFACT_ROOT_KEY] = str(admission.artefact_root)
        run = self._repository.create_run(
            revision_id,
            settings=settings,
            resources=resources,
            inputs=dict(inputs),
            origin=origin,
            source_run_id=source_run_id,
        )
        job = RunJob(
            run_id=run["run_id"],
            pipeline_id=run["pipeline_id"],
            revision_id=revision_id,
            graph_hash=run["graph_hash"],
            origin=origin,
            source_run_id=source_run_id,
            document_json=canonical_json(revision["document"]),
            inputs_json=inputs_json,
            settings_json=canonical_json(settings),
            resources_json=canonical_json(resources),
            payload=admission.payload,
        )
        self._queue.put(job)
        self._idle.clear()
        self._log.notify(job.run_id)
        return run

    # --- cancellation ------------------------------------------------------

    def cancel(self, run_id: str) -> RunRecord:
        """Cancel a run; a terminal or cancelling run is returned unchanged.

        Raises:
            KeyError: If the run does not exist.
            RunStateError: If this service does not own the unfinished run.
        """
        run = self._repository.get_run(run_id)
        if run["status"] in TERMINAL_RUN_STATUSES or run["status"] == "cancelling":
            return run
        active = self._active
        if run["status"] == "queued" and self._queue.remove(run_id) is not None:
            self._recorder.end(run_id, "cancelled", {"reason": "cancelled before start"})
            if active is None and not len(self._queue):
                self._idle.set()
        elif active is not None and active.job.run_id == run_id:
            self._request_cancel(active, "cancel requested")
        else:
            raise RunStateError(f"run {run_id} is not owned by this run service")
        return self._repository.get_run(run_id)

    def _request_cancel(self, active: _Active, reason: str) -> None:
        active.flag.cancel(reason)
        if self._repository.get_run(active.job.run_id)["status"] == "running":
            summary = {"status": "cancelling", "reason": reason}
            self._log.record(
                active.job.run_id, kind=STATUS_EVENT, summary=summary, status="cancelling"
            )

    # --- monitoring --------------------------------------------------------

    def replay(self, run_id: str, *, after_sequence: int = 0) -> list[RunEventRecord]:
        """Return committed events after ``after_sequence``, in order."""
        return self._log.replay(run_id, after_sequence=after_sequence)

    def subscribe(self, run_id: str, *, after_sequence: int = 0) -> AsyncIterator[RunEventRecord]:
        """Stream committed events after ``after_sequence`` until the run ends.

        Closing the stream detaches monitoring only; the run continues.
        """
        return self._log.subscribe(run_id, after_sequence=after_sequence)

    # --- consumer ----------------------------------------------------------

    async def _consume(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._execute(job)
            except Exception:
                logger.exception("run %s: the run service could not finish the run", job.run_id)
                self._recorder.fail_safely(job.run_id)
            finally:
                self._active = None
                if not len(self._queue):
                    self._idle.set()

    async def _execute(self, job: RunJob) -> None:
        flag = RunCancellation()
        self._active = _Active(job, flag)
        self._log.record(
            job.run_id, kind=STATUS_EVENT, summary={"status": "running"}, status="running"
        )
        started = self._monotonic()
        try:
            result = await self._executor(
                job, on_event=functools.partial(self._recorder.event, job.run_id), cancellation=flag
            )
        except Exception as exc:
            wall = self._monotonic() - started
            self._recorder.fail(job.run_id, f"{type(exc).__name__}: {exc}", wall=wall)
            return
        self._recorder.finish(job, result, self._monotonic() - started)
