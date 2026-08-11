"""Tests for the composition root (``rag_mcp.compose``) and provider helpers.

Covers the config-composition-root spec scenarios:
- ``compose.build_embed_model`` constructs the embedding provider
  by resolving lazy registries against the resolved ``Settings``.
- ``compose.build_reranker`` constructs the DI reranker wired to
  ``settings.retrieval.rerank_model``.
- ``compose.ensure_runtime_setup`` assigns the LlamaIndex global
  ``Settings.embed_model`` exactly once per process.
- ``core.providers.common.get_embed_endpoint`` returns the correct
  connection tuple for each provider scheme.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from rag_mcp.compose import (
    build_embed_model,
    build_reranker,
    ensure_runtime_setup,
    reset_runtime_setup,
)
from rag_mcp.config import Settings
from rag_mcp.core.providers.common import get_embed_endpoint

# Subpackage field -> the nested block that owns it (v2.0.0 schema).
_BLOCK_OF = {
    "embed_batch_size": "ingestion",
    "embed_concurrency": "ingestion",
    "rerank_model": "retrieval",
    "top_k": "retrieval",
    "ollama_classify_model": "metadata",
    "classify_timeout": "metadata",
}


# Flat defaults for ``_settings()``. Every key must be routable: either
# ``_BLOCK_OF`` owns it, or the root ``Settings`` model declares it. A key
# that is neither falls through to ``root`` and is silently dropped by
# ``Settings(extra="ignore")`` — see ``_assert_routable``.
_DEFAULT_FLAT: dict[str, object] = {
    "embed_provider": "local",
    "local_backend": "ollama",
    "embed_model": "nomic-embed-text",
    "ollama_base_url": "http://localhost:11434",
    "embed_batch_size": 64,
    "metadata_llm_provider": "local",
    "ollama_classify_model": "qwen3:0.6b",
    "classify_timeout": 30.0,
    "rerank_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
}


def _assert_routable(flat: dict[str, object]) -> None:
    """Fail if any flat key would be silently discarded.

    ``_settings()`` routes a key into a nested block when ``_BLOCK_OF``
    names one, and otherwise passes it to the root ``Settings`` model.
    A key in neither place — a subpackage field left behind by a rename,
    say — is accepted and dropped without a word by
    ``Settings(extra="ignore")``, so the test relying on it silently
    stops testing anything.

    Args:
        flat: The merged defaults-plus-overrides mapping to check.

    Raises:
        AssertionError: Naming every key that routes nowhere.
    """
    root_fields = set(Settings.model_fields)
    unroutable = sorted(key for key in flat if key not in _BLOCK_OF and key not in root_fields)
    assert not unroutable, (
        f"flat keys route nowhere and would be silently dropped: {unroutable}. "
        "Add each to _BLOCK_OF, or use its current root Settings name."
    )


def _settings(**overrides) -> Settings:
    """Build a fresh Settings with sensible defaults and no .env.

    Accepts flat keyword names for readability and routes each into its
    nested block, so callers need not restate the schema at every site.
    """
    from rag_mcp.core.ingestion.settings import IngestionSettings
    from rag_mcp.core.metadata.settings import MetadataSettings
    from rag_mcp.core.retrieval.settings import RetrievalSettings

    flat = dict(_DEFAULT_FLAT)
    flat.update(overrides)
    # Guards the override path too, not just the defaults: an override
    # naming a renamed field is the same silent no-op.
    _assert_routable(flat)

    blocks: dict[str, dict] = {}
    root: dict = {}
    for key, value in flat.items():
        block = _BLOCK_OF.get(key)
        if block:
            blocks.setdefault(block, {})[key] = value
        else:
            root[key] = value

    cls = {
        "ingestion": IngestionSettings,
        "retrieval": RetrievalSettings,
        "metadata": MetadataSettings,
    }
    nested = {name: cls[name](**fields) for name, fields in blocks.items()}
    return Settings(_env_file=None, **root, **nested)


# ── Fixture guard ───────────────────────────────────────────────────────────


def test_every_default_key_is_routable() -> None:
    """No default key may silently vanish into ``Settings(extra="ignore")``.

    Named explicitly rather than left to the in-fixture guard so the
    failure reads as its own test rather than as a collapse of every test
    that builds settings.
    """
    _assert_routable(dict(_DEFAULT_FLAT))


def test_routability_guard_rejects_a_renamed_key() -> None:
    """The guard itself must fail on a key that routes nowhere.

    ``classify_timeout`` was once ``ollama_classify_timeout``; the stale
    name sat in the defaults being silently dropped. This pins that the
    guard catches that shape of key rather than passing vacuously.
    """
    with pytest.raises(AssertionError, match="ollama_classify_timeout"):
        _assert_routable({"ollama_classify_timeout": 30.0})


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
    """Unknown provider values raise at Settings construction (§7.3).

    The Settings model validator raises ValueError naming the offending
    value before compose ever resolves a registry — so compose itself
    cannot see an unregistered provider through a validated Settings
    object.  (The registry-level ``KeyError`` path is covered in
    ``test_registry_contract.py``.)
    """
    with pytest.raises(ValueError, match="EMBED_PROVIDER='bogus'"):
        _settings(embed_provider="bogus")


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

    _ = _settings()
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


def test_ensure_runtime_setup_propagates_embed_model_failure() -> None:
    """A construction failure must propagate, not be swallowed (§5.4).

    Previously ensure_runtime_setup caught ImportError/ValueError from
    build_embed_model and logged a warning, leaving the process running
    with no embed model set.  Now the exception propagates so startup
    fails loudly.
    """

    _ = _settings()
    reset_runtime_setup()

    with patch(
        "rag_mcp.compose.build_embed_model",
        side_effect=ImportError("optional dep missing"),
    ):
        with pytest.raises(ImportError, match="optional dep missing"):
            ensure_runtime_setup()
    reset_runtime_setup()


# ── core.providers.common.get_embed_endpoint ────────────────────────────────


def test_get_embed_endpoint_ollama() -> None:
    """Ollama: (base_url, embed_model, no key)."""
    settings = _settings()
    endpoint = get_embed_endpoint(settings)
    assert endpoint == (
        "http://localhost:11434",
        "nomic-embed-text",
        "",
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


# ── resolve_sparse_backend (native path) ────────────────────────────────────


class TestResolveSparseBackendNative:
    """The explicit 'native' backend path with capability probing."""

    @staticmethod
    def _settings(backend: str):
        from rag_mcp.config import Settings
        from rag_mcp.core.retrieval.settings import RetrievalSettings

        return Settings(
            _env_file=None,
            retrieval=RetrievalSettings(hybrid_sparse_backend=backend),
        )

    def test_native_with_probe_true_returns_native(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A native request with the probe passing returns native."""
        import rag_mcp.compose as compose
        import rag_mcp.core.retrieval.sparse as sparse

        monkeypatch.setattr(sparse, "_detect_native_sparse_capability", lambda: True)
        assert compose.resolve_sparse_backend(self._settings("native")) == "native"

    def test_native_with_probe_false_falls_back_to_bm25(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.CaptureFixture[str],
    ) -> None:
        """A native request with the probe failing falls back to bm25 with a warning."""
        import logging

        import rag_mcp.compose as compose
        import rag_mcp.core.retrieval.sparse as sparse

        monkeypatch.setattr(sparse, "_detect_native_sparse_capability", lambda: False)
        with caplog.at_level(logging.WARNING, logger="rag_mcp.compose"):
            result = compose.resolve_sparse_backend(self._settings("native"))
        assert result == "bm25"
        assert any("native" in r.message and "bm25" in r.message for r in caplog.records)


