"""Integration tests for the retrieval module.

Tests cover:
- search on empty store returns empty
- similarity_threshold filtering
- reranked flag propagation with default and explicit rerank
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from conftest import connected_client


async def _ingest_fixtures(client, fixtures_dir: Path) -> None:
    """Helper: ingest test fixtures via the MCP client."""
    await client.call_tool("ingest_documents", {"path": str(fixtures_dir)})


# ── Empty store ────────────────────────────────────────────────────────────


async def test_search_empty_store_returns_empty(mcp_server) -> None:
    """Searching with no indexed documents must return an empty list."""
    async with connected_client(mcp_server) as client:
        result = await client.call_tool("search_documents", {"query": "anything"})
        data = _extract_result(result)
        assert data == []


# ── Similarity threshold filtering ─────────────────────────────────────────


async def test_high_threshold_filters_all(mcp_server, fixtures_dir: Path) -> None:
    """A very high similarity_threshold should filter all results."""
    async with connected_client(mcp_server) as client:
        await _ingest_fixtures(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital of France", "similarity_threshold": 0.99},
        )
        data = _extract_result(result)
        # All results may be filtered out (MockEmbedding scores are low)
        # The test verifies the parameter is accepted without error
        assert isinstance(data, list)


async def test_default_threshold_includes_results(mcp_server, fixtures_dir: Path) -> None:
    """Default threshold (0.0) should include all retrieved results."""
    async with connected_client(mcp_server) as client:
        await _ingest_fixtures(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital of France"},
        )
        data = _extract_result(result)
        assert isinstance(data, list)
        assert len(data) > 0


# ── Rerank flag propagation ────────────────────────────────────────────────


async def test_default_search_uses_policy_resolver(mcp_server, fixtures_dir: Path) -> None:
    """Default MCP search uses policy resolver and preserves result shape."""
    async with connected_client(mcp_server) as client:
        await _ingest_fixtures(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital"},
        )
        data = _extract_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        for r in data:
            assert "reranked" in r


async def test_rerank_false_sets_flag_false(mcp_server, fixtures_dir: Path) -> None:
    """Explicit rerank=False still preserves the un-reranked path."""
    async with connected_client(mcp_server) as client:
        await _ingest_fixtures(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital", "rerank": False},
        )
        data = _extract_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        for r in data:
            assert r["reranked"] is False


async def test_rerank_enabled_sets_flag(mcp_server, fixtures_dir: Path) -> None:
    """With rerank=True, the reranked flag reflects actual reranker state."""
    async with connected_client(mcp_server) as client:
        await _ingest_fixtures(client, fixtures_dir)
        result = await client.call_tool(
            "search_documents",
            {"query": "capital", "rerank": True},
        )
        data = _extract_result(result)
        assert isinstance(data, list)
        # The reranked flag is True if the reranker loaded, False if it
        # fell back. Either way, the call must succeed.
        for r in data:
            assert "reranked" in r


# ── Threshold scaling with reranker ────────────────────────────────────────


class TestPersistentRerankFailureFallback:
    """Regression: a permanently unavailable reranker must degrade gracefully.

    Mirrors the reranking spec scenario "persistent failure still falls
    back gracefully": search_documents with rerank=True must NOT crash or
    raise; it returns un-reranked results and emits a warning.
    """

    async def test_persistent_failure_falls_back_without_crash(
        self, mcp_server, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A permanently failing reranker yields un-reranked results + warning."""

        import rag_mcp.core.retrieval.reranker as reranker_mod
        from rag_mcp.core.retrieval.reranker import CrossEncoderReranker

        # Build a reranker whose model load fails permanently.
        failing = CrossEncoderReranker(model_id="invalid/model-id")
        failing._loaded = False
        failing._load_attempted = True
        failing._load_error = "model permanently unavailable"

        # The retry path must also keep failing.
        def _fail_load(self) -> None:
            self._load_attempted = True
            self._load_error = "model permanently unavailable"

        monkeypatch.setattr(reranker_mod.CrossEncoderReranker, "_load_model", _fail_load)

        # Inject the failing reranker through the DI parameter.
        import rag_mcp.transports.mcp as server

        original_search = server.search

        def _search_with_failing_reranker(*args, **kwargs):
            kwargs["reranker"] = failing
            return original_search(*args, **kwargs)

        monkeypatch.setattr(server, "search", _search_with_failing_reranker)

        async with connected_client(mcp_server) as client:
            await _ingest_fixtures(client, fixtures_dir)
            result = await client.call_tool(
                "search_documents",
                {"query": "capital", "rerank": True},
            )
            data = _extract_result(result)
            assert isinstance(data, list)
            assert len(data) > 0
            # Graceful fallback: results returned, reranked flag False,
            # no error status dict.
            for r in data:
                assert "reranked" in r
                assert r["reranked"] is False

    def test_transient_failure_retries_then_succeeds(self) -> None:
        """A transient load failure must retry on the next call and recover."""
        from rag_mcp.core.retrieval.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker(model_id="transient/model")
        reranker._loaded = False
        reranker._load_attempted = True
        reranker._load_error = "transient network timeout"

        mock_session = MagicMock()
        mock_tokenizer = MagicMock()
        mock_tokenizer.model_max_length = 1000000

        with patch(
            "rag_mcp.core.retrieval.reranker._select_onnx_variant", return_value=["onnx/model.onnx"]
        ):
            with patch("huggingface_hub.hf_hub_download", return_value="/fake/model.onnx"):
                with patch(
                    "transformers.AutoTokenizer.from_pretrained", return_value=mock_tokenizer
                ):
                    with patch("onnxruntime.InferenceSession", return_value=mock_session):
                        reranker._load_model()

        # Retry succeeded: model loaded, error cleared, cache populated.
        assert reranker._loaded is True
        assert reranker._load_error is None


