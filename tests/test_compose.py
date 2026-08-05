"""Tests for the composition root (``rag_mcp.compose``) and provider helpers.

Covers the config-composition-root spec scenarios:
- ``compose.build_embed_model`` / ``build_llm_model`` construct providers
  by resolving lazy registries against the resolved ``Settings``.
- ``compose.build_reranker`` constructs the DI reranker wired to
  ``settings.retrieval.rerank_model``.
- ``compose.ensure_runtime_setup`` assigns the LlamaIndex global
  ``Settings.embed_model`` exactly once per process.
- ``core.providers.common.get_embed_endpoint`` returns the correct
  connection tuple for each provider scheme.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rag_mcp.config import Settings
from rag_mcp.compose import (
    build_embed_model,
    build_llm_model,
    build_reranker,
    ensure_runtime_setup,
    reset_runtime_setup,
)
from rag_mcp.core.providers.common import get_embed_endpoint


def _settings(**overrides) -> Settings:
    """Build a fresh Settings with sensible defaults and no .env."""
    base = {
        "embed_provider": "local",
        "local_backend": "ollama",
        "embed_model": "nomic-embed-text",
        "ollama_base_url": "http://localhost:11434",
        "embed_batch_size": 64,
        "metadata_llm_provider": "local",
        "ollama_classify_model": "qwen3:0.6b",
        "ollama_classify_timeout": 30.0,
        "rerank_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


# ── build_embed_model ───────────────────────────────────────────────────────


def test_build_embed_model_ollama() -> None:
    """Ollama provider returns an OllamaEmbedding via the registry."""
    settings = _settings()
    with patch("llama_index.embeddings.ollama.OllamaEmbedding") as mock_cls:
        build_embed_model(settings)
        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["model_name"] == "nomic-embed-text"
        assert kwargs["base_url"] == "http://localhost:11434"
        assert kwargs["embed_batch_size"] == 64


def test_build_embed_model_llamacpp_two_tier() -> None:
    """EMBED_PROVIDER=local + LOCAL_BACKEND=llamacpp resolves llamacpp."""
    settings = _settings(local_backend="llamacpp", llamacpp_embed_model="t.gguf")
    with patch("llama_index.embeddings.openai.OpenAIEmbedding") as mock_cls:
        build_embed_model(settings)
        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["model"] == "t.gguf"
        assert kwargs["api_base"] == "http://localhost:8080/v1"


def test_build_embed_model_validates_unknown_provider() -> None:
    """Unknown provider values are clamped by the Settings validator.

    The Settings model falls back to ``local`` with a warning before
    compose ever resolves a registry — so compose itself cannot see an
    unregistered provider through a validated Settings object.  (The
    registry-level ``KeyError`` path is covered in
    ``test_registry_contract.py``.)
    """
    settings = _settings(embed_provider="bogus", local_backend="bogus")
    assert settings.embed_provider == "local"
    assert settings.local_backend == "llamacpp"


# ── build_llm_model ─────────────────────────────────────────────────────────


def test_build_llm_model_local_ollama() -> None:
    """METADATA_LLM_PROVIDER=local + LOCAL_BACKEND=ollama builds an Ollama."""
    settings = _settings()
    with patch("llama_index.llms.ollama.Ollama") as mock_cls:
        build_llm_model(settings)
        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["model"] == "qwen3:0.6b"
        assert kwargs["base_url"] == "http://localhost:11434"


def test_build_llm_model_cloud_openrouter_not_registered() -> None:
    """Cloud openrouter LLM is served by the extractor's HTTP path.

    The LLM provider registry deliberately registers only ``ollama`` and
    ``llamacpp`` (design: ``core/providers/llm/``).  OpenRouter chat
    extraction lives in ``core.metadata.extractor`` as a raw HTTP call
    (``_extract_openrouter_chat_async``), so ``build_llm_model`` with
    ``CLOUD_BACKEND=openrouter`` must raise a helpful ``KeyError``.
    """
    settings = _settings(
        metadata_llm_provider="cloud",
        cloud_backend="openrouter",
    )
    with pytest.raises(KeyError, match="openrouter"):
        build_llm_model(settings)


# ── build_reranker ──────────────────────────────────────────────────────────


def test_build_reranker_wires_model_id() -> None:
    """The DI reranker must be constructed with settings.retrieval.rerank_model."""
    settings = _settings(rerank_model="custom/rerank-model")
    reranker = build_reranker(settings)
    assert reranker._model_id == "custom/rerank-model"


# ── ensure_runtime_setup ────────────────────────────────────────────────────


def test_ensure_runtime_setup_assigns_embed_model_once() -> None:
    """ensure_runtime_setup assigns LlamaIndex Settings.embed_model once."""
    from llama_index.core import Settings as LlamaIndexSettings
    from llama_index.core.embeddings import MockEmbedding

    settings = _settings()
    reset_runtime_setup()

    mock_model = MockEmbedding(embed_dim=384)
    with patch("rag_mcp.compose.build_embed_model", return_value=mock_model):
        ensure_runtime_setup()
        assert LlamaIndexSettings.embed_model is mock_model

        # Second call must not rebuild.
        with patch("rag_mcp.compose.build_embed_model") as rebuild:
            ensure_runtime_setup()
            rebuild.assert_not_called()
    reset_runtime_setup()


def test_ensure_runtime_setup_degrades_gracefully() -> None:
    """A construction failure must warn, not crash."""
    from llama_index.core import Settings as LlamaIndexSettings

    settings = _settings()
    reset_runtime_setup()

    with patch(
        "rag_mcp.compose.build_embed_model",
        side_effect=ImportError("optional dep missing"),
    ):
        ensure_runtime_setup()  # must not raise
    reset_runtime_setup()


# ── core.providers.common.get_embed_endpoint ────────────────────────────────


def test_get_embed_endpoint_ollama() -> None:
    """Ollama: (base_url, embed_model, no key)."""
    settings = _settings()
    endpoint = get_embed_endpoint(settings)
    assert endpoint == (
        "http://localhost:11434", "nomic-embed-text", "",
    )


def test_get_embed_endpoint_llamacpp() -> None:
    """llamacpp: (embed_url, embed_model, 'no-key')."""
    settings = _settings(
        local_backend="llamacpp",
        llamacpp_embed_url="http://llm:8080/v1",
        llamacpp_embed_model="t.gguf",
    )
    endpoint = get_embed_endpoint(settings)
    assert endpoint == ("http://llm:8080/v1", "t.gguf", "no-key")


def test_get_embed_endpoint_openrouter() -> None:
    """openrouter: fixed api_base, embed_model, api_key."""
    settings = _settings(
        embed_provider="cloud",
        cloud_backend="openrouter",
        openrouter_embed_model="text-embedding-3-small",
        openrouter_api_key="sk-test",
    )
    endpoint = get_embed_endpoint(settings)
    assert endpoint == (
        "https://openrouter.ai/api/v1",
        "text-embedding-3-small",
        "sk-test",
    )
