"""``compose_providers``: the claim check judge choice locks as one unit (add-judge-model-setting).

Either ``ANSWER__VERIFY_PROVIDER`` or ``ANSWER__VERIFY_MODEL`` from the
environment or ``.env`` locks both judge fields, like the Chat pair (design D1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrg.compose_providers import (
    ProviderValues,
    apply_provider_values,
    locked_fields,
    provider_values_from_file,
)
from omrg.config import Settings
from omrg.config.settings_file import read_settings_file


def make_settings(**extra: object) -> Settings:
    return Settings(_env_file=None, **extra)


def _file(tmp_path: Path, text: str) -> object:
    folder = tmp_path / "cfg"
    folder.mkdir(exist_ok=True)
    (folder / "omrg.jsonc").write_text(text, encoding="utf-8")
    return read_settings_file(folder)


def test_the_judge_choice_locks_as_a_unit_when_the_environment_sets_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANSWER__VERIFY_MODEL", "openai/gpt-5-mini")
    base = make_settings(embed_provider="openrouter")
    assert "answer.verify_model" in base.provider_explicit
    locked = locked_fields(base, base.provider_explicit)
    assert (locked["answer.verify_provider"], locked["answer.verify_model"]) == (
        "environment",
        "environment",
    )
    assert "answer.provider" not in locked  # the Chat choice stays open
    saved = ProviderValues({"answer.verify_provider": "ollama", "answer.verify_model": "x"})
    result = apply_provider_values(base, saved)
    assert (result.answer.verify_provider, result.answer.verify_model) == (
        "cloud",
        "openai/gpt-5-mini",
    )


def test_the_judge_pair_locks_together_over_the_file(tmp_path: Path) -> None:
    base = make_settings()
    object.__setattr__(base, "provider_explicit", frozenset({"answer.verify_model"}))
    text = '{"answer": {"verify_provider": "llamacpp"}}'
    values = provider_values_from_file(base, _file(tmp_path, text), None)
    assert "answer.verify_provider" not in values.values


def test_a_judge_model_the_file_dropped_goes_back_to_empty(tmp_path: Path) -> None:
    base = make_settings(answer={"verify_model": "launch-judge", "verify_provider": "ollama"})
    sources = {"answer.verify_model": "config-file", "answer.verify_provider": "config-file"}
    object.__setattr__(base, "setting_sources", sources)
    values = provider_values_from_file(base, _file(tmp_path, "{}"), None)
    applied = apply_provider_values(base, values)
    assert (applied.answer.verify_provider, applied.answer.verify_model) == ("cloud", "")
    assert "answer.verify_model" not in applied.setting_sources
    assert "answer.verify_model" not in applied.__dict__  # no stray dotted attribute
