"""Tests for pluggable embedding and metadata LLM provider selection.

Verifies that EMBED_PROVIDER and METADATA_LLM_PROVIDER env vars correctly
switch between local/cloud categories, and that LOCAL_BACKEND/CLOUD_BACKEND
sub-providers resolve to the correct LlamaIndex classes.
"""

from __future__ import annotations

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
    monkeypatch.setitem(sys.modules, "llama_index.embeddings.openai_like", None)

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
    monkeypatch.setitem(sys.modules, "llama_index.embeddings.openai_like", None)

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
    """METADATA_LLM_PROVIDER defaults to local without environment sources."""
    monkeypatch.delenv("METADATA_LLM_PROVIDER", raising=False)

    from rag_mcp.config import Settings

    assert Settings(_env_file=None).metadata_llm_provider == "local"


def test_unknown_embed_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown EMBED_PROVIDER value raises at settings resolution (§7.5)."""
    monkeypatch.setenv("EMBED_PROVIDER", "nonexistent")
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")

    from rag_mcp.config import Settings

    with pytest.raises(ValueError, match="EMBED_PROVIDER='nonexistent'"):
        Settings(_env_file=None)


def test_unknown_local_backend_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown LOCAL_BACKEND value raises at settings resolution (§7.6)."""

    monkeypatch.setenv("EMBED_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_BACKEND", "nonexistent")
    monkeypatch.setenv("LLAMACPP_EMBED_MODEL", "test-model")

    from rag_mcp.config import Settings

    with pytest.raises(ValueError, match="LOCAL_BACKEND='nonexistent'"):
        Settings(_env_file=None)


# ── §6.10-6.15: provider-validation raise behaviour ───────────────────────


# (env_name, field_path, default, accepted_override)
# field_path uses dotted notation for nested fields.
# NOTE: DOCUMENT_BACKEND is deliberately absent — unknown values no longer
# raise at Settings; validation moved to capabilities.validate_document_backend
# (register-document-backend-strategies task 2.4). Dedicated tests live below.
# RETRIEVAL__HYBRID_SPARSE_BACKEND is deliberately absent for the same
# reason: validation moved to capabilities.validate_sparse_backend (task
# 3.5, implement-native-sparse-backend-strategy); the §6.10 whitespace
# idiom stays in Settings and dedicated composition-boundary tests live
# in tests/test_compose.py.
_PROVIDER_FIELDS: list[tuple[str, str, str, str]] = [
    ("EMBED_PROVIDER", "embed_provider", "local", "ollama"),
    ("METADATA_LLM_PROVIDER", "metadata_llm_provider", "local", "cloud"),
    ("LOCAL_BACKEND", "local_backend", "llamacpp", "ollama"),
    ("CLOUD_BACKEND", "cloud_backend", "openrouter", "openrouter"),
]


def _get_nested(obj: object, dotted: str) -> object:
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


