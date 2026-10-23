"""Restart interruption, shutdown and explicit retry (task 5.4).

The main guarantee: work that did not finish is reported, never repeated
automatically. Only an explicit retry starts a new run.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from tests.unit.test_workspace_service_support import (
    GRAPH_CHANGED,
    FakeAdmitter,
    FakeExecutor,
    idle,
    make_service,
    repository,
    saved_revision,
)

from omrs.core.workspace import RunStateError, ServiceClosedError


def _stale_runs(tmp_path: Path) -> tuple[str, str]:
    """Leave one queued and one running run, as a stopped process would."""
    repo = repository(tmp_path)
    revision_id = saved_revision(repo)
    queued = repo.create_run(revision_id, settings={}, resources={}, inputs={"name": "q"})
    running = repo.create_run(revision_id, settings={}, resources={}, inputs={"name": "r"})
    run_id = running["run_id"]
    repo.record_update(run_id, kind="run.status", summary={"status": "running"}, status="running")
    repo.record_update(
        run_id, kind="effect_committed", summary={"data": {"effect": "source:doc-1"}}, node_id="w"
    )
    return queued["run_id"], run_id


async def test_restart_marks_unfinished_runs_interrupted_without_rerun(tmp_path: Path) -> None:
    queued_id, running_id = _stale_runs(tmp_path)
    executor = FakeExecutor()
    service = make_service(tmp_path, executor, FakeAdmitter())

    interrupted = await service.start()
    await idle(service)
    await asyncio.sleep(0.02)

    assert sorted(interrupted) == sorted([queued_id, running_id])
    assert executor.calls == []
    repo = service.repository
    for run_id, previous in ((queued_id, "queued"), (running_id, "running")):
        record = repo.get_run(run_id)
        assert record["status"] == "interrupted"
        last = repo.list_events(run_id)[-1]
        assert last["summary"]["status"] == "interrupted"
        assert last["summary"]["previous_status"] == previous
    running = repo.get_run(running_id)
    assert running["failure"] is not None
    assert running["failure"]["completed_effects"] == ["source:doc-1"]
    assert running["failure"]["reason"] == "interrupted"
    assert [e["kind"] for e in repo.list_events(running_id)][:3] == [
        "run.status",
        "run.status",
        "effect_committed",
    ]
    await service.shutdown()


async def test_a_second_start_is_refused(tmp_path: Path) -> None:
    service = make_service(tmp_path, FakeExecutor(), FakeAdmitter())
    await service.start()
    with pytest.raises(RunStateError):
        await service.start()
    await service.shutdown()
    with pytest.raises(ServiceClosedError):
        await service.start()


async def test_shutdown_cancels_queued_and_waits_for_cooperative_run(tmp_path: Path) -> None:
    executor = FakeExecutor()
    service = make_service(tmp_path, executor, FakeAdmitter())
    await service.start()
    revision_id = saved_revision(service.repository)
    active = service.submit(revision_id, inputs={"name": "a", "mode": "cooperative"})
    await executor.wait_started("a")
    queued = service.submit(revision_id, inputs={"name": "b"})

    report = await service.shutdown(timeout=2)

    repo = service.repository
    assert repo.get_run(queued["run_id"])["status"] == "cancelled"
    assert repo.get_run(active["run_id"])["status"] == "cancelled"
    assert report.cancelled_queued == (queued["run_id"],)
    assert report.active_run_id == active["run_id"]
    assert report.interrupted == ()
    assert [j.inputs["name"] for j in executor.calls] == ["a"]
    with pytest.raises(ServiceClosedError):
        service.submit(revision_id, inputs={})


async def test_shutdown_timeout_interrupts_a_stuck_run(tmp_path: Path) -> None:
    executor = FakeExecutor()
    service = make_service(tmp_path, executor, FakeAdmitter())
    await service.start()
    run = service.submit(
        saved_revision(service.repository), inputs={"name": "a", "mode": "stubborn"}
    )
    await executor.wait_started("a")

    report = await service.shutdown(timeout=0.05)

    assert report.interrupted == (run["run_id"],)
    record = service.repository.get_run(run["run_id"])
    assert record["status"] == "interrupted"
    statuses = [e["summary"].get("status") for e in service.repository.list_events(run["run_id"])]
    assert statuses == ["queued", "running", "cancelling", "interrupted"]


async def test_shutdown_of_an_idle_service_is_clean(tmp_path: Path) -> None:
    service = make_service(tmp_path, FakeExecutor(), FakeAdmitter())
    await service.start()
    report = await service.shutdown()
    assert report.cancelled_queued == ()
    assert report.active_run_id is None
    assert await service.shutdown() == report


async def test_explicit_retry_creates_a_new_run_from_the_stored_snapshot(tmp_path: Path) -> None:
    executor, admitter = FakeExecutor(), FakeAdmitter()
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    repo = service.repository
    revision_id = saved_revision(repo)
    failed = service.submit(revision_id, inputs={"name": "a", "mode": "fail"})
    await idle(service)
    original_events = repo.list_events(failed["run_id"])
    repo.save_revision(failed["pipeline_id"], GRAPH_CHANGED, schema_version=1)
    admitter.index = "idx-2"
    await asyncio.sleep(0.02)
    assert len(executor.calls) == 1

    retried = service.retry(failed["run_id"])

    assert retried["run_id"] != failed["run_id"]
    assert retried["origin"] == "retry"
    assert retried["source_run_id"] == failed["run_id"]
    assert retried["revision_id"] == revision_id
    assert retried["inputs"] == {"name": "a", "mode": "fail"}
    assert retried["resources"]["index"] == "idx-2"
    assert len(admitter.calls) == 2
    await idle(service)
    assert len(executor.calls) == 2
    assert repo.get_run(failed["run_id"])["status"] == "failed"
    assert repo.list_events(failed["run_id"]) == original_events
    await service.shutdown()


async def test_interrupted_run_can_be_retried_explicitly(tmp_path: Path) -> None:
    _, running_id = _stale_runs(tmp_path)
    executor = FakeExecutor()
    service = make_service(tmp_path, executor, FakeAdmitter())
    await service.start()
    retried = service.retry(running_id)
    await idle(service)
    assert service.repository.get_run(retried["run_id"])["status"] == "succeeded"
    assert service.repository.get_run(running_id)["status"] == "interrupted"
    assert len(executor.calls) == 1
    await service.shutdown()


@pytest.mark.parametrize("mode", ["ok", "block"])
async def test_retry_is_refused_for_succeeded_or_active_runs(tmp_path: Path, mode: str) -> None:
    executor = FakeExecutor()
    service = make_service(tmp_path, executor, FakeAdmitter())
    await service.start()
    run = service.submit(saved_revision(service.repository), inputs={"name": "a", "mode": mode})
    if mode == "ok":
        await idle(service)
    else:
        await executor.wait_started("a")
    with pytest.raises(RunStateError):
        service.retry(run["run_id"])
    executor.release("a")
    await service.shutdown()


async def test_explicit_repeat_records_its_origin(tmp_path: Path) -> None:
    service = make_service(tmp_path, FakeExecutor(), FakeAdmitter())
    await service.start()
    run = service.submit(saved_revision(service.repository), inputs={}, origin="repeat")
    assert run["origin"] == "repeat"
    with pytest.raises(ValueError):
        service.submit(run["revision_id"], inputs={}, origin="retry")
    await service.shutdown()
