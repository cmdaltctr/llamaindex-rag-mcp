"""Shared fakes for the workspace run-service tests (tasks 5.2 to 5.4).

The fake executor is controlled with run inputs and asyncio events, so each
test decides when a job starts, blocks, fails or finishes. The last test
keeps the fake itself honest.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import aclosing
from pathlib import Path
from typing import Any

from omrs.core.pipelines import (
    CancellationToken,
    EventKind,
    NodeOutcome,
    NodeStatus,
    PipelineEvent,
    PipelineResult,
    RunStatus,
)
from omrs.core.workspace import (
    Admission,
    ArtefactStore,
    RevisionRecord,
    RunEventRecord,
    RunJob,
    RunService,
)
from omrs.integrations.workspace_sqlite import SqliteWorkspaceRepository

GRAPH = {"version": 1, "nodes": [{"id": "a", "op": "read"}], "edges": []}
GRAPH_CHANGED = {"version": 1, "nodes": [{"id": "a", "op": "chunk"}], "edges": []}
SECRET = "sk-test0123456789abcdefSECRET"  # noqa: S105 - fake credential


class FakeAdmitter:
    """Admission double that records each call and returns fixed identities."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.index = "idx-1"
        self.error: Exception | None = None
        self.artefact_root: Path | None = None

    def __call__(self, revision: RevisionRecord, inputs: Mapping[str, Any]) -> Admission:
        self.calls.append((revision["revision_id"], dict(inputs)))
        if self.error is not None:
            raise self.error
        return Admission(
            settings={"retrieval": {"top_k": 10}, "openrouter_api_key": SECRET},
            resources={"index": self.index, "embedder": "bge-small"},
            payload=("admitted", revision["content_hash"]),
            artefact_root=self.artefact_root,
        )


class FakeExecutor:
    """Executor double driven by the ``mode`` and ``name`` run inputs.

    Modes: ``ok`` returns success; ``fail`` returns a failed result; ``raise``
    raises; ``block`` waits for :meth:`release`; ``cooperative`` waits for
    release or cancellation; ``stubborn`` ignores cancellation forever.
    """

    def __init__(self) -> None:
        self.calls: list[RunJob] = []
        self.tokens: dict[str, CancellationToken] = {}
        self.started: dict[str, asyncio.Event] = {}
        self._gates: dict[str, asyncio.Event] = {}
        self.events: dict[str, list[PipelineEvent]] = {}
        self.outputs: dict[str, Any] = {"answer": "done"}
        self.nodes: tuple[NodeOutcome, ...] = ()
        self.runner_wall_time_s: float | None = None

    def _event(self, name: str, store: dict[str, asyncio.Event]) -> asyncio.Event:
        return store.setdefault(name, asyncio.Event())

    def release(self, name: str) -> None:
        """Let the blocked job ``name`` finish."""
        self._event(name, self._gates).set()

    async def wait_started(self, name: str) -> None:
        """Wait until job ``name`` has entered the executor."""
        await asyncio.wait_for(self._event(name, self.started).wait(), 2)

    async def __call__(
        self,
        job: RunJob,
        *,
        on_event: Callable[[PipelineEvent], Awaitable[None]],
        cancellation: CancellationToken,
    ) -> PipelineResult:
        self.calls.append(job)
        name = str(job.inputs.get("name", "job"))
        mode = job.inputs.get("mode", "ok")
        self.tokens[name] = cancellation
        for index, event in enumerate(self.events.get(name, []), start=1):
            await on_event(event.model_copy(update={"run_id": job.run_id, "sequence": index}))
        self._event(name, self.started).set()
        gate = self._event(name, self._gates)
        if mode == "raise":
            raise RuntimeError(f"boom with Bearer {SECRET}")
        if mode == "block":
            await gate.wait()
        if mode == "stubborn":
            await asyncio.Event().wait()
        if mode == "cooperative":
            while not gate.is_set() and not cancellation.cancelled:
                await asyncio.sleep(0.005)
            if cancellation.cancelled:
                return self._result(job, RunStatus.CANCELLED, effects=("source:a",))
        if mode == "fail":
            return self._result(job, RunStatus.FAILED, failed="a", effects=("source:a",))
        return self._result(job, RunStatus.SUCCEEDED)

    def _result(
        self,
        job: RunJob,
        status: RunStatus,
        *,
        failed: str | None = None,
        effects: tuple[str, ...] = (),
    ) -> PipelineResult:
        return PipelineResult(
            run_id=job.run_id,
            status=status,
            graph_identity=job.graph_hash,
            outputs=dict(self.outputs),
            nodes=self.nodes,
            failed_node=failed,
            completed_effects=effects,
            wall_time_s=self.runner_wall_time_s,
            error=f"node {failed} failed" if failed else None,
        )


async def idle(service: RunService, timeout: float = 5) -> None:
    """Wait for the service to go idle; fail instead of hanging."""
    await asyncio.wait_for(service.wait_idle(), timeout)


async def collect(stream: AsyncIterator[RunEventRecord], *, stop: int | None = None) -> list[int]:
    """Return event sequences from a stream, with a time limit; close the stream."""

    async def gather() -> list[int]:
        seen: list[int] = []
        async with aclosing(stream) as events:
            async for event in events:
                seen.append(event["sequence"])
                if stop is not None and len(seen) == stop:
                    break
        return seen

    return await asyncio.wait_for(gather(), 5)


def make_service(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter, **options: Any
) -> RunService:
    """Return a service on a real SQLite repository under ``tmp_path``."""
    return RunService(
        repository(tmp_path),
        executor,
        admit=admitter,
        artefacts=ArtefactStore(tmp_path / "ws" / "artefacts"),
        **options,
    )


def repository(tmp_path: Path) -> SqliteWorkspaceRepository:
    """Return the repository file shared by every service in one test."""
    return SqliteWorkspaceRepository(tmp_path / "ws" / "app.sqlite3")


def saved_revision(repo: SqliteWorkspaceRepository, document: Mapping[str, Any] = GRAPH) -> str:
    """Create a pipeline with one revision and return the revision id."""
    pipeline = repo.create_pipeline("Demo")
    return repo.save_revision(pipeline["pipeline_id"], document, schema_version=1)["revision_id"]


def node(node_id: str, duration_s: float) -> NodeOutcome:
    """Return a succeeded node outcome with a reported duration."""
    return NodeOutcome(node_id=node_id, status=NodeStatus.SUCCEEDED, duration_s=duration_s)


def runner_event(kind: EventKind, **fields: Any) -> PipelineEvent:
    """Return a runner event; the executor double fills run id and sequence."""
    return PipelineEvent(run_id="runner", sequence=1, kind=kind, **fields)


async def test_fake_executor_blocks_until_released(tmp_path: Path) -> None:
    executor, admitter = FakeExecutor(), FakeAdmitter()
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    revision_id = saved_revision(service.repository)
    run = service.submit(revision_id, inputs={"name": "a", "mode": "block"})
    await executor.wait_started("a")
    assert service.repository.get_run(run["run_id"])["status"] == "running"
    executor.release("a")
    await idle(service)
    assert service.repository.get_run(run["run_id"])["status"] == "succeeded"
    await service.shutdown()
