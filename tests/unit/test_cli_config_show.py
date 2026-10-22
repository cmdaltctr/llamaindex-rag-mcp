"""``omrs config show`` (move-settings-to-config-file tasks 8.1 and 8.2).

Every case runs in a temporary config folder named by ``OMRS_CONFIG_DIR``. A
fake keychain class replaces the system keychain. No test reads or writes the
real ``~/.config/omrs``. Keys here are fake constants.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from omrs.config import provenance
from omrs.config.settings_file import setting_paths
from omrs.transports.cli import app as cli_app

runner = CliRunner()
KEY = "Zq9XkP3lM7wVb2NrT4yQ1234"
LINE = re.compile(r"^\s{2}(\S+) = (.*?)  \((\S+)\)$")
VARIABLES = (
    "RETRIEVAL__TOP_K",
    "ANSWER__MODEL",
    "ANSWER__PROVIDER",
    "OPENROUTER_API_KEY",
    "OLLAMA_BASE_URL",
)


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    folder = tmp_path / "cfg" / "omrs"
    folder.mkdir(parents=True, mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(folder))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return folder


def write_config(folder: Path, text: str) -> None:
    (folder / "omrs.jsonc").write_text(text, encoding="utf-8")


def show() -> Any:
    return runner.invoke(cli_app, ["config", "show"])


def parsed(output: str) -> dict[str, tuple[str, str]]:
    """Return ``{key: (value text, source)}`` from the setting lines of the output."""
    found = {}
    for line in output.splitlines():
        match = LINE.match(line)
        if match:
            found[match.group(1)] = (match.group(2), match.group(3))
    return found


def flat(text: str) -> str:
    return " ".join(text.split())


def no_run_of(text: str, secret: str, size: int = 5) -> bool:
    return not any(secret[i : i + size] in text for i in range(len(secret) - size + 1))


# ── Output channel ───────────────────────────────────────────────────────


def test_output_goes_to_stderr_only(config_dir: Path) -> None:
    result = show()
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert result.stderr != ""


# ── Rows ─────────────────────────────────────────────────────────────────


def test_prints_every_setting_once_with_value_and_source(config_dir: Path) -> None:
    write_config(config_dir, '{ "retrieval": { "top_k": 7 } }')
    result = show()
    rows = parsed(result.stderr)
    assert sorted(rows) == sorted(setting_paths())
    assert sum(1 for line in result.stderr.splitlines() if LINE.match(line)) == len(rows)
    assert rows["retrieval.top_k"] == ("7", "config-file")
    assert rows["chunking.chunk_overlap"][1] == "default"


def test_text_values_are_quoted_and_booleans_are_plain(config_dir: Path) -> None:
    write_config(config_dir, '{ "answer": { "model": "vendor/model" }, "mcp_http_enabled": true }')
    rows = parsed(show().stderr)
    assert rows["answer.model"] == ('"vendor/model"', "config-file")
    assert rows["mcp_http_enabled"] == ("true", "config-file")


def test_environment_value_reports_env(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_config(config_dir, '{ "retrieval": { "top_k": 7 } }')
    monkeypatch.setenv("RETRIEVAL__TOP_K", "9")
    assert parsed(show().stderr)["retrieval.top_k"] == ("9", "env")


def test_file_only_keys_have_a_value(config_dir: Path) -> None:
    write_config(config_dir, '{ "web_port": 9100 }')
    rows = parsed(show().stderr)
    assert rows["web_port"] == ("9100", "config-file")
    assert rows["web_max_upload_mib"] == ("50", "default")


# ── Masking ──────────────────────────────────────────────────────────────


def test_key_file_key_shows_last_four_and_key_file(config_dir: Path) -> None:
    (config_dir / "secrets").mkdir(mode=0o700)
    (config_dir / "secrets" / "openrouter.key").write_text(KEY, encoding="utf-8")
    result = show()
    assert parsed(result.stderr)["openrouter_api_key"] == ("set, ending 1234", "key-file")
    assert no_run_of(result.stderr, KEY)


def test_keychain_reference_resolves_and_shows_last_four(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeStore:
        available = True

        def read(self, provider: str) -> Any:
            class Secret:
                def reveal(self) -> str:
                    return KEY

            return Secret() if provider == "openrouter" else None

    monkeypatch.setattr("omrs.integrations.keychain.KeychainStore", FakeStore)
    write_config(config_dir, '{ "openrouter_api_key": "keychain://openrouter" }')
    result = show()
    assert parsed(result.stderr)["openrouter_api_key"] == ("set, ending 1234", "keychain")
    assert no_run_of(result.stderr, KEY)


def test_keychain_reference_that_does_not_resolve_is_named(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class EmptyStore:
        available = True

        def read(self, provider: str) -> None:
            return None

    monkeypatch.setattr("omrs.integrations.keychain.KeychainStore", EmptyStore)
    write_config(config_dir, '{ "openrouter_api_key": "keychain://openrouter" }')
    result = show()
    assert result.exit_code == 0
    assert parsed(result.stderr)["openrouter_api_key"][0] == "not set"
    assert "The keychain has no key for openrouter." in flat(result.stderr)


def test_without_a_reference_the_keychain_is_never_opened(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the keychain was opened")

    monkeypatch.setattr("omrs.integrations.keychain.KeychainStore", forbidden)
    write_config(config_dir, '{ "retrieval": { "top_k": 7 } }')
    assert show().exit_code == 0


def test_environment_key_shows_last_four_and_env(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    result = show()
    assert parsed(result.stderr)["openrouter_api_key"] == ("set, ending 1234", "env")
    assert no_run_of(result.stderr, KEY)


def test_short_key_shows_no_characters(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "abc1234")
    result = show()
    assert parsed(result.stderr)["openrouter_api_key"] == ("set", "env")
    assert "abc1234" not in result.stderr


def test_unset_key_says_not_set(config_dir: Path) -> None:
    assert parsed(show().stderr)["anthropic_api_key"] == ("not set", "default")


# ── Problems ─────────────────────────────────────────────────────────────


def test_problems_are_listed_by_key_without_values(config_dir: Path) -> None:
    write_config(
        config_dir,
        '{ "retreival": { "top_k": 5 }, "ollama_base_url": "file:///etc/passwd" }',
    )
    result = show()
    text = flat(result.stderr)
    assert "Problems in" in text
    assert "retreival" in text and "ollama_base_url" in text
    assert "passwd" not in result.stderr
    assert parsed(result.stderr)["ollama_base_url"][1] != "config-file"


def test_a_broken_file_is_listed_and_the_command_still_succeeds(config_dir: Path) -> None:
    write_config(config_dir, '{ "retrieval": ')
    result = show()
    assert result.exit_code == 0
    assert "omrs.jsonc could not be read" in flat(result.stderr)
    assert sorted(parsed(result.stderr)) == sorted(setting_paths())


def test_no_problem_section_for_a_clean_file(config_dir: Path) -> None:
    write_config(config_dir, '{ "retrieval": { "top_k": 7 } }')
    assert "Problems in" not in show().stderr


def test_a_missing_file_is_said_and_defaults_are_listed(config_dir: Path) -> None:
    result = show()
    assert "not found" in flat(result.stderr)
    assert sorted(parsed(result.stderr)) == sorted(setting_paths())
    assert not (config_dir / "omrs.jsonc").exists()  # show writes nothing
