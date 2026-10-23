"""Reasoning levels in the answer settings (add-chat-reasoning-and-usage D4, tasks 1.1 and 1.2).

``answer.reasoning`` sets the level for the Chat model and
``answer.verify_reasoning`` for the claim judge. Each is empty or a short
level word. The Settings page may write both, and the environment or ``.env``
locks each one on its own.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from omrs.compose_providers import ProviderValues, apply_provider_values, locked_fields
from omrs.config import Settings
from omrs.config.settings_file_write import (
    ALLOWED_KEYS,
    SettingsFileRefused,
    write_settings,
)
from omrs.core.answer.settings import AnswerSettings
from omrs.core.settings import AnswerBlock

_FIELDS = ("reasoning", "verify_reasoning")


# ── 1.1 the level pattern ────────────────────────────────────────────────


@pytest.mark.parametrize("model", [AnswerSettings, AnswerBlock])
@pytest.mark.parametrize("field", _FIELDS)
def test_the_level_is_empty_by_default(model: type, field: str) -> None:
    assert getattr(model(), field) == ""


@pytest.mark.parametrize("model", [AnswerSettings, AnswerBlock])
@pytest.mark.parametrize("field", _FIELDS)
@pytest.mark.parametrize("level", ["", "low", "max", "x-high_2", "a" * 32])
def test_an_allowed_level_is_kept(model: type, field: str, level: str) -> None:
    assert getattr(model(**{field: level}), field) == level


@pytest.mark.parametrize("model", [AnswerSettings, AnswerBlock])
@pytest.mark.parametrize("field", _FIELDS)
@pytest.mark.parametrize("level", ["high; drop", "low medium", "a" * 33, "é"])
def test_a_level_outside_the_pattern_is_refused(model: type, field: str, level: str) -> None:
    with pytest.raises(ValidationError):
        model(**{field: level})


def test_the_environment_sets_both_levels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANSWER__REASONING", "low")
    monkeypatch.setenv("ANSWER__VERIFY_REASONING", "none")
    settings = Settings(_env_file=None)
    assert (settings.answer.reasoning, settings.answer.verify_reasoning) == ("low", "none")


def test_the_levels_reach_effective_settings() -> None:
    from omrs.compose import settings_to_effective

    settings = Settings(_env_file=None, answer={"reasoning": "high", "verify_reasoning": "low"})
    effective = settings_to_effective(settings)
    assert (effective.answer.reasoning, effective.answer.verify_reasoning) == ("high", "low")


# ── 1.2 allow-list, lock and template ────────────────────────────────────


@pytest.mark.parametrize("key", ["answer.reasoning", "answer.verify_reasoning"])
def test_the_page_may_write_the_level(key: str, tmp_path: Path) -> None:
    assert key in ALLOWED_KEYS
    write_settings({key: "low"}, revision=None, directory=tmp_path)
    assert '"low"' in (tmp_path / "omrs.jsonc").read_text(encoding="utf-8")


@pytest.mark.parametrize("key", ["answer.reasoning", "answer.verify_reasoning"])
def test_a_bad_level_is_refused_and_nothing_is_written(key: str, tmp_path: Path) -> None:
    with pytest.raises(SettingsFileRefused):
        write_settings({key: "high; drop"}, revision=None, directory=tmp_path)
    assert not (tmp_path / "omrs.jsonc").exists()


@pytest.mark.parametrize(
    ("env_name", "path", "other"),
    [
        ("ANSWER__REASONING", "answer.reasoning", "answer.verify_reasoning"),
        ("ANSWER__VERIFY_REASONING", "answer.verify_reasoning", "answer.reasoning"),
    ],
)
def test_the_environment_locks_only_its_own_level(
    env_name: str, path: str, other: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(env_name, "high")
    base = Settings(_env_file=None)
    assert path in base.provider_explicit
    locked = locked_fields(base, base.provider_explicit)
    assert locked[path] == "environment"
    assert other not in locked
    assert "answer.provider" not in locked  # the Chat choice stays open
    assert "answer.verify_provider" not in locked  # and so does the judge choice
    saved = ProviderValues({path: "low", other: "medium"})
    applied = apply_provider_values(base, saved)
    leaf, other_leaf = path.removeprefix("answer."), other.removeprefix("answer.")
    assert getattr(applied.answer, leaf) == "high"  # the locked value wins
    assert getattr(applied.answer, other_leaf) == "medium"  # the open one takes the save


def test_a_saved_level_applies_when_nothing_locks_it() -> None:
    base = Settings(_env_file=None)
    applied = apply_provider_values(
        base, ProviderValues({"answer.reasoning": "low", "answer.verify_reasoning": "none"})
    )
    assert (applied.answer.reasoning, applied.answer.verify_reasoning) == ("low", "none")


def test_config_init_lists_both_levels() -> None:
    from omrs.transports.cli.config_template import build_template

    template = build_template()
    assert '"reasoning"' in template
    assert '"verify_reasoning"' in template
