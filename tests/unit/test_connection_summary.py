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
from omrg.compose_connections import OPENROUTER_BASE_URL, build_connection_targets
from omrg.config import Settings
from omrg.core.answer.settings import AnswerSettings
from omrg.core.metadata.settings import MetadataSettings

SECRET = "sk-or-v1-SECRETVALUE0123456789"  # noqa: S105 - fake key for redaction tests
PROVIDERS = ("ollama", "llamacpp", "openrouter")


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
    return Settings(_env_file=None, **fields)


def summary(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> dict[str, Any]:
    monkeypatch.setattr(compose, "get_settings", lambda: settings)
    return compose.connection_summary()


def roles(result: dict[str, Any]) -> dict[str, list[str]]:
    return {entry["provider"]: entry["roles"] for entry in result["connections"]}


def test_entry_shape_and_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    result = summary(monkeypatch, make_settings())
    assert result["config_dir"] == str(tmp_path.resolve())
    assert [entry["provider"] for entry in result["connections"]] == list(PROVIDERS)
    by_name = {entry["provider"]: entry for entry in result["connections"]}
    assert by_name["ollama"]["urls"] == [{"label": "base", "url": "http://ollama.test:11434"}]
    assert by_name["llamacpp"]["urls"] == [
        {"label": "embeddings", "url": "http://llama.test:8080/v1"},
        {"label": "chat", "url": "http://llama.test:8081/v1"},
    ]
    assert by_name["openrouter"]["urls"] == [{"label": "base", "url": OPENROUTER_BASE_URL}]
    assert OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
    names = {
        entry["provider"]: {m["label"]: m["name"] for m in entry["models"]}
        for entry in result["connections"]
    }
    assert names["ollama"]["embeddings"] == "nomic-embed-text"
    assert names["ollama"]["chat"] == "qwen-m"
    assert names["llamacpp"] == {"embeddings": "embed-gguf", "chat": "chat-gguf"}
    assert (
        names["openrouter"]["embeddings"] == "or-embed" and names["openrouter"]["chat"] == "or-chat"
    )
    assert set(by_name["ollama"]) == {"provider", "urls", "models", "key_set", "roles"}


def test_key_set_is_a_boolean_and_the_value_never_appears(monkeypatch: pytest.MonkeyPatch) -> None:
    unset = summary(monkeypatch, make_settings())
    assert {e["provider"]: e["key_set"] for e in unset["connections"]} == {
        "ollama": False,
        "llamacpp": False,
        "openrouter": False,
    }
    with_key = summary(monkeypatch, make_settings(openrouter_api_key=SECRET))
    flags = {e["provider"]: e["key_set"] for e in with_key["connections"]}
    assert flags == {"ollama": False, "llamacpp": False, "openrouter": True}
    assert SECRET not in json.dumps(with_key)
    assert SECRET[:8] not in json.dumps(with_key)


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
    assert roles(result) == {"ollama": ["answers"], "llamacpp": ["embeddings"], "openrouter": []}


def test_embedding_role_cloud_scheme_uses_the_cloud_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cloud = summary(
        monkeypatch,
        make_settings(embed_provider="cloud", answer_enabled=False, extraction_mode="disabled"),
    )
    assert roles(cloud) == {"ollama": [], "llamacpp": [], "openrouter": ["embeddings"]}


@pytest.mark.parametrize("provider", PROVIDERS)
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
    entry = next(e for e in result["connections"] if e["provider"] == provider)
    assert {"label": "answers", "name": "answer-model"} in entry["models"]


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


@pytest.mark.parametrize("provider", PROVIDERS)
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
    entry = next(e for e in result["connections"] if e["provider"] == expected)
    assert {"label": "verification", "name": "judge-1"} in entry["models"]


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
    list(itertools.product(PROVIDERS, repeat=3)),
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
    assert targets["openrouter"].urls == (f"{OPENROUTER_BASE_URL}/models",)
    assert targets["openrouter"].headers == {"Authorization": f"Bearer {SECRET}"}
    assert SECRET not in repr(targets)
    assert build_connection_targets(make_settings())["openrouter"].urls == ()
    blank = build_connection_targets(make_settings(ollama_base_url="  "))
    assert blank["ollama"].urls == ()
