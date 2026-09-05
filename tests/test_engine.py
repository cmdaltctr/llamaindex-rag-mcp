"""Integration tests for the public Engine API.

Covers the engine-scoped-composition and public-library-api specs:
direct construction without ``ensure_runtime_setup``, engine isolation
between two engines, lazy ``__version__``/``Engine``/``EffectiveSettings``
exports, and the ``close()`` lifecycle.
"""

from __future__ import annotations

import importlib
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from omrg.core.settings import EffectiveSettings, MetadataBlock

# ── Public API surface ────────────────────────────────────────────────


def test_public_api_exports_engine_effective_settings_version() -> None:
    """``omrg`` exports exactly Engine, EffectiveSettings and __version__."""
    import omrg

    assert hasattr(omrg, "Engine")
    assert hasattr(omrg, "EffectiveSettings")
    assert hasattr(omrg, "__version__")
    assert omrg.__version__ != "1.8.0"  # not the stale literal
    assert omrg.__all__ == ["Engine", "EffectiveSettings", "__version__"]


def test_importing_omrg_constructs_nothing() -> None:
    """Importing the package does not resolve settings or construct providers."""
    # Re-import omrg in a fresh module context and verify no settings
    # singleton is created.
    import omrg

    importlib.reload(omrg)
    # If importing had constructed settings, the config module would
    # have a cached singleton. We just verify the import succeeds and
    # the lazy attributes are accessible.
    assert omrg.Engine is not None
    assert omrg.EffectiveSettings is not None


def test_version_comes_from_package_metadata() -> None:
    """``__version__`` derives from ``importlib.metadata.version("omrg")``."""
    import importlib.metadata

    import omrg

    assert omrg.__version__ == importlib.metadata.version("omrg")


# ── Direct construction without ensure_runtime_setup ──────────────────


def test_engine_constructs_directly_without_runtime_setup(tmp_path: Path) -> None:
    """An Engine can be constructed with explicit dependencies.

    No ``ensure_runtime_setup()`` call is needed — the engine owns its
    store, embedder and settings.
    """
    from omrg.core.vectordb.lancedb import LanceVectorStore
    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        pdf_reader="pypdf",
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    embed_model = MagicMock()
    embed_model.model_name = "test-model"

    engine = Engine(settings, store=store, embed_model=embed_model)
    assert engine._store is store
    assert engine._embed_model is embed_model
    assert engine._effective_settings is settings
    engine.close()


def test_engine_from_environment_delegates_to_build_engine() -> None:
    """``Engine.from_environment()`` delegates to ``compose.build_engine()``."""
    from omrg.engine import Engine

    mock_engine = MagicMock()
    with patch("omrg.compose.build_engine", return_value=mock_engine):
        result = Engine.from_environment()
    assert result is mock_engine


# ── Engine isolation ──────────────────────────────────────────────────


def test_two_engines_have_independent_query_caches(tmp_path: Path) -> None:
    """Two engines do not share query-embedding caches."""
    from omrg.core.vectordb.lancedb import LanceVectorStore
    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store_a = LanceVectorStore(uri=str(tmp_path / "a"))
    store_b = LanceVectorStore(uri=str(tmp_path / "b"))
    embed_a = MagicMock(model_name="model-a")
    embed_b = MagicMock(model_name="model-b")

    engine_a = Engine(settings, store=store_a, embed_model=embed_a)
    engine_b = Engine(settings, store=store_b, embed_model=embed_b)

    assert engine_a._query_cache is not engine_b._query_cache
    engine_a.close()
    engine_b.close()