@pytest.mark.parametrize(
    "env_name, field_path, expected_default, _",
    _PROVIDER_FIELDS,
    ids=[p[0] for p in _PROVIDER_FIELDS],
)
def test_empty_provider_value_resets_to_default(
    env_name: str,
    field_path: str,
    expected_default: str,
    _: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty or whitespace-only value resets to the field default (§6.10).

    ``SETTING=`` in .env is how operators unset a knob.  Raising on it
    would be hostile.  The field is reset to its declared default.
    """
    from rag_mcp.config import Settings

    monkeypatch.setenv(env_name, "   ")
    settings = Settings(_env_file=None)
    assert _get_nested(settings, field_path) == expected_default


@pytest.mark.parametrize(
    "env_name, field_path, _default, valid_value",
    _PROVIDER_FIELDS,
    ids=[p[0] for p in _PROVIDER_FIELDS],
)
def test_whitespace_padded_valid_value_is_stripped(
    env_name: str,
    field_path: str,
    _default: str,
    valid_value: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A whitespace-padded valid value resolves to the stripped value (§6.10)."""
    from rag_mcp.config import Settings

    monkeypatch.setenv(env_name, f"  {valid_value}  ")
    settings = Settings(_env_file=None)
    assert _get_nested(settings, field_path) == valid_value


@pytest.mark.parametrize(
    "env_name",
    [p[0] for p in _PROVIDER_FIELDS],
    ids=[p[0] for p in _PROVIDER_FIELDS],
)
def test_unknown_provider_value_raises_with_value_in_message(
    env_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each raising branch names the offending value (§6.11)."""
    from rag_mcp.config import Settings

    monkeypatch.setenv(env_name, "totally-bogus")
    with pytest.raises(ValueError, match=f"{env_name}='totally-bogus'"):
        Settings(_env_file=None)


def test_bad_embed_provider_reported_before_missing_embed_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bad EMBED_PROVIDER reports itself, not a missing EMBED_MODEL (§6.12).

    Guards the validator ordering: _validate_provider_selections runs
    before _validate_embed_model_required.
    """
    from rag_mcp.config import Settings

    monkeypatch.setenv("EMBED_PROVIDER", "bogus")
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
    monkeypatch.delenv("EMBED_MODEL", raising=False)
    with pytest.raises(ValueError, match="EMBED_PROVIDER='bogus'"):
        Settings(_env_file=None)


def test_document_backend_azure_missing_credentials_falls_back_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DOCUMENT_BACKEND=azure without credentials falls back to local (§6.13).

    Regression guard for the deliberate graceful-degradation boundary
    this change must not cross.
    """
    from rag_mcp.config import Settings

    monkeypatch.setenv("DOCUMENT_BACKEND", "azure")
    monkeypatch.delenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DOC_INTELLIGENCE_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.document_backend == "local"


def test_document_backend_whitespace_value_preserved_with_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DOCUMENT_BACKEND="  azure  " strips to azure (config idiom retained).

    The config layer keeps the strip/reset behaviour even though the
    unknown-value raise moved to the composition boundary. Dummy
    credentials keep the credential degradation from firing.
    """
    from rag_mcp.config import Settings

    monkeypatch.setenv("DOCUMENT_BACKEND", "  azure  ")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://example.azure.com/")
    monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_KEY", "dummy-key")
    assert Settings(_env_file=None).document_backend == "azure"


def test_unknown_document_backend_defers_to_compose_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bogus backend constructs at Settings and fails at the startup gate.

    Spec scenario "Unknown backend is configured": startup SHALL fail and
    list the available backend names. Validation now lives in
    ``capabilities.validate_document_backend``, so this test fails until
    register-document-backend-strategies lands.
    """
    from rag_mcp.capabilities import validate_document_backend
    from rag_mcp.config import Settings

    monkeypatch.setenv("DOCUMENT_BACKEND", "totally-bogus")
    settings = Settings(_env_file=None)
    with pytest.raises(ValueError) as excinfo:
        validate_document_backend(settings)
    message = str(excinfo.value)
    assert "DOCUMENT_BACKEND" in message
    assert "totally-bogus" in message
    assert "local" in message and "azure" in message


@pytest.mark.parametrize(
    "raw, expected",
    [("   ", "bm25"), ("  native  ", "native"), ("", "bm25")],
)
def test_sparse_backend_whitespace_idiom_stays_in_settings(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: str
) -> None:
    """§6.10 survives the registry-ownership move: strip and reset (task 3.5)."""
    from rag_mcp.config import Settings

    monkeypatch.setenv("RETRIEVAL__HYBRID_SPARSE_BACKEND", raw)
    settings = Settings(_env_file=None)
    assert settings.retrieval.hybrid_sparse_backend == expected


def test_unknown_sparse_backend_defers_to_compose_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bogus backend constructs at Settings and fails at the startup gate.

    Spec scenario "Unknown concrete backend is configured": startup
    SHALL fail and list the registered sparse backend names (``auto``
    plus the concrete registry). Validation lives in
    ``capabilities.validate_sparse_backend`` (task 3.5).
    """
    from rag_mcp.capabilities import validate_sparse_backend
    from rag_mcp.config import Settings

    monkeypatch.setenv("RETRIEVAL__HYBRID_SPARSE_BACKEND", "totally-bogus")
    settings = Settings(_env_file=None)
    with pytest.raises(ValueError) as excinfo:
        validate_sparse_backend(settings)
    message = str(excinfo.value)
    assert "RETRIEVAL__HYBRID_SPARSE_BACKEND" in message
    assert "totally-bogus" in message
    # auto (the policy name) plus both registered concrete backends.
    assert "auto" in message and "bm25" in message and "native" in message


def test_rag_profile_unknown_falls_back_to_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrecognised RAG_PROFILE falls back to documents (§6.14).

    Regression guard: RAG_PROFILE is warn-and-fallback by design.
    """
    from rag_mcp.config import Settings

    monkeypatch.setenv("RAG_PROFILE", "nonexistent")
    settings = Settings(_env_file=None)
    assert settings.rag_profile == "documents"


def test_vector_store_unknown_raises_at_runtime_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """VECTOR_STORE validation runs when the runtime starts."""
    from llama_index.core import Settings as LlamaIndexSettings
    from llama_index.core.embeddings import MockEmbedding

    from rag_mcp import compose
    from rag_mcp.config import Settings

    monkeypatch.setenv("VECTOR_STORE", "faiss")
    settings = Settings(_env_file=None)
    original_embed_model = LlamaIndexSettings.embed_model
    compose.reset_runtime_setup()

    try:
        with (
            patch.object(compose, "get_settings", return_value=settings),
            patch.object(compose, "build_embed_model", return_value=MockEmbedding(embed_dim=384)),
        ):
            with pytest.raises(ValueError, match="VECTOR_STORE='faiss'"):
                compose.ensure_runtime_setup()
    finally:
        LlamaIndexSettings.embed_model = original_embed_model
        compose.reset_runtime_setup()


def test_pdf_reader_unknown_clamps_to_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    """PDF_READER unknown-value behaviour is unchanged (§6.15)."""
    from rag_mcp.config import Settings

    monkeypatch.setenv("PDF_READER", "definitely-not-a-reader")
    settings = Settings(_env_file=None)
    assert settings.pdf_reader == "auto"
