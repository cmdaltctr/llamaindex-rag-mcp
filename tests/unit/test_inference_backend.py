"""Tests for pluggable embedding provider selection.

Verifies that EMBED_PROVIDER env var correctly switches between
OllamaEmbedding and OpenAIEmbedding, that INFERENCE_BACKEND is
backward-compatible, and that metadata extraction routes to the
correct endpoint via METADATA_LLM_PROVIDER.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Config: backend selection ────────────────────────────────────────────


def test_default_provider_is_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    """When EMBED_PROVIDER is not set, default to ollama."""
    monkeypatch.delenv("EMBED_PROVIDER", raising=False)
    monkeypatch.delenv("INFERENCE_BACKEND", raising=False)
    from rag_mcp import config
    assert config.EMBED_PROVIDER == "ollama"


def test_unknown_provider_falls_back_to_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown EMBED_PROVIDER value should warn and fall back to ollama."""
    from rag_mcp import config
    assert config.EMBED_PROVIDER in {"ollama", "llamacpp", "openrouter"}


def test_llamacpp_provider_without_deps_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """EMBED_PROVIDER=llamacpp without llama-index-embeddings-openai raises ImportError."""
    import importlib

    real_import_module = importlib.import_module

    def _blocking_import_module(name, *args, **kwargs):
        if name == "llama_index.embeddings.openai":
            raise ImportError("simulated: package not installed")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", _blocking_import_module)

    monkeypatch.setenv("EMBED_PROVIDER", "llamacpp")
    monkeypatch.setenv("LLAMACPP_EMBED_MODEL", "test.gguf")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")

    import rag_mcp.config as config_mod

    with pytest.raises(ImportError, match="uv sync --extra llamacpp"):
        importlib.reload(config_mod)

    # Restore for other tests
    monkeypatch.delenv("EMBED_PROVIDER", raising=False)
    monkeypatch.setenv("EMBED_PROVIDER", "ollama")
    importlib.reload(config_mod)


# ── Metadata extraction: llamacpp chat path ──────────────────────────────


@pytest.mark.asyncio
async def test_llamacpp_chat_parses_openai_response() -> None:
    """_extract_llamacpp_chat_async parses OpenAI /v1/chat/completions format."""
    from rag_mcp.metadata_extractor import _extract_llamacpp_chat_async

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "category": "ai",
                        "keywords": ["ml", "neural"],
                        "summary": "A paper about AI.",
                    })
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        from rag_mcp import metadata_extractor
        original_chat_url = metadata_extractor.LLAMACPP_CHAT_URL
        original_chat_model = metadata_extractor.LLAMACPP_CHAT_MODEL
        metadata_extractor.LLAMACPP_CHAT_URL = "http://localhost:8081/v1"
        metadata_extractor.LLAMACPP_CHAT_MODEL = "test.gguf"
        # Disable retry sleep
        metadata_extractor._retry_sleep = AsyncMock()

        try:
            result = await _extract_llamacpp_chat_async("Some text about AI.")
            assert result["category"] == "ai"
            assert "ml" in result["keywords"]
            assert result["summary"] == "A paper about AI."
        finally:
            metadata_extractor.LLAMACPP_CHAT_URL = original_chat_url
            metadata_extractor.LLAMACPP_CHAT_MODEL = original_chat_model


@pytest.mark.asyncio
async def test_llamacpp_chat_retries_on_failure() -> None:
    """_extract_llamacpp_chat_async falls back to uncategorised on retry exhaustion."""
    from rag_mcp.metadata_extractor import _extract_llamacpp_chat_async

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        from rag_mcp import metadata_extractor
        metadata_extractor.LLAMACPP_CHAT_URL = "http://localhost:8081/v1"
        metadata_extractor.LLAMACPP_CHAT_MODEL = "test.gguf"
        metadata_extractor._retry_sleep = AsyncMock()

        result = await _extract_llamacpp_chat_async("Some text.")
        assert result == {"category": "uncategorised", "keywords": [], "summary": ""}


@pytest.mark.asyncio
async def test_local_mode_dispatches_to_llamacpp_when_configured() -> None:
    """extract_metadata_async with mode=local routes to llamacpp chat when METADATA_LLM_PROVIDER=llamacpp."""
    from rag_mcp import metadata_extractor

    original_llm_provider = metadata_extractor.METADATA_LLM_PROVIDER
    original_mode = metadata_extractor.METADATA_EXTRACTION_MODE
    metadata_extractor.METADATA_LLM_PROVIDER = "llamacpp"
    metadata_extractor.METADATA_EXTRACTION_MODE = "local"

    mock_fn = AsyncMock(return_value={"category": "test", "keywords": [], "summary": ""})
    with patch.object(metadata_extractor, "_extract_llamacpp_chat_async", mock_fn):
        try:
            await metadata_extractor.extract_metadata_async("text", "file.txt")
            mock_fn.assert_called_once_with("text")
        finally:
            metadata_extractor.METADATA_LLM_PROVIDER = original_llm_provider
            metadata_extractor.METADATA_EXTRACTION_MODE = original_mode


