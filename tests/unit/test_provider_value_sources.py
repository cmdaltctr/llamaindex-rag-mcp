"""Which provider values come from the environment or ``.env`` (tasks 3.1, 3.2).

The five editable fields lock when an explicit operator source sets them
(design D2). YAML and ``defaults.yaml`` count as defaults, like
``vector_store_provenance``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrg.config import Settings

#: Editable provider fields (design D2) and the variable that sets each.
VARIABLES = {
    "ollama_base_url": "OLLAMA_BASE_URL",
    "llamacpp_chat_url": "LLAMACPP_CHAT_URL",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "answer.provider": "ANSWER__PROVIDER",
    "answer.model": "ANSWER__MODEL",
}


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in VARIABLES.values():
        monkeypatch.delenv(variable, raising=False)


def test_nothing_is_explicit_with_only_defaults(tmp_path: Path) -> None:
    empty = tmp_path / ".env"
    empty.write_text("", encoding="utf-8")
    assert Settings(_env_file=empty).provider_explicit == frozenset()


@pytest.mark.parametrize(("field", "variable"), list(VARIABLES.items()))
def test_environment_variable_marks_the_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str, variable: str
) -> None:
    monkeypatch.setenv(variable, "value-from-env")
    settings = Settings(_env_file=tmp_path / "absent.env")
    assert settings.provider_explicit == frozenset({field})


@pytest.mark.parametrize(("field", "variable"), list(VARIABLES.items()))
def test_dotenv_marks_the_field(tmp_path: Path, field: str, variable: str) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"{variable}=value-from-dotenv\n", encoding="utf-8")
    assert Settings(_env_file=dotenv).provider_explicit == frozenset({field})


def test_answer_provider_and_model_are_tracked_apart(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("ANSWER__MODEL=qwen3:8b\n", encoding="utf-8")
    assert Settings(_env_file=dotenv).provider_explicit == frozenset({"answer.model"})


def test_blank_value_is_not_explicit(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("OPENROUTER_API_KEY=\nOLLAMA_BASE_URL=  \n", encoding="utf-8")
    assert Settings(_env_file=dotenv).provider_explicit == frozenset()


def test_unrelated_variables_do_not_mark_provider_fields(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("LLAMACPP_EMBED_URL=http://e:1/v1\nEMBED_MODEL=x\n", encoding="utf-8")
    assert Settings(_env_file=dotenv).provider_explicit == frozenset()


def test_env_example_leaves_the_chat_address_open_and_the_default_unchanged() -> None:
    """Task 3.7: the commented example line equals the code default."""
    root = Path(__file__).resolve().parents[2]
    lines = (root / ".env.example").read_text(encoding="utf-8").splitlines()
    assert "# LLAMACPP_CHAT_URL=http://localhost:8081/v1" in lines
    assert not any(line.startswith("LLAMACPP_CHAT_URL=") for line in lines)
    assert Settings.model_fields["llamacpp_chat_url"].default == "http://localhost:8081/v1"


def test_a_value_only_in_defaults_yaml_or_a_profile_is_a_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Task 3.1: YAML layers never lock a field; only env and ``.env`` do."""
    from omrg.config import sources

    monkeypatch.setattr(
        sources._YamlDefaultsSource,
        "_load_yaml",
        lambda self: {
            "ollama_base_url": "http://yaml-defaults:1",
            "answer": {"provider": "ollama", "model": "yaml-model"},
        },
    )
    monkeypatch.setattr(
        sources._ProfileYamlSettingsSource,
        "_load_profile",
        lambda self: {"llamacpp_chat_url": "http://profile:2/v1"},
    )
    settings = Settings(_env_file=tmp_path / "absent.env")
    assert settings.ollama_base_url == "http://yaml-defaults:1"
    assert settings.llamacpp_chat_url == "http://profile:2/v1"
    assert settings.provider_explicit == frozenset()
