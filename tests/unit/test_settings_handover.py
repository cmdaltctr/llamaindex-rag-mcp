"""Handover of saved workspace rows into ``omrg.jsonc`` (move-settings-to-config-file 6.1).

Each test follows a scenario of "Saved settings move out of the workspace
database". A fake keychain stands in for the system keychain. Every test uses
a temporary workspace database and a temporary config folder. No test reads
the real ``~/.config/omrg``, ``~/.omrg`` or the real keychain.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from omrg.config.settings_file import read_settings_file
from omrg.integrations.keychain import KeychainUnavailableError
from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository
from omrg.integrations.workspace_sqlite.settings import WorkspaceSettings, provider_key
from omrg.transports.api.settings_handover import HandoverResult, run_handover

STAMP = "2026-10-18T10:00:00+00:00"


class FakeSecret:
    def reveal(self) -> str:
        return "sk-test-never-written-anywhere"


class FakeKeychain:
    """A keychain with named entries. It can be unavailable or fail on read."""

    def __init__(
        self, entries: set[str] | None = None, *, available: bool = True, fails: bool = False
    ) -> None:
        self.entries = entries or set()
        self._available = available
        self.fails = fails
        self.reads: list[str] = []

    @property
    def available(self) -> bool:
        return self._available

    def read(self, provider: str) -> FakeSecret | None:
        self.reads.append(provider)
        if self.fails:
            raise KeychainUnavailableError("fake")
        return FakeSecret() if provider in self.entries else None


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "omrg-config"
    root.mkdir(mode=0o700)
    return root


@pytest.fixture
def rows(tmp_path: Path) -> WorkspaceSettings:
    path = tmp_path / "ws" / "workspace.db"
    SqliteWorkspaceRepository(path)
    return WorkspaceSettings(path)


def count_rows(settings: WorkspaceSettings) -> int:
    conn = sqlite3.connect(settings.path)
    try:
        return int(conn.execute("SELECT count(*) FROM workspace_settings").fetchone()[0])
    finally:
        conn.close()


def handover(rows: WorkspaceSettings, folder: Path, keychain: Any | None = None) -> HandoverResult:
    return run_handover(rows, keychain or FakeKeychain(), folder)


# ── Rows that move ───────────────────────────────────────────────────────


def test_saved_port_moves_and_the_table_stays_empty(rows: WorkspaceSettings, folder: Path) -> None:
    rows.set_web_port(9100)
    result = handover(rows, folder)
    assert result.pending is False and result.folder is None
    assert read_settings_file(folder).values["web_port"] == 9100
    assert count_rows(rows) == 0  # the table stays, empty


def test_every_row_kind_lands_under_its_file_key(rows: WorkspaceSettings, folder: Path) -> None:
    rows.set_web_port(9100)
    rows.set_upload_limit_mib(200)
    rows.set_mcp_http_enabled(True)
    rows.set_chat_choice("openrouter", "vendor/model")
    rows.set(provider_key("ollama", "base_url"), "http://localhost:11500")
    rows.set(provider_key("ollama", "context_window"), "32768")
    rows.set(provider_key("llamacpp", "chat_url"), "http://localhost:8099/v1")
    rows.set(provider_key("openai_compatible", "base_url"), "https://example.test/v1")
    rows.set(provider_key("llamacpp", "server_binary"), "/opt/bin/llama-server")
    rows.set(provider_key("llamacpp", "server_model"), "model.gguf")
    rows.set(provider_key("llamacpp", "context_window"), "8192")
    rows.set(provider_key("llamacpp", "idle_sleep"), "60")
    handover(rows, folder)
    values = dict(read_settings_file(folder).values)
    assert values == {
        "web_port": 9100,
        "web_max_upload_mib": 200,
        "mcp_http_enabled": True,
        "answer.provider": "openrouter",
        "answer.model": "vendor/model",
        "ollama_base_url": "http://localhost:11500",
        "ollama_context_window": 32768,
        "llamacpp_chat_url": "http://localhost:8099/v1",
        "openai_compatible_base_url": "https://example.test/v1",
        "llamacpp_server_binary": "/opt/bin/llama-server",
        "llamacpp_server_model": "model.gguf",
        "llamacpp_context_window": 8192,
        "llamacpp_idle_sleep_seconds": 60,
    }
    assert count_rows(rows) == 0


def test_a_saved_off_switch_moves_as_false(rows: WorkspaceSettings, folder: Path) -> None:
    rows.set_mcp_http_enabled(False)
    handover(rows, folder)
    assert read_settings_file(folder).values["mcp_http_enabled"] is False


def test_comments_and_other_keys_in_the_file_stay(rows: WorkspaceSettings, folder: Path) -> None:
    (folder / "omrg.jsonc").write_text(
        '// my notes\n{\n  "retrieval": { "top_k": 7 } // keep\n}\n', encoding="utf-8"
    )
    rows.set_web_port(9100)
    handover(rows, folder)
    text = (folder / "omrg.jsonc").read_text(encoding="utf-8")
    assert "// my notes" in text and "// keep" in text
    parsed = read_settings_file(folder).values
    assert parsed["retrieval.top_k"] == 7 and parsed["web_port"] == 9100


# ── File wins ────────────────────────────────────────────────────────────


def test_file_value_wins_and_the_row_is_deleted(rows: WorkspaceSettings, folder: Path) -> None:
    (folder / "omrg.jsonc").write_text('{ "ollama_base_url": "http://localhost:1111" }')
    rows.set(provider_key("ollama", "base_url"), "http://localhost:2222")
    handover(rows, folder)
    assert read_settings_file(folder).values["ollama_base_url"] == "http://localhost:1111"
    assert rows.get(provider_key("ollama", "base_url")) is None


def test_a_file_key_with_an_invalid_value_still_wins(rows: WorkspaceSettings, folder: Path) -> None:
    # The person typed the key. A page save must not overwrite it.
    (folder / "omrg.jsonc").write_text('{ "web_port": 80 }')
    rows.set_web_port(9100)
    handover(rows, folder)
    assert '"web_port": 80' in (folder / "omrg.jsonc").read_text()
    assert count_rows(rows) == 0


def test_chat_choice_moves_as_a_unit_or_not_at_all(rows: WorkspaceSettings, folder: Path) -> None:
    (folder / "omrg.jsonc").write_text('{ "answer": { "model": "file-model" } }')
    rows.set_chat_choice("openrouter", "row-model")
    handover(rows, folder)
    values = read_settings_file(folder).values
    assert values["answer.model"] == "file-model"
    assert "answer.provider" not in values
    assert count_rows(rows) == 0


# ── Keys ─────────────────────────────────────────────────────────────────


def test_a_saved_key_becomes_a_keychain_reference(rows: WorkspaceSettings, folder: Path) -> None:
    rows.set_key_saved_at("openrouter", STAMP)
    keychain = FakeKeychain({"openrouter"})
    handover(rows, folder, keychain)
    file = read_settings_file(folder)
    assert file.references == {"openrouter_api_key": "openrouter"}
    text = (folder / "omrg.jsonc").read_text()
    assert '"openrouter_api_key": "keychain://openrouter"' in text
    assert "sk-test" not in text  # a key never reaches the file
    assert count_rows(rows) == 0


def test_a_key_row_with_no_keychain_entry_adds_no_reference(
    rows: WorkspaceSettings, folder: Path
) -> None:
    rows.set_key_saved_at("anthropic", STAMP)
    handover(rows, folder, FakeKeychain())
    assert read_settings_file(folder).references == {}
    assert rows.get_key_saved_at("anthropic") is None  # the dead row goes


def test_an_unavailable_keychain_leaves_the_key_row_for_the_next_start(
    rows: WorkspaceSettings, folder: Path
) -> None:
    rows.set_key_saved_at("openrouter", STAMP)
    rows.set_web_port(9100)
    for keychain in (FakeKeychain(available=False), FakeKeychain({"openrouter"}, fails=True)):
        result = handover(rows, folder, keychain)
        assert result.pending is False  # the folder is fine; only the keychain is unknown
    assert rows.get_key_saved_at("openrouter") == STAMP
    assert read_settings_file(folder).references == {}
    assert read_settings_file(folder).values["web_port"] == 9100


def test_a_file_reference_wins_over_the_saved_key(rows: WorkspaceSettings, folder: Path) -> None:
    (folder / "omrg.jsonc").write_text('{ "openrouter_api_key": "env://MY_OPENROUTER_KEY" }')
    rows.set_key_saved_at("openrouter", STAMP)
    handover(rows, folder, FakeKeychain({"openrouter"}))
    assert read_settings_file(folder).references == {}
    assert "env://MY_OPENROUTER_KEY" in (folder / "omrg.jsonc").read_text()
    assert rows.get_key_saved_at("openrouter") is None


# ── Damaged rows ─────────────────────────────────────────────────────────


def test_a_row_that_breaks_its_rule_is_not_copied(rows: WorkspaceSettings, folder: Path) -> None:
    rows.set(provider_key("ollama", "base_url"), "file:///etc/passwd")
    rows.set(provider_key("ollama", "context_window"), "12")
    rows.set(provider_key("llamacpp", "idle_sleep"), "soon")
    rows.set("chat.provider", "not a name!")
    handover(rows, folder)
    assert read_settings_file(folder).values == {}
    assert not (folder / "omrg.jsonc").exists()  # nothing to write, nothing created
    assert count_rows(rows) == 0  # an unusable row read as unset already


# ── Folder not writable ──────────────────────────────────────────────────


@pytest.fixture
def blocked(tmp_path: Path) -> Path:
    """A config folder that cannot be created, because its parent is a file."""
    parent = tmp_path / "blocked"
    parent.write_text("not a folder", encoding="utf-8")
    return parent / "omrg"


def test_unwritable_folder_keeps_the_rows_and_gives_a_notice(
    rows: WorkspaceSettings, blocked: Path
) -> None:
    rows.set_web_port(9100)
    rows.set_chat_choice("openrouter", "vendor/model")
    result = run_handover(rows, FakeKeychain(), blocked)
    assert result.pending is True
    assert result.folder is not None and "blocked" in result.folder
    assert rows.get_web_port() == 9100
    assert rows.get_chat_model() == "vendor/model"
    assert count_rows(rows) == 3  # the port and the two Chat rows


def test_a_broken_file_keeps_the_rows_and_gives_a_notice(
    rows: WorkspaceSettings, folder: Path
) -> None:
    (folder / "omrg.jsonc").write_text('{ "web_port": ')
    rows.set_web_port(9100)
    result = handover(rows, folder)
    assert result.pending is True and result.folder == str(folder)
    assert rows.get_web_port() == 9100
    assert (folder / "omrg.jsonc").read_text() == '{ "web_port": '  # not touched


def test_the_next_start_retries_and_moves_the_rows(
    rows: WorkspaceSettings, folder: Path, tmp_path: Path
) -> None:
    rows.set_web_port(9100)
    (tmp_path / "later").write_text("blocker")
    assert run_handover(rows, FakeKeychain(), tmp_path / "later" / "omrg").pending is True
    assert handover(rows, folder).pending is False
    assert read_settings_file(folder).values["web_port"] == 9100
    assert count_rows(rows) == 0


# ── Edges ────────────────────────────────────────────────────────────────


def test_a_second_run_changes_nothing(rows: WorkspaceSettings, folder: Path) -> None:
    rows.set_web_port(9100)
    handover(rows, folder)
    before = (folder / "omrg.jsonc").read_bytes()
    result = handover(rows, folder)
    assert result == HandoverResult(pending=False, folder=None)
    assert (folder / "omrg.jsonc").read_bytes() == before


def test_a_missing_database_is_left_alone(tmp_path: Path, folder: Path) -> None:
    ghost = WorkspaceSettings(tmp_path / "ws" / "workspace.db")
    result = run_handover(ghost, FakeKeychain(), folder)
    assert result.pending is False
    assert not ghost.path.exists()  # the handover never creates the database
    assert not (folder / "omrg.jsonc").exists()


def test_an_unmigrated_database_is_left_alone(tmp_path: Path, folder: Path) -> None:
    path = tmp_path / "old.db"
    sqlite3.connect(path).close()
    result = run_handover(WorkspaceSettings(path), FakeKeychain(), folder)
    assert result.pending is False
    assert not (folder / "omrg.jsonc").exists()


def test_the_result_holds_no_value(rows: WorkspaceSettings, folder: Path) -> None:
    rows.set(provider_key("ollama", "base_url"), "http://localhost:12345")
    result = handover(rows, folder)
    assert "12345" not in repr(result)


def test_no_other_process_imports_the_handover() -> None:
    # Gotcha 17: the CLI, the stdio server and the watcher never touch the rows.
    import omrg

    src = Path(omrg.__file__).parent
    offenders = [
        str(path.relative_to(src))
        for part in ("transports/cli", "transports/mcp", "daemon", "core")
        for path in (src / part).rglob("*.py")
        if "settings_handover" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


# ── The judge choice has no workspace row (add-judge-model-setting 1.8) ──


def test_the_handover_writes_no_judge_key(rows: WorkspaceSettings, folder: Path) -> None:
    from omrg.transports.api.settings_handover import _plan

    judge = {"answer.verify_provider", "answer.verify_model", "answer.verify_claims"}
    plan = _plan()
    assert not judge & {row.file_key for row in plan}
    for row in plan:  # fill every text row the old page could save, then move them
        if row.kind == "text":
            rows.set(row.row_key, "x")
    handover(rows, folder)
    written = set(read_settings_file(folder).values)
    assert written and not judge & written
