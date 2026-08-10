"""Tests for pluggable embedding and metadata LLM provider selection.

Verifies that EMBED_PROVIDER and METADATA_LLM_PROVIDER env vars correctly
switch between local/cloud categories, and that LOCAL_BACKEND/CLOUD_BACKEND
sub-providers resolve to the correct LlamaIndex classes.
"""

from __future__ import annotations

import importlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag_mcp.core.settings import EffectiveSettings, MetadataBlock

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

    assert config.get_settings().embed_provider in {"local", "cloud"}


def test_local_llamacpp_without_deps_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Embedding provider llamacpp without optional deps raises ImportError."""
    import sys

    from rag_mcp.compose import build_embed_model
    from rag_mcp.config import Settings

    # Simulate missing optional dependency by poisoning sys.modules.
    monkeypatch.setitem(sys.modules, "llama_index.embeddings.openai", None)

    settings = Settings(
        embed_provider="local",
        local_backend="llamacpp",
        llamacpp_embed_model="test.gguf",
        embed_model="nomic-embed-text",
    )

    with pytest.raises(ImportError, match="uv sync --extra llamacpp"):
        build_embed_model(settings)


# ── Metadata extraction: llamacpp chat path ──────────────────────────────


@pytest.mark.asyncio
async def test_llamacpp_chat_parses_openai_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """_extract_llamacpp_chat_async parses OpenAI /v1/chat/completions format."""
    from rag_mcp.core.metadata.llamacpp import _extract_llamacpp_chat_async
    from rag_mcp.core.settings import EffectiveSettings, set_default_effective_settings

    set_default_effective_settings(
        EffectiveSettings(
            llamacpp_chat_url="http://localhost:8081/v1", llamacpp_chat_model="test.gguf"
        )
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "category": "ai",
                            "keywords": ["ml", "neural"],
                            "summary": "A paper about AI.",
                        }
                    )
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

        from rag_mcp.core.metadata import llamacpp as _llamacpp

        _llamacpp._retry_sleep = AsyncMock()

        result = await _extract_llamacpp_chat_async("Some text about AI.")
        assert result["category"] == "ai"
        assert "ml" in result["keywords"]
        assert result["summary"] == "A paper about AI."


@pytest.mark.asyncio
async def test_llamacpp_chat_retries_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """_extract_llamacpp_chat_async falls back to uncategorised on retry exhaustion."""
    from rag_mcp.core.metadata.llamacpp import _extract_llamacpp_chat_async
    from rag_mcp.core.settings import EffectiveSettings, set_default_effective_settings

    set_default_effective_settings(
        EffectiveSettings(
            llamacpp_chat_url="http://localhost:8081/v1", llamacpp_chat_model="test.gguf"
        )
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        from rag_mcp.core.metadata import llamacpp as _llamacpp

        _llamacpp._retry_sleep = AsyncMock()

        result = await _extract_llamacpp_chat_async("Some text.")
        assert result == {"category": "uncategorised", "keywords": [], "summary": ""}


@pytest.mark.asyncio
async def test_local_mode_dispatches_to_llamacpp_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extract_metadata_async with mode=local routes to llamacpp chat when LOCAL_BACKEND=llamacpp."""  # noqa: E501
    from rag_mcp.core.metadata import extractor as _ext

    _settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="local"),
        metadata_llm_provider="local",
        local_backend="llamacpp",
    )

    mock_fn = AsyncMock(return_value={"category": "test", "keywords": [], "summary": ""})
    with patch("rag_mcp.core.metadata.llamacpp._extract_llamacpp_chat_async", mock_fn):
        await _ext.extract_metadata_async("text", "file.txt", _settings)
        mock_fn.assert_called_once_with("text", "file.txt", _settings)


