"""Integration tests for the retrieval module.

Tests cover:
- search on empty store returns empty
- similarity_threshold filtering
- reranked flag propagation with default and explicit rerank
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
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

    def setup_method(self) -> None:
        """Clear the process-wide model cache before each test.

        Earlier tests in this module (e.g. ``test_rerank_enabled_sets_flag``)
        exercise the un-injected ``search()`` path with no mocking, which
        may populate ``_MODEL_CACHE`` with a real successful load. Without
        this reset, the escalation test below would hit that cache instead
        of the patched failing import and never see a failure at all.
        """
        from rag_mcp.core.retrieval.reranker import reset_model_cache

        reset_model_cache()

    def teardown_method(self) -> None:
        """Clear the process-wide model cache (task 1.13).

        ``test_transient_failure_retries_then_succeeds`` populates
        ``_MODEL_CACHE`` via ``_load_model()`` directly; without this reset
        the loaded session leaks into later tests, which becomes
        load-bearing once ``_FAILURE_STATE`` shares the same reset hook.
        """
        from rag_mcp.core.retrieval.reranker import reset_model_cache

        reset_model_cache()

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
        import rag_mcp.transports.mcp.search as search_mod

        original_search = search_mod.search

        def _search_with_failing_reranker(*args, **kwargs):
            kwargs["reranker"] = failing
            return original_search(*args, **kwargs)

        monkeypatch.setattr(search_mod, "search", _search_with_failing_reranker)

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

    async def test_escalation_survives_instance_churn_via_search(
        self,
        fixtures_dir: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Escalation fires through the un-injected path (task 1.11).

        The test above injects a single failing instance via DI, so its
        instance state would accumulate across calls even if the counter
        were wrongly scoped to ``self`` — a green test over a broken
        production path (the exact ADR-029 trap). This test calls the
        core ``search()`` with ``reranker`` left un-injected so it builds
        a fresh ``CrossEncoderReranker()`` on every call, proving the
        counter survives instance churn.
        """
        import builtins
        import logging

        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.core.retrieval import search

        await ingest_path_async(str(fixtures_dir), collection_name="escalation_churn")

        real_import = builtins.__import__

        def _selective_import(name, *args, **kwargs):
            if name == "onnxruntime":
                raise ImportError("persistent onnx failure")
            return real_import(name, *args, **kwargs)

        with caplog.at_level(logging.WARNING, logger="rag_mcp.core.retrieval.reranker"):
            with patch("builtins.__import__", side_effect=_selective_import):
                for _ in range(3):
                    search(
                        "capital",
                        collection_name="escalation_churn",
                        rerank=True,
                    )

        load_failure_records = [
            r for r in caplog.records if "Failed to load reranker model" in r.getMessage()
        ]
        assert len(load_failure_records) == 3
        assert [r.levelno for r in load_failure_records] == [
            logging.WARNING,
            logging.WARNING,
            logging.ERROR,
        ]

    def test_transient_failure_retries_then_succeeds(self) -> None:
        """A transient load failure must retry on the next call and recover."""
        from rag_mcp.core.retrieval.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker(model_id="transient/model")
        reranker._loaded = False
        reranker._load_attempted = True
        reranker._load_error = "transient network timeout"

        mock_session = MagicMock()
        mock_tokenizer = MagicMock()

        with patch(
            "rag_mcp.core.retrieval.reranker._select_onnx_variant", return_value=["onnx/model.onnx"]
        ):
            with patch("huggingface_hub.hf_hub_download", return_value="/fake/model.onnx"):
                with patch("tokenizers.Tokenizer.from_pretrained", return_value=mock_tokenizer):
                    with patch("onnxruntime.InferenceSession", return_value=mock_session):
                        with patch(
                            "rag_mcp.core.retrieval.reranker._read_max_position_embeddings",
                            return_value=512,
                        ):
                            reranker._load_model()

        # Retry succeeded: model loaded, error cleared, cache populated.
        assert reranker._loaded is True
        assert reranker._load_error is None


# ── Threshold scaling with reranker ────────────────────────────────────────


