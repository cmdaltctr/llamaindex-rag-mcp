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


# --- Schema version 3: the profiles table (unify-profiles-and-pipelines, D1) ---


def _v2_database(path: Path) -> None:
    """Create a version 2 workspace with one pipeline, as an older release left it."""
    repo = SqliteWorkspaceRepository(path, migrations=SCHEMA_MIGRATIONS[:2])
    repo.create_pipeline("Old")


def _raw(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _pipeline_ids(path: Path, count: int) -> list[str]:
    repo = SqliteWorkspaceRepository(path)
    return [repo.create_pipeline(f"Slot {i}")["pipeline_id"] for i in range(count)]


def _insert_profile(
    conn: sqlite3.Connection,
    profile_id: str,
    slots: tuple[str, str, str],
    base: str = "documents",
) -> None:
    conn.execute(
        "INSERT INTO profiles (profile_id, title, base_profile, ingest_pipeline_id, "
        "search_pipeline_id, answer_pipeline_id, created_at, updated_at) "
        "VALUES (?, 'T', ?, ?, ?, ?, 'now', 'now')",
        (profile_id, base, *slots),
    )


def test_version_two_database_migrates_to_profiles_table_with_backup(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    _v2_database(path)
    assert _user_version(path) == 2
    SqliteWorkspaceRepository(path, migrations=SCHEMA_MIGRATIONS[:3])
    assert _user_version(path) == 3
    assert "profile_id" in _columns(path, "profiles")
    (backup,) = list(tmp_path.glob("*.bak"))
    assert "v2-to-v3" in backup.name
    assert _user_version(backup) == 2
    assert _columns(backup, "profiles") == []


@pytest.mark.parametrize("reserved", ["documents", "codebase", "hybrid"])
def test_reserved_profile_ids_are_refused(tmp_path: Path, reserved: str) -> None:
    path = tmp_path / "app.sqlite3"
    slots = _pipeline_ids(path, 3)
    conn = _raw(path)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_profile(conn, reserved, (slots[0], slots[1], slots[2]))
    conn.close()


def test_unknown_base_profile_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    slots = _pipeline_ids(path, 3)
    conn = _raw(path)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_profile(conn, "mine", (slots[0], slots[1], slots[2]), base="hybrid")
    conn.close()


def test_one_pipeline_cannot_fill_two_slots(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    slots = _pipeline_ids(path, 6)
    conn = _raw(path)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_profile(conn, "same-column", (slots[0], slots[1], slots[2]))
        _insert_profile(conn, "other", (slots[0], slots[4], slots[5]))
    with pytest.raises(sqlite3.IntegrityError):
        _insert_profile(conn, "cross-slot", (slots[3], slots[3], slots[4]))
    conn.close()


def test_pipeline_cannot_move_between_slots_of_two_profiles(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    slots = _pipeline_ids(path, 6)
    conn = _raw(path)
    _insert_profile(conn, "first", (slots[0], slots[1], slots[2]))
    with pytest.raises(sqlite3.IntegrityError):
        _insert_profile(conn, "second", (slots[3], slots[4], slots[0]))
    conn.close()


@pytest.mark.parametrize(
    "assignment",
    [
        "profile_id = 'renamed'",
        "base_profile = 'codebase'",
        "ingest_pipeline_id = (SELECT pipeline_id FROM pipelines WHERE title = 'Spare')",
        "search_pipeline_id = (SELECT pipeline_id FROM pipelines WHERE title = 'Spare')",
        "answer_pipeline_id = (SELECT pipeline_id FROM pipelines WHERE title = 'Spare')",
    ],
)
def test_profile_identity_columns_never_change(tmp_path: Path, assignment: str) -> None:
    path = tmp_path / "app.sqlite3"
    slots = _pipeline_ids(path, 3)
    SqliteWorkspaceRepository(path).create_pipeline("Spare")
    conn = _raw(path)
    _insert_profile(conn, "mine", (slots[0], slots[1], slots[2]))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"UPDATE profiles SET {assignment} WHERE profile_id = 'mine'")  # noqa: S608 - fixed literals
    conn.close()


def test_profile_title_description_and_archive_may_change(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    slots = _pipeline_ids(path, 3)
    conn = _raw(path)
    _insert_profile(conn, "mine", (slots[0], slots[1], slots[2]))
    conn.execute(
        "UPDATE profiles SET title = 'New', description = 'd', updated_at = 'later', "
        "archived_at = 'later' WHERE profile_id = 'mine'"
    )
    row = conn.execute("SELECT title, archived_at FROM profiles").fetchone()
    assert row == ("New", "later")
    conn.close()


# --- Schema version 4: the embedding choice of a profile (add-profile-embedding-model, D1) ---


def _v3_database_with_profile(path: Path) -> None:
    """Create a version 3 workspace that holds one profile, as the earlier release left it."""
    repo = SqliteWorkspaceRepository(path, migrations=SCHEMA_MIGRATIONS[:3])
    slots = [repo.create_pipeline(f"Slot {i}")["pipeline_id"] for i in range(3)]
    conn = _raw(path)
    _insert_profile(conn, "old", (slots[0], slots[1], slots[2]))
    conn.close()


def test_version_three_database_gains_the_embedding_columns_with_backup(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    _v3_database_with_profile(path)
    assert _user_version(path) == 3
    SqliteWorkspaceRepository(path)
    assert _user_version(path) == 4
    columns = _columns(path, "profiles")
    assert {"embed_provider", "embed_model", "embed_dimensions"} <= set(columns)
    (backup,) = list(tmp_path.glob("*.bak"))
    assert "v3-to-v4" in backup.name
    assert _user_version(backup) == 3
    assert "embed_model" not in _columns(backup, "profiles")


def test_existing_profiles_read_as_the_server_default(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    _v3_database_with_profile(path)
    SqliteWorkspaceRepository(path)
    conn = _raw(path)
    row = conn.execute(
        "SELECT embed_provider, embed_model, embed_dimensions FROM profiles"
    ).fetchone()
    conn.close()
    assert row == (None, None, None)


@pytest.mark.parametrize(
    "assignment",
    [
        "embed_provider = 'ollama'",
        "embed_model = 'nomic-embed-text'",
        "embed_provider = 'ollama', embed_model = NULL",
    ],
)
def test_a_provider_without_a_model_is_refused(tmp_path: Path, assignment: str) -> None:
    path = tmp_path / "app.sqlite3"
    slots = _pipeline_ids(path, 3)
    conn = _raw(path)
    _insert_profile(conn, "mine", (slots[0], slots[1], slots[2]))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"UPDATE profiles SET {assignment} WHERE profile_id = 'mine'")  # noqa: S608 - fixed literals
    conn.close()


def test_a_provider_with_a_model_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    slots = _pipeline_ids(path, 3)
    conn = _raw(path)
    _insert_profile(conn, "mine", (slots[0], slots[1], slots[2]))
    conn.execute(
        "UPDATE profiles SET embed_provider = 'ollama', embed_model = 'nomic-embed-text', "
        "embed_dimensions = 768 WHERE profile_id = 'mine'"
    )
    row = conn.execute("SELECT embed_provider, embed_model, embed_dimensions FROM profiles")
    assert row.fetchone() == ("ollama", "nomic-embed-text", 768)
    conn.close()