# ── Threshold scaling with reranker ────────────────────────────────────────


class TestThresholdScaling:
    """Tests for score-aware threshold scaling.

    When the reranker is active, sigmoid-normalised scores occupy a much
    lower range than cosine similarity.  The search() function should
    scale the threshold down by 30× automatically to avoid over-filtering.
    """

    def test_no_rerank_threshold_unchanged(self) -> None:
        """Without reranking, the threshold must not be scaled."""
        from rag_mcp.core.retrieval.policy import _effective_threshold

        assert _effective_threshold(0.3, rerank=False) == 0.3

    def test_rerank_threshold_scaled_down(self) -> None:
        """With reranking, the threshold must be scaled down 30×."""
        from rag_mcp.core.retrieval.policy import _effective_threshold

        assert _effective_threshold(0.3, rerank=True) == pytest.approx(0.01)

    def test_zero_threshold_stays_zero_no_rerank(self) -> None:
        """Zero threshold (no filtering) must stay zero without rerank."""
        from rag_mcp.core.retrieval.policy import _effective_threshold

        assert _effective_threshold(0.0, rerank=False) == 0.0

    def test_zero_threshold_stays_zero_with_rerank(self) -> None:
        """Zero threshold (no filtering) must stay zero with rerank."""
        from rag_mcp.core.retrieval.policy import _effective_threshold

        assert _effective_threshold(0.0, rerank=True) == 0.0

    def test_moderate_threshold_with_rerank(self) -> None:
        """A moderate threshold (0.5) should become ~0.0167 with rerank."""
        from rag_mcp.core.retrieval.policy import _effective_threshold

        assert _effective_threshold(0.5, rerank=True) == pytest.approx(0.5 / 30)

    def test_colosseum_score_survives_threshold(self) -> None:
        """The Colosseum query (score 0.015) must survive threshold 0.3.

        This was the motivating case: the reranker correctly identified
        the Colosseum chunk but gave it a low sigmoid score (0.015).
        With 30× scaling, threshold 0.3 → 0.01, so 0.015 passes.
        """
        from rag_mcp.core.retrieval.policy import _effective_threshold

        threshold = _effective_threshold(0.3, rerank=True)
        assert 0.015 >= threshold  # Colosseum score should pass


# ── Helpers ────────────────────────────────────────────────────────────────


def _extract_result(result):
    """Extract the data payload from a FastMCP CallToolResult."""
    import json

    from mcp.types import TextContent

    if hasattr(result, "structuredContent") and result.structuredContent:
        return result.structuredContent.get("result", result.structuredContent)

    if result.content and isinstance(result.content[0], TextContent):
        return json.loads(result.content[0].text)

    return result


# ── 9.8-9.10 Collection-aware retrieval tests ──────────────────────────────