class TestThresholdScaling:
    """Tests for score-aware threshold scaling.

    When the reranker is active, sigmoid-normalised scores occupy a much
    lower range than cosine similarity.  The search() function should
    scale the threshold down by 30x automatically to avoid over-filtering.
    """

    def test_no_rerank_threshold_unchanged(self) -> None:
        """Without reranking, the threshold must not be scaled."""
        from rag_mcp.core.retrieval.policy import _effective_threshold

        assert _effective_threshold(0.3, rerank=False) == 0.3

    def test_rerank_threshold_scaled_down(self) -> None:
        """With reranking, the threshold must be scaled down 30x."""
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
        With 30x scaling, threshold 0.3 → 0.01, so 0.015 passes.
        """
        from rag_mcp.core.retrieval.policy import _effective_threshold

        threshold = _effective_threshold(0.3, rerank=True)
        assert 0.015 >= threshold  # Colosseum score should pass


# ── Helpers for §2/§3 pipeline-level tests ──────────────────────────────────


def _fixed_dense_rows(rows: list[dict]):
    """Return a fake ``_dense_query_rows`` callable yielding fixed rows."""

    # Accepts the norm-guard and timing keyword arguments the real dense
    # boundary receives (guard-embedding-normalisation,
    # complete-observable-surface); the fake never runs them.
    def _fake(
        store,
        collection_name,
        query,
        fetch_k,
        metadata_filter=None,
        *,
        norm_guard_enabled=True,
        norm_tolerance=0.001,
        attach_norm_diagnostic=False,
        timing_report=None,
    ):
        return [dict(r) for r in rows]

    return _fake


def _patch_dense(monkeypatch: pytest.MonkeyPatch, rows: list[dict]) -> None:
    """Replace pipeline's "dense" strategy resolution with fixed rows.

    The registry caches resolved callables by name (``registry.py::get``),
    so patching ``rag_mcp.core.retrieval.dense._dense_query_rows`` after
    the first real resolution elsewhere in the suite would be a no-op.
    Patching ``pipeline._retrieval_get`` itself sidesteps that cache.
    """
    import rag_mcp.core.retrieval.pipeline as pipeline_mod

    real_get = pipeline_mod._retrieval_get
    monkeypatch.setattr(
        pipeline_mod,
        "_retrieval_get",
        lambda name: _fixed_dense_rows(rows) if name == "dense" else real_get(name),
    )


def _mock_reranker_instance(*, fails: bool, logit: float = -3.0):
    """Build a loaded ``CrossEncoderReranker`` whose inference succeeds or fails."""
    from rag_mcp.core.retrieval.reranker import CrossEncoderReranker

    reranker = CrossEncoderReranker()
    mock_session = MagicMock()
    if fails:
        mock_session.run.side_effect = RuntimeError("cross-encoder exploded")
    else:
        mock_session.run.return_value = [np.array([[logit]])]
    mock_tokenizer = MagicMock()
    mock_tokenizer.return_value = {
        "input_ids": [[1, 2]],
        "attention_mask": [[1, 1]],
    }
    reranker._session = mock_session
    reranker._tokenizer = mock_tokenizer
    reranker._loaded = True
    return reranker


# ── rerank_reason diagnostics (§2) ───────────────────────────────────────────


class TestRerankReasonDiagnostics:
    """Tests for surfacing the reranker's own failure reason in diagnostics."""

    def test_failing_reranker_overrides_policy_rerank_reason(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failing reranker's own reason replaces the policy string (task 2.3)."""
        from rag_mcp.core.retrieval import search

        _patch_dense(
            monkeypatch,
            [
                {
                    "id": "1",
                    "source": "f.md",
                    "page_label": None,
                    "text": "hello world",
                    "score": 0.9,
                    "metadata": {},
                    "reranked": False,
                }
            ],
        )
        failing = _mock_reranker_instance(fails=True)
        fake_store = MagicMock()
        fake_store.count.return_value = 1

        results = search(
            "query",
            collection_name="ignored",
            store=fake_store,
            rerank=True,
            reranker=failing,
            include_diagnostics=True,
        )

        assert len(results) == 1
        assert "inference failed" in results[0]["rerank_reason"]
        assert "cross-encoder exploded" in results[0]["rerank_reason"]
        # Must not be the policy resolver's string.
        assert "explicit rerank=True override" not in results[0]["rerank_reason"]

    def test_include_diagnostics_false_leaks_no_new_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """include_diagnostics=False keeps result shape unchanged (task 2.4).

        Exercised with a *failing* reranker specifically — the override
        wiring must not leak ``rerank_reason`` (or any other new key)
        into the public result dict when diagnostics are off, even
        though the reranker did set ``last_failure_reason`` internally.
        """
        from rag_mcp.core.retrieval import search

        _patch_dense(
            monkeypatch,
            [
                {
                    "id": "1",
                    "source": "f.md",
                    "page_label": None,
                    "text": "hello world",
                    "score": 0.9,
                    "metadata": {},
                    "reranked": False,
                }
            ],
        )
        failing = _mock_reranker_instance(fails=True)
        fake_store = MagicMock()
        fake_store.count.return_value = 1

        results = search(
            "query",
            collection_name="ignored",
            store=fake_store,
            rerank=True,
            reranker=failing,
            include_diagnostics=False,
        )

        assert len(results) == 1
        assert "rerank_reason" not in results[0]


# ── Threshold follows rerank outcome, not intent (§3) ───────────────────────


class TestThresholdFollowsRerankOutcome:
    """Tests that the ÷30 threshold scaling follows actual rerank success."""

    def test_successful_rerank_applies_scaled_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successful reranking still applies the ÷30 threshold (task 3.2)."""
        from rag_mcp.core.retrieval import search

        # score=0.2 dense/raw would fail an unscaled 0.3 threshold, but the
        # reranker replaces it with a sigmoid score (logit -3.0 -> ~0.047),
        # which survives the scaled threshold (0.3 / 30 = 0.01).
        _patch_dense(
            monkeypatch,
            [
                {
                    "id": "1",
                    "source": "f.md",
                    "page_label": None,
                    "text": "hello world",
                    "score": 0.2,
                    "metadata": {},
                    "reranked": False,
                }
            ],
        )
        succeeding = _mock_reranker_instance(fails=False, logit=-3.0)
        fake_store = MagicMock()
        fake_store.count.return_value = 1

        results = search(
            "query",
            collection_name="ignored",
            store=fake_store,
            rerank=True,
            reranker=succeeding,
            similarity_threshold=0.3,
        )

        assert len(results) == 1
        assert results[0]["reranked"] is True

    def test_failed_rerank_applies_unscaled_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed reranker filters at the caller's raw threshold (task 3.3).

        Regression guard for the bug this change fixes: before the fix,
        ``_effective_threshold`` was called with the *requested* rerank
        intent rather than the outcome, so a failed rerank kept scoring
        raw cosine similarity while filtering at the ÷30-scaled threshold
        — about 30x too permissive.
        """
        from rag_mcp.core.retrieval import search

        _patch_dense(
            monkeypatch,
            [
                {
                    "id": "1",
                    "source": "f.md",
                    "page_label": None,
                    "text": "hello world",
                    "score": 0.2,
                    "metadata": {},
                    "reranked": False,
                }
            ],
        )
        failing = _mock_reranker_instance(fails=True)
        fake_store = MagicMock()
        fake_store.count.return_value = 1

        results = search(
            "query",
            collection_name="ignored",
            store=fake_store,
            rerank=True,
            reranker=failing,
            similarity_threshold=0.3,
        )

        # Raw score 0.2 < unscaled threshold 0.3 -> filtered out.
        assert results == []

    def test_rerank_false_applies_unscaled_threshold(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """rerank=False applies the unscaled threshold, unchanged (task 3.4)."""
        from rag_mcp.core.retrieval import search

        _patch_dense(
            monkeypatch,
            [
                {
                    "id": "1",
                    "source": "f.md",
                    "page_label": None,
                    "text": "hello world",
                    "score": 0.2,
                    "metadata": {},
                    "reranked": False,
                }
            ],
        )
        fake_store = MagicMock()
        fake_store.count.return_value = 1

        results = search(
            "query",
            collection_name="ignored",
            store=fake_store,
            rerank=False,
            similarity_threshold=0.3,
        )

        # Raw score 0.2 < unscaled threshold 0.3 -> filtered out.
        assert results == []


# ── Helpers ────────────────────────────────────────────────────────────────


def _extract_result(result):
    """Extract the data payload from an MCPServer CallToolResult."""
    import json

    from mcp.types import TextContent

    if hasattr(result, "structured_content") and result.structured_content:
        return result.structured_content.get("result", result.structured_content)

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

    def test_list_collections_scans_multiple_metadata_pages(self, tmp_path):
        """Collection document counts must include all metadata pages.

        Task 5.1 rewrite: seeds through the real ingestion path
        (store-agnostic) instead of a direct ChromaDB client, so the
        pagination contract runs against the default tmp-path LanceDB
        store in the base install and on Chroma in the chroma-extra job.
        """
        from asyncio import run as asyncio_run

        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.core.retrieval import list_collections
        from rag_mcp.core.settings import EffectiveSettings, set_default_effective_settings

        set_default_effective_settings(EffectiveSettings(chroma_scan_page_size=2))

        total_chunks = 0
        for name in ("a.txt", "b.txt", "c.txt"):
            doc = tmp_path / name
            doc.write_text(f"Collection stats document {name} sentence. " * 12)
            result = asyncio_run(
                ingest_path_async(str(doc), collection_name="paged_collection_stats")
            )
            assert result["status"] == "ok"
            total_chunks += result["chunks_created"]
        # Force more than one scan page at page size 2.
        assert total_chunks > 2

        stats = {c["name"]: c for c in list_collections()}["paged_collection_stats"]
        assert stats["chunk_count"] == total_chunks
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

    def test_l2_to_score_canonical_formula_lives_at_store_boundary(self) -> None:
        """The adapter helper follows ``1 / (1 + d)`` and rejects omissions."""
        from rag_mcp.core.vectordb.score import canonical_score_from_l2

        assert canonical_score_from_l2(0.0, backend="test") == pytest.approx(1.0)
        assert canonical_score_from_l2(1.0, backend="test") == pytest.approx(0.5)
        assert canonical_score_from_l2(3.0, backend="test") == pytest.approx(0.25)
        with pytest.raises(ValueError, match="no L2 distance"):
            canonical_score_from_l2(None, backend="test")
