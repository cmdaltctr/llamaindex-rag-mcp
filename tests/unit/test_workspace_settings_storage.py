"""Workspace settings and MCP token storage (design D4, D6; tasks 2.1 to 2.3)."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from omrg.integrations.workspace_sqlite import SCHEMA_MIGRATIONS, SqliteWorkspaceRepository
from omrg.integrations.workspace_sqlite.settings import (
    UnknownSettingError,
    WorkspaceSettings,
    read_saved_web_port,
)
from omrg.integrations.workspace_sqlite.tokens import MCP_TOKEN_PREFIX, McpTokenStore


def _tables(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def _columns(path: Path, table: str) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    finally:
        conn.close()


def _user_version(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "ws" / "workspace.db"
    SqliteWorkspaceRepository(path)
    return path


# ── 2.1 Migration ────────────────────────────────────────────────────────


def test_migration_two_creates_the_two_tables_with_the_design_columns(db: Path) -> None:
    assert SCHEMA_MIGRATIONS[1][0] == 2
    assert _user_version(db) == 2
    assert _columns(db, "workspace_settings") == ["key", "value"]
    assert _columns(db, "mcp_tokens") == ["token_id", "token_hash", "created_at"]


def test_upgrade_from_version_one_only_adds_tables_and_keeps_records(tmp_path: Path) -> None:
    path = tmp_path / "workspace.db"
    old = SqliteWorkspaceRepository(path, migrations=SCHEMA_MIGRATIONS[:1])
    pipeline_id = old.create_pipeline("Kept")["pipeline_id"]
    before = _tables(path)
    columns_before = {name: _columns(path, name) for name in before}

    upgraded = SqliteWorkspaceRepository(path)

    assert _user_version(path) == 2
    assert _tables(path) - before == {"workspace_settings", "mcp_tokens"}
    assert before <= _tables(path)
    for name, columns in columns_before.items():
        assert _columns(path, name) == columns, name
    assert upgraded.get_pipeline(pipeline_id)["title"] == "Kept"
    assert len(list(tmp_path.glob("*.v1-to-v2.*.bak"))) == 1


# ── 2.2 Settings repository ──────────────────────────────────────────────


def test_settings_default_to_off_and_unset(db: Path) -> None:
    settings = WorkspaceSettings(db)
    assert settings.get_mcp_http_enabled() is False
    assert settings.get_web_port() is None


def test_settings_round_trip_and_survive_a_new_instance(db: Path) -> None:
    settings = WorkspaceSettings(db)
    settings.set_mcp_http_enabled(True)
    settings.set_web_port(9100)

    again = WorkspaceSettings(db)
    assert again.get_mcp_http_enabled() is True
    assert again.get_web_port() == 9100

    again.set_mcp_http_enabled(False)
    again.set_web_port(None)
    assert again.get_mcp_http_enabled() is False
    assert again.get_web_port() is None


def test_unknown_keys_are_refused(db: Path) -> None:
    settings = WorkspaceSettings(db)
    with pytest.raises(UnknownSettingError):
        settings.get("not_a_setting")
    with pytest.raises(UnknownSettingError):
        settings.set("not_a_setting", "x")
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM workspace_settings").fetchone()[0] == 0
    conn.close()


@pytest.mark.parametrize("stored", ["maybe", "", "2", "TRUE "])
def test_invalid_stored_flag_reads_as_unset(db: Path, stored: str) -> None:
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO workspace_settings VALUES ('mcp_http_enabled', ?)", (stored,))
    conn.commit()
    conn.close()
    assert WorkspaceSettings(db).get_mcp_http_enabled() is False


@pytest.mark.parametrize("stored", ["abc", "", "80", "1023", "65536", "-5", "8765.5"])
def test_invalid_stored_port_reads_as_unset(db: Path, stored: str) -> None:
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO workspace_settings VALUES ('web_port', ?)", (stored,))
    conn.commit()
    conn.close()
    assert WorkspaceSettings(db).get_web_port() is None
    assert read_saved_web_port(db) is None


@pytest.mark.parametrize("port", [0, 80, 1023, 65536, -1])
def test_setting_an_out_of_range_port_is_refused(db: Path, port: int) -> None:
    with pytest.raises(ValueError):
        WorkspaceSettings(db).set_web_port(port)
    assert WorkspaceSettings(db).get_web_port() is None


def test_read_saved_web_port_tolerates_a_missing_or_old_database(tmp_path: Path) -> None:
    assert read_saved_web_port(tmp_path / "absent.db") is None
    old = tmp_path / "old.db"
    SqliteWorkspaceRepository(old, migrations=SCHEMA_MIGRATIONS[:1])
    assert read_saved_web_port(old) is None


def test_read_saved_web_port_returns_the_saved_value(db: Path) -> None:
    WorkspaceSettings(db).set_web_port(9100)
    assert read_saved_web_port(db) == 9100


# ── Upload limit (add-run-output-inspection-and-upload-limit 3.1) ─────────


def test_upload_limit_round_trips_and_none_clears_it(db: Path) -> None:
    settings = WorkspaceSettings(db)
    assert settings.get_upload_limit_mib() is None
    settings.set_upload_limit_mib(200)
    assert WorkspaceSettings(db).get_upload_limit_mib() == 200
    for edge in (1, 2048):
        settings.set_upload_limit_mib(edge)
        assert settings.get_upload_limit_mib() == edge
    settings.set_upload_limit_mib(None)
    assert settings.get_upload_limit_mib() is None


@pytest.mark.parametrize("stored", ["0", "2049", "big", "", "-5", "1.5", " 10"])
def test_invalid_stored_upload_limit_reads_as_unset(db: Path, stored: str) -> None:
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO workspace_settings VALUES ('upload_limit_mib', ?)", (stored,))
    conn.commit()
    conn.close()
    assert WorkspaceSettings(db).get_upload_limit_mib() is None


@pytest.mark.parametrize("mib", [0, 2049, -1])
def test_setting_an_out_of_range_upload_limit_is_refused(db: Path, mib: int) -> None:
    with pytest.raises(ValueError):
        WorkspaceSettings(db).set_upload_limit_mib(mib)
    assert WorkspaceSettings(db).get_upload_limit_mib() is None


# ── 2.3 Token repository ─────────────────────────────────────────────────


def test_create_returns_a_prefixed_token_and_stores_only_its_hash(db: Path) -> None:
    store = McpTokenStore(db)
    created = store.create()

    assert created.token.startswith(MCP_TOKEN_PREFIX)
    assert MCP_TOKEN_PREFIX == "omrg_mcp_"  # noqa: S105
    assert len(created.token) >= len(MCP_TOKEN_PREFIX) + 43  # token_urlsafe(32)
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT * FROM mcp_tokens").fetchall()
    conn.close()
    assert len(rows) == 1
    assert created.token not in "".join(str(value) for value in rows[0])
    assert rows[0][1] == hashlib.sha256(created.token.encode()).hexdigest()
    assert db.read_bytes().find(created.token.encode()) == -1


def test_verify_accepts_the_token_and_refuses_everything_else(db: Path) -> None:
    store = McpTokenStore(db)
    created = store.create()
    assert store.verify(created.token) is True
    assert store.verify(created.token + "x") is False
    assert store.verify("") is False
    assert store.verify("omrg_mcp_wrong") is False


def test_rotation_replaces_the_row_and_invalidates_the_old_token(db: Path) -> None:
    store = McpTokenStore(db)
    first = store.create()
    second = store.create()

    assert second.token != first.token
    assert store.verify(first.token) is False
    assert store.verify(second.token) is True
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM mcp_tokens").fetchone()[0] == 1
    conn.close()


def test_revoke_deletes_the_row(db: Path) -> None:
    store = McpTokenStore(db)
    created = store.create()
    assert store.revoke() is True
    assert store.verify(created.token) is False
    assert store.describe() == {"exists": False, "created_at": None}
    assert store.revoke() is False


def test_describe_reports_existence_and_creation_time_only(db: Path) -> None:
    store = McpTokenStore(db)
    assert store.describe() == {"exists": False, "created_at": None}
    created = store.create()
    described = store.describe()
    assert described == {"exists": True, "created_at": created.created_at}
    assert created.token not in str(described)


def test_the_token_survives_a_new_store_instance(db: Path) -> None:
    created = McpTokenStore(db).create()
    assert McpTokenStore(db).verify(created.token) is True


def test_a_failed_rotation_keeps_the_old_token(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = McpTokenStore(db)
    first = store.create()

    def _boom(*_a: object, **_k: object) -> str:
        raise RuntimeError("entropy source failed")

    monkeypatch.setattr("omrg.integrations.workspace_sqlite.tokens.secrets.token_urlsafe", _boom)
    with pytest.raises(RuntimeError):
        store.create()
    assert store.verify(first.token) is True