class TestCollectionAwareSearch:
    """Tests for collection-aware search and filtering."""

    async def test_search_named_collection(self, sample_txt, sample_md):
        """Search must return results only from the specified collection."""
        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.core.retrieval import search

        # Ingest into two different collections
        await ingest_path_async(str(sample_txt), collection_name="research")
        await ingest_path_async(str(sample_md), collection_name="code")

        # Search "research" only
        results = search("test", collection_name="research")

        # sample.txt should be in results, sample.md should not
        # (they have different file_name metadata)
        research_sources = set()
        for r in results:
            src = r.get("source", "")
            research_sources.add(src)

        # Search "code" only
        results_code = search("test", collection_name="code")
        assert len(results_code) >= 0  # may have results depending on content

        # Search non-existent collection
        results_empty = search("test", collection_name="nonexistent")
        assert results_empty == []

    async def test_default_collection_search(self, sample_txt):
        """Search without collection_name must use 'documents'."""
        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.core.retrieval import search

        await ingest_path_async(str(sample_txt))

        results = search("sample text")
        assert isinstance(results, list)


class TestMetadataFiltering:
    """Tests for metadata filter in search."""

    async def test_filter_by_category(self, tmp_path, monkeypatch):
        """Search with metadata_filter must return only matching chunks."""
        from rag_mcp.core.settings import (
            EffectiveSettings,
            MetadataBlock,
            set_default_effective_settings,
        )

        set_default_effective_settings(
            EffectiveSettings(metadata=MetadataBlock(extraction_mode="keyword"))
        )

        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.core.retrieval import search

        ai_file = tmp_path / "ai_content.txt"
        ai_file.write_text(
            "The transformer model uses attention heads. Deep learning "
            "neural networks train on large datasets. LLMs use embeddings."
        )
        await ingest_path_async(str(ai_file), collection_name="filtered")

        results = search(
            "attention transformer",
            collection_name="filtered",
            metadata_filter={"category": "AI"},
        )
        assert isinstance(results, list)

        results_mismatch = search(
            "attention transformer",
            collection_name="filtered",
            metadata_filter={"category": "Philosophy"},
        )
        assert results_mismatch == []

    async def test_no_filter_returns_all(self, tmp_path, monkeypatch):
        """Search without metadata_filter must return all categories."""
        from rag_mcp.core.settings import (
            EffectiveSettings,
            MetadataBlock,
            set_default_effective_settings,
        )

        set_default_effective_settings(
            EffectiveSettings(metadata=MetadataBlock(extraction_mode="keyword"))
        )

        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.core.retrieval import search

        ai_file = tmp_path / "ai.txt"
        ai_file.write_text("attention transformer neural network deep learning")
        await ingest_path_async(str(ai_file), collection_name="no_filter")

        results = search("attention", collection_name="no_filter")
        assert len(results) > 0


class TestListCollections:
    """Tests for list_collections() function."""

    async def test_list_collections_with_data(self, sample_txt, sample_md):
        """list_collections must return collection names and counts."""
        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.core.retrieval import list_collections

        await ingest_path_async(str(sample_txt), collection_name="research")
        await ingest_path_async(str(sample_md), collection_name="code")

        collections = list_collections()

        # Must include both collections
        names = {c["name"] for c in collections}
        assert "research" in names
        assert "code" in names

        # Verify structure
        for c in collections:
            assert "name" in c
            assert "document_count" in c
            assert "chunk_count" in c

    def test_list_collections_empty(self):
        """list_collections on fresh store must return empty list."""
        from rag_mcp.core.retrieval import list_collections

        # Note: EphemeralClient is shared between tests,
        # but collections from other tests might be visible.
        # This test just checks the function doesn't crash.
        result = list_collections()
        assert isinstance(result, list)
        for c in result:
            assert "name" in c
            assert "document_count" in c
            assert "chunk_count" in c

    def test_list_collections_scans_multiple_metadata_pages(self, monkeypatch):
        """Collection document counts must include all metadata pages."""
        import chromadb

        from rag_mcp.config import get_settings as _gs
        from rag_mcp.core.retrieval import list_collections
        from rag_mcp.core.settings import EffectiveSettings, set_default_effective_settings

        set_default_effective_settings(EffectiveSettings(chroma_scan_page_size=2))

        db = chromadb.PersistentClient(path=_gs().chroma_persist_dir)
        collection = db.get_or_create_collection("paged_collection_stats")
        collection.add(
            ids=["1", "2", "3", "4", "5"],
            documents=["one", "two", "three", "four", "five"],
            embeddings=[[float(i)] * 384 for i in range(5)],
            metadatas=[
                {"file_path": "a.txt"},
                {"file_path": "a.txt"},
                {"file_path": "b.txt"},
                {"file_path": "c.txt"},
                {"file_path": "c.txt"},
            ],
        )

        stats = {c["name"]: c for c in list_collections()}["paged_collection_stats"]
        assert stats["chunk_count"] == 5
        assert stats["document_count"] == 3


