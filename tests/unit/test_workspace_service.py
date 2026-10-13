"""Bounded single-consumer run service (task 5.2).

Covers queue overflow, failed-job recovery, immutable job snapshots,
cancellation, and status/event transactions that commit before subscribers
see them. Uses a real SQLite repository and a fake executor.
"""

from __future__ import annotations

import asyncio
import dataclasses
from contextlib import aclosing
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_workspace_service_support import (
    GRAPH,
    GRAPH_CHANGED,
    SECRET,
    FakeAdmitter,
    FakeExecutor,
    idle,
    make_service,
    repository,
    runner_event,
    saved_revision,
)

from omrg.core.pipelines import EventKind, RunCancellation
from omrg.core.workspace import (
    NONTERMINAL_RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    QueueFullError,
    RunEventLog,
    RunService,
    RunStateError,
    ServiceClosedError,
    UnsafeInputError,
)


@pytest.fixture
def executor() -> FakeExecutor:
    """Return a fresh executor double."""
    return FakeExecutor()


@pytest.fixture
def admitter() -> FakeAdmitter:
    """Return a fresh admission double."""
    return FakeAdmitter()


def _statuses(service: Any, run_id: str) -> list[str]:
    events = service.repository.list_events(run_id)
    return [e["summary"]["status"] for e in events if e["kind"] == "run.status"]


async def test_cancelling_is_a_nonterminal_status() -> None:
    assert "cancelling" in NONTERMINAL_RUN_STATUSES
    assert "cancelling" not in TERMINAL_RUN_STATUSES


