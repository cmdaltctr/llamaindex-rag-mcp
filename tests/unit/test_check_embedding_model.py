"""Check model: one probe embedding for a provider and a model (ADR-081, design D8).

Fake embedders replace the registry builders, and a fake model list replaces
the llama.cpp ``/models`` request. No network call happens.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from omrg import compose_embedding
from omrg.compose_embedding import (
    UnknownEmbeddingProviderError,
    check_embedding_model,
    provider_listing,
    server_default_identity,
)
from omrg.config import Settings
from omrg.core.settings import EmbeddingSettings

KEY = "sk-or-fake-key"


def _settings(**extra: Any) -> Settings:
    values: dict[str, Any] = {
        "embed_provider": "llamacpp",
        "embed_model": "host-ollama",
        "llamacpp_embed_model": "host-llamacpp",
        "llamacpp_embed_url": "http://llama.example:8081/v1",
        "openrouter_api_key": KEY,
        "openrouter_embed_model": "host/openrouter",
        **extra,
    }
    return Settings(_env_file=None, **values)


class _Embedder:
    def __init__(self, vector: list[float] | None = None, error: Exception | None = None) -> None:
        self.vector = vector if vector is not None else [1.0]
        self.error = error
        self.texts: list[str] = []

    def get_text_embedding(self, text: str) -> list[float]:
        self.texts.append(text)
        if self.error is not None:
            raise self.error
        return self.vector


def _unit(size: int) -> list[float]:
    return [1.0 / math.sqrt(size)] * size


@pytest.fixture
def builders(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace the registry lookup. ``seen`` records every ``(provider, model)`` built."""
    state: dict[str, Any] = {"embedder": _Embedder(_unit(4)), "seen": [], "missing": {}}

    def get(name: str):
        if name in state["missing"]:
            raise ImportError(state["missing"][name])
        if name not in ("ollama", "llamacpp", "openrouter"):
            raise KeyError(f"Unknown embedding provider {name!r}.")

        def build(settings: Any, *, model: str | None = None) -> Any:
            state["seen"].append((name, model))
            return state["embedder"]

        return build

    monkeypatch.setattr(compose_embedding.embed_registry, "get", get)
    return state


def _check(provider: str, model: str, **kw: Any) -> dict[str, Any]:
    return check_embedding_model(provider, model, settings=kw.pop("settings", _settings()), **kw)


def test_a_unit_vector_passes_and_reports_its_size(builders: dict[str, Any]) -> None:
    builders["embedder"] = _Embedder(_unit(1024))
    result = _check("ollama", "nomic-embed-text")
    assert result["ok"] is True and result["dimensions"] == 1024
    assert result["norm"] == pytest.approx(1.0)
    assert result["reason"] is None
    assert builders["seen"] == [("ollama", "nomic-embed-text")]
    assert builders["embedder"].texts == ["OMRG model check"]


def test_a_llamacpp_name_that_the_server_does_not_list_fails_before_the_probe(
    builders: dict[str, Any],
) -> None:
    asked: list[str] = []

    def served(url: str) -> list[str]:
        asked.append(url)
        return ["model-a.gguf", "/models/other.gguf"]

    result = _check("llamacpp", "model-b.gguf", list_models=served)
    assert result["ok"] is False and result["dimensions"] is None
    assert "does not serve model-b.gguf" in result["reason"]
    assert "model-a.gguf" in result["reason"] and "other.gguf" in result["reason"]
    assert asked == ["http://llama.example:8081/v1"]
    assert builders["embedder"].texts == []


def test_a_llamacpp_name_matches_the_served_id_or_its_file_name(builders: dict[str, Any]) -> None:
    for served in (["model-a.gguf"], ["/models/model-a.gguf"]):
        assert _check("llamacpp", "model-a.gguf", list_models=lambda url, s=served: s)["ok"]


def test_an_unreachable_llamacpp_server_fails_with_a_reason(builders: dict[str, Any]) -> None:
    def down(url: str) -> list[str]:
        raise OSError(f"connection refused {url} {KEY}")

    result = _check("llamacpp", "m", list_models=down)
    assert result["ok"] is False and "llama.cpp" in result["reason"]
    assert KEY not in result["reason"]
    assert builders["embedder"].texts == []