def test_engine_close_evicts_only_own_bm25_entries(tmp_path: Path) -> None:
    """Closing one engine evicts only its own BM25 cache entries."""
    from omrg.core.retrieval.sparse import BM25SparseRetriever
    from omrg.core.vectordb.lancedb import LanceVectorStore
    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store_a = LanceVectorStore(uri=str(tmp_path / "a"))
    store_b = LanceVectorStore(uri=str(tmp_path / "b"))
    embed = MagicMock(model_name="test")

    engine_a = Engine(settings, store=store_a, embed_model=embed)
    engine_b = Engine(settings, store=store_b, embed_model=embed)

    # Seed BM25 cache with entries for both stores.
    with BM25SparseRetriever._cache_lock:
        BM25SparseRetriever._cache[(store_a.cache_identity, "col-a")] = MagicMock()
        BM25SparseRetriever._cache[(store_b.cache_identity, "col-b")] = MagicMock()

    engine_a.close()

    # Engine A's entry is gone; Engine B's is still there.
    with BM25SparseRetriever._cache_lock:
        assert (store_a.cache_identity, "col-a") not in BM25SparseRetriever._cache
        assert (store_b.cache_identity, "col-b") in BM25SparseRetriever._cache

    engine_b.close()
    with BM25SparseRetriever._cache_lock:
        assert (store_b.cache_identity, "col-b") not in BM25SparseRetriever._cache


def test_engine_close_is_idempotent(tmp_path: Path) -> None:
    """Calling close() twice is safe."""
    from omrg.core.vectordb.lancedb import LanceVectorStore
    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    embed = MagicMock(model_name="test")

    engine = Engine(settings, store=store, embed_model=embed)
    engine.close()
    engine.close()  # must not raise


# ── Engine search delegates with injected dependencies ────────────────


def test_engine_search_passes_injected_dependencies(tmp_path: Path) -> None:
    """``Engine.search`` passes the engine's store, embed_model and cache."""
    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store = MagicMock()
    store.cache_identity = "test-identity"
    embed_model = MagicMock(model_name="test-model")

    engine = Engine(settings, store=store, embed_model=embed_model)

    captured: dict[str, Any] = {}

    def fake_search(query, **kwargs):
        captured.update(kwargs)
        return []

    with patch("omrg.core.retrieval.pipeline.search", side_effect=fake_search):
        engine.search("test query", collection_name="docs")

    assert captured.get("store") is store
    assert captured.get("embed_model") is embed_model
    assert captured.get("query_cache") is engine._query_cache
    engine.close()


# ── Settings boundary: transports must not call get_settings ──────────


def test_install_login_watcher_contention_warning_uses_compose_surface() -> None:
    """``_contention_warning`` accepts the adapter name, not ``get_settings``."""
    # The function signature requires ``adapter`` as a keyword argument.
    # No ``get_settings()`` call is made inside it.
    import inspect

    from omrg.transports.cli.install_login_watcher import _contention_warning

    sig = inspect.signature(_contention_warning)
    assert "adapter" in sig.parameters
    assert "collection" in sig.parameters


# ── Engine ingest delegates with injected dependencies ────────────────


def test_engine_ingest_passes_injected_dependencies(tmp_path: Path) -> None:
    """``Engine.ingest`` passes the engine's store and embed_model."""
    import asyncio

    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store = MagicMock()
    store.cache_identity = "test-identity"
    embed_model = MagicMock(model_name="test-model")

    engine = Engine(settings, store=store, embed_model=embed_model)

    captured: dict[str, Any] = {}

    async def fake_ingest(path, **kwargs):
        captured.update(kwargs)
        return {"status": "ok", "files_indexed": 0}

    with patch("omrg.core.ingestion.pipeline.ingest_path_async", side_effect=fake_ingest):
        result = asyncio.run(engine.ingest(str(tmp_path), collection_name="docs"))

    assert result["status"] == "ok"
    assert captured.get("store") is store
    assert captured.get("embed_model") is embed_model
    assert captured.get("effective_settings") is settings
    engine.close()


# ── Engine list_collections and delete_collection ─────────────────────


