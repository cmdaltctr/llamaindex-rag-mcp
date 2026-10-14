"""Workspace SQLite schema migrations, backups and permissions (task 5.1)."""

from __future__ import annotations

import os
import sqlite3
import stat
import sys
from pathlib import Path

import pytest

from omrg.integrations.workspace_sqlite import (
    SCHEMA_MIGRATIONS,
    SqliteWorkspaceRepository,
    WorkspaceSchemaError,
)

_POSIX = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")

# The shipped schema version; tests add one more migration on top of it.
_LATEST = SCHEMA_MIGRATIONS[-1][0]
_NEXT = _LATEST + 1


def _user_version(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def _columns(path: Path, table: str) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    finally:
        conn.close()


def _seed(path: Path) -> str:
    repo = SqliteWorkspaceRepository(path)
    return repo.create_pipeline("Seeded")["pipeline_id"]


def test_fresh_database_gets_latest_schema_without_backup(tmp_path: Path) -> None:
    path = tmp_path / "ws" / "app.sqlite3"
    SqliteWorkspaceRepository(path)
    assert _user_version(path) == SCHEMA_MIGRATIONS[-1][0]
    assert sorted(p.name for p in path.parent.iterdir()) == ["app.sqlite3"]


def test_reopening_current_schema_is_a_no_op(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    pipeline_id = _seed(path)
    repo = SqliteWorkspaceRepository(path)
    assert repo.get_pipeline(pipeline_id)["title"] == "Seeded"
    assert list(tmp_path.glob("*.bak")) == []


def test_upgrade_backs_up_previous_records_before_mutation(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    pipeline_id = _seed(path)
    upgrade = (_NEXT, ("ALTER TABLE pipelines ADD COLUMN description TEXT",))
    repo = SqliteWorkspaceRepository(path, migrations=(*SCHEMA_MIGRATIONS, upgrade))
    assert _user_version(path) == _NEXT
    assert "description" in _columns(path, "pipelines")
    assert repo.get_pipeline(pipeline_id)["title"] == "Seeded"
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == 1
    assert f"v{_LATEST}-to-v{_NEXT}" in backups[0].name
    assert _user_version(backups[0]) == _LATEST
    assert "description" not in _columns(backups[0], "pipelines")


def test_failed_migration_rolls_back_and_keeps_original_intact(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    pipeline_id = _seed(path)
    broken = (
        _NEXT,
        (
            "ALTER TABLE pipelines ADD COLUMN description TEXT",
            "UPDATE pipelines SET title = 'mutated'",
            "INSERT INTO no_such_table VALUES (1)",
        ),
    )
    with pytest.raises(WorkspaceSchemaError, match="rolled back") as excinfo:
        SqliteWorkspaceRepository(path, migrations=(*SCHEMA_MIGRATIONS, broken))
    assert "backup" in str(excinfo.value)
    assert _user_version(path) == _LATEST
    assert "description" not in _columns(path, "pipelines")
    repo = SqliteWorkspaceRepository(path)
    assert repo.get_pipeline(pipeline_id)["title"] == "Seeded"
    assert len(list(tmp_path.glob("*.bak"))) == 1


def test_newer_schema_is_refused_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    _seed(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    with pytest.raises(WorkspaceSchemaError, match="newer"):
        SqliteWorkspaceRepository(path)
    assert _user_version(path) == 99
    assert list(tmp_path.glob("*.bak")) == []


def test_foreign_database_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "other.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE vectors (id INTEGER)")
    conn.close()
    with pytest.raises(WorkspaceSchemaError, match="not an OMRG workspace"):
        SqliteWorkspaceRepository(path)
    assert _columns(path, "vectors") == ["id"]
    assert _user_version(path) == 0


def test_migrations_must_be_ordered_from_one() -> None:
    with pytest.raises(ValueError):
        SqliteWorkspaceRepository(Path("unused.sqlite3"), migrations=((2, ()),))


@_POSIX
def test_new_workspace_directory_and_files_are_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "ws" / "nested" / "app.sqlite3"
    _seed(path)
    upgrade = (_NEXT, ("ALTER TABLE pipelines ADD COLUMN description TEXT",))
    SqliteWorkspaceRepository(path, migrations=(*SCHEMA_MIGRATIONS, upgrade))
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    (backup,) = list(path.parent.glob("*.bak"))
    assert stat.S_IMODE(os.stat(backup).st_mode) == 0o600


@_POSIX
def test_existing_database_permissions_are_tightened(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    _seed(path)
    path.chmod(0o644)
    SqliteWorkspaceRepository(path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
