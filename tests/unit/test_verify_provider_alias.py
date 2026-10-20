"""``compose_answer.resolve_verify_provider``: the judge alias rule (add-judge-model-setting 2.1).

``cloud`` or a blank value resolves to ``cloud_backend``, ``local`` to
``local_backend``, and any other value is a registry name as it stands. The
judge builder and the judge settings route share this one rule (design D1).
"""

from __future__ import annotations

import pytest

from omrg.compose_answer import resolve_verify_provider
from omrg.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, cloud_backend="openrouter", local_backend="ollama")


@pytest.mark.parametrize(
    ("raw", "resolved"),
    [
        ("cloud", "openrouter"),
        ("", "openrouter"),
        ("  ", "openrouter"),
        (" cloud ", "openrouter"),
        ("local", "ollama"),
        ("anthropic", "anthropic"),
        (" llamacpp ", "llamacpp"),
        ("gemini", "gemini"),  # an unknown name passes through; the caller checks it
    ],
)
def test_alias_resolves_to_a_registry_name(settings: Settings, raw: str, resolved: str) -> None:
    assert resolve_verify_provider(settings, raw) == resolved


def test_none_reads_as_the_cloud_alias(settings: Settings) -> None:
    assert resolve_verify_provider(settings, None) == "openrouter"
