"""Shared helpers for the workspace cleanup tests (task 5.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from omrg.core.workspace import ArtefactStore, WorkspaceLayout
from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository

GRAPH: dict[str, Any] = {"version": 1, "nodes": [{"id": "a", "op": "read"}], "edges": []}
START = datetime(2026, 1, 1, tzinfo=UTC)


class Clock:
    """A settable clock shared by the repository and the cleanup service."""

    def __init__(self, now: datetime = START) -> None:
        """Start at *now*."""
        self.now = now

    def __call__(self) -> datetime:
        """Return the current fake time."""
        return self.now

    def advance(self, **delta: float) -> None:
        """Move the clock forward by a ``timedelta`` keyword amount."""
        self.now += timedelta(**delta)


class Workspace:
    """A temporary workspace with records, artefacts and a fake clock."""

    def __init__(self, root: Path) -> None:
        """Create the workspace layout and an empty repository under *root*."""
        self.clock = Clock()
        self.layout = WorkspaceLayout(root)
        self.repo = SqliteWorkspaceRepository(self.layout.records, clock=self.clock)
        self.store = ArtefactStore(self.layout.artefacts)
        pipeline = self.repo.create_pipeline("Demo")
        self.pipeline_id = pipeline["pipeline_id"]
        revision = self.repo.save_revision(self.pipeline_id, GRAPH, schema_version=1)
        self.revision_id = revision["revision_id"]

    def run(
        self,
        status: str = "succeeded",
        *,
        events: int = 0,
        artefacts: int = 1,
        source_run_id: str | None = None,
    ) -> str:
        """Create a run, add events and artefacts, then move it to *status*.

        Returns:
            The new run identifier.
        """
        origin = "submit" if source_run_id is None else "retry"
        run = self.repo.create_run(
            self.revision_id,
            settings={},
            resources={},
            inputs={"query": "q"},
            origin=origin,
            source_run_id=source_run_id,
        )
        run_id = run["run_id"]
        if status != "queued":
            self.repo.record_update(run_id, kind="run.status", summary={}, status="running")
        for index in range(events):
            self.repo.record_update(run_id, kind="node.finished", summary={"n": index})
        for index in range(artefacts):
            self.store.write_json(run_id, f"part-{index}", {"rows": [index]})
        if status not in {"queued", "running"}:
            self.repo.record_update(run_id, kind="run.status", summary={}, status=status)
        return run_id

    def run_ids(self) -> set[str]:
        """Return every stored run identifier."""
        return {run["run_id"] for run in self.repo.list_runs()}