async def test_submit_requires_a_started_service(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    revision_id = saved_revision(service.repository)
    with pytest.raises(ServiceClosedError):
        service.submit(revision_id, inputs={})
    assert service.repository.list_runs() == []


async def test_queue_overflow_is_rejected_visibly_without_starting_work(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter, max_waiting=2)
    await service.start()
    revision_id = saved_revision(service.repository)
    active = service.submit(revision_id, inputs={"name": "a", "mode": "block"})
    await executor.wait_started("a")
    waiting = [service.submit(revision_id, inputs={"name": n}) for n in ("b", "c")]
    before = {r["run_id"]: r for r in service.repository.list_runs()}

    with pytest.raises(QueueFullError) as caught:
        service.submit(revision_id, inputs={"name": "d"})

    assert caught.value.limit == 2
    assert "2" in str(caught.value)
    after = {r["run_id"]: r for r in service.repository.list_runs()}
    assert after == before
    assert len(admitter.calls) == 3
    assert [r["status"] for r in waiting] == ["queued", "queued"]
    assert service.waiting_count == 2
    executor.release("a")
    await idle(service)
    assert service.repository.get_run(active["run_id"])["status"] == "succeeded"
    assert [j.inputs["name"] for j in executor.calls] == ["a", "b", "c"]
    await service.shutdown()


async def test_default_waiting_limit_is_sixteen(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    assert service.max_waiting == 16
    with pytest.raises(ValueError):
        make_service(tmp_path, executor, admitter, max_waiting=0)


@pytest.mark.parametrize("mode", ["raise", "fail"])
async def test_failed_job_does_not_stop_the_consumer(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter, mode: str
) -> None:
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    revision_id = saved_revision(service.repository)
    bad = service.submit(revision_id, inputs={"name": "bad", "mode": mode})
    good = service.submit(revision_id, inputs={"name": "good"})
    await idle(service)

    bad_record = service.repository.get_run(bad["run_id"])
    assert bad_record["status"] == "failed"
    assert bad_record["failure"] is not None
    assert SECRET not in str(bad_record["failure"])
    assert service.repository.get_run(good["run_id"])["status"] == "succeeded"
    assert _statuses(service, bad["run_id"]) == ["queued", "running", "failed"]
    await service.shutdown()


async def test_failed_result_records_failing_node_and_completed_effects(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    revision_id = saved_revision(service.repository)
    run = service.submit(revision_id, inputs={"name": "x", "mode": "fail"})
    await idle(service)
    record = service.repository.get_run(run["run_id"])
    assert record["failure"] is not None
    assert record["failure"]["failed_node"] == "a"
    assert record["failure"]["completed_effects"] == ["source:a"]
    await service.shutdown()


async def test_job_snapshot_is_immutable_and_survives_later_edits(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    repo = service.repository
    revision_id = saved_revision(repo)
    inputs: dict[str, Any] = {"name": "a", "mode": "block", "files": ["one.md"]}
    run = service.submit(revision_id, inputs=inputs)
    inputs["files"].append("two.md")
    repo.save_revision(run["pipeline_id"], GRAPH_CHANGED, schema_version=1)
    await executor.wait_started("a")

    job = executor.calls[0]
    assert job.document == GRAPH
    assert job.inputs["files"] == ["one.md"]
    job.inputs["files"].append("mutated")
    assert job.inputs["files"] == ["one.md"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        job.run_id = "other"  # type: ignore[misc]
    assert job.revision_id == revision_id
    assert job.graph_hash == repo.get_revision(revision_id)["content_hash"]
    assert job.settings["openrouter_api_key"] == "[redacted]"
    assert job.settings["retrieval"] == {"top_k": 10}
    assert job.resources == {"index": "idx-1", "embedder": "bge-small"}
    assert job.payload == ("admitted", job.graph_hash)
    assert repo.get_run(run["run_id"])["revision_id"] == revision_id
    assert repo.get_run(run["run_id"])["settings"]["openrouter_api_key"] == "[redacted]"
    executor.release("a")
    await service.shutdown()


async def test_admission_failure_creates_no_run(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    revision_id = saved_revision(service.repository)
    admitter.error = ValueError("graph invalid")
    with pytest.raises(ValueError, match="graph invalid"):
        service.submit(revision_id, inputs={})
    assert service.repository.list_runs() == []
    await service.shutdown()


async def test_inputs_with_credentials_are_refused(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    revision_id = saved_revision(service.repository)
    with pytest.raises(UnsafeInputError):
        service.submit(revision_id, inputs={"query": f"use {SECRET}"})
    with pytest.raises(UnsafeInputError):
        service.submit(revision_id, inputs={"api_key": "abc12345"})
    assert service.repository.list_runs() == []
    await service.shutdown()


async def test_status_and_runner_events_are_committed_in_order(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    executor.events["a"] = [
        runner_event(EventKind.NODE_STARTED, node_id="a"),
        runner_event(EventKind.NODE_PROGRESS, node_id="a", unit_id="doc-1", message="half"),
        runner_event(EventKind.NODE_COMPLETED, node_id="a"),
    ]
    revision_id = saved_revision(service.repository)
    run = service.submit(revision_id, inputs={"name": "a"})
    await idle(service)

    events = service.repository.list_events(run["run_id"])
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    assert [e["kind"] for e in events] == [
        "run.status",
        "run.status",
        "node_started",
        "node_progress",
        "node_completed",
        "run.status",
    ]
    assert events[3]["unit_id"] == "doc-1"
    assert events[3]["summary"]["message"] == "half"
    assert events[-1]["summary"]["status"] == "succeeded"
    await service.shutdown()


async def test_subscribers_see_events_only_after_commit(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    executor.events["a"] = [runner_event(EventKind.NODE_STARTED, node_id="a")]
    repo = service.repository
    revision_id = saved_revision(repo)
    run = service.submit(revision_id, inputs={"name": "a", "mode": "block"})
    seen: list[tuple[int, bool]] = []

    async def watch() -> None:
        async with aclosing(service.subscribe(run["run_id"])) as stream:
            async for event in stream:
                stored = repo.list_events(run["run_id"], after_sequence=event["sequence"] - 1)
                seen.append((event["sequence"], stored[0] == event))

    watcher = asyncio.create_task(watch())
    await executor.wait_started("a")
    executor.release("a")
    await asyncio.wait_for(watcher, 2)
    assert [s for s, _ in seen] == [1, 2, 3, 4]
    assert all(committed for _, committed in seen)
    await service.shutdown()


async def test_cancel_queued_run_is_immediate_and_never_executes(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    revision_id = saved_revision(service.repository)
    service.submit(revision_id, inputs={"name": "a", "mode": "block"})
    await executor.wait_started("a")
    queued = service.submit(revision_id, inputs={"name": "b"})

    record = service.cancel(queued["run_id"])

    assert record["status"] == "cancelled"
    assert service.waiting_count == 0
    executor.release("a")
    await idle(service)
    assert [j.inputs["name"] for j in executor.calls] == ["a"]
    assert service.cancel(queued["run_id"])["status"] == "cancelled"
    await service.shutdown()


async def test_cancel_running_run_is_cooperative(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    revision_id = saved_revision(service.repository)
    run = service.submit(revision_id, inputs={"name": "a", "mode": "cooperative"})
    await executor.wait_started("a")

    requested = service.cancel(run["run_id"])
    assert requested["status"] == "cancelling"
    assert service.cancel(run["run_id"])["status"] == "cancelling"
    await idle(service)

    record = service.repository.get_run(run["run_id"])
    assert record["status"] == "cancelled"
    assert _statuses(service, run["run_id"]) == ["queued", "running", "cancelling", "cancelled"]
    requests = [
        e
        for e in service.repository.list_events(run["run_id"])
        if e["summary"].get("status") == "cancelling"
    ]
    assert len(requests) == 1
    assert requests[0]["summary"]["reason"] == "cancel requested"
    assert record["failure"] is not None
    assert record["failure"]["completed_effects"] == ["source:a"]
    await service.shutdown()


async def test_cancel_unknown_run_raises_key_error(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    with pytest.raises(KeyError):
        service.cancel("missing")
    await service.shutdown()


async def test_cancel_of_a_run_owned_by_no_consumer_is_refused(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    repo = service.repository
    revision_id = saved_revision(repo)
    stray = repo.create_run(revision_id, settings={}, resources={}, inputs={})
    repo.record_update(stray["run_id"], kind="run.status", summary={}, status="running")
    with pytest.raises(RunStateError):
        service.cancel(stray["run_id"])
    await service.shutdown()


class _FailOnceRepository:
    """Repository proxy whose first terminal ``succeeded`` update fails."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.failed = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def record_update(self, run_id: str, **fields: Any) -> Any:
        if fields.get("status") == "succeeded" and not self.failed:
            self.failed = True
            raise OSError("disk full")
        return self._inner.record_update(run_id, **fields)


async def test_consumer_survives_a_recording_failure(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    flaky = _FailOnceRepository(service.repository)
    service = RunService(
        flaky,
        executor,
        admit=admitter,
        artefacts=service.artefacts,  # type: ignore[arg-type]
    )
    await service.start()
    revision_id = saved_revision(flaky._inner)
    first = service.submit(revision_id, inputs={"name": "a"})
    second = service.submit(revision_id, inputs={"name": "b"})
    await idle(service)

    assert flaky.failed
    record = flaky.get_run(first["run_id"])
    assert record["status"] == "failed"
    assert record["failure"]["error"] == "the run service could not record the result"
    assert flaky.get_run(second["run_id"])["status"] == "succeeded"
    await service.shutdown()


async def test_executor_receives_a_wakeable_cancellation_token(
    tmp_path: Path, executor: FakeExecutor, admitter: FakeAdmitter
) -> None:
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    run = service.submit(saved_revision(service.repository), inputs={"name": "a", "mode": "block"})
    await executor.wait_started("a")
    service.cancel(run["run_id"])
    token = executor.tokens["a"]
    assert isinstance(token, RunCancellation)
    await asyncio.wait_for(token.wait(), 1)
    assert token.cancelled
    executor.release("a")
    await service.shutdown()


async def test_failed_commit_wakes_no_subscriber(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    run_id = repo.create_run(saved_revision(repo), settings={}, resources={}, inputs={})["run_id"]
    log = RunEventLog(repo)
    stream = log.subscribe(run_id)
    assert (await asyncio.wait_for(anext(stream), 2))["sequence"] == 1
    waiting = asyncio.create_task(anext(stream))
    await asyncio.sleep(0.01)

    with pytest.raises(ValueError):
        log.record(run_id, kind="", summary={})
    await asyncio.sleep(0.01)
    assert not waiting.done()

    log.record(run_id, kind="run.status", summary={"status": "running"}, status="running")
    assert (await asyncio.wait_for(waiting, 2))["sequence"] == 2
    await stream.aclose()
