"""The user config folder: ``omrg.jsonc`` and ``secrets/<provider>.key``.

Every test points ``OMRG_CONFIG_DIR`` at a temporary folder. No test reads the
real ``~/.config/omrg`` and no test uses a real key: the keys are fake
constants (design D1, user decision 2026-10-18).

A value from ``omrg.jsonc`` does not lock its field (ADR-087): only the
environment and ``.env`` lock.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.unit import test_web_connections_edit as edit

from omrg import compose
from omrg.compose_connections import build_connection_summary
from omrg.compose_providers import ProviderValues, apply_provider_values, locked_fields
from omrg.config import Settings
from omrg.config.settings_file import load_user_config
from omrg.config.user_config import display_path, parse_jsonc, user_config_dir

FILE_KEY = "sk-or-v1-FILEKEYVALUE0123456789"  # gitleaks:allow
OTHER_KEY = "sk-or-v1-OTHERKEYVALUE012345678"  # gitleaks:allow
LITERAL_KEY = "sk-or-v1-LITERALKEYVALUE0123456"  # gitleaks:allow
SAVED_KEY = "sk-or-v1-SAVEDKEYVALUE0123456789"  # gitleaks:allow
ENV_KEY = "sk-or-v1-ENVKEYVALUE012345678901"  # gitleaks:allow
harness = edit.harness  # the web test fixture, reused as is
KEY64, ORIGIN, put_key = edit.KEY64, edit.ORIGIN, edit.put_key
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")

VARIABLES = (
    "OLLAMA_BASE_URL",
    "LLAMACPP_CHAT_URL",
    "OPENAI_COMPATIBLE_BASE_URL",
    "OPENROUTER_API_KEY",
    "OPENAI_COMPATIBLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANSWER__PROVIDER",
    "ANSWER__MODEL",
    "XDG_CONFIG_HOME",
    "MY_TEST_KEY",
)


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    root = tmp_path / "omrg-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(root))
    return root


def write_config(root: Path, text: str) -> Path:
    path = root / "omrg.jsonc"
    path.write_text(text, encoding="utf-8")
    return path


def secrets_dir(root: Path) -> Path:
    path = root / "secrets"
    path.mkdir(mode=0o700, exist_ok=True)
    path.chmod(0o700)
    return path


def write_key(root: Path, provider: str, value: str, mode: int = 0o600) -> Path:
    path = secrets_dir(root) / f"{provider}.key"
    path.write_text(value, encoding="utf-8")
    path.chmod(mode)
    return path


def build(tmp_path: Path, dotenv: str = "") -> Settings:
    env_file = tmp_path / "test.env"
    env_file.write_text(dotenv, encoding="utf-8")
    return Settings(_env_file=env_file)


def warnings_of(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


# ── Folder resolution ────────────────────────────────────────────────────


def test_omrg_config_dir_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(tmp_path / "a"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert user_config_dir() == tmp_path / "a"


def test_xdg_config_home_is_next(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OMRG_CONFIG_DIR")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert user_config_dir() == tmp_path / "xdg" / "omrg"


def test_home_config_is_the_last_resort(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OMRG_CONFIG_DIR")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert user_config_dir() == tmp_path / ".config" / "omrg"


def test_display_path_shortens_the_home_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert display_path(tmp_path / ".config" / "omrg") == "~/.config/omrg"
    assert display_path(Path("/elsewhere/omrg")) == "/elsewhere/omrg"


# ── JSONC parser ─────────────────────────────────────────────────────────


def test_jsonc_comments_and_trailing_commas_parse() -> None:
    text = """
    // a line comment
    {
      /* a block
         comment */
      "ollama_base_url": "http://box:11434/v1", // trailing note
      "url_in_string": "http://x//y /* not a comment */",
      "answer": {"provider": "ollama", "model": "m",},
      "list": [1, 2,],
    }
    """
    data = parse_jsonc(text)
    assert data["ollama_base_url"] == "http://box:11434/v1"
    assert data["url_in_string"] == "http://x//y /* not a comment */"
    assert data["answer"] == {"provider": "ollama", "model": "m"}
    assert data["list"] == [1, 2]


def test_jsonc_rejects_bad_json() -> None:
    with pytest.raises(ValueError):
        parse_jsonc('{"a": ')


# ── omrg.jsonc fields ────────────────────────────────────────────────────


def test_jsonc_sets_addresses_and_chat_choice(folder: Path) -> None:
    write_config(
        folder,
        """{
          // comment
          "ollama_base_url": "http://ollama.cfg:11434",
          "llamacpp_chat_url": "http://llama.cfg:8081/v1",
          "openai_compatible_base_url": "http://oai.cfg/v1",
          "answer": {"provider": "anthropic", "model": "claude-x",},
          "unknown_key": "ignored",
        }""",
    )
    config = load_user_config()
    assert config.values == {
        "ollama_base_url": "http://ollama.cfg:11434",
        "llamacpp_chat_url": "http://llama.cfg:8081/v1",
        "openai_compatible_base_url": "http://oai.cfg/v1",
        "answer.provider": "anthropic",
        "answer.model": "claude-x",
    }


def test_literal_key_is_ignored_and_never_logged(
    folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_config(folder, f'{{"openrouter_api_key": "{LITERAL_KEY}"}}')
    with caplog.at_level(logging.WARNING):
        config = load_user_config()
    assert "openrouter_api_key" not in config.values
    messages = warnings_of(caplog)
    assert len(messages) == 1
    assert "openrouter_api_key" in messages[0]
    assert LITERAL_KEY not in messages[0]
    assert LITERAL_KEY not in repr(config)


def test_env_reference_resolves(folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TEST_KEY", f"  {FILE_KEY}\n")
    write_config(folder, '{"openrouter_api_key": "env://MY_TEST_KEY"}')
    assert load_user_config().values["openrouter_api_key"] == FILE_KEY


def test_env_reference_to_unset_variable_gives_nothing(folder: Path) -> None:
    write_config(folder, '{"openrouter_api_key": "env://MY_TEST_KEY"}')
    assert "openrouter_api_key" not in load_user_config().values


def test_file_reference_inside_secrets_resolves(folder: Path) -> None:
    target = secrets_dir(folder) / "custom.txt"
    target.write_text(FILE_KEY + "\n", encoding="utf-8")
    target.chmod(0o600)
    write_config(folder, f'{{"anthropic_api_key": "file://{target}"}}')
    assert load_user_config().values["anthropic_api_key"] == FILE_KEY


def test_file_reference_outside_secrets_is_rejected(
    folder: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    secrets_dir(folder)
    outside = tmp_path / "elsewhere.key"
    outside.write_text(FILE_KEY, encoding="utf-8")
    write_config(folder, f'{{"anthropic_api_key": "file://{outside}"}}')
    with caplog.at_level(logging.WARNING):
        config = load_user_config()
    assert "anthropic_api_key" not in config.values
    messages = warnings_of(caplog)
    assert len(messages) == 1
    assert "anthropic_api_key" in messages[0]
    assert FILE_KEY not in messages[0]
    assert str(outside) not in messages[0]


@POSIX_ONLY
def test_file_reference_through_a_link_that_escapes_is_rejected(
    folder: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "elsewhere.key"
    outside.write_text(FILE_KEY, encoding="utf-8")
    link = secrets_dir(folder) / "link.txt"
    link.symlink_to(outside)
    write_config(folder, f'{{"anthropic_api_key": "file://{link}"}}')
    assert "anthropic_api_key" not in load_user_config().values


def test_file_reference_must_be_absolute(folder: Path) -> None:
    write_key(folder, "anthropic", FILE_KEY)
    write_config(folder, '{"anthropic_api_key": "file://secrets/anthropic.key"}')
    assert "anthropic_api_key" not in load_user_config().values


def test_relative_file_reference_is_refused_even_from_inside_the_folder(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative path must not resolve against the working directory."""
    write_key(folder, "anthropic", FILE_KEY)
    write_config(folder, '{"anthropic_api_key": "file://secrets/anthropic.key"}')
    monkeypatch.chdir(folder)
    assert "anthropic_api_key" not in load_user_config().values


