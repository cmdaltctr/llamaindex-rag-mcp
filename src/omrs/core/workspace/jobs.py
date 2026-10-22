"""Run jobs, the executor contract and the bounded waiting queue.

A job is an immutable snapshot taken at admission: the revision document,
the run inputs, the redacted settings and resource identities, and an
opaque admission payload for the executor. Mutable values are stored as
canonical JSON text and returned as fresh copies, so later edits to a
draft graph, the inputs or a profile cannot reach an admitted job.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from omrs.core.workspace.records import RevisionRecord

if TYPE_CHECKING:
    from omrs.core.pipelines import CancellationToken, PipelineEvent, PipelineResult

DEFAULT_MAX_WAITING = 16
#: Resource key that records where a run stores its artefacts, when the
#: admission chose a directory outside the workspace artefact store.
ARTEFACT_ROOT_KEY = "artefact_root"


class WorkspaceRunError(Exception):
    """Base class for run-service errors that a transport shows to the user."""


class QueueFullError(WorkspaceRunError):
    """The waiting-job limit is reached; the submission did not start.

    Attributes:
        limit: The configured waiting-job limit.
    """

    def __init__(self, limit: int) -> None:
        """Record the limit in the message."""
        super().__init__(f"run queue is full: {limit} jobs are already waiting")
        self.limit = limit


class ServiceClosedError(WorkspaceRunError):
    """The service is not started, or it is shutting down."""


class RunStateError(WorkspaceRunError):
    """The requested action does not apply to the run's current state."""


class UnsafeInputError(WorkspaceRunError):
    """Run inputs hold a credential; inputs are stored and must be safe."""


@dataclass(frozen=True)
class Admission:
    """What admission returns for one submission.

    Attributes:
        settings: Effective settings. They are redacted before storage.
        resources: Backend, model, index and operation-version identities.
            They are redacted before storage.
        payload: Opaque, immutable object for the executor, for example an
            ``AdmissionSnapshot``. It is never stored.
        artefact_root: Directory for the run's result and overflow
            artefacts, for example below an approved experiment workspace.
            ``None`` uses the workspace artefact store. The service records
            it as resource ``artefact_root``.
    """

    settings: Mapping[str, Any]
    resources: Mapping[str, Any]
    payload: Any = None
    artefact_root: Path | None = None


Admitter = Callable[[RevisionRecord, Mapping[str, Any]], Admission]
"""Fresh admission checks for a revision and run inputs.

The admitter raises (for example ``PipelineValidationError``) to refuse a
submission before any record is written.
"""


def _copy(text: str) -> Any:
    return json.loads(text)


@dataclass(frozen=True)
class RunJob:
    """Immutable snapshot of one admitted run.

    Attributes:
        run_id: Run identifier from the repository.
        pipeline_id: Pipeline of the revision.
        revision_id: Admitted revision.
        graph_hash: Content hash of the admitted revision.
        origin: ``submit``, ``repeat`` or ``retry``.
        source_run_id: Run that a retry repeats.
        document_json: Canonical JSON of the revision document.
        inputs_json: Canonical JSON of the run inputs.
        settings_json: Canonical JSON of the redacted settings.
        resources_json: Canonical JSON of the redacted resource identities.
        payload: Opaque admission payload for the executor.
    """

    run_id: str
    pipeline_id: str
    revision_id: str
    graph_hash: str
    origin: str
    source_run_id: str | None
    document_json: str
    inputs_json: str
    settings_json: str
    resources_json: str
    payload: Any = field(default=None, compare=False)

    @property
    def document(self) -> dict[str, Any]:
        """Return a fresh copy of the revision document."""
        return _copy(self.document_json)

    @property
    def inputs(self) -> dict[str, Any]:
        """Return a fresh copy of the run inputs."""
        return _copy(self.inputs_json)

    @property
    def settings(self) -> dict[str, Any]:
        """Return a fresh copy of the redacted settings."""
        return _copy(self.settings_json)

    @property
    def resources(self) -> dict[str, Any]:
        """Return a fresh copy of the redacted resource identities."""
        return _copy(self.resources_json)


class RunExecutor(Protocol):
    """Runs one job and returns its result.

    The signature matches ``omrs.core.pipelines.run_pipeline``: ``on_event``
    is an async event sink, and ``cancellation`` is a ``RunCancellation``
    token. Composition adapts the runner and passes ``job.run_id`` as its
    run id. The service commits each event before ``on_event`` returns and
    then wakes subscribers. The executor checks ``cancellation`` before it
    schedules more work and before a protected commit. An exception means
    the run failed; the service records it and continues with the next job.
    """

    def __call__(
        self,
        job: RunJob,
        *,
        on_event: Callable[[PipelineEvent], Awaitable[None]],
        cancellation: CancellationToken,
    ) -> Awaitable[PipelineResult]:
        """Execute ``job``."""
        ...


class JobQueue:
    """First-in, first-out waiting jobs with a fixed limit.

    Args:
        limit: Maximum number of waiting jobs. The active job does not count.

    Raises:
        ValueError: If ``limit`` is less than 1.
    """

    def __init__(self, limit: int = DEFAULT_MAX_WAITING) -> None:
        """Create an empty queue."""
        if limit < 1:
            raise ValueError("the waiting-job limit must be at least 1")
        self.limit = limit
        self._jobs: deque[RunJob] = deque()
        self._ready = asyncio.Event()

    def __len__(self) -> int:
        """Return the number of waiting jobs."""
        return len(self._jobs)

    def check_capacity(self) -> None:
        """Raise :class:`QueueFullError` when no job can be added."""
        if len(self._jobs) >= self.limit:
            raise QueueFullError(self.limit)

    def put(self, job: RunJob) -> None:
        """Add a job at the end of the queue.

        Raises:
            QueueFullError: If the queue is full.
        """
        self.check_capacity()
        self._jobs.append(job)
        self._ready.set()

    def remove(self, run_id: str) -> RunJob | None:
        """Remove and return the waiting job of ``run_id``, if present."""
        for job in self._jobs:
            if job.run_id == run_id:
                self._jobs.remove(job)
                return job
        return None

    def drain(self) -> list[RunJob]:
        """Remove and return every waiting job, oldest first."""
        jobs = list(self._jobs)
        self._jobs.clear()
        return jobs

    async def get(self) -> RunJob:
        """Wait for and remove the oldest waiting job."""
        while not self._jobs:
            self._ready.clear()
            await self._ready.wait()
        return self._jobs.popleft()
