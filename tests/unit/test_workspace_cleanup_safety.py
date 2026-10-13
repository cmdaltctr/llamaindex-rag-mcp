"""Cleanup never touches data outside app records and run artefacts (task 5.5).

Source files, vector store directories, notebooks, experiment outputs,
uploads and environment files survive a confirmed cleanup, whether they
sit inside the workspace directory or next to it. Symbolic links in the
artefact tree are reported and never followed.
"""

from __future__ import annotations

import os
from collections.abc import Collection
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_workspace_cleanup_support import Workspace

from omrg.core.workspace import CleanupSelector, WorkspaceCleanup

# Files that cleanup must never change, relative to a base directory.
_PROTECTED = {
    "sources/report.md": b"# Source document\n",
    "sources/paper.pdf": b"%PDF-1.4 fake\n",
    "lancedb/docs.lance/data/part-0.lance": b"vector bytes",
    "lancedb/docs.lance/_versions/1.manifest": b"manifest",
    "chroma/chroma.sqlite3": b"chroma records",
    "notebooks/explore.py": b"import marimo\napp = marimo.App()\n",
    "notebooks/analysis.ipynb": b'{"cells": []}',
    "experiments/42-demo/output/results.json": b'{"score": 1}',
    "experiments/42-demo/output/per_query.jsonl": b"{}\n",
    ".env": b"OPENAI_API_KEY=not-a-real-key\n",
}
_INSIDE_EXTRA = {
    "uploads/u1/upload.md": b"uploaded source",
    "artefacts/notes/readme.md": b"not a run directory",
}