def test_broken_json_gives_no_values_and_one_warning(
    folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_config(folder, '{"ollama_base_url": "http://secret-host-name:1", oops')
    with caplog.at_level(logging.WARNING):
        assert load_user_config().values == {}
        assert load_user_config().values == {}
    messages = warnings_of(caplog)
    assert len(messages) == 1
    assert "omrg.jsonc" in messages[0]
    assert "secret-host-name" not in messages[0]


def test_a_wrong_type_is_ignored_with_one_warning_and_the_rest_stay(
    folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_config(folder, '{"ollama_base_url": 12, "llamacpp_chat_url": "http://ok/v1"}')
    with caplog.at_level(logging.WARNING):
        assert load_user_config().values == {"llamacpp_chat_url": "http://ok/v1"}
    messages = warnings_of(caplog)
    assert len(messages) == 1
    assert "ollama_base_url" in messages[0]


def test_missing_folder_gives_nothing_and_creates_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "never"
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(missing))
    config = load_user_config()
    assert config.values == {}
    assert config.key_file == {}
    assert not missing.exists()


# ── secrets/<provider>.key ───────────────────────────────────────────────


def test_key_file_is_read_and_stripped(folder: Path) -> None:
    write_key(folder, "openrouter", f"\n  {FILE_KEY}  \n")
    assert load_user_config().key_file == {"openrouter_api_key": FILE_KEY}


def test_empty_key_file_means_unset(folder: Path) -> None:
    write_key(folder, "openrouter", " \n")
    assert load_user_config().key_file == {}


def test_oversize_key_file_is_rejected(folder: Path, caplog: pytest.LogCaptureFixture) -> None:
    write_key(folder, "openrouter", "k" * 5000)
    with caplog.at_level(logging.WARNING):
        assert load_user_config().key_file == {}
    assert all("kkkk" not in m for m in warnings_of(caplog))


@POSIX_ONLY
def test_a_named_pipe_key_file_is_refused_without_blocking(folder: Path) -> None:
    """Reading a FIFO would block the server at launch, so it is refused unread."""
    import os
    import threading

    os.mkfifo(secrets_dir(folder) / "openrouter.key", 0o600)
    result: dict[str, object] = {}
    worker = threading.Thread(
        target=lambda: result.update(key_file=load_user_config().key_file), daemon=True
    )
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), "reading the key folder blocked on a named pipe"
    assert result["key_file"] == {}


