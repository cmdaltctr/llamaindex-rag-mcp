"""Tests for pluggable embedding and metadata LLM provider selection.

Verifies that EMBED_PROVIDER and METADATA_LLM_PROVIDER env vars correctly
switch between local/cloud categories, and that LOCAL_BACKEND/CLOUD_BACKEND
sub-providers resolve to the correct LlamaIndex classes.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Config: provider selection ───────────────────────────────────────────


def test_default_provider_is_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """When EMBED_PROVIDER is not set, config defaults to local."""
    import os
    monkeypatch.delenv("EMBED_PROVIDER", raising=False)
    assert os.getenv("EMBED_PROVIDER", "local") == "local"


def test_default_local_backend_is_llamacpp(monkeypatch: pytest.MonkeyPatch) -> None:
    """When LOCAL_BACKEND is not set, config defaults to llamacpp."""
    import os
    monkeypatch.delenv("LOCAL_BACKEND", raising=False)
    assert os.getenv("LOCAL_BACKEND", "llamacpp") == "llamacpp"


def test_unknown_provider_falls_back_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown EMBED_PROVIDER value should warn and fall back to local."""
    from rag_mcp import config
    assert config.EMBED_PROVIDER in {"local", "cloud"}


def test_local_llamacpp_without_deps_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """EMBED_PROVIDER=local + LOCAL_BACKEND=llamacpp without deps raises ImportError."""
    import importlib

    real_import_module = importlib.import_module

    def _blocking_import_module(name, *args, **kwargs):
        if name == "llama_index.embeddings.openai":
            raise ImportError("simulated: package not installed")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", _blocking_import_module)

    monkeypatch.setenv("EMBED_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_BACKEND", "llamacpp")
    monkeypatch.setenv("LLAMACPP_EMBED_MODEL", "test.gguf")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")

    import rag_mcp.config as config_mod

    with pytest.raises(ImportError, match="uv sync --extra llamacpp"):
        importlib.reload(config_mod)

    # Restore for other tests
    monkeypatch.setenv("EMBED_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
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
    """extract_metadata_async with mode=local routes to llamacpp chat when LOCAL_BACKEND=llamacpp."""
    from rag_mcp import metadata_extractor

    original_llm_provider = metadata_extractor.METADATA_LLM_PROVIDER
    original_local_backend = metadata_extractor.LOCAL_BACKEND
    original_mode = metadata_extractor.METADATA_EXTRACTION_MODE
    metadata_extractor.METADATA_LLM_PROVIDER = "local"
    metadata_extractor.LOCAL_BACKEND = "llamacpp"
    metadata_extractor.METADATA_EXTRACTION_MODE = "local"

    mock_fn = AsyncMock(return_value={"category": "test", "keywords": [], "summary": ""})
    with patch.object(metadata_extractor, "_extract_llamacpp_chat_async", mock_fn):
        try:
            await metadata_extractor.extract_metadata_async("text", "file.txt")
            mock_fn.assert_called_once_with("text")
        finally:
            metadata_extractor.METADATA_LLM_PROVIDER = original_llm_provider
            metadata_extractor.LOCAL_BACKEND = original_local_backend
            metadata_extractor.METADATA_EXTRACTION_MODE = original_mode


@pytest.mark.asyncio
async def test_local_mode_dispatches_to_ollama_when_configured() -> None:
    """extract_metadata_async with mode=local routes to ollama when LOCAL_BACKEND=ollama."""
    from rag_mcp import metadata_extractor

    original_llm_provider = metadata_extractor.METADATA_LLM_PROVIDER
    original_local_backend = metadata_extractor.LOCAL_BACKEND
    original_mode = metadata_extractor.METADATA_EXTRACTION_MODE
    metadata_extractor.METADATA_LLM_PROVIDER = "local"
    metadata_extractor.LOCAL_BACKEND = "ollama"
    metadata_extractor.METADATA_EXTRACTION_MODE = "local"

    mock_fn = AsyncMock(return_value={"category": "test", "keywords": [], "summary": ""})
    with patch.object(metadata_extractor, "_extract_ollama_async", mock_fn):
        try:
            await metadata_extractor.extract_metadata_async("text", "file.txt")
            mock_fn.assert_called_once_with("text")
        finally:
            metadata_extractor.METADATA_LLM_PROVIDER = original_llm_provider
            metadata_extractor.LOCAL_BACKEND = original_local_backend
            metadata_extractor.METADATA_EXTRACTION_MODE = original_mode


@pytest.mark.asyncio
async def test_cloud_mode_dispatches_to_openrouter() -> None:
    """extract_metadata_async with mode=local routes to openrouter when METADATA_LLM_PROVIDER=cloud."""
    from rag_mcp import metadata_extractor

    original_llm_provider = metadata_extractor.METADATA_LLM_PROVIDER
    original_mode = metadata_extractor.METADATA_EXTRACTION_MODE
    metadata_extractor.METADATA_LLM_PROVIDER = "cloud"
    metadata_extractor.METADATA_EXTRACTION_MODE = "local"

    mock_fn = AsyncMock(return_value={"category": "test", "keywords": [], "summary": ""})
    with patch.object(metadata_extractor, "_extract_openrouter_chat_async", mock_fn):
        try:
            await metadata_extractor.extract_metadata_async("text", "file.txt")
            mock_fn.assert_called_once_with("text")
        finally:
            metadata_extractor.METADATA_LLM_PROVIDER = original_llm_provider
            metadata_extractor.METADATA_EXTRACTION_MODE = original_mode


@pytest.mark.asyncio
async def test_llamaindex_mode_falls_back_to_local_chat_on_import_error() -> None:
    """llamaindex mode with local llamacpp falls back to chat mode when OpenAILike not installed."""
    from rag_mcp import metadata_extractor

    original_llm_provider = metadata_extractor.METADATA_LLM_PROVIDER
    original_local_backend = metadata_extractor.LOCAL_BACKEND
    metadata_extractor.METADATA_LLM_PROVIDER = "local"
    metadata_extractor.LOCAL_BACKEND = "llamacpp"

    mock_fn = AsyncMock(return_value={"category": "fallback", "keywords": [], "summary": ""})

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
            metadata_extractor.LOCAL_BACKEND = original_local_backend


# ── Provider registry tests ──────────────────────────────────────────────


def test_cloud_openrouter_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """EMBED_PROVIDER=cloud + CLOUD_BACKEND=openrouter with missing API key raises ValueError."""
    import importlib

    monkeypatch.setenv("EMBED_PROVIDER", "cloud")
    monkeypatch.setenv("CLOUD_BACKEND", "openrouter")
    monkeypatch.setenv("OPENROUTER_EMBED_MODEL", "text-embedding-3-small")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")

    import rag_mcp.config as config_mod

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        importlib.reload(config_mod)

    # Restore
    monkeypatch.setenv("EMBED_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
    importlib.reload(config_mod)


def test_cloud_openrouter_missing_optional_deps_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """EMBED_PROVIDER=cloud without llama-index-embeddings-openai raises ImportError."""
    import importlib

    real_import_module = importlib.import_module

    def _blocking_import_module(name, *args, **kwargs):
        if name == "llama_index.embeddings.openai":
            raise ImportError("simulated: package not installed")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", _blocking_import_module)

    monkeypatch.setenv("EMBED_PROVIDER", "cloud")
    monkeypatch.setenv("CLOUD_BACKEND", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("OPENROUTER_EMBED_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")

    import rag_mcp.config as config_mod

    with pytest.raises(ImportError, match="uv sync --extra openrouter"):
        importlib.reload(config_mod)

    # Restore
    monkeypatch.setenv("EMBED_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
    importlib.reload(config_mod)


def test_metadata_llm_provider_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """METADATA_LLM_PROVIDER defaults to local when not explicitly set."""
    import importlib

    monkeypatch.setenv("EMBED_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    monkeypatch.delenv("METADATA_LLM_PROVIDER", raising=False)

    import rag_mcp.config as config_mod
    importlib.reload(config_mod)
    assert config_mod.METADATA_LLM_PROVIDER == "local"

    # Restore
    monkeypatch.setenv("METADATA_LLM_PROVIDER", "local")
    importlib.reload(config_mod)


def test_unknown_embed_provider_falls_back_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown EMBED_PROVIDER value falls back to local."""
    import importlib

    monkeypatch.setenv("EMBED_PROVIDER", "nonexistent")
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")

    import rag_mcp.config as config_mod
    importlib.reload(config_mod)
    assert config_mod.EMBED_PROVIDER == "local"

    # Restore
    monkeypatch.setenv("EMBED_PROVIDER", "local")
    importlib.reload(config_mod)


def test_unknown_local_backend_falls_back_to_llamacpp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown LOCAL_BACKEND value falls back to llamacpp after config reload."""
    import importlib

    monkeypatch.setenv("EMBED_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_BACKEND", "nonexistent")
    monkeypatch.setenv("LLAMACPP_EMBED_MODEL", "test-model")

    real_import_module = importlib.import_module

    def _mock_import(name, *args, **kwargs):
        if name == "llama_index.embeddings.openai":
            from llama_index.core.embeddings import MockEmbedding
            mock_mod = MagicMock()
            mock_mod.OpenAIEmbedding = MagicMock(return_value=MockEmbedding(embed_dim=8))
            return mock_mod
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", _mock_import)

    import rag_mcp.config as config_mod
    importlib.reload(config_mod)
    assert config_mod.LOCAL_BACKEND == "llamacpp"

    # Restore
    monkeypatch.setattr(importlib, "import_module", real_import_module)
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    importlib.reload(config_mod)
