"""Migration 5: chat tables in the workspace database (add-chat-history task 1.1)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from omrs.integrations.workspace_sqlite import SCHEMA_MIGRATIONS, SqliteWorkspaceRepository
from omrs.integrations.workspace_sqlite.schema import connect

_V4 = SCHEMA_MIGRATIONS[:4]


def _names(path: Path, kind: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = ?", (kind,))
        return {row[0] for row in rows}
    finally:
        conn.close()


def test_migration_five_exists() -> None:
    assert SCHEMA_MIGRATIONS[-1][0] >= 5


def test_v4_file_with_profiles_migrates_with_backup(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    repo = SqliteWorkspaceRepository(path, migrations=_V4)
    pipeline_id = repo.create_pipeline("Kept")["pipeline_id"]
    assert "chats" not in _names(path, "table")

    upgraded = SqliteWorkspaceRepository(path)

    assert upgraded.get_pipeline(pipeline_id)["title"] == "Kept"
    assert {"chat_folders", "chats", "chat_turns"} <= _names(path, "table")
    assert {"chats_by_folder", "chats_by_updated"} <= _names(path, "index")
    backups = list(tmp_path.glob(f"*.v4-to-v{SCHEMA_MIGRATIONS[-1][0]}.*.bak"))
    assert len(backups) == 1


def _seed_chat(path: Path) -> None:
    conn = connect(path)
    try:
        conn.execute(
            "INSERT INTO chat_folders (folder_id, name, created_at) VALUES ('f1', 'Work', 't')"
        )
        conn.execute("INSERT INTO chats VALUES ('c1', 'f1', 'Title', 't', 't')")
        conn.execute("INSERT INTO chat_turns VALUES ('c1', 1, 'docs', 'q', '{}', 't')")
    finally:
        conn.close()


def _count(path: Path, table: str) -> int:
    conn = connect(path)
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608
    finally:
        conn.close()


def test_folder_delete_cascades_to_chats_and_turns(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    SqliteWorkspaceRepository(path)
    _seed_chat(path)
    conn = connect(path)
    try:
        conn.execute("DELETE FROM chat_folders WHERE folder_id = 'f1'")
    finally:
        conn.close()
    assert _count(path, "chats") == 0
    assert _count(path, "chat_turns") == 0


def test_cascade_is_what_removes_the_rows(tmp_path: Path) -> None:
    """Without ON DELETE CASCADE the folder delete is refused by the foreign key."""
    path = tmp_path / "app.sqlite3"
    SqliteWorkspaceRepository(path)
    _seed_chat(path)
    conn = connect(path)
    try:
        conn.execute("DELETE FROM chats WHERE chat_id = 'c1'")
        assert _count(path, "chat_turns") == 0
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO chat_turns VALUES ('missing', 1, 'd', 'q', '{}', 't')")
    finally:
        conn.close()


def test_migration_six_numbers_existing_folders_in_creation_order(tmp_path: Path) -> None:
    path = tmp_path / "app.sqlite3"
    SqliteWorkspaceRepository(path, migrations=SCHEMA_MIGRATIONS[:5])
    conn = sqlite3.connect(path)
    try:
        conn.executemany(
            "INSERT INTO chat_folders VALUES (?, ?, ?)",
            [("b", "Second", "2026-01-02"), ("a", "First", "2026-01-01")],
        )
        conn.commit()
    finally:
        conn.close()

    SqliteWorkspaceRepository(path)
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT folder_id, position FROM chat_folders ORDER BY position")
        assert [tuple(row) for row in rows] == [("a", 1), ("b", 2)]
    finally:
        conn.close()
