"""Workspace repository behaviour through the SQLite adapter (task 5.1).

Covers immutable revisions, separate presentation layouts, run records,
atomic status/event updates, per-run event sequences and plugin records.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from omrs.core.workspace import (
    NONTERMINAL_RUN_STATUSES,
    RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    WorkspaceRepository,
)
from omrs.integrations.workspace_sqlite import SqliteWorkspaceRepository
from omrs.integrations.workspace_sqlite import repository as sqlite_repository

_GRAPH = {"version": 1, "nodes": [{"id": "a", "op": "read"}], "edges": []}
_GRAPH_CHANGED = {"version": 1, "nodes": [{"id": "a", "op": "chunk"}], "edges": []}


@pytest.fixture
def repo(tmp_path: Path) -> SqliteWorkspaceRepository:
    """Return a repository on a fresh database under ``tmp_path``."""
    return SqliteWorkspaceRepository(tmp_path / "workspace" / "app.sqlite3")


def _queued_run(repo: SqliteWorkspaceRepository) -> tuple[str, str]:
    pipeline = repo.create_pipeline("Demo")
    revision = repo.save_revision(pipeline["pipeline_id"], _GRAPH, schema_version=1)
    run = repo.create_run(
        revision["revision_id"],
        settings={"retrieval": {"top_k": 10}},
        resources={"index": "idx-1"},
        inputs={"query": "q"},
    )
    return run["run_id"], revision["revision_id"]


def test_adapter_satisfies_repository_protocol(repo: SqliteWorkspaceRepository) -> None:
    assert isinstance(repo, WorkspaceRepository)


def test_adapter_status_sets_match_core_contract() -> None:
    assert sqlite_repository.RUN_STATUSES == RUN_STATUSES
    assert sqlite_repository.TERMINAL_RUN_STATUSES == TERMINAL_RUN_STATUSES
    assert RUN_STATUSES == TERMINAL_RUN_STATUSES | NONTERMINAL_RUN_STATUSES


# --- pipelines and revisions -------------------------------------------------


def test_create_and_list_pipelines(repo: SqliteWorkspaceRepository) -> None:
    created = repo.create_pipeline("Demo", layout={"a": {"x": 1, "y": 2}})
    assert created["title"] == "Demo"
    assert created["current_revision_id"] is None
    assert created["layout"] == {"a": {"x": 1, "y": 2}}
    assert repo.get_pipeline(created["pipeline_id"]) == created
    assert [p["pipeline_id"] for p in repo.list_pipelines()] == [created["pipeline_id"]]


def test_unknown_identifiers_raise_key_error(repo: SqliteWorkspaceRepository) -> None:
    with pytest.raises(KeyError):
        repo.get_pipeline("missing")
    with pytest.raises(KeyError):
        repo.get_revision("missing")
    with pytest.raises(KeyError):
        repo.get_run("missing")
    with pytest.raises(KeyError):
        repo.save_layout("missing", {})
    with pytest.raises(KeyError):
        repo.save_revision("missing", _GRAPH, schema_version=1)
    with pytest.raises(KeyError):
        repo.create_run("missing", settings={}, resources={}, inputs={})
    with pytest.raises(KeyError):
        repo.record_update("missing", kind="node.started", summary={})
    with pytest.raises(KeyError):
        repo.list_events("missing")


def test_revision_identity_is_sha256_of_canonical_json(
    repo: SqliteWorkspaceRepository,
) -> None:
    pipeline = repo.create_pipeline("Demo")
    revision = repo.save_revision(pipeline["pipeline_id"], _GRAPH, schema_version=1)
    canonical = json.dumps(_GRAPH, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert revision["content_hash"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert revision["document"] == _GRAPH
    assert revision["revision_number"] == 1
    assert revision["schema_version"] == 1


def test_identical_content_returns_existing_revision(
    repo: SqliteWorkspaceRepository,
) -> None:
    pipeline_id = repo.create_pipeline("Demo")["pipeline_id"]
    first = repo.save_revision(pipeline_id, _GRAPH, schema_version=1)
    reordered = {"edges": [], "nodes": [{"op": "read", "id": "a"}], "version": 1}
    again = repo.save_revision(pipeline_id, reordered, schema_version=1)
    assert again == first
    assert len(repo.list_revisions(pipeline_id)) == 1
    with pytest.raises(ValueError, match="schema version"):
        repo.save_revision(pipeline_id, _GRAPH, schema_version=2)


def test_semantic_change_creates_new_revision_and_moves_current(
    repo: SqliteWorkspaceRepository,
) -> None:
    pipeline_id = repo.create_pipeline("Demo")["pipeline_id"]
    first = repo.save_revision(pipeline_id, _GRAPH, schema_version=1)
    second = repo.save_revision(pipeline_id, _GRAPH_CHANGED, schema_version=1)
    assert second["revision_id"] != first["revision_id"]
    assert second["revision_number"] == 2
    assert repo.get_pipeline(pipeline_id)["current_revision_id"] == second["revision_id"]
    assert repo.get_revision(first["revision_id"]) == first
    # Re-saving older content points current back at the existing revision.
    back = repo.save_revision(pipeline_id, _GRAPH, schema_version=1)
    assert back == first
    assert repo.get_pipeline(pipeline_id)["current_revision_id"] == first["revision_id"]
    assert [r["revision_number"] for r in repo.list_revisions(pipeline_id)] == [1, 2]


def test_non_json_document_is_rejected(repo: SqliteWorkspaceRepository) -> None:
    pipeline_id = repo.create_pipeline("Demo")["pipeline_id"]
    with pytest.raises(ValueError):
        repo.save_revision(pipeline_id, {"bad": float("nan")}, schema_version=1)
    with pytest.raises(ValueError):
        repo.save_revision(pipeline_id, {"bad": object()}, schema_version=1)
    assert repo.list_revisions(pipeline_id) == []


def test_stored_revisions_cannot_be_updated_or_deleted(
    repo: SqliteWorkspaceRepository,
) -> None:
    pipeline_id = repo.create_pipeline("Demo")["pipeline_id"]
    revision = repo.save_revision(pipeline_id, _GRAPH, schema_version=1)
    conn = sqlite3.connect(repo.path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE pipeline_revisions SET document_json = '{}'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("DELETE FROM pipeline_revisions")
    finally:
        conn.close()
    assert repo.get_revision(revision["revision_id"]) == revision


def test_layout_save_never_creates_a_revision(repo: SqliteWorkspaceRepository) -> None:
    pipeline_id = repo.create_pipeline("Demo")["pipeline_id"]
    revision = repo.save_revision(pipeline_id, _GRAPH, schema_version=1)
    updated = repo.save_layout(pipeline_id, {"a": {"x": 50, "y": 9}})
    assert updated["layout"] == {"a": {"x": 50, "y": 9}}
    assert updated["current_revision_id"] == revision["revision_id"]
    assert repo.list_revisions(pipeline_id) == [revision]


# --- runs and events ---------------------------------------------------------


def test_create_run_snapshots_revision_and_writes_first_event(
    repo: SqliteWorkspaceRepository,
) -> None:
    run_id, revision_id = _queued_run(repo)
    run = repo.get_run(run_id)
    revision = repo.get_revision(revision_id)
    assert run["status"] == "queued"
    assert run["revision_id"] == revision_id
    assert run["graph_hash"] == revision["content_hash"]
    assert run["pipeline_id"] == revision["pipeline_id"]
    assert run["origin"] == "submit"
    assert run["source_run_id"] is None
    assert run["settings"] == {"retrieval": {"top_k": 10}}
    assert run["resources"] == {"index": "idx-1"}
    assert run["inputs"] == {"query": "q"}
    assert run["last_sequence"] == 1
    events = repo.list_events(run_id)
    assert [(e["sequence"], e["kind"], e["summary"]) for e in events] == [
        (1, "run.status", {"status": "queued"})
    ]


def test_editing_after_submission_keeps_the_admitted_revision(
    repo: SqliteWorkspaceRepository,
) -> None:
    run_id, revision_id = _queued_run(repo)
    pipeline_id = repo.get_run(run_id)["pipeline_id"]
    assert pipeline_id is not None
    repo.save_revision(pipeline_id, _GRAPH_CHANGED, schema_version=1)
    assert repo.get_run(run_id)["revision_id"] == revision_id


def test_repeat_and_retry_runs_identify_their_origin(
    repo: SqliteWorkspaceRepository,
) -> None:
    run_id, revision_id = _queued_run(repo)
    retry = repo.create_run(
        revision_id,
        settings={},
        resources={},
        inputs={},
        origin="retry",
        source_run_id=run_id,
    )
    assert retry["origin"] == "retry"
    assert retry["source_run_id"] == run_id
    assert repo.get_run(run_id)["status"] == "queued"
    with pytest.raises(ValueError):
        repo.create_run(revision_id, settings={}, resources={}, inputs={}, origin="other")
    with pytest.raises(KeyError):
        repo.create_run(revision_id, settings={}, resources={}, inputs={}, source_run_id="missing")


def test_status_update_and_event_commit_together(tmp_path: Path) -> None:
    times = iter(datetime(2026, 10, 13, 12, 0, second, tzinfo=UTC) for second in range(10))
    repo = SqliteWorkspaceRepository(tmp_path / "app.sqlite3", clock=lambda: next(times))
    run_id, _ = _queued_run(repo)
    run, event = repo.record_update(
        run_id, kind="run.status", summary={"status": "running"}, status="running"
    )
    assert run["status"] == "running"
    assert run["started_at"] is not None
    assert run["finished_at"] is None
    assert event["sequence"] == 2
    assert run["last_sequence"] == 2
    run, event = repo.record_update(
        run_id,
        kind="run.status",
        summary={"status": "failed"},
        status="failed",
        failure={"node_id": "a", "message": "boom"},
        result_ref="results/run.json",
    )
    assert run["status"] == "failed"
    assert run["failure"] == {"node_id": "a", "message": "boom"}
    assert run["result_ref"] == "results/run.json"
    assert run["finished_at"] is not None
    assert run["started_at"] is not None and run["started_at"] < run["finished_at"]
    assert repo.get_run(run_id) == run


def test_failed_event_write_rolls_back_the_status_update(
    repo: SqliteWorkspaceRepository,
) -> None:
    run_id, _ = _queued_run(repo)
    with pytest.raises(ValueError):
        repo.record_update(
            run_id, kind="run.status", summary={"bad": float("inf")}, status="running"
        )
    # Make the event insert fail after the run row is updated in the same transaction.
    conn = sqlite3.connect(repo.path)
    conn.execute(
        "CREATE TRIGGER block_event BEFORE INSERT ON run_events "
        "BEGIN SELECT RAISE(ABORT, 'event store unavailable'); END"
    )
    conn.close()
    with pytest.raises(sqlite3.IntegrityError, match="event store unavailable"):
        repo.record_update(run_id, kind="run.status", summary={}, status="running")
    run = repo.get_run(run_id)
    assert run["status"] == "queued"
    assert run["last_sequence"] == 1
    assert len(repo.list_events(run_id)) == 1


def test_event_only_updates_keep_status_and_sequence_monotonic(
    repo: SqliteWorkspaceRepository,
) -> None:
    run_id, _ = _queued_run(repo)
    repo.record_update(run_id, kind="run.status", summary={}, status="running")
    for unit in ("f1", "f2", "f3"):
        run, _ = repo.record_update(
            run_id, kind="node.unit", node_id="read", unit_id=unit, summary={"ok": True}
        )
        assert run["status"] == "running"
    events = repo.list_events(run_id)
    assert [e["sequence"] for e in events] == [1, 2, 3, 4, 5]
    assert events[-1]["node_id"] == "read"
    assert events[-1]["unit_id"] == "f3"


def test_replay_returns_events_after_a_sequence_in_order(
    repo: SqliteWorkspaceRepository,
) -> None:
    run_id, _ = _queued_run(repo)
    for index in range(4):
        repo.record_update(run_id, kind="node.progress", summary={"i": index})
    replay = repo.list_events(run_id, after_sequence=3)
    assert [e["sequence"] for e in replay] == [4, 5]
    assert [e["sequence"] for e in repo.list_events(run_id, after_sequence=1, limit=2)] == [
        2,
        3,
    ]
    assert repo.list_events(run_id, after_sequence=5) == []


def test_sequences_are_independent_per_run(repo: SqliteWorkspaceRepository) -> None:
    first, revision_id = _queued_run(repo)
    second = repo.create_run(revision_id, settings={}, resources={}, inputs={})["run_id"]
    repo.record_update(first, kind="node.progress", summary={})
    _, event = repo.record_update(second, kind="node.progress", summary={})
    assert event["sequence"] == 2


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        (("running", "succeeded"), "running"),
        (("cancelled",), "running"),
        (("interrupted",), "queued"),
    ],
)
def test_terminal_runs_reject_further_updates(
    repo: SqliteWorkspaceRepository, path: tuple[str, ...], bad: str
) -> None:
    run_id, _ = _queued_run(repo)
    for status in path:
        repo.record_update(run_id, kind="run.status", summary={}, status=status)
    with pytest.raises(ValueError):
        repo.record_update(run_id, kind="run.status", summary={}, status=bad)
    with pytest.raises(ValueError):
        repo.record_update(run_id, kind="node.progress", summary={})
    assert repo.get_run(run_id)["last_sequence"] == len(path) + 1


def test_invalid_transitions_are_rejected(repo: SqliteWorkspaceRepository) -> None:
    run_id, _ = _queued_run(repo)
    with pytest.raises(ValueError):
        repo.record_update(run_id, kind="run.status", summary={}, status="unknown")
    with pytest.raises(ValueError):
        repo.record_update(run_id, kind="run.status", summary={}, status="queued")
    repo.record_update(run_id, kind="run.status", summary={}, status="running")
    with pytest.raises(ValueError):
        repo.record_update(run_id, kind="run.status", summary={}, status="queued")
    with pytest.raises(ValueError):
        repo.record_update(run_id, kind="", summary={})


def test_list_runs_filters_by_pipeline_and_status(
    repo: SqliteWorkspaceRepository,
) -> None:
    first, revision_id = _queued_run(repo)
    second = repo.create_run(revision_id, settings={}, resources={}, inputs={})["run_id"]
    repo.record_update(second, kind="run.status", summary={}, status="running")
    pipeline_id = repo.get_run(first)["pipeline_id"]
    assert pipeline_id is not None
    other = repo.create_pipeline("Other")["pipeline_id"]
    assert {r["run_id"] for r in repo.list_runs()} == {first, second}
    assert {r["run_id"] for r in repo.list_runs(pipeline_id=pipeline_id)} == {first, second}
    assert repo.list_runs(pipeline_id=other) == []
    running = repo.list_runs(statuses=NONTERMINAL_RUN_STATUSES - {"queued"})
    assert [r["run_id"] for r in running] == [second]
    assert len(repo.list_runs(limit=1)) == 1
    with pytest.raises(ValueError):
        repo.list_runs(statuses={"bogus"})


# --- plugin registrations ----------------------------------------------------


def test_plugin_registration_round_trip(repo: SqliteWorkspaceRepository) -> None:
    created = repo.register_plugin(
        "marimo",
        manifest_ref="plugins/marimo/manifest.json",
        executable_ref="/opt/bin/marimo",
        manifest_hash="abc",
    )
    assert created["compatibility_status"] == "unchecked"
    assert created["checked_at"] is None
    checked = repo.set_plugin_compatibility("marimo", "compatible", detail={"version": "0.9"})
    assert checked["compatibility_status"] == "compatible"
    assert checked["detail"] == {"version": "0.9"}
    assert checked["checked_at"] is not None
    assert repo.get_plugin("marimo") == checked
    assert repo.list_plugins() == [checked]
    # Re-registration replaces the references and resets compatibility.
    again = repo.register_plugin(
        "marimo", manifest_ref="m2.json", executable_ref="/opt/bin/marimo2"
    )
    assert again["manifest_ref"] == "m2.json"
    assert again["compatibility_status"] == "unchecked"
    with pytest.raises(ValueError):
        repo.set_plugin_compatibility("marimo", "great")
    with pytest.raises(KeyError):
        repo.set_plugin_compatibility("missing", "compatible")
    with pytest.raises(KeyError):
        repo.get_plugin("missing")