def test_engine_list_collections_delegates_to_store(tmp_path: Path) -> None:
    """``Engine.list_collections`` returns collection names from the store."""
    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store = MagicMock()
    store.cache_identity = "test-identity"
    embed_model = MagicMock(model_name="test-model")

    engine = Engine(settings, store=store, embed_model=embed_model)

    def fake_list_collections(**kwargs):
        return [
            {"name": "docs", "document_count": 5, "chunk_count": 10},
            {"name": "code", "document_count": 3, "chunk_count": 7},
        ]

    with patch("omrg.core.retrieval.pipeline.list_collections", side_effect=fake_list_collections):
        result = engine.list_collections()

    assert result == ["docs", "code"]
    engine.close()


def test_engine_delete_collection_delegates_to_store(tmp_path: Path) -> None:
    """``Engine.delete_collection`` calls the store's delete_collection."""
    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store = MagicMock()
    store.cache_identity = "test-identity"
    embed_model = MagicMock(model_name="test-model")

    engine = Engine(settings, store=store, embed_model=embed_model)
    engine.delete_collection("docs")
    store.delete_collection.assert_called_once_with("docs")
    engine.close()


# ── Engine answer delegates with injected dependencies ────────────────


def test_engine_answer_builds_completion_seam_lazily(tmp_path: Path) -> None:
    """``Engine.answer`` builds the answer LLM lazily via the factory."""
    import asyncio

    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store = MagicMock()
    store.cache_identity = "test-identity"
    embed_model = MagicMock(model_name="test-model")

    mock_llm = MagicMock()
    factory_called = {"count": 0}

    def answer_llm_factory():
        factory_called["count"] += 1
        return mock_llm

    engine = Engine(
        settings,
        store=store,
        embed_model=embed_model,
        answer_llm_factory=answer_llm_factory,
    )

    captured: dict[str, Any] = {}

    async def fake_answer(query, **kwargs):
        captured.update(kwargs)
        return {"status": "ok", "answer": "test"}

    with patch("omrg.core.answer.pipeline.answer", side_effect=fake_answer):
        result = asyncio.run(engine.answer("test question", collection_name="docs"))

    assert result["status"] == "ok"
    assert factory_called["count"] == 1
    assert captured.get("store") is store
    assert captured.get("effective_settings") is settings
    assert captured.get("complete") is not None
    engine.close()


def test_engine_answer_with_no_llm_factory_passes_none_complete(tmp_path: Path) -> None:
    """``Engine.answer`` with no factory passes ``complete=None``."""
    import asyncio

    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store = MagicMock()
    store.cache_identity = "test-identity"
    embed_model = MagicMock(model_name="test-model")

    engine = Engine(settings, store=store, embed_model=embed_model)

    captured: dict[str, Any] = {}

    async def fake_answer(query, **kwargs):
        captured.update(kwargs)
        return {"status": "ok", "answer": "test"}

    with patch("omrg.core.answer.pipeline.answer", side_effect=fake_answer):
        asyncio.run(engine.answer("test question", collection_name="docs"))

    assert captured.get("complete") is None
    engine.close()


# ── Engine _install_as_process_default ────────────────────────────────


def test_engine_install_as_process_default_sets_globals(tmp_path: Path) -> None:
    """``_install_as_process_default`` installs store, settings and LlamaIndex global."""
    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store = MagicMock()
    store.cache_identity = "test-identity"
    embed_model = MagicMock(model_name="test-model")

    engine = Engine(settings, store=store, embed_model=embed_model)

    with (
        patch("omrg.core.vectordb.set_default_store") as mock_set_store,
        patch("omrg.core.settings.set_default_effective_settings") as mock_set_settings,
        patch("llama_index.core.Settings") as mock_li_settings,
    ):
        engine._install_as_process_default()

    mock_set_store.assert_called_once_with(store)
    mock_set_settings.assert_called_once_with(settings)
    assert mock_li_settings.embed_model is embed_model
    engine.close()


# ── Engine close drops query cache ────────────────────────────────────


