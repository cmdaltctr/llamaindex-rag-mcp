"""Previewed workspace cleanup: selectors, tokens and record removal (task 5.5)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from tests.unit.test_workspace_cleanup_support import Workspace

from omrg.core.workspace import (
    CleanupRejected,
    CleanupSelector,
    WorkspaceCleanup,
    WorkspaceRepository,
)


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    """Return a fresh workspace under ``tmp_path``."""
    return Workspace(tmp_path / "workspace")


def _cleanup(ws: Workspace, **kwargs: float) -> WorkspaceCleanup:
    return WorkspaceCleanup.for_layout(ws.repo, ws.layout, clock=ws.clock, **kwargs)


# --- selectors ---------------------------------------------------------------


def test_selector_needs_a_criterion() -> None:
    with pytest.raises(ValueError, match="at least one"):
        CleanupSelector()


@pytest.mark.parametrize("status", ["queued", "running", "cancelling", "bogus"])
def test_selector_refuses_active_or_unknown_statuses(status: str) -> None:
    with pytest.raises(ValueError, match="finished"):
        CleanupSelector.by_status(status)


@pytest.mark.parametrize("days", [-1.0, float("nan"), float("inf")])
def test_selector_refuses_invalid_age(days: float) -> None:
    with pytest.raises(ValueError):
        CleanupSelector.older_than(days)


def test_selector_refuses_empty_run_id() -> None:
    with pytest.raises(ValueError, match="run_id"):
        CleanupSelector.run("")


def test_selector_dict_is_canonical() -> None:
    selector = CleanupSelector(statuses=("failed", "cancelled", "failed"), older_than_days=2)
    assert selector.as_dict() == {
        "older_than_days": 2,
        "run_id": None,
        "statuses": ["cancelled", "failed"],
    }


def test_older_than_selects_finished_runs_by_finish_time(ws: Workspace) -> None:
    old = ws.run("succeeded")
    ws.clock.advance(days=10)
    recent = ws.run("failed")
    ws.clock.advance(days=1)
    active = ws.run("running")
    preview = _cleanup(ws).preview_cleanup(CleanupSelector.older_than(5))
    assert [run.run_id for run in preview.runs] == [old]
    assert recent not in {run.run_id for run in preview.runs}
    assert active not in {run.run_id for run in preview.runs}


def test_status_selector_matches_only_listed_statuses(ws: Workspace) -> None:
    failed = ws.run("failed")
    cancelled = ws.run("cancelled")
    ws.run("succeeded")
    preview = _cleanup(ws).preview_cleanup(CleanupSelector.by_status("failed", "cancelled"))
    assert {run.run_id for run in preview.runs} == {failed, cancelled}


def test_run_selector_matches_one_run(ws: Workspace) -> None:
    target = ws.run("succeeded")
    ws.run("succeeded")
    preview = _cleanup(ws).preview_cleanup(CleanupSelector.run(target))
    assert [run.run_id for run in preview.runs] == [target]


def test_run_selector_for_unknown_run_raises(ws: Workspace) -> None:
    with pytest.raises(KeyError):
        _cleanup(ws).preview_cleanup(CleanupSelector.run("missing"))


@pytest.mark.parametrize("status", ["queued", "running"])
def test_active_run_is_never_selected(ws: Workspace, status: str) -> None:
    active = ws.run(status)
    cleanup = _cleanup(ws)
    preview = cleanup.preview_cleanup(CleanupSelector.run(active))
    assert preview.runs == ()
    assert [skip.item for skip in preview.skipped] == [f"run {active}"]
    assert "active" in preview.skipped[0].reason
    result = cleanup.apply_cleanup(preview.token)
    assert result.runs_removed == 0
    assert active in ws.run_ids()


def test_cancelling_run_is_never_selected(ws: Workspace) -> None:
    run_id = ws.run("running")
    ws.repo.record_update(run_id, kind="run.status", summary={}, status="cancelling")
    preview = _cleanup(ws).preview_cleanup(CleanupSelector.run(run_id))
    assert preview.runs == ()


def test_run_referenced_by_a_kept_retry_is_skipped(ws: Workspace) -> None:
    first = ws.run("failed")
    retry = ws.run("succeeded", source_run_id=first)
    preview = _cleanup(ws).preview_cleanup(CleanupSelector.by_status("failed"))
    assert preview.runs == ()
    assert retry in preview.skipped[0].reason
    both = _cleanup(ws).preview_cleanup(CleanupSelector.older_than(0))
    assert {run.run_id for run in both.runs} == {first, retry}


def test_retry_chain_keeps_every_referenced_run(ws: Workspace) -> None:
    first = ws.run("failed")
    second = ws.run("failed", source_run_id=first)
    ws.run("succeeded", source_run_id=second)
    preview = _cleanup(ws).preview_cleanup(CleanupSelector.by_status("failed"))
    assert preview.runs == ()
    assert {skip.item for skip in preview.skipped} == {f"run {first}", f"run {second}"}


# --- preview content ------------------------------------------------------------


def test_preview_lists_records_events_files_and_totals(ws: Workspace) -> None:
    run_id = ws.run("succeeded", events=3, artefacts=2)
    preview = _cleanup(ws).preview_cleanup(CleanupSelector.run(run_id))
    (item,) = preview.runs
    stored = ws.repo.get_run(run_id)
    assert item.events == stored["last_sequence"] == len(ws.repo.list_events(run_id))
    assert [file.ref for file in item.files] == [f"{run_id}/part-0.json", f"{run_id}/part-1.json"]
    sizes = sum(os.path.getsize(ws.layout.artefacts / f.ref) for f in item.files)
    assert preview.totals == {"runs": 1, "events": item.events, "files": 2, "bytes": sizes}
    assert preview.token.startswith("wc_")
    assert preview.expires_at > ws.clock.now.isoformat()
    data = preview.as_dict()
    assert data["runs"][0]["files"][0]["ref"] == f"{run_id}/part-0.json"
    assert data["selector"] == {"older_than_days": None, "run_id": run_id, "statuses": []}


def test_preview_changes_nothing(ws: Workspace) -> None:
    run_id = ws.run("failed", events=2)
    before = (ws.repo.get_run(run_id), ws.repo.list_events(run_id))
    files = sorted(p.name for p in (ws.layout.artefacts / run_id).iterdir())
    _cleanup(ws).preview_cleanup(CleanupSelector.run(run_id))
    assert (ws.repo.get_run(run_id), ws.repo.list_events(run_id)) == before
    assert sorted(p.name for p in (ws.layout.artefacts / run_id).iterdir()) == files


def test_interrupted_runs_carry_a_warning(ws: Workspace) -> None:
    ws.run("interrupted")
    preview = _cleanup(ws).preview_cleanup(CleanupSelector.by_status("interrupted"))
    assert len(preview.runs) == 1
    assert preview.warnings and "interrupted" in preview.warnings[0]


def test_run_without_artefacts_has_no_files(ws: Workspace) -> None:
    run_id = ws.run("succeeded", artefacts=0)
    (item,) = _cleanup(ws).preview_cleanup(CleanupSelector.run(run_id)).runs
    assert item.files == ()


# --- apply ---------------------------------------------------------------------------


def test_apply_removes_exactly_the_previewed_items(ws: Workspace) -> None:
    target = ws.run("failed", events=2, artefacts=2)
    kept = ws.run("succeeded", events=1, artefacts=1)
    cleanup = _cleanup(ws)
    preview = cleanup.preview_cleanup(CleanupSelector.by_status("failed"))
    result = cleanup.apply_cleanup(preview.token)
    assert (result.runs_removed, result.events_removed) == (1, preview.totals["events"])
    assert (result.files_removed, result.bytes_removed) == (2, preview.totals["bytes"])
    assert result.failed == ()
    assert ws.run_ids() == {kept}
    assert not (ws.layout.artefacts / target).exists()
    assert (ws.layout.artefacts / kept / "part-0.json").is_file()
    assert len(ws.repo.list_events(kept)) == ws.repo.get_run(kept)["last_sequence"]
    with pytest.raises(KeyError):
        ws.repo.list_events(target)


def test_apply_keeps_pipelines_and_revisions(ws: Workspace) -> None:
    ws.run("succeeded")
    cleanup = _cleanup(ws)
    cleanup.apply_cleanup(cleanup.preview_cleanup(CleanupSelector.older_than(0)).token)
    assert ws.repo.get_pipeline(ws.pipeline_id)["current_revision_id"] == ws.revision_id
    assert [r["revision_id"] for r in ws.repo.list_revisions(ws.pipeline_id)] == [ws.revision_id]
    assert ws.run_ids() == set()


def test_token_is_single_use(ws: Workspace) -> None:
    ws.run("failed")
    cleanup = _cleanup(ws)
    token = cleanup.preview_cleanup(CleanupSelector.by_status("failed")).token
    cleanup.apply_cleanup(token)
    with pytest.raises(CleanupRejected) as exc:
        cleanup.apply_cleanup(token)
    assert exc.value.reason == "unknown"


def test_altered_token_is_rejected_and_changes_nothing(ws: Workspace) -> None:
    run_id = ws.run("failed")
    cleanup = _cleanup(ws)
    token = cleanup.preview_cleanup(CleanupSelector.by_status("failed")).token
    altered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(CleanupRejected) as exc:
        cleanup.apply_cleanup(altered)
    assert exc.value.reason == "unknown"
    assert ws.run_ids() == {run_id}


def test_token_from_another_service_is_rejected(ws: Workspace) -> None:
    ws.run("failed")
    token = _cleanup(ws).preview_cleanup(CleanupSelector.by_status("failed")).token
    with pytest.raises(CleanupRejected):
        _cleanup(ws).apply_cleanup(token)


def test_expired_token_is_rejected(ws: Workspace) -> None:
    run_id = ws.run("failed")
    cleanup = _cleanup(ws, ttl_seconds=60)
    token = cleanup.preview_cleanup(CleanupSelector.by_status("failed")).token
    ws.clock.advance(seconds=61)
    with pytest.raises(CleanupRejected) as exc:
        cleanup.apply_cleanup(token)
    assert exc.value.reason == "expired"
    assert ws.run_ids() == {run_id}


def test_selector_mismatch_is_rejected(ws: Workspace) -> None:
    run_id = ws.run("failed")
    cleanup = _cleanup(ws)
    token = cleanup.preview_cleanup(CleanupSelector.by_status("failed")).token
    with pytest.raises(CleanupRejected) as exc:
        cleanup.apply_cleanup(token, selector=CleanupSelector.by_status("failed", "cancelled"))
    assert exc.value.reason == "selector"
    assert ws.run_ids() == {run_id}


def test_matching_selector_is_accepted(ws: Workspace) -> None:
    ws.run("failed")
    cleanup = _cleanup(ws)
    token = cleanup.preview_cleanup(CleanupSelector.by_status("failed")).token
    result = cleanup.apply_cleanup(token, selector=CleanupSelector.by_status("failed"))
    assert result.runs_removed == 1


def test_new_matching_run_makes_the_preview_stale(ws: Workspace) -> None:
    first = ws.run("failed")
    cleanup = _cleanup(ws)
    token = cleanup.preview_cleanup(CleanupSelector.by_status("failed")).token
    second = ws.run("failed")
    with pytest.raises(CleanupRejected) as exc:
        cleanup.apply_cleanup(token)
    assert exc.value.reason == "stale"
    assert ws.run_ids() == {first, second}


def test_changed_artefact_makes_the_preview_stale(ws: Workspace) -> None:
    run_id = ws.run("failed")
    cleanup = _cleanup(ws)
    token = cleanup.preview_cleanup(CleanupSelector.by_status("failed")).token
    ws.store.write_json(run_id, "late", {"rows": list(range(50))})
    with pytest.raises(CleanupRejected) as exc:
        cleanup.apply_cleanup(token)
    assert exc.value.reason == "stale"
    assert (ws.layout.artefacts / run_id / "late.json").is_file()


def test_new_retry_of_a_previewed_run_makes_the_preview_stale(ws: Workspace) -> None:
    first = ws.run("failed")
    cleanup = _cleanup(ws)
    token = cleanup.preview_cleanup(CleanupSelector.run(first)).token
    ws.run("queued", artefacts=0, source_run_id=first)
    with pytest.raises(CleanupRejected) as exc:
        cleanup.apply_cleanup(token)
    assert exc.value.reason == "stale"
    assert first in ws.run_ids()


def test_older_than_cutoff_is_fixed_at_preview(ws: Workspace) -> None:
    ws.run("succeeded")
    ws.clock.advance(days=3)
    cleanup = _cleanup(ws, ttl_seconds=10 * 86400)
    preview = cleanup.preview_cleanup(CleanupSelector.older_than(2))
    ws.clock.advance(days=2)
    result = cleanup.apply_cleanup(preview.token)
    assert result.runs_removed == len(preview.runs) == 1


def test_pending_previews_are_bounded(ws: Workspace) -> None:
    ws.run("failed")
    cleanup = _cleanup(ws)
    first = cleanup.preview_cleanup(CleanupSelector.by_status("failed")).token
    for _ in range(cleanup.max_pending):
        cleanup.preview_cleanup(CleanupSelector.by_status("failed"))
    with pytest.raises(CleanupRejected):
        cleanup.apply_cleanup(first)


def test_empty_cleanup_applies_without_change(ws: Workspace) -> None:
    kept = ws.run("succeeded")
    cleanup = _cleanup(ws)
    preview = cleanup.preview_cleanup(CleanupSelector.by_status("failed"))
    assert preview.totals == {"runs": 0, "events": 0, "files": 0, "bytes": 0}
    result = cleanup.apply_cleanup(preview.token)
    assert result.runs_removed == 0
    assert ws.run_ids() == {kept}


# --- repository deletion ---------------------------------------------------------------


def test_repository_protocol_includes_delete_runs(ws: Workspace) -> None:
    assert isinstance(ws.repo, WorkspaceRepository)
    assert hasattr(WorkspaceRepository, "delete_runs")


def test_delete_runs_removes_runs_and_events_together(ws: Workspace) -> None:
    run_id = ws.run("succeeded", events=2)
    kept = ws.run("failed")
    events = ws.repo.get_run(run_id)["last_sequence"]
    assert ws.repo.delete_runs([run_id]) == {"runs": 1, "events": events}
    assert ws.run_ids() == {kept}


def test_delete_runs_refuses_active_runs_without_change(ws: Workspace) -> None:
    done = ws.run("succeeded")
    active = ws.run("running")
    with pytest.raises(ValueError, match="active"):
        ws.repo.delete_runs([done, active])
    assert ws.run_ids() == {done, active}


def test_delete_runs_refuses_unknown_runs_without_change(ws: Workspace) -> None:
    done = ws.run("succeeded")
    with pytest.raises(KeyError):
        ws.repo.delete_runs([done, "missing"])
    assert ws.run_ids() == {done}


def test_delete_runs_refuses_a_run_a_kept_run_refers_to(ws: Workspace) -> None:
    first = ws.run("failed")
    retry = ws.run("succeeded", source_run_id=first)
    with pytest.raises(ValueError, match=retry):
        ws.repo.delete_runs([first])
    assert ws.repo.delete_runs([retry, first])["runs"] == 2


def test_delete_runs_with_no_ids_is_a_no_op(ws: Workspace) -> None:
    ws.run("succeeded")
    assert ws.repo.delete_runs([]) == {"runs": 0, "events": 0}
