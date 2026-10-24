"""Writing ``omrs.jsonc`` safely (move-settings-to-config-file, tasks 4.3 and 4.4).

Every test points ``OMRS_CONFIG_DIR`` at a temporary folder. No test reads or
writes the real ``~/.config/omrs``. Keys are fake constants.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
import threading
from pathlib import Path

import pytest

from omrs.config.settings_file import file_revision, read_settings_file
from omrs.config.settings_file_write import (
    ALLOWED_KEYS,
    SettingsFileConflict,
    SettingsFileRefused,
    SettingsFileWriteError,
    write_settings,
)
from omrs.config.user_config import parse_jsonc

LITERAL_KEY = "sk-or-v1-LITERALKEYVALUE0123456"  # gitleaks:allow
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")


@pytest.fixture
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "cfg" / "omrs"
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


@pytest.fixture
def existing(folder: Path) -> Path:
    folder.mkdir(parents=True, mode=0o700)
    path = folder / "omrs.jsonc"
    path.write_text(
        '// my settings\n{\n  "retrieval": { "top_k": 7 }, // keep\n  "ollama_base_url": "http://a:1"\n}\n',
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def data(folder: Path) -> dict:
    return parse_jsonc((folder / "omrs.jsonc").read_text(encoding="utf-8"))


# ── Allowed keys ─────────────────────────────────────────────────────────


def test_the_card_keys_stay_allowed_and_key_fields_are_not() -> None:
    # edit-settings-from-configuration-page D1: ALLOWED_KEYS grew to every plain
    # setting. Key fields left it; the writer still takes them as references.
    assert not {"openrouter_api_key", "openai_compatible_api_key", "anthropic_api_key"} & set(
        ALLOWED_KEYS
    )
    assert set(ALLOWED_KEYS) >= {
        "ollama_base_url",
        "llamacpp_chat_url",
        "openai_compatible_base_url",
        "ollama_context_window",
        "llamacpp_context_window",
        "llamacpp_idle_sleep_seconds",
        "llamacpp_server_binary",
        "llamacpp_server_model",
        "answer.provider",
        "answer.model",
        "answer.verify_provider",
        "answer.verify_model",
        # add-chat-reasoning-and-usage D4: one reasoning level per role
        "answer.reasoning",
        "answer.verify_reasoning",
        "web_port",
        "web_max_upload_mib",
        "mcp_http_enabled",
        # document-reading-settings: Settings > Document reading
        "pdf_reader",
        "ocr_fallback_enabled",
        "ocr_fallback_min_confidence",
        "ocr_fallback_page_fraction",
        "ocr_routing_unit",
        "ocr_engine_primary",
        "ocr_engine_fallback",
        "ocr_maths_routing_enabled",
        "ocr_maths_page_fraction",
    }


def test_a_key_outside_the_list_is_refused_and_changes_nothing(existing: Path) -> None:
    before = existing.read_bytes()
    with pytest.raises(SettingsFileRefused) as caught:
        write_settings({"embed_provider": "local"}, revision=None)
    assert "embed_provider" in str(caught.value)
    assert existing.read_bytes() == before


def test_a_refused_key_does_not_create_the_file(folder: Path) -> None:
    with pytest.raises(SettingsFileRefused):
        write_settings({"lancedb_uri": "./elsewhere"}, revision=None)
    assert not folder.exists()


def test_one_refused_change_applies_none_of_the_batch(existing: Path) -> None:
    before = existing.read_bytes()
    with pytest.raises(SettingsFileRefused):
        write_settings({"answer.model": "m", "embed_provider": "local"}, revision=None)
    assert existing.read_bytes() == before


# ── Values ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ollama_base_url", "file:///etc/passwd"),
        ("ollama_base_url", "http://user:pw@host:1"),
        ("web_port", 80),
        ("web_port", "9100"),
        ("web_max_upload_mib", 0),
        ("mcp_http_enabled", "yes"),
        ("ollama_context_window", 12),
        ("ollama_context_window", True),
        ("answer.model", 7),
    ],
)
def test_an_invalid_value_is_refused_without_echoing_it(
    existing: Path, key: str, value: object
) -> None:
    before = existing.read_bytes()
    with pytest.raises(SettingsFileRefused) as caught:
        write_settings({key: value}, revision=None)
    assert key in str(caught.value)
    for fragment in ("passwd", "pw@"):
        assert fragment not in str(caught.value)
    assert existing.read_bytes() == before


def test_valid_values_of_every_kind_are_written(folder: Path) -> None:
    write_settings(
        {
            "web_port": 9100,
            "web_max_upload_mib": 200,
            "mcp_http_enabled": True,
            "ollama_context_window": 8192,
            "ollama_base_url": "http://gpu-box.local:11434",
            "answer.provider": "ollama",
            "answer.model": "qwen3:8b",
        },
        revision="absent",
    )
    assert data(folder) == {
        "web_port": 9100,
        "web_max_upload_mib": 200,
        "mcp_http_enabled": True,
        "ollama_context_window": 8192,
        "ollama_base_url": "http://gpu-box.local:11434",
        "answer": {"provider": "ollama", "model": "qwen3:8b"},
    }
    assert read_settings_file().problems == ()


# ── No literal secrets ───────────────────────────────────────────────────


def test_a_literal_key_is_refused_and_never_echoed(folder: Path) -> None:
    with pytest.raises(SettingsFileRefused) as caught:
        write_settings({"openrouter_api_key": LITERAL_KEY}, revision=None)
    assert "openrouter_api_key" in str(caught.value)
    assert LITERAL_KEY not in str(caught.value)
    assert not folder.exists()


@pytest.mark.parametrize("reference", ["env://MY_ROUTER_KEY", "keychain://openrouter"])
def test_a_reference_is_accepted(folder: Path, reference: str) -> None:
    write_settings({"openrouter_api_key": reference}, revision=None)
    assert data(folder) == {"openrouter_api_key": reference}


def test_a_tilde_file_reference_inside_secrets_is_accepted(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = folder.parent
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(home / ".config" / "omrs"))
    reference = "file://~/.config/omrs/secrets/x.key"
    write_settings({"openrouter_api_key": reference}, revision=None)
    assert data(home / ".config" / "omrs") == {"openrouter_api_key": reference}


@pytest.mark.parametrize(
    "reference",
    ["env://not a name", "keychain://", "file:///etc/passwd", "file://secrets/x.key", "https://x"],
)
def test_a_bad_reference_is_refused(folder: Path, reference: str) -> None:
    with pytest.raises(SettingsFileRefused):
        write_settings({"anthropic_api_key": reference}, revision=None)


def test_a_file_reference_must_stay_inside_secrets(folder: Path) -> None:
    inside = f"file://{folder}/secrets/ok.key"
    escape = f"file://{folder}/secrets/../../outside.key"
    write_settings({"anthropic_api_key": inside}, revision=None)
    with pytest.raises(SettingsFileRefused):
        write_settings({"openrouter_api_key": escape}, revision=None)


def test_writing_a_key_reference_touches_nothing_else(folder: Path) -> None:
    write_settings({"openrouter_api_key": "keychain://openrouter"}, revision=None)
    assert sorted(p.name for p in folder.rglob("*")) == ["omrs.jsonc"]


# ── Revision and conflicts ───────────────────────────────────────────────


def test_a_matching_revision_writes_and_returns_the_new_revision(existing: Path) -> None:
    before = file_revision()
    result = write_settings({"answer.model": "m"}, revision=before)
    assert result.revision == file_revision()
    assert result.revision == hashlib.sha256(existing.read_bytes()).hexdigest()
    assert result.revision != before


def test_a_stale_revision_is_a_conflict_and_keeps_the_hand_edit(existing: Path) -> None:
    stale = file_revision()
    existing.write_text(existing.read_text(encoding="utf-8") + "// edited by hand\n", "utf-8")
    edited = existing.read_bytes()
    with pytest.raises(SettingsFileConflict) as caught:
        write_settings({"answer.model": "m"}, revision=stale)
    assert str(caught.value) == "omrs.jsonc changed on disk. Reload to see the new values."
    assert existing.read_bytes() == edited


def test_a_file_that_appeared_after_the_page_loaded_is_a_conflict(folder: Path) -> None:
    folder.mkdir(parents=True, mode=0o700)
    (folder / "omrs.jsonc").write_text('{ "web_port": 9100 }', encoding="utf-8")
    with pytest.raises(SettingsFileConflict):
        write_settings({"answer.model": "m"}, revision="absent")


def test_a_file_that_vanished_is_a_conflict(existing: Path) -> None:
    stale = file_revision()
    existing.unlink()
    with pytest.raises(SettingsFileConflict):
        write_settings({"answer.model": "m"}, revision=stale)


def test_revision_none_skips_the_check(existing: Path) -> None:
    write_settings({"answer.model": "m"}, revision=None)
    assert data(existing.parent)["answer"] == {"model": "m"}


def test_a_duplicate_key_is_a_conflict_that_names_it(folder: Path) -> None:
    folder.mkdir(parents=True, mode=0o700)
    (folder / "omrs.jsonc").write_text('{ "web_port": 9100, "web_port": 9200 }', encoding="utf-8")
    before = (folder / "omrs.jsonc").read_bytes()
    with pytest.raises(SettingsFileConflict) as caught:
        write_settings({"web_port": 9300}, revision=None)
    assert "web_port" in str(caught.value)
    assert (folder / "omrs.jsonc").read_bytes() == before


# ── Broken file ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("text", ['{ "a": ', "[1, 2]", "just words", '{ "a": 1 } trailing'])
def test_a_broken_file_is_never_overwritten(folder: Path, text: str) -> None:
    folder.mkdir(parents=True, mode=0o700)
    path = folder / "omrs.jsonc"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SettingsFileConflict) as caught:
        write_settings({"answer.model": "m"}, revision=None)
    assert str(caught.value) == "omrs.jsonc could not be read. Fix it, then save again."
    assert path.read_text(encoding="utf-8") == text


# ── Creating the file ────────────────────────────────────────────────────


@POSIX_ONLY
def test_a_new_file_is_0600_in_a_0700_folder_with_a_header(folder: Path) -> None:
    write_settings({"ollama_base_url": "http://box:11434"}, revision="absent")
    assert stat.S_IMODE((folder / "omrs.jsonc").stat().st_mode) == 0o600
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    text = (folder / "omrs.jsonc").read_text(encoding="utf-8")
    assert text.startswith("//")
    assert data(folder) == {"ollama_base_url": "http://box:11434"}
    assert read_settings_file().values["ollama_base_url"] == "http://box:11434"


@POSIX_ONLY
def test_the_mode_of_an_existing_file_is_kept(existing: Path) -> None:
    existing.chmod(0o640)
    write_settings({"answer.model": "m"}, revision=None)
    assert stat.S_IMODE(existing.stat().st_mode) == 0o640


@POSIX_ONLY
def test_an_existing_folder_mode_is_not_changed(existing: Path) -> None:
    existing.parent.chmod(0o750)
    write_settings({"answer.model": "m"}, revision=None)
    assert stat.S_IMODE(existing.parent.stat().st_mode) == 0o750


def test_removing_from_a_missing_file_creates_nothing(folder: Path) -> None:
    result = write_settings({"answer.model": None}, revision="absent")
    assert result.revision == "absent"
    assert not folder.exists()


# ── Keeping the rest of the file ─────────────────────────────────────────


def test_comments_order_and_other_keys_stay(existing: Path) -> None:
    write_settings({"answer.model": "claude-x"}, revision=None)
    text = existing.read_text(encoding="utf-8")
    assert text.startswith("// my settings\n")
    assert "// keep" in text
    assert data(existing.parent) == {
        "retrieval": {"top_k": 7},
        "ollama_base_url": "http://a:1",
        "answer": {"model": "claude-x"},
    }


def test_none_removes_the_member_and_the_field_reads_as_default(existing: Path) -> None:
    write_settings({"ollama_base_url": None}, revision=None)
    assert "ollama_base_url" not in data(existing.parent)
    assert "ollama_base_url" not in read_settings_file().values


def test_a_blank_string_clears_the_member(existing: Path) -> None:
    write_settings({"ollama_base_url": "  "}, revision=None)
    assert "ollama_base_url" not in data(existing.parent)


def test_a_save_that_changes_nothing_does_not_rewrite_the_file(existing: Path) -> None:
    before_revision = file_revision()
    before = existing.stat().st_mtime_ns
    result = write_settings({"ollama_base_url": "http://a:1"}, revision=before_revision)
    assert result.revision == before_revision
    assert existing.stat().st_mtime_ns == before


def test_a_batch_writes_every_change_in_one_replace(existing: Path) -> None:
    write_settings(
        {"answer.provider": "ollama", "answer.model": "m", "web_port": 9100}, revision=None
    )
    assert data(existing.parent)["answer"] == {"provider": "ollama", "model": "m"}
    assert data(existing.parent)["web_port"] == 9100


def test_a_symlinked_file_is_written_through_the_link(folder: Path, tmp_path: Path) -> None:
    folder.mkdir(parents=True, mode=0o700)
    target = tmp_path / "dotfiles" / "omrs.jsonc"
    target.parent.mkdir()
    target.write_text("{\n}\n", encoding="utf-8")
    (folder / "omrs.jsonc").symlink_to(target)
    write_settings({"web_port": 9100}, revision=None)
    assert (folder / "omrs.jsonc").is_symlink()
    assert parse_jsonc(target.read_text(encoding="utf-8")) == {"web_port": 9100}


# ── Atomic replace ───────────────────────────────────────────────────────


def test_a_crash_at_replace_leaves_the_old_content_and_no_temporary_file(
    existing: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = existing.read_bytes()

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(SettingsFileWriteError):
        write_settings({"answer.model": "m"}, revision=None)
    assert existing.read_bytes() == before
    assert [p.name for p in existing.parent.iterdir()] == ["omrs.jsonc"]


def test_a_crash_while_flushing_leaves_the_old_content(
    existing: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = existing.read_bytes()

    def boom(*_a: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(SettingsFileWriteError):
        write_settings({"answer.model": "m"}, revision=None)
    assert existing.read_bytes() == before
    assert [p.name for p in existing.parent.iterdir()] == ["omrs.jsonc"]


def test_a_stale_temporary_file_from_a_crash_does_not_block_a_save(existing: Path) -> None:
    (existing.parent / "omrs.jsonc.tmp").write_text("half", encoding="utf-8")
    write_settings({"answer.model": "m"}, revision=None)
    assert data(existing.parent)["answer"] == {"model": "m"}
    assert [p.name for p in existing.parent.iterdir()] == ["omrs.jsonc"]


@POSIX_ONLY
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores modes")
def test_a_folder_that_cannot_be_written_raises_a_write_error(existing: Path) -> None:
    existing.parent.chmod(0o500)
    try:
        with pytest.raises(SettingsFileWriteError) as caught:
            write_settings({"answer.model": "m"}, revision=None)
        assert "could not be written" in str(caught.value)
    finally:
        existing.parent.chmod(0o700)


def test_concurrent_saves_in_one_process_do_not_lose_updates(folder: Path) -> None:
    folder.mkdir(parents=True, mode=0o700)
    (folder / "omrs.jsonc").write_text("{\n}\n", encoding="utf-8")

    def save(offset: int) -> None:
        for i in range(10):
            write_settings({"answer.model": f"m{offset}-{i}"}, revision=None)
            write_settings({"web_max_upload_mib": 1 + offset * 10 + i}, revision=None)

    threads = [threading.Thread(target=save, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    final = data(folder)
    assert set(final) == {"answer", "web_max_upload_mib"}
    assert read_settings_file().problems == ()
