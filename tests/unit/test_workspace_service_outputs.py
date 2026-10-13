"""Bounded run outputs, reconnect replay and timing through the service (task 5.3)."""

from __future__ import annotations

import asyncio
import stat
from pathlib import Path

from tests.unit.test_workspace_service_support import (
    SECRET,
    FakeAdmitter,
    FakeExecutor,
    collect,
    idle,
    make_service,
    node,
    runner_event,
    saved_revision,
)

from omrg.core.pipelines import EventKind
from omrg.core.workspace import MAX_PREVIEW_ROWS, REDACTED


def _all_bytes(root: Path) -> bytes:
    return b"".join(p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file())


async def test_large_output_is_previewed_with_a_private_reference(tmp_path: Path) -> None:
    executor, admitter = FakeExecutor(), FakeAdmitter()
    executor.outputs = {"rows": [{"id": i, "text": "t" * 50} for i in range(500)]}
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    run = service.submit(saved_revision(service.repository), inputs={"name": "a"})
    await idle(service)

    record = service.repository.get_run(run["run_id"])
    terminal = service.repository.list_events(run["run_id"])[-1]["summary"]
    assert record["result_ref"] is not None
    assert terminal["result_ref"] == record["result_ref"]
    assert len(terminal["outputs"]["rows"]) == MAX_PREVIEW_ROWS
    assert terminal["outputs_truncated"] is True
    result = service.artefacts.read_json(record["result_ref"])
    assert len(result["outputs"]["rows"]) == 500
    path = service.artefacts.path(record["result_ref"])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    await service.shutdown()


async def test_secrets_never_reach_records_events_or_artefacts(tmp_path: Path) -> None:
    executor, admitter = FakeExecutor(), FakeAdmitter()
    executor.outputs = {"answer": f"see https://bob:{SECRET}@host/x", "api_key": SECRET}
    executor.events["a"] = [
        runner_event(EventKind.NODE_PROGRESS, node_id="a", message=f"Bearer {SECRET}"),
        runner_event(EventKind.NODE_PROGRESS, node_id="a", data={"token": SECRET}),
    ]
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    revision_id = saved_revision(service.repository)
    ok = service.submit(revision_id, inputs={"name": "a"})
    bad = service.submit(revision_id, inputs={"name": "b", "mode": "raise"})
    await idle(service)

    workspace = tmp_path / "ws"
    stored = _all_bytes(workspace)
    assert SECRET.encode() not in stored
    events = service.repository.list_events(ok["run_id"])
    assert events[2]["summary"]["message"] == f"Bearer {REDACTED}"
    assert events[3]["summary"]["data"] == {"token": REDACTED}
    failure = service.repository.get_run(bad["run_id"])["failure"]
    assert failure is not None
    assert REDACTED in failure["error"]
    await service.shutdown()


async def test_large_event_payloads_are_bounded(tmp_path: Path) -> None:
    executor, admitter = FakeExecutor(), FakeAdmitter()
    executor.events["a"] = [
        runner_event(
            EventKind.NODE_PROGRESS,
            node_id="a",
            data={"text": "z" * 9000, "embedding": [0.25] * 384},
        )
    ]
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    run = service.submit(saved_revision(service.repository), inputs={"name": "a"})
    await idle(service)

    summary = service.repository.list_events(run["run_id"])[2]["summary"]
    assert summary["truncated"] is True
    assert len(summary["data"]["text"]) == 4096
    assert summary["data"]["embedding"] == {"omitted": "vector data", "length": 384}
    full = service.artefacts.read_json(summary["artefact_ref"])
    assert full["data"]["text"] == "z" * 9000
    assert "0.25" not in str(full)
    await service.shutdown()


async def test_reconnect_replays_later_events_in_order(tmp_path: Path) -> None:
    executor, admitter = FakeExecutor(), FakeAdmitter()
    executor.events["a"] = [runner_event(EventKind.NODE_STARTED, node_id=n) for n in "abc"]
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    run = service.submit(saved_revision(service.repository), inputs={"name": "a", "mode": "block"})
    await executor.wait_started("a")

    first = await collect(service.subscribe(run["run_id"]), stop=3)
    assert first == [1, 2, 3]
    assert service.repository.get_run(run["run_id"])["status"] == "running"

    executor.release("a")
    replayed = await collect(service.subscribe(run["run_id"], after_sequence=first[-1]))
    assert replayed == [4, 5, 6]
    assert service.replay(run["run_id"], after_sequence=5)[0]["sequence"] == 6
    assert service.repository.get_run(run["run_id"])["status"] == "succeeded"
    await service.shutdown()


async def test_subscriber_disconnect_does_not_cancel_the_run(tmp_path: Path) -> None:
    executor, admitter = FakeExecutor(), FakeAdmitter()
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    run = service.submit(saved_revision(service.repository), inputs={"name": "a", "mode": "block"})
    stream = service.subscribe(run["run_id"])
    assert (await asyncio.wait_for(anext(stream), 5))["sequence"] == 1
    await stream.aclose()
    executor.release("a")
    await idle(service)
    assert service.repository.get_run(run["run_id"])["status"] == "succeeded"
    await service.shutdown()


async def test_subscribe_to_finished_run_replays_and_ends(tmp_path: Path) -> None:
    executor, admitter = FakeExecutor(), FakeAdmitter()
    service = make_service(tmp_path, executor, admitter)
    await service.start()
    run = service.submit(saved_revision(service.repository), inputs={"name": "a"})
    await idle(service)

    assert await collect(service.subscribe(run["run_id"], after_sequence=1)) == [2, 3]
    await service.shutdown()


async def test_overlapping_node_durations_are_never_summed(tmp_path: Path) -> None:
    executor, admitter = FakeExecutor(), FakeAdmitter()
    executor.nodes = (node("left", 5.0), node("right", 5.0))
    executor.runner_wall_time_s = 5.5
    ticks = iter([100.0, 106.0])
    service = make_service(tmp_path, executor, admitter, monotonic=lambda: next(ticks))
    await service.start()
    run = service.submit(saved_revision(service.repository), inputs={"name": "a"})
    await idle(service)

    summary = service.repository.list_events(run["run_id"])[-1]["summary"]
    assert summary["wall_time_s"] == 6.0
    assert summary["runner_wall_time_s"] == 5.5
    assert summary["node_durations_s"] == {"left": 5.0, "right": 5.0}
    assert 10.0 not in summary.values()
    assert "total_node_time_s" not in summary
    await service.shutdown()