@POSIX_ONLY
def test_loose_file_mode_warns_once_and_still_reads(
    folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = write_key(folder, "openrouter", FILE_KEY, mode=0o644)
    with caplog.at_level(logging.WARNING):
        assert load_user_config().key_file == {"openrouter_api_key": FILE_KEY}
        assert load_user_config().key_file == {"openrouter_api_key": FILE_KEY}
    messages = warnings_of(caplog)
    assert len(messages) == 1
    assert str(path) in messages[0]
    assert "644" in messages[0]
    assert FILE_KEY not in messages[0]


@POSIX_ONLY
def test_loose_secrets_folder_warns_once_and_still_reads(
    folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_key(folder, "anthropic", FILE_KEY)
    (folder / "secrets").chmod(0o755)
    with caplog.at_level(logging.WARNING):
        assert load_user_config().key_file == {"anthropic_api_key": FILE_KEY}
        load_user_config()
    messages = warnings_of(caplog)
    assert len(messages) == 1
    assert "755" in messages[0]


def test_tight_modes_do_not_warn(folder: Path, caplog: pytest.LogCaptureFixture) -> None:
    write_key(folder, "anthropic", FILE_KEY)
    with caplog.at_level(logging.WARNING):
        load_user_config()
    assert warnings_of(caplog) == []


def test_mode_check_is_skipped_on_windows(
    folder: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    write_key(folder, "openrouter", FILE_KEY, mode=0o644)
    monkeypatch.setattr("omrg.config.user_config._is_windows", lambda: True)
    with caplog.at_level(logging.WARNING):
        assert load_user_config().key_file == {"openrouter_api_key": FILE_KEY}
    assert warnings_of(caplog) == []


@POSIX_ONLY
def test_symlink_escaping_secrets_is_refused(folder: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.key"
    outside.write_text(FILE_KEY, encoding="utf-8")
    (secrets_dir(folder) / "openrouter.key").symlink_to(outside)
    assert load_user_config().key_file == {}


@POSIX_ONLY
def test_symlink_inside_secrets_is_allowed(folder: Path) -> None:
    real = write_key(folder, "shared", FILE_KEY)
    (secrets_dir(folder) / "anthropic.key").symlink_to(real)
    assert load_user_config().key_file == {"anthropic_api_key": FILE_KEY}


def test_a_directory_named_like_a_key_file_is_refused(folder: Path) -> None:
    (secrets_dir(folder) / "openrouter.key").mkdir()
    assert load_user_config().key_file == {}


# ── Precedence: env > .env > jsonc > saved > key file > default ──────────


def test_default_when_nothing_is_set(tmp_path: Path) -> None:
    settings = build(tmp_path)
    assert settings.ollama_base_url == Settings.model_fields["ollama_base_url"].default
    assert settings.provider_explicit == frozenset()
    assert settings.config_file_fields == frozenset()


def test_address_precedence(folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_config(folder, '{"ollama_base_url": "http://from-jsonc:1"}')
    settings = build(tmp_path)
    assert settings.ollama_base_url == "http://from-jsonc:1"
    assert "ollama_base_url" not in settings.provider_explicit  # the file does not lock
    assert "ollama_base_url" in settings.config_file_fields

    dotenv = build(tmp_path, "OLLAMA_BASE_URL=http://from-dotenv:2\n")
    assert dotenv.ollama_base_url == "http://from-dotenv:2"
    assert "ollama_base_url" not in dotenv.config_file_fields

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://from-env:3")
    env = build(tmp_path, "OLLAMA_BASE_URL=http://from-dotenv:2\n")
    assert env.ollama_base_url == "http://from-env:3"
    assert "ollama_base_url" not in env.config_file_fields


def test_jsonc_address_does_not_lock_a_saved_address(folder: Path, tmp_path: Path) -> None:
    saved = ProviderValues(values={"llamacpp_chat_url": "http://saved:4"})
    write_config(folder, '{"llamacpp_chat_url": "http://from-jsonc:1"}')
    file_set = build(tmp_path)
    assert "llamacpp_chat_url" not in locked_fields(file_set, file_set.provider_explicit)
    assert apply_provider_values(file_set, saved).llamacpp_chat_url == "http://saved:4"
    dotenv_set = build(tmp_path, "LLAMACPP_CHAT_URL=http://from-dotenv:2/v1\n")
    assert apply_provider_values(dotenv_set, saved).llamacpp_chat_url == "http://from-dotenv:2/v1"


def test_key_precedence(folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_key(folder, "openrouter", FILE_KEY)
    settings = build(tmp_path)
    assert settings.openrouter_api_key == FILE_KEY
    assert settings.key_file_fields == frozenset({"openrouter_api_key"})
    assert "openrouter_api_key" not in settings.provider_explicit

    monkeypatch.setenv("MY_TEST_KEY", OTHER_KEY)
    write_config(folder, '{"openrouter_api_key": "env://MY_TEST_KEY"}')
    jsonc = build(tmp_path)
    assert jsonc.openrouter_api_key == OTHER_KEY
    assert "openrouter_api_key" in jsonc.config_file_fields
    assert jsonc.key_file_fields == frozenset()

    dotenv = build(tmp_path, f"OPENROUTER_API_KEY={ENV_KEY}\n")
    assert dotenv.openrouter_api_key == ENV_KEY
    assert dotenv.config_file_fields == frozenset()

    monkeypatch.setenv("OPENROUTER_API_KEY", SAVED_KEY)
    assert build(tmp_path, f"OPENROUTER_API_KEY={ENV_KEY}\n").openrouter_api_key == SAVED_KEY


def test_blank_env_key_does_not_hide_the_key_file(folder: Path, tmp_path: Path) -> None:
    write_key(folder, "openrouter", FILE_KEY)
    assert build(tmp_path, "OPENROUTER_API_KEY=\n").openrouter_api_key == FILE_KEY


def test_unresolved_jsonc_reference_falls_back_to_the_key_file(
    folder: Path, tmp_path: Path
) -> None:
    write_key(folder, "openrouter", FILE_KEY)
    write_config(folder, '{"openrouter_api_key": "env://MY_TEST_KEY"}')
    settings = build(tmp_path)
    assert settings.openrouter_api_key == FILE_KEY
    assert settings.config_file_fields == frozenset()


def test_keychain_key_overrides_the_key_file_and_removal_falls_back(
    folder: Path, tmp_path: Path
) -> None:
    write_key(folder, "openrouter", FILE_KEY)
    settings = build(tmp_path)
    with_saved = apply_provider_values(
        settings, ProviderValues(values={"openrouter_api_key": SAVED_KEY})
    )
    assert with_saved.openrouter_api_key == SAVED_KEY
    assert apply_provider_values(settings, ProviderValues()).openrouter_api_key == FILE_KEY


def test_jsonc_chat_choice_does_not_lock(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{"answer": {"provider": "anthropic"}}')
    settings = build(tmp_path)
    assert settings.answer.provider == "anthropic"
    assert settings.config_file_fields == frozenset({"answer.provider"})
    locks = locked_fields(settings, settings.provider_explicit)
    assert "answer.provider" not in locks
    assert "answer.model" not in locks


def test_dotenv_chat_model_locks_both_chat_fields(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{"answer": {"provider": "anthropic"}}')
    settings = build(tmp_path, "ANSWER__MODEL=qwen3:8b\n")
    locks = locked_fields(settings, settings.provider_explicit)
    assert locks["answer.provider"] == locks["answer.model"] == "environment"


def test_stdio_and_cli_settings_see_the_jsonc_values(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(folder, '{"llamacpp_chat_url": "http://cli.cfg:8081/v1"}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("omrg.config._settings", None)
    assert compose.get_settings().llamacpp_chat_url == "http://cli.cfg:8081/v1"
    monkeypatch.setattr("omrg.config._settings", None)


# ── Summary and locks ────────────────────────────────────────────────────


def entry(summary: dict[str, Any], provider: str) -> dict[str, Any]:
    return next(c for c in summary["connections"] if c["provider"] == provider)


def field_of(summary: dict[str, Any], provider: str, field_id: str) -> dict[str, Any]:
    return next(f for f in entry(summary, provider)["fields"] if f["id"] == field_id)


@pytest.mark.xfail(
    strict=True,
    reason="group 5: compose_connections must read Settings.setting_sources (ADR-087)",
)
def test_summary_reports_config_file_field_unlocked(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(folder.parent))
    monkeypatch.setenv("USERPROFILE", str(folder.parent))
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(folder.parent / "omrg-config"))
    write_config(folder, '{"ollama_base_url": "http://from-jsonc:1"}')
    summary = build_connection_summary(build(tmp_path), tmp_path)
    field = field_of(summary, "ollama", "base_url")
    assert field["source"] == "config-file"
    assert field["locked"] is False
    assert field["lock_reason"] is None
    assert summary["user_config_dir"] == "~/omrg-config"


def test_summary_user_config_dir_is_present_even_when_empty(tmp_path: Path) -> None:
    summary = build_connection_summary(build(tmp_path), tmp_path)
    assert isinstance(summary["user_config_dir"], str)
    assert summary["user_config_dir"]


def test_summary_key_file_key_is_not_locked(folder: Path, tmp_path: Path) -> None:
    write_key(folder, "openrouter", FILE_KEY)
    values = ProviderValues(keychain_available=True)
    summary = build_connection_summary(build(tmp_path), tmp_path, values)
    field = field_of(summary, "openrouter", "api_key")
    assert field["source"] == "key-file"
    assert field["locked"] is False
    assert field["set"] is True
    assert field["lock_reason"] == (
        "Set from the key file (read-only here). Saving a key in the keychain overrides it."
    )
    assert FILE_KEY not in str(summary)


def test_summary_saved_key_beats_key_file(folder: Path, tmp_path: Path) -> None:
    write_key(folder, "openrouter", FILE_KEY)
    values = ProviderValues(values={"openrouter_api_key": SAVED_KEY}, keychain_available=True)
    settings = apply_provider_values(build(tmp_path), values)
    field = field_of(build_connection_summary(settings, tmp_path, values), "openrouter", "api_key")
    assert field["source"] == "keychain"
    assert field["lock_reason"] is None


def test_summary_key_file_without_keychain_keeps_the_no_keychain_lock(
    folder: Path, tmp_path: Path
) -> None:
    write_key(folder, "openrouter", FILE_KEY)
    summary = build_connection_summary(build(tmp_path), tmp_path, ProviderValues())
    field = field_of(summary, "openrouter", "api_key")
    assert field["source"] == "key-file"
    assert field["locked"] is True
    assert "No system keychain" in field["lock_reason"]


@pytest.mark.xfail(
    strict=True,
    reason="group 5: compose_connections must read Settings.setting_sources (ADR-087)",
)
def test_summary_jsonc_key_reference_is_not_locked(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MY_TEST_KEY", FILE_KEY)
    write_config(folder, '{"openrouter_api_key": "env://MY_TEST_KEY"}')
    summary = build_connection_summary(
        build(tmp_path), tmp_path, ProviderValues(keychain_available=True)
    )
    field = field_of(summary, "openrouter", "api_key")
    assert field["source"] == "config-file"
    assert field["locked"] is False


def test_environment_still_reports_env(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(folder, '{"ollama_base_url": "http://from-jsonc:1"}')
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://from-env:3")
    summary = build_connection_summary(build(tmp_path), tmp_path)
    field = field_of(summary, "ollama", "base_url")
    assert field["source"] == "env"
    assert "environment" in field["lock_reason"]


# ── Redaction and read-only guarantee ────────────────────────────────────


def test_key_file_key_is_redacted_from_error_text(folder: Path, tmp_path: Path) -> None:
    from omrg.compose_engine import build_redaction

    write_key(folder, "anthropic", FILE_KEY)
    redaction = build_redaction(build(tmp_path))
    text = redaction.redact(f"401 from provider for key {FILE_KEY}")
    assert FILE_KEY not in text


def test_jsonc_reference_key_is_redacted_from_error_text(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrg.compose_engine import build_redaction

    monkeypatch.setenv("MY_TEST_KEY", OTHER_KEY)
    write_config(folder, '{"openai_compatible_api_key": "env://MY_TEST_KEY"}')
    text = build_redaction(build(tmp_path)).redact(f"failed with {OTHER_KEY}")
    assert OTHER_KEY not in text


def snapshot(root: Path) -> dict[str, tuple[float, int, int]]:
    result = {}
    for path in sorted([root, *root.rglob("*")]):
        info = path.lstat()
        result[str(path)] = (info.st_mtime_ns, info.st_mode, info.st_size)
    return result


def test_resolving_never_writes_creates_or_chmods(folder: Path, tmp_path: Path) -> None:
    write_key(folder, "openrouter", FILE_KEY, mode=0o644)
    write_config(folder, '{"ollama_base_url": "http://from-jsonc:1"}')
    before = snapshot(folder)
    settings = build(tmp_path)
    build_connection_summary(settings, tmp_path, ProviderValues(keychain_available=True))
    load_user_config()
    assert snapshot(folder) == before


# ── Key references (move-settings-to-config-file, task 3.1) ──────────────


def test_tilde_in_a_file_reference_expands_to_the_home_folder(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = folder.parent
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(home / ".config" / "omrg"))
    config = home / ".config" / "omrg"
    config.mkdir(parents=True, mode=0o700)
    write_key(config, "custom", FILE_KEY)
    write_config(config, '{"openrouter_api_key": "file://~/.config/omrg/secrets/custom.key"}')
    loaded = load_user_config()
    assert loaded.values["openrouter_api_key"] == FILE_KEY
    assert loaded.key_paths["openrouter_api_key"] == str(config / "secrets" / "custom.key")


def test_tilde_path_outside_secrets_is_refused(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = folder.parent
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    secrets_dir(folder)
    (home / "stray.key").write_text(FILE_KEY, encoding="utf-8")
    write_config(folder, '{"openrouter_api_key": "file://~/stray.key"}')
    assert "openrouter_api_key" not in load_user_config().values


def test_keychain_reference_comes_back_unresolved(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{"openrouter_api_key": "keychain://openrouter"}')
    loaded = load_user_config()
    assert loaded.references == {"openrouter_api_key": "openrouter"}
    assert "openrouter_api_key" not in loaded.values
    settings = build(tmp_path)
    assert settings.keychain_refs == {"openrouter_api_key": "openrouter"}
    assert settings.openrouter_api_key == ""


def test_keychain_reference_needs_a_provider_name(folder: Path) -> None:
    write_config(folder, '{"openrouter_api_key": "keychain://"}')
    assert load_user_config().references == {}


def test_keychain_reference_beats_the_implicit_key_file(folder: Path, tmp_path: Path) -> None:
    write_key(folder, "openrouter", FILE_KEY)
    write_config(folder, '{"openrouter_api_key": "keychain://openrouter"}')
    settings = build(tmp_path)
    assert settings.openrouter_api_key == ""
    assert settings.keychain_refs == {"openrouter_api_key": "openrouter"}


def test_environment_drops_a_keychain_reference(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(folder, '{"openrouter_api_key": "keychain://openrouter"}')
    monkeypatch.setenv("OPENROUTER_API_KEY", ENV_KEY)
    settings = build(tmp_path)
    assert settings.openrouter_api_key == ENV_KEY
    assert settings.keychain_refs == {}


def test_literal_key_never_reaches_settings_or_the_problem_list(
    folder: Path, tmp_path: Path
) -> None:
    from omrg.config.settings_file import KIND_INVALID, read_settings_file

    write_config(folder, f'{{"openrouter_api_key": "{LITERAL_KEY}"}}')
    settings = build(tmp_path)
    assert settings.openrouter_api_key == ""
    (problem,) = read_settings_file().problems
    assert (problem.kind, problem.key) == (KIND_INVALID, "openrouter_api_key")
    assert LITERAL_KEY not in repr(read_settings_file()) + problem.message


def test_implicit_key_file_reports_key_file_and_its_path(folder: Path, tmp_path: Path) -> None:
    write_key(folder, "anthropic", FILE_KEY)
    settings = build(tmp_path)
    assert settings.anthropic_api_key == FILE_KEY
    assert settings.setting_sources["anthropic_api_key"] == "key-file"
    assert settings.key_file_paths["anthropic_api_key"] == str(folder / "secrets" / "anthropic.key")
    assert settings.key_file_fields == frozenset({"anthropic_api_key"})
    assert settings.config_file_fields == frozenset()


def test_file_reference_reports_key_file_and_env_reference_reports_config_file(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = write_key(folder, "custom", FILE_KEY)
    monkeypatch.setenv("MY_TEST_KEY", OTHER_KEY)
    write_config(
        folder,
        f'{{"anthropic_api_key": "file://{target}", "openrouter_api_key": "env://MY_TEST_KEY"}}',
    )
    settings = build(tmp_path)
    assert settings.setting_sources["anthropic_api_key"] == "key-file"
    assert settings.key_file_paths["anthropic_api_key"] == str(target)
    assert settings.setting_sources["openrouter_api_key"] == "config-file"
    assert settings.config_file_fields == frozenset({"openrouter_api_key"})
    assert OTHER_KEY not in repr(settings.setting_sources)


def test_other_key_fields_take_references_too(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MY_TEST_KEY", OTHER_KEY)
    monkeypatch.delenv("VECTOR_STORE")  # conftest pins lancedb; the file picks chroma here
    write_config(
        folder,
        '{"vector_store": "chroma", "chroma_cloud_api_key": "env://MY_TEST_KEY",'
        ' "azure_doc_intelligence_key": "keychain://azure"}',
    )
    settings = build(tmp_path)
    assert settings.chroma_cloud_api_key == OTHER_KEY
    assert settings.keychain_refs == {"azure_doc_intelligence_key": "azure"}


# ── Web routes ───────────────────────────────────────────────────────────


def test_a_key_file_key_is_overridden_by_the_keychain_and_comes_back(
    harness: Any, folder: Path
) -> None:
    write_key(folder, "anthropic", FILE_KEY)
    with harness() as h:
        assert h.field("anthropic", "api_key")["source"] == "key-file"
        assert put_key(h, KEY64, "anthropic").status_code == 200
        assert h.field("anthropic", "api_key")["source"] == "keychain"
        deleted = h.client.delete("/v1/connections/anthropic/key", headers=ORIGIN)
        assert deleted.status_code == 200
        field = h.field("anthropic", "api_key")
        assert (field["source"], field["locked"], field["set"]) == ("key-file", False, True)