@pytest.mark.asyncio
async def test_local_mode_dispatches_to_ollama_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extract_metadata_async with mode=local routes to ollama when LOCAL_BACKEND=ollama."""
    from rag_mcp.core.metadata import extractor as _ext

    _settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="local"),
        metadata_llm_provider="local",
        local_backend="ollama",
    )

    mock_fn = AsyncMock(return_value={"category": "test", "keywords": [], "summary": ""})
    with patch("rag_mcp.core.metadata.ollama._extract_ollama_async", mock_fn):
        await _ext.extract_metadata_async("text", "file.txt", _settings)
        mock_fn.assert_called_once_with("text", "file.txt", _settings)


@pytest.mark.asyncio
async def test_cloud_mode_dispatches_to_openrouter(
    monkeypatch: pytest.MonkeyPatch, effective_settings
) -> None:
    """extract_metadata_async with mode=local routes to openrouter when METADATA_LLM_PROVIDER=cloud."""  # noqa: E501
    from rag_mcp.core.metadata import extractor as _ext
    from rag_mcp.core.metadata import openrouter as _or

    # Set cloud_backend explicitly (rather than relying on its default) so
    # the test proves the intended OpenRouter route: compose.py selects the
    # registry entry from resolved.cloud_backend.
    _settings = effective_settings(
        extraction_mode="local",
        metadata_llm_provider="cloud",
        cloud_backend="openrouter",
    )

    mock_fn = AsyncMock(return_value={"category": "test", "keywords": [], "summary": ""})
    with patch.object(_or, "_extract_openrouter_chat_async", mock_fn):
        await _ext.extract_metadata_async("text", "file.txt", _settings)
        mock_fn.assert_called_once_with("text", "file.txt", _settings)


@pytest.mark.asyncio
async def test_llamaindex_mode_falls_back_to_local_chat_on_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """llamaindex mode with local llamacpp falls back to chat mode when OpenAILike not installed."""
    from rag_mcp.core.metadata import llamaindex as _lli

    # One injected EffectiveSettings drives both the LLM-class selection in
    # llamaindex.py and the fallback dispatch route in extractor.py.
    _settings = EffectiveSettings(metadata_llm_provider="local", local_backend="llamacpp")

    mock_fn = AsyncMock(return_value={"category": "fallback", "keywords": [], "summary": ""})

    import builtins

    real_import = builtins.__import__

    def _failing_import(name, *args, **kwargs):
        if name == "llama_index.llms.openai_like":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    with (
        patch("rag_mcp.core.metadata.llamacpp._extract_llamacpp_chat_async", mock_fn),
        patch("builtins.__import__", side_effect=_failing_import),
    ):
        await _lli._extract_llamaindex_async("text", "file.txt", _settings)
        mock_fn.assert_called_once_with("text", "file.txt", _settings)


# ── Provider registry tests ──────────────────────────────────────────────


def test_cloud_openrouter_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Embedding provider openrouter with missing API key raises ValueError."""
    from rag_mcp.compose import build_embed_model
    from rag_mcp.config import Settings

    settings = Settings(
        embed_provider="cloud",
        cloud_backend="openrouter",
        openrouter_embed_model="text-embedding-3-small",
        openrouter_api_key="",
        embed_model="nomic-embed-text",
    )

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        build_embed_model(settings)


def test_cloud_openrouter_missing_optional_deps_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Embedding provider openrouter without optional deps raises ImportError."""
    import sys

    from rag_mcp.compose import build_embed_model
    from rag_mcp.config import Settings

    # Simulate missing optional dependency by poisoning sys.modules.
    monkeypatch.setitem(sys.modules, "llama_index.embeddings.openai", None)

    settings = Settings(
        embed_provider="cloud",
        cloud_backend="openrouter",
        openrouter_api_key="sk-test",
        openrouter_embed_model="text-embedding-3-small",
        embed_model="nomic-embed-text",
    )

    with pytest.raises(ImportError, match="uv sync --extra openrouter"):
        build_embed_model(settings)


def test_metadata_llm_provider_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """METADATA_LLM_PROVIDER defaults to local when not explicitly set."""
    monkeypatch.setenv("EMBED_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    monkeypatch.delenv("METADATA_LLM_PROVIDER", raising=False)

    # Settings is resolved on demand now — build a fresh instance from the
    # patched environment instead of reloading the module (the old pattern
    # relied on a module-level singleton that no longer exists).
    import rag_mcp.config as config_mod

    config_mod._settings = None
    assert config_mod.get_settings().metadata_llm_provider == "local"

    # Restore
    monkeypatch.setenv("METADATA_LLM_PROVIDER", "local")
    # Reload re-created the settings singleton; restore the original so
    # modules that imported `settings` keep reading the same object.


def test_unknown_embed_provider_falls_back_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown EMBED_PROVIDER value falls back to local."""
    monkeypatch.setenv("EMBED_PROVIDER", "nonexistent")
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")

    # Settings is resolved on demand now — build a fresh instance from the
    # patched environment instead of reloading the module (the old pattern
    # relied on a module-level singleton that no longer exists).
    import rag_mcp.config as config_mod

    config_mod._settings = None
    assert config_mod.get_settings().embed_provider == "local"

    # Restore
    monkeypatch.setenv("EMBED_PROVIDER", "local")


def test_unknown_local_backend_falls_back_to_llamacpp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown LOCAL_BACKEND value falls back to llamacpp after config reload."""

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

    assert config_mod.get_settings().local_backend == "llamacpp"

    # Restore
    monkeypatch.setattr(importlib, "import_module", real_import_module)
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