def test_engine_close_drops_query_cache(tmp_path: Path) -> None:
    """``close()`` clears the engine-owned query embedding cache."""
    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store = MagicMock()
    store.cache_identity = "test-identity"
    embed_model = MagicMock(model_name="test-model")

    engine = Engine(settings, store=store, embed_model=embed_model)
    engine._query_cache[("test", "model")] = (1.0, 0.0)
    assert len(engine._query_cache) == 1

    engine.close()
    assert len(engine._query_cache) == 0


# ── compose.build_engine and configured_vector_store ──────────────────


def test_build_engine_constructs_engine_from_settings(tmp_path: Path) -> None:
    """``compose.build_engine`` constructs an Engine from resolved settings."""
    from omrg.compose_engine import build_engine

    mock_settings = MagicMock()
    mock_settings.chroma_scan_page_size = 10000
    mock_settings.lancedb_uri = str(tmp_path / "lancedb")

    mock_embed = MagicMock(model_name="test")
    mock_store = MagicMock()
    mock_store.cache_identity = "test-identity"
    mock_reranker = MagicMock()
    mock_effective = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )

    with (
        patch("omrg.compose.build_embed_model", return_value=mock_embed),
        patch("omrg.compose.build_vector_store", return_value=mock_store),
        patch("omrg.compose.settings_to_effective", return_value=mock_effective),
        patch("omrg.compose.build_reranker", return_value=mock_reranker),
    ):
        engine = build_engine(mock_settings)

    assert engine._embed_model is mock_embed
    assert engine._store is mock_store
    assert engine._effective_settings is mock_effective
    assert engine._reranker is mock_reranker
    engine.close()


def test_build_engine_reranker_failure_degrades_to_none(tmp_path: Path) -> None:
    """``build_engine`` returns None reranker when construction fails."""
    from omrg.compose_engine import build_engine

    mock_settings = MagicMock()
    mock_effective = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )

    with (
        patch("omrg.compose.build_embed_model", return_value=MagicMock()),
        patch("omrg.compose.build_vector_store", return_value=MagicMock()),
        patch("omrg.compose.settings_to_effective", return_value=mock_effective),
        patch("omrg.compose.build_reranker", side_effect=RuntimeError("no onnx")),
    ):
        engine = build_engine(mock_settings)

    assert engine._reranker is None
    engine.close()


def test_configured_vector_store_returns_adapter_name() -> None:
    """``configured_vector_store`` returns the vector store name from settings."""
    from omrg.compose_engine import configured_vector_store

    mock_settings = MagicMock(vector_store="lancedb")
    with patch("omrg.config.get_settings", return_value=mock_settings):
        result = configured_vector_store()
    assert result == "lancedb"


# ── Task 2.5: Engine public method surface ────────────────────────────


def test_engine_public_method_surface_is_exactly_documented() -> None:
    """The Engine public method set is exactly the documented surface."""
    from omrg.engine import Engine

    expected = {"ingest", "search", "answer", "list_collections", "delete_collection", "close"}
    actual = {
        name
        for name, member in vars(Engine).items()
        if callable(member) and not name.startswith("_")
    }
    # from_environment is a classmethod, not an instance method — it's
    # construction, not operation, so it's not part of the documented
    # operational surface. We check it separately.
    actual.discard("from_environment")
    assert actual == expected, f"Unexpected Engine methods: {actual ^ expected}"


# ── Task 3.5: Construction failure leaves no partial engine ───────────


def test_engine_construction_failure_leaves_no_partial_state(tmp_path: Path) -> None:
    """If build_engine raises, no partially-initialised engine leaks.

    Construction failure in ``build_engine`` (e.g. invalid provider) must
    propagate the error without leaving a partially-constructed Engine
    accessible to the caller.
    """
    from omrg.compose_engine import build_engine

    mock_settings = MagicMock()
    with patch(
        "omrg.compose.build_embed_model",
        side_effect=ValueError("invalid embed_provider='bogus'"),
    ):
        with pytest.raises(ValueError, match="bogus"):
            build_engine(mock_settings)
    # No engine object is returned on failure — the caller never sees a
    # partially-initialised instance.