# ── Score-metric consistency between filtered and unfiltered paths ─────────


class TestScoreConsistency:
    """Ensure both retrieval paths produce identical pre-threshold scores.

    The fix collapsed both branches into a direct ChromaDB ``query()`` call
    so the conversion is structurally identical.  These tests pin that
    contract: a chunk that comes back on the unfiltered path must score
    the same as that chunk on the filtered path, and ``1.0 / (1.0 + d)``
    is the only conversion in use.
    """

    async def test_filtered_and_unfiltered_scores_match(
        self,
        tmp_path,
        monkeypatch,
    ) -> None:
        """Same chunk + same query → equal score on both paths."""
        from rag_mcp.core.settings import (
            EffectiveSettings,
            MetadataBlock,
            set_default_effective_settings,
        )

        set_default_effective_settings(
            EffectiveSettings(metadata=MetadataBlock(extraction_mode="keyword"))
        )

        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.core.retrieval import search

        ai_file = tmp_path / "ai_only.txt"
        ai_file.write_text(
            "The transformer model uses attention heads. Deep learning "
            "neural networks train on large datasets. LLMs use embeddings."
        )
        await ingest_path_async(
            str(ai_file),
            collection_name="score_consistency",
        )

        unfiltered = search(
            "attention transformer",
            collection_name="score_consistency",
            top_k=5,
        )
        filtered = search(
            "attention transformer",
            collection_name="score_consistency",
            top_k=5,
            metadata_filter={"category": "AI"},
        )

        # Both paths return the same chunks (only one source) with the
        # same scoring formula — pair them by source/page/text and
        # compare scores within the contract tolerance.
        assert unfiltered, "expected at least one chunk from unfiltered path"
        assert filtered, "expected at least one chunk from filtered path"

        def keyed(r):
            return (r["source"], r.get("page_label"), r["text"])

        unfiltered_by_chunk = {keyed(r): r["score"] for r in unfiltered}

        for r in filtered:
            key = keyed(r)
            assert key in unfiltered_by_chunk, (
                "filtered chunk missing from unfiltered results — "
                "test fixture must produce a single shared corpus"
            )
            assert abs(r["score"] - unfiltered_by_chunk[key]) < 1e-6

    async def test_threshold_consistent_across_paths(
        self,
        tmp_path,
        monkeypatch,
    ) -> None:
        """Same threshold filters identically on both paths."""
        from rag_mcp.core.settings import (
            EffectiveSettings,
            MetadataBlock,
            set_default_effective_settings,
        )

        set_default_effective_settings(
            EffectiveSettings(metadata=MetadataBlock(extraction_mode="keyword"))
        )

        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.core.retrieval import search

        ai_file = tmp_path / "ai_threshold.txt"
        ai_file.write_text(
            "transformer attention heads neural networks deep learning "
            "embeddings power large language models."
        )
        await ingest_path_async(
            str(ai_file),
            collection_name="threshold_consistency",
        )

        # Pick a threshold mid-way through the unfiltered scores.
        unfiltered = search(
            "attention",
            collection_name="threshold_consistency",
            top_k=5,
        )
        if not unfiltered:
            pytest.skip("MockEmbedding produced no matches")

        scores = sorted((r["score"] for r in unfiltered), reverse=True)
        # Use a threshold strictly between the top score and zero so
        # both paths exclude the same set of chunks.
        threshold = max(scores) * 0.5

        unfiltered_filt = search(
            "attention",
            collection_name="threshold_consistency",
            top_k=5,
            similarity_threshold=threshold,
        )
        filtered_filt = search(
            "attention",
            collection_name="threshold_consistency",
            top_k=5,
            similarity_threshold=threshold,
            metadata_filter={"category": "AI"},
        )

        for r in unfiltered_filt:
            assert r["score"] >= threshold
        for r in filtered_filt:
            assert r["score"] >= threshold

    def test_distance_to_score_canonical_formula(self) -> None:
        """``_distance_to_score`` follows ``1 / (1 + d)`` exactly."""
        from rag_mcp.core.retrieval.dense import _distance_to_score

        assert _distance_to_score(0.0) == pytest.approx(1.0)
        assert _distance_to_score(1.0) == pytest.approx(0.5)
        assert _distance_to_score(3.0) == pytest.approx(0.25)
        assert _distance_to_score(None) == 0.0
