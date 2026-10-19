"""The workspace catalogue for processes that only read the workspace (D11, tasks 8.1-8.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from omrg import compose
from omrg.compose_profile_setup import workspace_profile_catalogue
from omrg.integrations.workspace_sqlite import (
    SqliteProfileCatalogue,
    SqliteProfileRepository,
    SqliteWorkspaceRepository,
)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _make_workspace(root: Path) -> Path:
    records = root / "workspace.db"
    SqliteWorkspaceRepository(records)
    SqliteProfileRepository(records).create_profile(
        "My notes",
        base_profile="documents",
        slots={"ingest": {"nodes": []}, "search": None, "answer": None},
        schema_version=1,
    )
    return records


def test_returns_a_read_only_catalogue_when_the_default_workspace_exists(home: Path) -> None:
    records = _make_workspace(home / ".omrg" / "workspace")
    catalogue = workspace_profile_catalogue()
    assert isinstance(catalogue, SqliteProfileCatalogue)
    assert catalogue.path == records
    assert catalogue.get_profile("my-notes")["base_profile"] == "documents"
    with catalogue.connection() as conn, pytest.raises(Exception, match="readonly"):
        conn.execute("DELETE FROM profiles")


def test_returns_none_when_the_default_workspace_file_is_missing(home: Path) -> None:
    assert workspace_profile_catalogue() is None


def test_never_creates_the_folder_or_the_file(home: Path) -> None:
    workspace_profile_catalogue()
    assert not (home / ".omrg").exists()


def test_a_folder_without_the_file_gives_none_and_stays_empty(home: Path) -> None:
    folder = home / ".omrg" / "workspace"
    folder.mkdir(parents=True)
    assert workspace_profile_catalogue() is None
    assert list(folder.iterdir()) == []


def test_an_explicit_root_overrides_the_default(home: Path, tmp_path: Path) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    _make_workspace(other)
    catalogue = workspace_profile_catalogue(other)
    assert catalogue is not None and catalogue.get_profile("my-notes") is not None
    assert workspace_profile_catalogue() is None


def test_ensure_runtime_setup_passes_the_catalogue_and_runtime_engine_returns_the_engine(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_workspace(home / ".omrg" / "workspace")
    seen: dict[str, object] = {}

    class FakeEngine:
        def _install_as_process_default(self) -> None:
            seen["installed"] = True

    def fake_build(*args: object, **kwargs: object) -> FakeEngine:
        seen["catalogue"] = kwargs.get("catalogue")
        engine = FakeEngine()
        seen["engine"] = engine
        return engine

    monkeypatch.setattr(compose, "build_engine", fake_build)
    compose.reset_runtime_setup()
    try:
        compose.ensure_runtime_setup()
        assert isinstance(seen["catalogue"], SqliteProfileCatalogue)
        assert compose.runtime_engine() is seen["engine"]
    finally:
        compose.reset_runtime_setup()


def test_ensure_runtime_setup_without_a_workspace_passes_no_catalogue(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {"catalogue": "unset"}

    class FakeEngine:
        def _install_as_process_default(self) -> None:
            pass

    def fake_build(*args: object, **kwargs: object) -> FakeEngine:
        seen["catalogue"] = kwargs.get("catalogue", "missing")
        return FakeEngine()

    monkeypatch.setattr(compose, "build_engine", fake_build)
    compose.reset_runtime_setup()
    try:
        compose.ensure_runtime_setup()
        assert seen["catalogue"] is None
    finally:
        compose.reset_runtime_setup()
