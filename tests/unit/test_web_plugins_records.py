"""Plugin registration records: detail at registration and unregistration (task 8.6).

The plugin routes need to remove a registration, and registration can
store the approved executable identity in one write. Both are additive
repository methods; the existing round trip stays unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrg.core.workspace import WorkspaceRepository
from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository


@pytest.fixture
def repo(tmp_path: Path) -> SqliteWorkspaceRepository:
    return SqliteWorkspaceRepository(tmp_path / "ws.sqlite3")


def test_register_plugin_keeps_given_detail(repo: SqliteWorkspaceRepository) -> None:
    created = repo.register_plugin(
        "marimo",
        manifest_ref="/m.json",
        executable_ref="/bin/marimo",
        manifest_hash="abc",
        detail={"approved": True, "message": "registered"},
    )
    assert created["detail"] == {"approved": True, "message": "registered"}
    assert created["compatibility_status"] == "unchecked"
    assert created["checked_at"] is None


def test_register_plugin_without_detail_still_resets_it(repo: SqliteWorkspaceRepository) -> None:
    repo.register_plugin("marimo", manifest_ref="/m.json", executable_ref="/bin/marimo")
    repo.set_plugin_compatibility("marimo", "compatible", detail={"version": "1"})
    again = repo.register_plugin("marimo", manifest_ref="/m.json", executable_ref="/bin/marimo")
    assert again["detail"] == {}
    assert again["compatibility_status"] == "unchecked"


def test_unregister_plugin_removes_only_that_record(repo: SqliteWorkspaceRepository) -> None:
    repo.register_plugin("marimo", manifest_ref="/m.json", executable_ref="/bin/marimo")
    repo.register_plugin("other", manifest_ref="/o.json", executable_ref="/bin/other")
    removed = repo.unregister_plugin("marimo")
    assert removed["name"] == "marimo"
    assert [record["name"] for record in repo.list_plugins()] == ["other"]
    with pytest.raises(KeyError):
        repo.get_plugin("marimo")
    with pytest.raises(KeyError):
        repo.unregister_plugin("marimo")


def test_protocol_declares_the_new_methods(repo: SqliteWorkspaceRepository) -> None:
    assert isinstance(repo, WorkspaceRepository)
    assert hasattr(WorkspaceRepository, "unregister_plugin")
