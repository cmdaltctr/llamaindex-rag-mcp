"""Restart-only snapshot (move-settings-to-config-file task 5.5, snapshot half).

``omrg web`` keeps the restart-only file values it launched with and reports
each key whose file value now differs. Every test points ``OMRG_CONFIG_DIR`` at
a temporary folder. No test reads the real ``~/.config/omrg``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrg.config import Settings
from omrg.config.rules import FILE_ONLY, SECRET_FIELDS
from omrg.config.settings_file import read_settings_file, setting_paths
from omrg.transports.api.restart_snapshot import capture, pending
from omrg.transports.settings_view import LIVE_KEYS, applies, restart_only_keys


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "omrg-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(root))
    return root


def write_config(root: Path, text: str) -> None:
    (root / "omrg.jsonc").write_text(text, encoding="utf-8")


def test_restart_only_set_comes_from_the_model_not_a_hand_list() -> None:
    keys = set(restart_only_keys())
    assert keys == set(setting_paths()) - LIVE_KEYS
    for expected in (
        "retrieval.top_k",
        "chunking.chunk_overlap",
        "embed_provider",
        "embed_model",
        "metadata.extraction_mode",
        "ocr_fallback_enabled",
        "chroma_mode",
        "web_port",
    ):
        assert expected in keys
    # The other answer members apply at the next launch; the Chat choice is live.
    assert "answer.provider" not in keys and "answer.model" not in keys
    assert {"web_max_upload_mib", "mcp_http_enabled"}.isdisjoint(keys)


def test_every_settings_field_is_either_live_or_restart() -> None:
    # A new Settings field is restart-only without an edit.
    for path in setting_paths():
        assert applies(path) in {"live", "restart"}
    assert set(FILE_ONLY) <= set(setting_paths())
    assert applies("retrieval.top_k") == "restart"
    assert applies("answer.model") == "live"


def test_capture_holds_only_restart_only_keys(folder: Path) -> None:
    write_config(
        folder,
        '{ "retrieval": { "top_k": 7 }, "answer": { "model": "m1" },'
        ' "web_port": 9100, "web_max_upload_mib": 200 }',
    )
    snapshot = capture(read_settings_file(folder))
    assert snapshot["retrieval.top_k"] == 7
    assert snapshot["web_port"] == 9100
    assert "answer.model" not in snapshot
    assert "web_max_upload_mib" not in snapshot
    assert set(snapshot) == set(restart_only_keys())
    assert snapshot["chunking.chunk_overlap"] is None  # not set by the file


def test_hand_edit_of_top_k_is_pending_and_not_applied_live(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "retrieval": { "top_k": 7 } }')
    launched = Settings(_env_file=tmp_path / "none.env")
    snapshot = capture(read_settings_file(folder))
    write_config(folder, '{ "retrieval": { "top_k": 5 } }')
    assert pending(snapshot, read_settings_file(folder)) == {"retrieval.top_k"}
    # The process keeps the value it launched with.
    assert launched.retrieval.top_k == 7


def test_hand_edit_of_the_chat_model_is_live_so_never_pending(folder: Path) -> None:
    write_config(folder, '{ "answer": { "model": "one" } }')
    snapshot = capture(read_settings_file(folder))
    write_config(folder, '{ "answer": { "model": "two" } }')
    assert pending(snapshot, read_settings_file(folder)) == set()


def test_an_unchanged_file_has_nothing_pending(folder: Path) -> None:
    write_config(folder, '{ "retrieval": { "top_k": 7 }, "web_port": 9100 }')
    snapshot = capture(read_settings_file(folder))
    assert pending(snapshot, read_settings_file(folder)) == set()


def test_added_and_removed_keys_are_pending(folder: Path) -> None:
    write_config(folder, '{ "retrieval": { "top_k": 7 } }')
    snapshot = capture(read_settings_file(folder))
    write_config(folder, '{ "web_port": 9100, "chunking": { "chunk_overlap": 50 } }')
    assert pending(snapshot, read_settings_file(folder)) == {
        "retrieval.top_k",
        "web_port",
        "chunking.chunk_overlap",
    }


def test_a_broken_file_reports_nothing_pending(folder: Path) -> None:
    write_config(folder, '{ "retrieval": { "top_k": 7 } }')
    snapshot = capture(read_settings_file(folder))
    write_config(folder, '{ "retrieval": { "top_k": ')  # mid-edit
    assert pending(snapshot, read_settings_file(folder)) == set()


def test_an_invalid_new_value_is_ignored_so_it_is_not_pending(folder: Path) -> None:
    write_config(folder, '{ "retrieval": { "top_k": 7 } }')
    snapshot = capture(read_settings_file(folder))
    write_config(folder, '{ "retrieval": { "top_k": 7 }, "chunking": { "chunk_overlap": "many" } }')
    assert pending(snapshot, read_settings_file(folder)) == set()


def test_snapshot_never_holds_a_key(folder: Path) -> None:
    secret = "sk-test-0123456789abcdef"  # noqa: S105 - a fake key
    (folder / "secrets").mkdir()
    (folder / "secrets" / "openrouter.key").write_text(secret, encoding="utf-8")
    write_config(
        folder,
        '{ "chroma_cloud_api_key": "env://OMRG_TEST_NO_SUCH_VARIABLE",'
        ' "azure_doc_intelligence_key": "keychain://azure" }',
    )
    snapshot = capture(read_settings_file(folder))
    assert secret not in repr(snapshot)
    # A restart-only key field is tracked by reference, never by value.
    assert snapshot["azure_doc_intelligence_key"] == "keychain://azure"
    assert set(SECRET_FIELDS) & set(restart_only_keys()) <= set(snapshot)


def test_a_new_keychain_reference_on_a_restart_only_key_is_pending(folder: Path) -> None:
    write_config(folder, "{}")
    snapshot = capture(read_settings_file(folder))
    write_config(folder, '{ "azure_doc_intelligence_key": "keychain://azure" }')
    assert pending(snapshot, read_settings_file(folder)) == {"azure_doc_intelligence_key"}