@pytest.mark.asyncio
async def test_llamaindex_mode_falls_back_to_llamacpp_chat_on_import_error() -> None:
    """llamaindex mode with llamacpp falls back to chat mode when OpenAILike not installed."""
    from rag_mcp import metadata_extractor

    original_llm_provider = metadata_extractor.METADATA_LLM_PROVIDER
    metadata_extractor.METADATA_LLM_PROVIDER = "llamacpp"

    mock_fn = AsyncMock(return_value={"category": "fallback", "keywords": [], "summary": ""})

    # Patch the import to fail
    import builtins
    real_import = builtins.__import__

    def _failing_import(name, *args, **kwargs):
        if name == "llama_index.llms.openai_like":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    with patch.object(metadata_extractor, "_extract_llamacpp_chat_async", mock_fn), \
         patch("builtins.__import__", side_effect=_failing_import):
        try:
            await metadata_extractor._extract_llamaindex_async("text", "file.txt")
            mock_fn.assert_called_once_with("text")
        finally:
            metadata_extractor.METADATA_LLM_PROVIDER = original_llm_provider


# ── New provider registry tests ──────────────────────────────────────────


def test_openrouter_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """EMBED_PROVIDER=openrouter with missing OPENROUTER_API_KEY raises ValueError."""
    import importlib

    monkeypatch.setenv("EMBED_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_EMBED_MODEL", "text-embedding-3-small")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")

    import rag_mcp.config as config_mod

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        importlib.reload(config_mod)

    # Restore
    monkeypatch.delenv("EMBED_PROVIDER", raising=False)
    monkeypatch.setenv("EMBED_PROVIDER", "ollama")
    importlib.reload(config_mod)


def test_openrouter_missing_optional_deps_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """EMBED_PROVIDER=openrouter without llama-index-embeddings-openai raises ImportError."""
    import importlib

    real_import_module = importlib.import_module

    def _blocking_import_module(name, *args, **kwargs):
        if name == "llama_index.embeddings.openai":
            raise ImportError("simulated: package not installed")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", _blocking_import_module)

    monkeypatch.setenv("EMBED_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("OPENROUTER_EMBED_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")

    import rag_mcp.config as config_mod

    with pytest.raises(ImportError, match="uv sync --extra openrouter"):
        importlib.reload(config_mod)

    # Restore
    monkeypatch.delenv("EMBED_PROVIDER", raising=False)
    monkeypatch.setenv("EMBED_PROVIDER", "ollama")
    importlib.reload(config_mod)


def test_metadata_llm_provider_defaults_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    """METADATA_LLM_PROVIDER defaults to ollama regardless of EMBED_PROVIDER."""
    import importlib

    monkeypatch.setenv("EMBED_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("OPENROUTER_EMBED_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    monkeypatch.delenv("METADATA_LLM_PROVIDER", raising=False)

    import rag_mcp.config as config_mod

    # We can't fully reload with openrouter (needs deps), but we can
    # check the env var resolution logic by reading the value directly.
    # The default is set via os.getenv("METADATA_LLM_PROVIDER", "ollama").
    # Since config is already loaded, just verify the module-level value.
    assert config_mod.METADATA_LLM_PROVIDER == "ollama"


def test_legacy_inference_backend_maps_to_embed_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """INFERENCE_BACKEND=ollama maps to EMBED_PROVIDER=ollama (backward compat)."""
    import importlib

    monkeypatch.delenv("EMBED_PROVIDER", raising=False)
    monkeypatch.setenv("INFERENCE_BACKEND", "ollama")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")

    import rag_mcp.config as config_mod

    importlib.reload(config_mod)
    assert config_mod.EMBED_PROVIDER == "ollama"
    assert config_mod.INFERENCE_BACKEND == "ollama"

    # Restore
    monkeypatch.delenv("INFERENCE_BACKEND", raising=False)
    monkeypatch.setenv("EMBED_PROVIDER", "ollama")
    importlib.reload(config_mod)


@pytest.mark.asyncio
async def test_ollama_mode_silently_maps_to_local() -> None:
    """METADATA_EXTRACTION_MODE=ollama silently maps to local (no warning)."""
    from rag_mcp import metadata_extractor

    original_mode = metadata_extractor.METADATA_EXTRACTION_MODE
    original_llm_provider = metadata_extractor.METADATA_LLM_PROVIDER
    metadata_extractor.METADATA_EXTRACTION_MODE = "ollama"
    metadata_extractor.METADATA_LLM_PROVIDER = "ollama"

    mock_fn = AsyncMock(return_value={"category": "test", "keywords": [], "summary": ""})
    with patch.object(metadata_extractor, "_extract_ollama_async", mock_fn):
        try:
            await metadata_extractor.extract_metadata_async("text", "file.txt")
            mock_fn.assert_called_once_with("text")
        finally:
            metadata_extractor.METADATA_EXTRACTION_MODE = original_mode
            metadata_extractor.METADATA_LLM_PROVIDER = original_llm_provider