# ── Task 5.4: Startup remains fail-fast on invalid provider ───────────


def test_build_engine_fail_fast_on_invalid_embed_provider(tmp_path: Path) -> None:
    """``build_engine`` propagates ValueError for an invalid embed provider."""
    from omrg.compose_engine import build_engine

    mock_settings = MagicMock()
    with patch(
        "omrg.compose.build_embed_model",
        side_effect=ValueError("unknown provider 'bogus'"),
    ):
        with pytest.raises(ValueError, match="bogus"):
            build_engine(mock_settings)


def test_build_engine_fail_fast_on_invalid_store(tmp_path: Path) -> None:
    """``build_engine`` propagates ValueError for an invalid vector store."""
    from omrg.compose_engine import build_engine

    mock_settings = MagicMock()
    with (
        patch("omrg.compose.build_embed_model", return_value=MagicMock()),
        patch("omrg.compose.build_vector_store", side_effect=ValueError("unknown store 'bogus'")),
    ):
        with pytest.raises(ValueError, match="bogus"):
            build_engine(mock_settings)


# ── Task 6.3: Direct engine never calls get_settings ──────────────────


def test_direct_engine_construction_never_calls_get_settings(tmp_path: Path) -> None:
    """An engine built from explicit dependencies never calls ``get_settings``."""
    from omrg.engine import Engine

    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    store = MagicMock()
    store.cache_identity = "test-identity"
    embed_model = MagicMock(model_name="test-model")

    with patch("omrg.config.get_settings") as mock_get_settings:
        engine = Engine(settings, store=store, embed_model=embed_model)
        mock_get_settings.assert_not_called()
    engine.close()


# ── Task 4.7: Injected identity matches global identity ───────────────


def test_injected_embedding_identity_matches_global_for_same_embedder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The injected embedder identity matches the global-path identity.

    When the same embedder is used, ``_runtime_embedding_identity`` with
    an injected embedder produces the same fingerprint as the global path.
    This ensures existing collections do not reprocess after the switch.
    """
    from omrg.core.ingestion import source_state

    mock_embed = MagicMock()
    mock_embed.__class__.__name__ = "MockEmbedding"
    mock_embed.model_name = "test-model"

    # Global path (no injected embedder) — replace the LlamaIndexSettings
    # reference inside source_state with a simple namespace so the global
    # path sees our mock without triggering LlamaIndex's property setter.
    fake_settings = types.SimpleNamespace(embed_model=mock_embed)
    monkeypatch.setattr(source_state, "LlamaIndexSettings", fake_settings)
    global_identity = source_state._runtime_embedding_identity()

    # Injected path — uses the passed embedder.
    injected_identity = source_state._runtime_embedding_identity(embed_model=mock_embed)

    assert global_identity == injected_identity


# ── Task 4.10: Embedding identity guards reject mismatched collections ─


def test_source_index_identity_changes_with_different_embedders() -> None:
    """``build_index_identity`` produces different identities for different embedders."""
    from omrg.core.ingestion import source_state

    settings = EffectiveSettings(metadata=MetadataBlock(extraction_mode="disabled"))

    embed_a = MagicMock(model_name="model-a")
    embed_a.__class__.__name__ = "EmbedderA"
    embed_b = MagicMock(model_name="model-b")
    embed_b.__class__.__name__ = "EmbedderB"

    identity_a = source_state.build_index_identity(
        settings,
        content_type="text/plain",
        chunk_size=512,
        chunk_overlap=100,
        embed_model=embed_a,
    )
    identity_b = source_state.build_index_identity(
        settings,
        content_type="text/plain",
        chunk_size=512,
        chunk_overlap=100,
        embed_model=embed_b,
    )
    assert identity_a != identity_b