def test_only_llamacpp_lists_models(builders: dict[str, Any]) -> None:
    def forbidden(url: str) -> list[str]:
        raise AssertionError("must not list models")

    assert _check("ollama", "m", list_models=forbidden)["ok"]
    assert _check("openrouter", "m", list_models=forbidden)["ok"]


def test_a_probe_error_fails_with_the_text_and_without_the_key(builders: dict[str, Any]) -> None:
    builders["embedder"] = _Embedder(error=RuntimeError(f"model not found, key {KEY}"))
    result = _check("openrouter", "no-such")
    assert result["ok"] is False
    assert "model not found" in result["reason"]
    assert KEY not in result["reason"] and KEY[:8] not in result["reason"]


def test_a_custom_redactor_runs_on_the_reason(builders: dict[str, Any]) -> None:
    builders["embedder"] = _Embedder(error=RuntimeError("boom secret-x"))
    result = _check("ollama", "m", redact=lambda text: text.replace("secret-x", "***"))
    assert "secret-x" not in result["reason"] and "boom" in result["reason"]


def test_a_vector_of_the_wrong_length_fails_when_the_norm_guard_is_on(
    builders: dict[str, Any],
) -> None:
    builders["embedder"] = _Embedder([1.4])
    result = _check("ollama", "m")
    assert result["ok"] is False
    assert result["dimensions"] == 1 and result["norm"] == pytest.approx(1.4)
    assert "ingestion would refuse" in result["reason"]


def test_a_vector_of_the_wrong_length_passes_when_the_norm_guard_is_off(
    builders: dict[str, Any],
) -> None:
    builders["embedder"] = _Embedder([1.4])
    off = _settings(embedding=EmbeddingSettings(norm_guard_enabled=False))
    assert _check("ollama", "m", settings=off)["ok"] is True


def test_an_empty_vector_fails(builders: dict[str, Any]) -> None:
    builders["embedder"] = _Embedder([])
    result = _check("ollama", "m")
    assert result["ok"] is False and "no vector" in result["reason"].lower()


def test_a_missing_extra_names_the_extra(builders: dict[str, Any]) -> None:
    builders["missing"]["openrouter"] = (
        "Provider 'openrouter' requires an optional dependency.\n"
        "  Install it with:  uv sync --extra openrouter"
    )
    result = _check("openrouter", "m")
    assert result["ok"] is False
    assert "uv sync --extra openrouter" in result["reason"]


def test_a_builder_error_is_a_failed_check(builders: dict[str, Any], monkeypatch: Any) -> None:
    def get(name: str):
        def build(settings: Any, *, model: str | None = None) -> Any:
            raise ValueError(f"OPENROUTER_API_KEY is required {KEY}")

        return build

    monkeypatch.setattr(compose_embedding.embed_registry, "get", get)
    result = _check("openrouter", "m")
    assert result["ok"] is False and "required" in result["reason"] and KEY not in result["reason"]


def test_an_unknown_provider_is_refused(builders: dict[str, Any]) -> None:
    with pytest.raises(UnknownEmbeddingProviderError):
        _check("nope", "m")


def test_a_blank_model_is_a_failed_check(builders: dict[str, Any]) -> None:
    result = _check("ollama", "   ")
    assert result["ok"] is False and "model" in result["reason"].lower()
    assert builders["seen"] == []


# ── Provider listing and the server default ──────────────────────────────


def test_provider_listing_reports_availability_and_the_missing_extra(
    builders: dict[str, Any],
) -> None:
    builders["missing"]["llamacpp"] = "Provider 'llamacpp' requires. uv sync --extra llamacpp"
    monkey_names = ["ollama", "llamacpp", "openrouter"]
    listing = {item["name"]: item for item in provider_listing(names=monkey_names)}
    assert listing["ollama"] == {"name": "ollama", "available": True, "reason": None}
    assert listing["llamacpp"]["available"] is False
    assert "--extra llamacpp" in listing["llamacpp"]["reason"]


def test_the_server_default_is_the_concrete_provider_and_its_model() -> None:
    identity = server_default_identity(_settings())
    assert (identity.provider, identity.model) == ("llamacpp", "host-llamacpp")
    cloud = server_default_identity(_settings(embed_provider="openrouter"))
    assert (cloud.provider, cloud.model) == ("openrouter", "host/openrouter")
