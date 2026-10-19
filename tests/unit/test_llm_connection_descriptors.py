"""LLM provider connection descriptors and ``registry.describe_all()`` (tasks 2.1, 2.4).

Each LLM provider module declares a ``CONNECTION`` descriptor (design D5).
The registry returns them in registration order, so a card needs no code
that names a provider.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest

from omrg.config import Settings
from omrg.core.providers.llm import registry
from omrg.core.providers.llm.connection import (
    ConnectionDescriptor,
    ConnectionField,
    ConnectionTarget,
    models_from,
)

SECRET = "sk-or-v1-SECRETVALUE0123456789"  # noqa: S105 - fake key
PROVIDERS = ["ollama", "llamacpp", "openrouter", "openai_compatible", "anthropic"]
DISPLAY_NAMES = ["Ollama", "llama.cpp", "OpenRouter", "OpenAI-compatible", "Anthropic"]


def make_settings(**extra: Any) -> Settings:
    return Settings(_env_file=None, **extra)


def test_describe_all_lists_the_built_in_providers_in_registration_order() -> None:
    described = registry.describe_all()
    assert list(described) == PROVIDERS
    assert all(isinstance(d, ConnectionDescriptor) for d in described.values())
    assert [d.display_name for d in described.values()] == DISPLAY_NAMES
    assert [d.locality for d in described.values()] == ["local", "local", "cloud", "cloud", "cloud"]


def test_fields_name_the_setting_and_environment_variable() -> None:
    fields = {name: {f.id: f for f in d.fields} for name, d in registry.describe_all().items()}
    assert fields["ollama"]["base_url"] == ConnectionField(
        "base_url", "Address", "url", "ollama_base_url", "OLLAMA_BASE_URL"
    )
    assert fields["llamacpp"]["chat_url"].settings_field == "llamacpp_chat_url"
    assert fields["llamacpp"]["chat_url"].env_var == "LLAMACPP_CHAT_URL"
    key = fields["openrouter"]["api_key"]
    assert (key.kind, key.settings_field, key.env_var) == (
        "secret",
        "openrouter_api_key",
        "OPENROUTER_API_KEY",
    )


def test_extras_and_required_modules() -> None:
    described = registry.describe_all()
    assert described["ollama"].extra is None
    assert described["llamacpp"].extra == "llamacpp"
    assert described["openrouter"].extra == "openrouter"
    assert described["openrouter"].requires_module == "llama_index.llms.openai_like"


def test_test_targets_follow_the_design() -> None:
    settings = make_settings(
        ollama_base_url="http://ollama.test:11434/",
        llamacpp_embed_url="http://llama.test:8080/v1",
        llamacpp_chat_url="http://llama.test:8081/v1",
        openrouter_api_key=SECRET,
    )
    described = registry.describe_all()
    assert described["ollama"].test_targets(settings).urls == ("http://ollama.test:11434/api/tags",)
    assert described["llamacpp"].test_targets(settings).urls == (
        "http://llama.test:8080/v1/models",
        "http://llama.test:8081/v1/models",
    )
    openrouter = described["openrouter"].test_targets(settings)
    assert openrouter.urls == ("https://openrouter.ai/api/v1/key",)
    assert openrouter.headers == {"Authorization": f"Bearer {SECRET}"}
    assert SECRET not in repr(openrouter)


def test_openrouter_without_a_key_has_no_target() -> None:
    target = registry.describe_all()["openrouter"].test_targets(
        make_settings(openrouter_api_key="")
    )
    assert target == ConnectionTarget(())


def test_models_targets() -> None:
    settings = make_settings(
        ollama_base_url="http://ollama.test:11434",
        llamacpp_chat_url="http://llama.test:8081/v1",
        openrouter_api_key=SECRET,
    )
    described = registry.describe_all()
    assert described["ollama"].models_target(settings).urls == (
        "http://ollama.test:11434/api/tags",
    )
    assert described["llamacpp"].models_target(settings).urls == (
        "http://llama.test:8081/v1/models",
    )
    assert described["openrouter"].models_target(settings).urls == (
        "https://openrouter.ai/api/v1/models",
    )


def test_read_only_rows_hold_embedding_values() -> None:
    settings = make_settings(
        embed_model="nomic", llamacpp_embed_url="http://e:1/v1", llamacpp_embed_model="gguf"
    )
    described = registry.describe_all()
    ollama = {r.label: r.value for r in described["ollama"].read_only(settings)}
    assert ollama["Embedding model"] == "nomic"
    llama = {r.label: r.value for r in described["llamacpp"].read_only(settings)}
    assert llama["Embedding address"] == "http://e:1/v1"
    openrouter = {r.label: r.value for r in described["openrouter"].read_only(settings)}
    assert openrouter["Address"] == "https://openrouter.ai/api/v1"


@pytest.fixture
def fake_provider() -> Iterator[None]:
    module = types.ModuleType("fake_llm_provider")
    module.build = lambda settings, **_: None  # type: ignore[attr-defined]
    module.CONNECTION = ConnectionDescriptor(  # type: ignore[attr-defined]
        display_name="Fake",
        locality="local",
        requires_module="json",
        extra=None,
        fields=(),
        read_only=lambda settings: [],
        test_targets=lambda settings: ConnectionTarget(()),
        models_target=lambda settings: ConnectionTarget(()),
        parse_models=lambda payload: [],
    )
    sys.modules["fake_llm_provider"] = module
    before = dict(registry._registry)
    registry.register("fake", "fake_llm_provider:build")
    try:
        yield
    finally:
        registry._registry.clear()
        registry._registry.update(before)
        sys.modules.pop("fake_llm_provider", None)


@pytest.mark.usefixtures("fake_provider")
def test_a_registered_provider_appears_with_no_other_change() -> None:
    described = registry.describe_all()
    assert list(described) == [*PROVIDERS, "fake"]
    assert described["fake"].display_name == "Fake"


# ── parse_models (task 2.4) ────────────────────────────────────────


def test_ollama_models_come_from_models_name() -> None:
    parse = registry.describe_all()["ollama"].parse_models
    payload = {"models": [{"name": "qwen3:4b"}, {"name": "llama3.2:latest"}, {"size": 1}]}
    assert parse(payload) == ["qwen3:4b", "llama3.2:latest"]


@pytest.mark.parametrize("provider", ["llamacpp", "openrouter"])
def test_openai_style_models_come_from_data_id(provider: str) -> None:
    parse = registry.describe_all()[provider].parse_models
    payload = {"data": [{"id": "openai/gpt-4o-mini"}, {"id": "b"}, {"object": "x"}]}
    assert parse(payload) == ["openai/gpt-4o-mini", "b"]


@pytest.mark.parametrize("provider", ["ollama", "llamacpp", "openrouter"])
@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "text",
        7,
        {},
        {"models": "x", "data": 3},
        {"models": [1, None, {"name": 5}]},
        {"data": [["id"], {"id": None}]},
    ],
)
def test_malformed_payloads_give_an_empty_list(provider: str, payload: Any) -> None:
    assert registry.describe_all()[provider].parse_models(payload) == []


def test_models_from_ignores_non_string_names() -> None:
    assert models_from({"k": [{"n": "a"}, {"n": 1}]}, "k", "n") == ["a"]
