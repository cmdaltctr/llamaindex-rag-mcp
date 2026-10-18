"""``compose.connection_summary()``: provider endpoints, models and roles (task 7.1).

The summary shows which LLM registry providers (ollama, llamacpp,
openrouter) each role uses, resolved by the startup rules. The key itself
never leaves the process. The settings are built in memory, with no
``.env`` file, so the tests read no operator configuration.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import pytest

from omrg import compose
from omrg.compose_connections import build_connection_summary, build_connection_targets
from omrg.compose_providers import ProviderValues
from omrg.config import Settings
from omrg.core.answer.settings import AnswerSettings
from omrg.core.metadata.settings import MetadataSettings

SECRET = "sk-or-v1-SECRETVALUE0123456789"  # noqa: S105 - fake key for redaction tests
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
PROVIDERS = ("ollama", "llamacpp", "openrouter", "openai_compatible", "anthropic")
#: The new Chat-only providers are not embedding or metadata providers (config rejects them).
EMBEDDING_PROVIDERS = PROVIDERS[:3]
CHAT_ONLY = {"openai_compatible": [], "anthropic": []}


def make_settings(
    *,
    embed_provider: str = "local",
    local_backend: str = "ollama",
    cloud_backend: str = "openrouter",
    metadata_llm_provider: str = "local",
    extraction_mode: str = "llamaindex",
    answer_enabled: bool = True,
    answer_provider: str = "ollama",
    verify_claims: bool = False,
    verify_provider: str = "cloud",
    verify_model: str = "",
    openrouter_api_key: str = "",
    explicit: frozenset[str] = frozenset(),
    **extra: Any,
) -> Settings:
    fields: dict[str, Any] = dict(
        embed_provider=embed_provider,
        local_backend=local_backend,
        cloud_backend=cloud_backend,
        metadata_llm_provider=metadata_llm_provider,
        embed_model="nomic-embed-text",
        ollama_base_url="http://ollama.test:11434",
        llamacpp_embed_url="http://llama.test:8080/v1",
        llamacpp_embed_model="embed-gguf",
        llamacpp_chat_url="http://llama.test:8081/v1",
        llamacpp_chat_model="chat-gguf",
        openrouter_api_key=openrouter_api_key,
        openrouter_embed_model="or-embed",
        openrouter_llm_model="or-chat",
        metadata=MetadataSettings(extraction_mode=extraction_mode, ollama_classify_model="qwen-m"),
        answer=AnswerSettings(
            enabled=answer_enabled,
            provider=answer_provider,
            model="answer-model",
            verify_claims=verify_claims,
            verify_provider=verify_provider,
            verify_model=verify_model,
        ),
    )
    fields.update(extra)
    settings = Settings(_env_file=None, **fields)
    object.__setattr__(settings, "provider_explicit", explicit)
    return settings


def summary(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> dict[str, Any]:
    monkeypatch.setattr(compose, "get_settings", lambda: settings)
    return compose.connection_summary()


def roles(result: dict[str, Any]) -> dict[str, list[str]]:
    return {entry["provider"]: entry["roles"] for entry in result["connections"]}


def by_provider(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["provider"]: entry for entry in result["connections"]}


def field(entry: dict[str, Any], field_id: str) -> dict[str, Any]:
    return next(f for f in entry["fields"] if f["id"] == field_id)


def test_entry_shape_and_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    result = summary(monkeypatch, make_settings())
    assert result["config_dir"] == str(tmp_path.resolve())
    assert result["keychain"] == "unavailable"
    assert [entry["provider"] for entry in result["connections"]] == list(PROVIDERS)
    entries = by_provider(result)
    assert set(entries["ollama"]) == {
        "provider",
        "display_name",
        "locality",
        "installed",
        "install_hint",
        "fields",
        "read_only",
        "roles",
    }
    assert [(e["display_name"], e["locality"]) for e in entries.values()] == [
        ("Ollama", "local"),
        ("llama.cpp", "local"),
        ("OpenRouter", "cloud"),
        ("OpenAI-compatible", "cloud"),
        ("Anthropic", "cloud"),
    ]
    assert entries["ollama"]["installed"] is True and entries["ollama"]["install_hint"] is None
    read_only = {
        name: {row["label"]: row["value"] for row in entry["read_only"]}
        for name, entry in entries.items()
    }
    assert read_only["ollama"]["Embedding model"] == "nomic-embed-text"
    assert read_only["ollama"]["Metadata model"] == "qwen-m"
    assert read_only["llamacpp"] == {
        "Embedding address": "http://llama.test:8080/v1",
        "Embedding model": "embed-gguf",
        "Chat model": "chat-gguf",
    }
    assert read_only["openrouter"]["Address"] == OPENROUTER_BASE_URL


def test_url_field_shape_and_default_source(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = by_provider(summary(monkeypatch, make_settings(local_backend="llamacpp")))
    assert field(entries["ollama"], "base_url") == {
        "id": "base_url",
        "label": "Address",
        "kind": "url",
        "required": True,
        "value": "http://ollama.test:11434",
        "source": "default",
        "locked": False,
        "lock_reason": None,
        "set": True,
        "last4": None,
        "saved_at": None,
        "state": None,
    }
    assert field(entries["llamacpp"], "chat_url")["value"] == "http://llama.test:8081/v1"


def test_environment_value_has_source_env_and_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    result = summary(monkeypatch, make_settings(explicit=frozenset({"llamacpp_chat_url"})))
    chat = field(by_provider(result)["llamacpp"], "chat_url")
    assert (chat["source"], chat["locked"]) == ("env", True)
    assert "LLAMACPP_CHAT_URL" in chat["lock_reason"]


def test_saved_value_has_source_saved(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(ollama_base_url="http://gpu-box.local:11434", local_backend="llamacpp")
    values = ProviderValues({"ollama_base_url": "http://gpu-box.local:11434"})
    result = build_connection_summary(settings, Path.cwd(), values)
    base = field(by_provider(result)["ollama"], "base_url")
    assert (base["source"], base["locked"], base["value"]) == (
        "saved",
        False,
        "http://gpu-box.local:11434",
    )


def test_ollama_address_locked_while_embeddings_use_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = summary(monkeypatch, make_settings(embed_provider="ollama"))
    base = field(by_provider(result)["ollama"], "base_url")
    assert base["locked"] is True
    assert "embeddings" in base["lock_reason"].lower()
    assert base["source"] == "default"


def test_key_field_when_unset_without_a_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    key = field(by_provider(summary(monkeypatch, make_settings()))["openrouter"], "api_key")
    assert (key["kind"], key["set"], key["source"], key["value"]) == (
        "secret",
        False,
        "none",
        None,
    )
    assert key["locked"] is True
    assert "OPENROUTER_API_KEY" in key["lock_reason"]


def test_key_from_the_keychain_shows_last_four_only(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(openrouter_api_key=SECRET)
    values = ProviderValues(
        {"openrouter_api_key": SECRET},
        key_saved_at={"openrouter": "2026-10-18T09:00:00Z"},
        keychain_available=True,
    )
    result = build_connection_summary(settings, Path.cwd(), values)
    assert result["keychain"] == "available"
    key = field(by_provider(result)["openrouter"], "api_key")
    assert (key["set"], key["source"], key["locked"]) == (True, "keychain", False)
    assert key["last4"] == SECRET[-4:]
    assert key["saved_at"] == "2026-10-18T09:00:00Z"
    assert key["value"] is None
    dumped = json.dumps(result)
    assert SECRET not in dumped
    assert not any(SECRET[i : i + 5] in dumped for i in range(len(SECRET) - 4))
    # Only the last four characters appear, and not as a longer run.
    assert dumped.count(SECRET[-4:]) >= 1


def test_key_from_the_environment_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(openrouter_api_key=SECRET, explicit=frozenset({"openrouter_api_key"}))
    key = field(by_provider(summary(monkeypatch, settings))["openrouter"], "api_key")
    assert (key["set"], key["source"], key["locked"]) == (True, "env", True)
    assert "OPENROUTER_API_KEY" in key["lock_reason"]
    assert key["last4"] == SECRET[-4:]


def test_short_key_shows_no_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    short = "sk-short-key"  # fewer than 16 characters
    settings = make_settings(openrouter_api_key=short, explicit=frozenset({"openrouter_api_key"}))
    result = summary(monkeypatch, settings)
    key = field(by_provider(result)["openrouter"], "api_key")
    assert key["set"] is True and key["last4"] is None
    assert short not in json.dumps(result)
    assert short[-4:] not in json.dumps(result)


@pytest.mark.parametrize("state", ["keychain-missing", "keychain-unreadable"])
def test_a_saved_key_that_cannot_be_used_reports_its_state(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    values = ProviderValues(
        key_saved_at={"openrouter": "2026-10-18T09:00:00Z"},
        key_problems={"openrouter": state},
        keychain_available=True,
    )
    result = build_connection_summary(make_settings(), Path.cwd(), values)
    key = field(by_provider(result)["openrouter"], "api_key")
    assert (key["set"], key["source"], key["state"]) == (False, "none", state)


def test_installed_flag_and_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a: None if name == "llama_index.llms.openai_like" else real(name, *a),
    )
    entries = by_provider(summary(monkeypatch, make_settings()))
    assert entries["llamacpp"]["installed"] is False
    assert entries["llamacpp"]["install_hint"] == "uv sync --extra llamacpp"
    assert entries["openrouter"]["install_hint"] == "uv sync --extra openrouter"


def test_a_registered_provider_gets_an_entry_with_no_other_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omrg.core.providers.llm import registry
    from omrg.core.providers.llm.connection import ConnectionDescriptor, ConnectionTarget

    fake = ConnectionDescriptor(
        display_name="Fake",
        locality="local",
        requires_module="json",
        extra=None,
        fields=(),
        read_only=lambda s: [],
        test_targets=lambda s: ConnectionTarget(()),
        models_target=lambda s: ConnectionTarget(()),
        parse_models=lambda p: [],
    )
    real = registry.describe_all()
    monkeypatch.setattr(registry, "describe_all", lambda: {**real, "fake": fake})
    result = summary(monkeypatch, make_settings())
    assert [e["provider"] for e in result["connections"]] == [*PROVIDERS, "fake"]
    assert set(build_connection_targets(make_settings())) == {*PROVIDERS, "fake"}


def test_compose_connections_names_no_provider() -> None:
    source = (Path(compose.__file__).parent / "compose_connections.py").read_text()
    for name in PROVIDERS:
        assert f'== "{name}"' not in source
        assert f'"{name}":' not in source


def test_documented_scenario_llamacpp_embeds_and_ollama_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = summary(
        monkeypatch,
        make_settings(
            embed_provider="local",
            local_backend="llamacpp",
            answer_provider="ollama",
            extraction_mode="disabled",
        ),
    )
    assert roles(result) == {
        "ollama": ["answers"],
        "llamacpp": ["embeddings"],
        "openrouter": [],
        **CHAT_ONLY,
    }


def test_embedding_role_cloud_scheme_uses_the_cloud_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cloud = summary(
        monkeypatch,
        make_settings(embed_provider="cloud", answer_enabled=False, extraction_mode="disabled"),
    )
    assert roles(cloud) == {
        "ollama": [],
        "llamacpp": [],
        "openrouter": ["embeddings"],
        **CHAT_ONLY,
    }


@pytest.mark.parametrize("provider", EMBEDDING_PROVIDERS)
def test_embedding_role_follows_the_effective_provider(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    flat = summary(
        monkeypatch,
        make_settings(embed_provider=provider, answer_enabled=False, extraction_mode="disabled"),
    )
    assert roles(flat)[provider] == ["embeddings"]
    local = summary(
        monkeypatch,
        make_settings(
            embed_provider="local",
            local_backend="ollama" if provider == "openrouter" else provider,
            answer_enabled=False,
            extraction_mode="disabled",
        ),
    )
    assert "embeddings" in roles(local)["ollama" if provider == "openrouter" else provider]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_answers_role_follows_answer_provider(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    result = summary(
        monkeypatch,
        make_settings(answer_provider=provider, extraction_mode="disabled", local_backend="ollama"),
    )
    holders = [name for name, held in roles(result).items() if "answers" in held]
    assert holders == [provider]


def test_answers_role_is_absent_when_answering_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = summary(monkeypatch, make_settings(answer_enabled=False, extraction_mode="disabled"))
    assert all("answers" not in held for held in roles(result).values())


@pytest.mark.parametrize(
    ("alias", "backend_field", "expected"),
    [
        ("local", "local_backend", "llamacpp"),
        ("cloud", "cloud_backend", "openrouter"),
    ],
)
def test_metadata_role_resolves_the_local_and_cloud_aliases(
    monkeypatch: pytest.MonkeyPatch, alias: str, backend_field: str, expected: str
) -> None:
    result = summary(
        monkeypatch,
        make_settings(
            metadata_llm_provider=alias,
            local_backend="llamacpp",
            cloud_backend="openrouter",
            embed_provider="local",
            answer_enabled=False,
        ),
    )
    assert "metadata" in roles(result)[expected]


@pytest.mark.parametrize("mode", ["llamaindex", "local"])
def test_metadata_role_present_for_llm_backed_modes(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    result = summary(monkeypatch, make_settings(extraction_mode=mode, answer_enabled=False))
    assert "metadata" in roles(result)["ollama"]


@pytest.mark.parametrize("mode", ["disabled", "keyword"])
def test_metadata_role_absent_when_extraction_calls_no_model(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    result = summary(monkeypatch, make_settings(extraction_mode=mode))
    assert all("metadata" not in held for held in roles(result).values())


@pytest.mark.parametrize("provider", EMBEDDING_PROVIDERS)
def test_metadata_role_follows_a_mode_that_names_its_provider(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    result = summary(
        monkeypatch,
        make_settings(
            extraction_mode=provider,
            metadata_llm_provider="cloud" if provider != "openrouter" else "local",
            answer_enabled=False,
        ),
    )
    assert [name for name, held in roles(result).items() if "metadata" in held] == [provider]


@pytest.mark.parametrize(
    ("verify_provider", "expected"),
    [("cloud", "openrouter"), ("local", "llamacpp"), ("ollama", "ollama"), ("", "openrouter")],
)
def test_verification_role_resolves_aliases_and_literal_names(
    monkeypatch: pytest.MonkeyPatch, verify_provider: str, expected: str
) -> None:
    result = summary(
        monkeypatch,
        make_settings(
            verify_claims=True,
            verify_provider=verify_provider,
            verify_model="judge-1",
            local_backend="llamacpp",
            extraction_mode="disabled",
            answer_provider="ollama",
        ),
    )
    holders = [name for name, held in roles(result).items() if "verification" in held]
    assert holders == [expected]


def test_verification_role_needs_answering_and_the_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    off = summary(monkeypatch, make_settings(verify_claims=False, extraction_mode="disabled"))
    assert all("verification" not in held for held in roles(off).values())
    no_answers = summary(
        monkeypatch,
        make_settings(verify_claims=True, answer_enabled=False, extraction_mode="disabled"),
    )
    assert all("verification" not in held for held in roles(no_answers).values())


def test_an_unknown_provider_name_is_listed_nowhere(monkeypatch: pytest.MonkeyPatch) -> None:
    result = summary(
        monkeypatch, make_settings(answer_provider="mystery", extraction_mode="disabled")
    )
    assert all("answers" not in held for held in roles(result).values())


@pytest.mark.parametrize(
    "placement",
    list(itertools.product(PROVIDERS[:3], PROVIDERS, PROVIDERS)),
)
def test_every_role_provider_combination(
    monkeypatch: pytest.MonkeyPatch, placement: tuple[str, str, str]
) -> None:
    """Embeddings, answers and verification each land on exactly one provider."""
    embed, answer, verify = placement
    result = summary(
        monkeypatch,
        make_settings(
            embed_provider=embed,
            answer_provider=answer,
            verify_claims=True,
            verify_provider=verify,
            extraction_mode="disabled",
        ),
    )
    held = roles(result)
    for role, provider in (("embeddings", embed), ("answers", answer), ("verification", verify)):
        assert [name for name, r in held.items() if role in r] == [provider]


def test_connection_targets_carry_the_key_server_side_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    targets = build_connection_targets(make_settings(openrouter_api_key=SECRET))
    assert targets["ollama"].urls == ("http://ollama.test:11434/api/tags",)
    assert targets["llamacpp"].urls == (
        "http://llama.test:8080/v1/models",
        "http://llama.test:8081/v1/models",
    )
    assert targets["openrouter"].urls == (f"{OPENROUTER_BASE_URL}/key",)
    assert targets["openrouter"].headers == {"Authorization": f"Bearer {SECRET}"}
    assert SECRET not in repr(targets)
    assert build_connection_targets(make_settings())["openrouter"].urls == ()
    blank = build_connection_targets(make_settings(ollama_base_url="  "))
    assert blank["ollama"].urls == ()


class _OllamaProfileCatalogue:
    def list_profiles(self) -> list[dict[str, Any]]:
        return [{"profile_id": "p", "embed_provider": "ollama", "embed_model": "nomic"}]


def test_ollama_address_is_locked_when_a_profile_uses_ollama_embeddings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(embed_provider="openrouter")
    monkeypatch.setattr(compose, "get_settings", lambda: settings)
    open_field = field(by_provider(compose.connection_summary())["ollama"], "base_url")
    assert open_field["locked"] is False
    result = compose.connection_summary(catalogue=_OllamaProfileCatalogue())
    locked = field(by_provider(result)["ollama"], "base_url")
    assert locked["locked"] is True
    assert "Embeddings use this address" in locked["lock_reason"]


def test_a_saved_ollama_address_does_not_show_while_a_profile_uses_ollama_embeddings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(embed_provider="openrouter")
    monkeypatch.setattr(compose, "get_settings", lambda: settings)
    values = ProviderValues({"ollama_base_url": "http://saved:11434"})
    result = compose.connection_summary(values, _OllamaProfileCatalogue())
    shown = field(by_provider(result)["ollama"], "base_url")
    assert shown["value"] == settings.ollama_base_url