def _plant(base: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _snapshot(base: Path, files: Collection[str]) -> dict[str, bytes]:
    return {rel: (base / rel).read_bytes() for rel in files}


@pytest.fixture
def setup(tmp_path: Path) -> tuple[Workspace, Path]:
    """Return a workspace with protected files inside it and next to it."""
    ws = Workspace(tmp_path / "workspace")
    _plant(ws.layout.root, {**_PROTECTED, **_INSIDE_EXTRA})
    _plant(tmp_path / "outside", _PROTECTED)
    return ws, tmp_path / "outside"


def _apply_all(ws: Workspace, cleanup: WorkspaceCleanup | None = None) -> Any:
    cleanup = cleanup or WorkspaceCleanup.for_layout(ws.repo, ws.layout, clock=ws.clock)
    preview = cleanup.preview_cleanup(CleanupSelector.older_than(0))
    return preview, cleanup.apply_cleanup(preview.token)


def test_protected_files_inside_and_next_to_workspace_survive(
    setup: tuple[Workspace, Path],
) -> None:
    ws, outside = setup
    for status in ("succeeded", "failed", "cancelled", "interrupted"):
        ws.run(status, events=2, artefacts=2)
    inside_before = _snapshot(ws.layout.root, {**_PROTECTED, **_INSIDE_EXTRA})
    outside_before = _snapshot(outside, _PROTECTED)
    preview, result = _apply_all(ws)
    assert result.runs_removed == 4
    assert result.files_removed == preview.totals["files"] == 8
    assert ws.run_ids() == set()
    assert _snapshot(ws.layout.root, {**_PROTECTED, **_INSIDE_EXTRA}) == inside_before
    assert _snapshot(outside, _PROTECTED) == outside_before
    assert ws.layout.records.is_file()


def test_symlinked_files_in_a_run_directory_are_not_followed(
    setup: tuple[Workspace, Path],
) -> None:
    ws, outside = setup
    run_id = ws.run("failed", artefacts=1)
    run_dir = ws.layout.artefacts / run_id
    (run_dir / "notebook.json").symlink_to(outside / "notebooks/analysis.ipynb")
    (run_dir / "vectors").symlink_to(outside / "lancedb", target_is_directory=True)
    before = _snapshot(outside, _PROTECTED)
    preview, result = _apply_all(ws)
    listed = [file.ref for run in preview.runs for file in run.files]
    assert listed == [f"{run_id}/part-0.json"]
    skipped = {skip.item: skip.reason for skip in preview.skipped}
    assert "symbolic link" in skipped[f"{run_id}/notebook.json"]
    assert "symbolic link" in skipped[f"{run_id}/vectors"]
    assert result.files_removed == 1
    assert (run_dir / "notebook.json").is_symlink()
    assert (run_dir / "vectors").is_symlink()
    assert _snapshot(outside, _PROTECTED) == before


def test_symlinked_run_directory_is_not_followed(setup: tuple[Workspace, Path]) -> None:
    ws, outside = setup
    run_id = ws.run("succeeded", artefacts=0)
    target = outside / "experiments/42-demo/output"
    (ws.layout.artefacts).mkdir(exist_ok=True)
    (ws.layout.artefacts / run_id).symlink_to(target, target_is_directory=True)
    before = _snapshot(outside, _PROTECTED)
    preview, result = _apply_all(ws)
    assert preview.runs[0].files == ()
    assert "symbolic link" in {s.item: s.reason for s in preview.skipped}[run_id]
    assert result.runs_removed == 1
    assert result.files_removed == 0
    assert (ws.layout.artefacts / run_id).is_symlink()
    assert _snapshot(outside, _PROTECTED) == before


def test_symlinked_artefact_root_is_not_followed(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    run_id = ws.run("succeeded", artefacts=0)
    elsewhere = tmp_path / "elsewhere"
    _plant(elsewhere, {f"{run_id}/result.json": b"{}", "notebook.py": b"x = 1\n"})
    ws.layout.artefacts.symlink_to(elsewhere, target_is_directory=True)
    preview, result = _apply_all(ws)
    assert preview.runs[0].files == ()
    assert "symbolic link" in {s.item: s.reason for s in preview.skipped}["artefacts"]
    assert result.runs_removed == 1
    assert (elsewhere / run_id / "result.json").read_bytes() == b"{}"
    assert (elsewhere / "notebook.py").read_bytes() == b"x = 1\n"


def test_unexpected_directory_in_run_directory_is_left(setup: tuple[Workspace, Path]) -> None:
    ws, _ = setup
    run_id = ws.run("failed", artefacts=1)
    nested = ws.layout.artefacts / run_id / "nested"
    _plant(nested, {"keep.txt": b"keep"})
    preview, result = _apply_all(ws)
    assert "not a regular file" in {s.item: s.reason for s in preview.skipped}[f"{run_id}/nested"]
    assert result.files_removed == 1
    assert (nested / "keep.txt").read_bytes() == b"keep"


def test_run_directory_swapped_for_a_link_after_the_check_is_not_followed(
    setup: tuple[Workspace, Path],
) -> None:
    ws, outside = setup
    run_id = ws.run("failed", artefacts=1)
    decoy = outside / "decoy"
    _plant(decoy, {"part-0.json": b"decoy data"})

    class SwapOnDelete:
        """Repository proxy that swaps the run directory during deletion."""

        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

        def delete_runs(self, run_ids: Collection[str]) -> dict[str, int]:
            counts = self._inner.delete_runs(run_ids)
            run_dir = ws.layout.artefacts / run_id
            os.rename(run_dir, ws.layout.root / "moved-away")
            run_dir.symlink_to(decoy, target_is_directory=True)
            return counts

    cleanup = WorkspaceCleanup.for_layout(SwapOnDelete(ws.repo), ws.layout, clock=ws.clock)  # type: ignore[arg-type]
    _, result = _apply_all(ws, cleanup)
    assert result.files_removed == 0
    assert [f.item for f in result.failed] == [f"{run_id}/part-0.json"]
    assert (decoy / "part-0.json").read_bytes() == b"decoy data"


def test_files_are_removed_only_after_records(setup: tuple[Workspace, Path]) -> None:
    ws, _ = setup
    run_id = ws.run("failed", artefacts=1)
    seen: list[bool] = []

    class Observe:
        """Repository proxy that records whether artefacts exist at deletion."""

        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

        def delete_runs(self, run_ids: Collection[str]) -> dict[str, int]:
            seen.append((ws.layout.artefacts / run_id / "part-0.json").exists())
            return self._inner.delete_runs(run_ids)

    cleanup = WorkspaceCleanup.for_layout(Observe(ws.repo), ws.layout, clock=ws.clock)  # type: ignore[arg-type]
    _apply_all(ws, cleanup)
    assert seen == [True]
    assert not (ws.layout.artefacts / run_id).exists()


def test_failed_record_deletion_removes_no_files(setup: tuple[Workspace, Path]) -> None:
    ws, _ = setup
    run_id = ws.run("failed", artefacts=1)

    class Refuse:
        """Repository proxy whose deletion fails."""

        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

        def delete_runs(self, run_ids: Collection[str]) -> dict[str, int]:
            raise ValueError("run is active")

    cleanup = WorkspaceCleanup.for_layout(Refuse(ws.repo), ws.layout, clock=ws.clock)  # type: ignore[arg-type]
    from omrg.core.workspace import CleanupRejected

    with pytest.raises(CleanupRejected) as exc:
        _apply_all(ws, cleanup)
    assert exc.value.reason == "stale"
    assert (ws.layout.artefacts / run_id / "part-0.json").is_file()
    assert run_id in ws.run_ids()


def test_artefact_files_and_directories_keep_private_modes(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    kept = ws.run("succeeded", artefacts=1)
    ws.run("failed", artefacts=1)
    cleanup = WorkspaceCleanup.for_layout(ws.repo, ws.layout, clock=ws.clock)
    cleanup.apply_cleanup(cleanup.preview_cleanup(CleanupSelector.by_status("failed")).token)
    assert (ws.layout.artefacts / kept).stat().st_mode & 0o777 == 0o700
    assert (ws.layout.artefacts / kept / "part-0.json").stat().st_mode & 0o777 == 0o600
    assert ws.layout.records.stat().st_mode & 0o777 == 0o600


def test_experiment_run_outputs_survive_cleanup_of_their_record(tmp_path: Path) -> None:
    """A run whose artefacts sit below an experiment workspace keeps them."""
    from omrg.core.workspace import ARTEFACT_ROOT_KEY, ArtefactStore

    ws = Workspace(tmp_path / "workspace")
    outputs = tmp_path / "experiments" / "exp-a" / "output" / "omrg-runs"
    run = ws.repo.create_run(
        ws.revision_id,
        settings={},
        resources={ARTEFACT_ROOT_KEY: str(outputs)},
        inputs={},
        origin="submit",
        source_run_id=None,
    )
    run_id = run["run_id"]
    ws.repo.record_update(run_id, kind="run.status", summary={}, status="running")
    ref = ArtefactStore(outputs).write_json(run_id, "result", {"rows": [1]})
    ws.repo.record_update(run_id, kind="run.status", summary={}, status="succeeded")
    before = (outputs / ref).read_bytes()

    preview, result = _apply_all(ws)

    assert [item.run_id for item in preview.runs] == [run_id]
    assert preview.runs[0].files == ()
    assert result.runs_removed == 1 and result.files_removed == 0
    assert ws.run_ids() == set()
    assert (outputs / ref).read_bytes() == before