# ── resolve_pdf_reader (import probing) ─────────────────────────────────────


class TestResolvePdfReader:
    """The resolve_pdf_reader import-probe branches."""

    def test_liteparse_available_returns_liteparse(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A liteparse reader with the package importable returns liteparse."""
        import rag_mcp.compose as compose
        from rag_mcp.config import Settings

        monkeypatch.setitem(sys.modules, "liteparse", MagicMock())
        settings = Settings(_env_file=None, pdf_reader="liteparse")
        assert compose.resolve_pdf_reader(settings) == "liteparse"

    def test_liteparse_missing_falls_back_to_pypdf(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A liteparse reader with the package absent falls back to pypdf."""
        import rag_mcp.compose as compose
        from rag_mcp.config import Settings

        monkeypatch.setitem(sys.modules, "liteparse", None)
        settings = Settings(_env_file=None, pdf_reader="liteparse")
        assert compose.resolve_pdf_reader(settings) == "pypdf"

    def test_auto_resolves_to_liteparse_when_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An auto reader resolves to liteparse when the package is importable."""
        import rag_mcp.compose as compose
        from rag_mcp.config import Settings

        monkeypatch.setitem(sys.modules, "liteparse", MagicMock())
        settings = Settings(_env_file=None, pdf_reader="auto")
        assert compose.resolve_pdf_reader(settings) == "liteparse"

    def test_auto_falls_back_to_pypdf_when_none_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An auto reader falls back to pypdf when both optional packages are absent."""
        import rag_mcp.compose as compose
        from rag_mcp.config import Settings

        monkeypatch.setitem(sys.modules, "liteparse", None)
        monkeypatch.setitem(sys.modules, "pypdfium2", None)
        settings = Settings(_env_file=None, pdf_reader="auto")
        assert compose.resolve_pdf_reader(settings) == "pypdf"


# ── build_vector_store (chroma path) ────────────────────────────────────────


def test_build_vector_store_chroma_delegates_to_factory() -> None:
    """build_vector_store with chroma delegates to build_chroma_vector_store."""
    from rag_mcp.compose import build_vector_store

    with patch("rag_mcp.core.vectordb.chroma.build_chroma_vector_store") as mock_build:
        build_vector_store(_settings(vector_store="chroma"))
        mock_build.assert_called_once()


# ── settings_to_effective(None) ─────────────────────────────────────────────


def test_settings_to_effective_none_delegates_to_get_settings() -> None:
    """Passing None calls get_settings and bakes its embed_model into the result."""
    from rag_mcp.compose import settings_to_effective
    from rag_mcp.core.settings import EffectiveSettings

    controlled = _settings(embed_model="controlled-embed-model")
    with patch("rag_mcp.compose.get_settings", return_value=controlled) as mock_gs:
        result = settings_to_effective(None)
    mock_gs.assert_called_once()
    assert isinstance(result, EffectiveSettings)
    assert result.embed_model == "controlled-embed-model"


# ── _resolve_active_strategies ──────────────────────────────────────────────


class TestResolveActiveStrategies:
    """The startup strategy resolution gate."""

    def test_disabled_mode_skips_metadata(self) -> None:
        """A 'disabled' extraction mode is not passed to the metadata registry."""
        from rag_mcp.compose import _resolve_active_strategies
        from rag_mcp.config import Settings
        from rag_mcp.core.chunking import registry as chunking_reg
        from rag_mcp.core.metadata import registry as metadata_reg
        from rag_mcp.core.metadata.settings import MetadataSettings
        from rag_mcp.core.providers.embeddings import registry as embed_reg
        from rag_mcp.core.providers.llm import registry as llm_reg

        settings = Settings(
            _env_file=None,
            metadata=MetadataSettings(extraction_mode="disabled"),
        )
        with (
            patch.object(chunking_reg, "get"),
            patch.object(metadata_reg, "get") as mock_metadata,
            patch.object(embed_reg, "get"),
            patch.object(llm_reg, "get"),
        ):
            _resolve_active_strategies(settings)
            mock_metadata.assert_not_called()

    def test_unknown_name_skips_resolution(self) -> None:
        """A chunking name not in registry.available() skips the get() call."""
        from rag_mcp.compose import _resolve_active_strategies
        from rag_mcp.config import Settings
        from rag_mcp.core.chunking import registry as chunking_reg
        from rag_mcp.core.chunking.settings import ChunkingSettings
        from rag_mcp.core.metadata import registry as metadata_reg
        from rag_mcp.core.providers.embeddings import registry as embed_reg
        from rag_mcp.core.providers.llm import registry as llm_reg

        settings = Settings(
            _env_file=None,
            chunking=ChunkingSettings(strategy_fallback="totally-bogus"),
        )
        with (
            patch.object(chunking_reg, "get") as mock_chunking,
            patch.object(metadata_reg, "get"),
            patch.object(embed_reg, "get"),
            patch.object(llm_reg, "get"),
        ):
            _resolve_active_strategies(settings)
            mock_chunking.assert_not_called()

    def test_valid_name_is_resolved(self) -> None:
        """A registered chunking name triggers registry.get()."""
        from rag_mcp.compose import _resolve_active_strategies
        from rag_mcp.config import Settings
        from rag_mcp.core.chunking import registry as chunking_reg
        from rag_mcp.core.chunking.settings import ChunkingSettings
        from rag_mcp.core.metadata import registry as metadata_reg
        from rag_mcp.core.providers.embeddings import registry as embed_reg
        from rag_mcp.core.providers.llm import registry as llm_reg

        settings = Settings(
            _env_file=None,
            chunking=ChunkingSettings(strategy_fallback="sentence"),
        )
        with (
            patch.object(chunking_reg, "get") as mock_chunking,
            patch.object(metadata_reg, "get"),
            patch.object(embed_reg, "get"),
            patch.object(llm_reg, "get"),
        ):
            _resolve_active_strategies(settings)
            mock_chunking.assert_any_call("sentence")


# ── ensure_runtime_setup (vector-store failure) ─────────────────────────────


def test_ensure_runtime_setup_propagates_vector_store_failure() -> None:
    """A vector store construction failure must propagate (§5.5).

    Previously ensure_runtime_setup caught ImportError/ValueError from
    build_vector_store and logged a warning, leaving the process running
    with no default store registered.  Now the exception propagates.
    """
    from llama_index.core.embeddings import MockEmbedding

    from rag_mcp.compose import ensure_runtime_setup, reset_runtime_setup

    _ = _settings()
    reset_runtime_setup()
    mock_model = MockEmbedding(embed_dim=384)
    with (
        patch("rag_mcp.compose.build_embed_model", return_value=mock_model),
        patch("rag_mcp.compose.build_vector_store", side_effect=ImportError("missing")),
    ):
        with pytest.raises(ImportError, match="missing"):
            ensure_runtime_setup()
    reset_runtime_setup()


def test_pytest_collection_succeeds_under_conftest_defaults() -> None:
    """Pytest collection succeeds under conftest provider defaults (§5.6).

    conftest.py sets EMBED_PROVIDER=local, LOCAL_BACKEND=ollama, and
    EMBED_MODEL via setdefault before any import.  Once construction
    failures propagate at import (§5), invalid defaults would break
    collection itself, not just execution.  This test pins that the
    defaults remain valid: if it runs, collection succeeded.
    """
    import rag_mcp.compose  # noqa: F401 — proves import-time setup survived


# ── build functions (settings=None delegation) ──────────────────────────────


def test_build_embed_model_none_delegates_to_get_settings() -> None:
    """Passing None calls get_settings for embed model construction."""
    controlled = _settings()
    with (
        patch("rag_mcp.compose.get_settings", return_value=controlled) as mock_gs,
        patch("llama_index.embeddings.ollama.OllamaEmbedding"),
    ):
        build_embed_model(None)
    mock_gs.assert_called_once()


def test_build_vector_store_none_delegates_to_get_settings() -> None:
    """Passing None calls get_settings for vector store construction."""
    from rag_mcp.compose import build_vector_store

    controlled = _settings(vector_store="chroma")
    with (
        patch("rag_mcp.compose.get_settings", return_value=controlled) as mock_gs,
        patch("rag_mcp.core.vectordb.chroma.build_chroma_vector_store"),
    ):
        build_vector_store(None)
    mock_gs.assert_called_once()


def test_build_profile_resolver_none_delegates_to_get_settings() -> None:
    """Passing None calls get_settings for profile resolver construction."""
    from rag_mcp.compose import build_profile_resolver

    controlled = _settings()
    with patch("rag_mcp.compose.get_settings", return_value=controlled) as mock_gs:
        build_profile_resolver(None)
    mock_gs.assert_called_once()


def test_build_profile_resolver_explicit_settings_skips_get_settings() -> None:
    """Passing explicit settings does NOT call get_settings."""
    from rag_mcp.compose import build_profile_resolver

    with patch("rag_mcp.compose.get_settings") as mock_gs:
        build_profile_resolver(_settings())
    mock_gs.assert_not_called()
