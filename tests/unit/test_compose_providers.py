"""``compose_providers``: saved provider values over resolved settings (tasks 3.3, 3.4)."""

from __future__ import annotations

from typing import Any

from omrg import compose
from omrg.compose_providers import (
    ProviderValues,
    apply_provider_values,
    locked_fields,
)
from omrg.config import Settings

SECRET = "sk-or-v1-SECRETVALUE0123456789"  # noqa: S105 - fake key


def make_settings(**extra: Any) -> Settings:
    return Settings(_env_file=None, **extra)


def test_compose_re_exports_the_names() -> None:
    assert compose.ProviderValues is ProviderValues
    assert compose.apply_provider_values is apply_provider_values


def test_saved_values_replace_defaults() -> None:
    base = make_settings(embed_provider="openrouter", answer={"provider": "ollama"})
    values = ProviderValues(
        {
            "ollama_base_url": "http://gpu-box.local:11434",
            "llamacpp_chat_url": "http://gpu-box.local:8081/v1",
            "openrouter_api_key": SECRET,
            "answer.provider": "openrouter",
            "answer.model": "openai/gpt-4o-mini",
        }
    )
    result = apply_provider_values(base, values, frozenset())
    assert result.ollama_base_url == "http://gpu-box.local:11434"
    assert result.llamacpp_chat_url == "http://gpu-box.local:8081/v1"
    assert result.openrouter_api_key == SECRET
    assert (result.answer.provider, result.answer.model) == ("openrouter", "openai/gpt-4o-mini")


def test_the_input_settings_are_not_changed() -> None:
    base = make_settings(embed_provider="openrouter")
    before = base.model_copy(deep=True)
    apply_provider_values(base, ProviderValues({"ollama_base_url": "http://x:1"}), frozenset())
    assert base == before


def test_environment_value_wins_and_locks() -> None:
    base = make_settings(embed_provider="openrouter", llamacpp_chat_url="http://env:8081/v1")
    values = ProviderValues({"llamacpp_chat_url": "http://saved:8081/v1"})
    result = apply_provider_values(base, values, frozenset({"llamacpp_chat_url"}))
    assert result.llamacpp_chat_url == "http://env:8081/v1"
    assert locked_fields(base, frozenset({"llamacpp_chat_url"})) == {
        "llamacpp_chat_url": "environment"
    }


def test_explicit_defaults_to_the_settings_record() -> None:
    base = make_settings(embed_provider="openrouter")
    object.__setattr__(base, "provider_explicit", frozenset({"answer.model"}))
    values = ProviderValues({"answer.model": "saved", "answer.provider": "openrouter"})
    result = apply_provider_values(base, values)
    assert result.answer.model == base.answer.model
    assert result.answer.provider == base.answer.provider


def test_blank_saved_value_is_ignored() -> None:
    base = make_settings(embed_provider="openrouter", openrouter_api_key="from-env")
    result = apply_provider_values(base, ProviderValues({"openrouter_api_key": "  "}), frozenset())
    assert result.openrouter_api_key == "from-env"


def test_unknown_key_is_ignored() -> None:
    base = make_settings(embed_provider="openrouter")
    result = apply_provider_values(base, ProviderValues({"embed_model": "other"}), frozenset())
    assert result.embed_model == base.embed_model


def test_ollama_address_is_locked_while_embeddings_use_ollama() -> None:
    base = make_settings(embed_provider="local", local_backend="ollama", embed_model="nomic")
    values = ProviderValues({"ollama_base_url": "http://other:11434"})
    result = apply_provider_values(base, values, frozenset())
    assert result.ollama_base_url == base.ollama_base_url
    assert locked_fields(base, frozenset()) == {"ollama_base_url": "embeddings"}


def test_ollama_address_applies_when_embeddings_use_another_provider() -> None:
    base = make_settings(embed_provider="openrouter")
    assert locked_fields(base, frozenset()) == {}
    values = ProviderValues({"ollama_base_url": "http://other:11434"})
    assert apply_provider_values(base, values, frozenset()).ollama_base_url == "http://other:11434"


def test_environment_lock_wins_over_the_embeddings_reason() -> None:
    base = make_settings(embed_provider="local", local_backend="ollama", embed_model="nomic")
    assert locked_fields(base, frozenset({"ollama_base_url"})) == {"ollama_base_url": "environment"}


def test_repr_hides_every_value() -> None:
    values = ProviderValues({"openrouter_api_key": SECRET, "ollama_base_url": "http://h:1"})
    assert SECRET not in repr(values)
    assert "http://h:1" not in repr(values)
    assert "openrouter_api_key" in repr(values)


def test_provider_effective_settings_applies_the_source_to_the_resolved_settings(
    monkeypatch,
) -> None:
    base = make_settings(embed_provider="openrouter")
    monkeypatch.setattr(compose, "get_settings", lambda: base)
    effective = compose.provider_effective_settings(
        lambda: ProviderValues({"answer.model": "saved-model"})
    )
    assert effective.answer.model == "saved-model"
    assert effective.ollama_base_url == base.ollama_base_url


def test_chat_choice_locks_as_one_unit_when_only_the_model_is_explicit() -> None:
    base = make_settings(embed_provider="openrouter")
    explicit = frozenset({"answer.model"})
    assert locked_fields(base, explicit) == {
        "answer.model": "environment",
        "answer.provider": "environment",
    }
    values = ProviderValues({"answer.provider": "openrouter", "answer.model": "saved"})
    result = apply_provider_values(base, values, explicit)
    assert (result.answer.provider, result.answer.model) == (
        base.answer.provider,
        base.answer.model,
    )


def test_chat_choice_locks_as_one_unit_when_only_the_provider_is_explicit() -> None:
    base = make_settings(embed_provider="openrouter")
    explicit = frozenset({"answer.provider"})
    assert set(locked_fields(base, explicit)) == {"answer.provider", "answer.model"}


class _Catalogue:
    def __init__(self, *records: dict[str, Any]) -> None:
        self.records = list(records)

    def list_profiles(self) -> list[dict[str, Any]]:
        return self.records


def test_profiles_use_ollama_reads_the_catalogue() -> None:
    from omrg.core.profiles.catalogue import uses_ollama_embeddings as profiles_use_ollama

    assert profiles_use_ollama(None) is False
    assert profiles_use_ollama(_Catalogue({"profile_id": "a"})) is False
    other = {"embed_provider": "openrouter", "embed_model": "m"}
    assert profiles_use_ollama(_Catalogue(other)) is False
    mine = {"embed_provider": "ollama", "embed_model": "nomic"}
    assert profiles_use_ollama(_Catalogue(other, mine)) is True


def test_ollama_address_locks_when_a_profile_uses_ollama_embeddings() -> None:
    base = make_settings(embed_provider="openrouter")
    assert locked_fields(base, frozenset(), profiles_ollama=True) == {
        "ollama_base_url": "embeddings"
    }
    values = ProviderValues({"ollama_base_url": "http://other:11434"})
    result = apply_provider_values(base, values, frozenset(), profiles_ollama=True)
    assert result.ollama_base_url == base.ollama_base_url
