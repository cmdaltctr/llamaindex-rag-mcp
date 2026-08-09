"""Tests for metadata degradation surfacing.

Covers openspec/changes/fix-silent-metadata-degradation/ task group 4:
the ``_signal_degraded`` abandon points in the LLM-backed backends, the
``extract_metadata_with_status_async`` wrapper in ``core/metadata/
extractor.py``, the chunker settings-forwarding fix (chunker.py:168), and
the ``metadata_degraded`` aggregation in ``core/ingestion/pipeline.py``.

See specs/metadata-extraction/spec.md ("Metadata degradation is reported,
not only logged") and specs/async-ingestion/spec.md ("Ingestion result
reports metadata degradation").
"""

from __future__ import annotations

import asyncio
import json

import pytest

from rag_mcp.core.metadata._common import _degradation_flag
from rag_mcp.core.settings import EffectiveSettings, MetadataBlock


class _FakeAsyncClient:
    """httpx.AsyncClient stand-in whose ``post`` always fails.

    Drives a direct-chat backend to exhaust its retry budget and return
    the ``uncategorised`` fallback without any real network access.
    """

    def __init__(self, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None

    async def post(self, *args, **kwargs):
        raise RuntimeError("stub client — no real request")


class _AlwaysSucceedsClient:
    """httpx.AsyncClient stand-in that returns a valid classification."""

    def __init__(self, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None

    async def post(self, *args, **kwargs):
        from unittest.mock import MagicMock

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"category": "ai", "keywords": ["a"], "summary": "s"}
                        )
                    }
                }
            ]
        }
        return resp


# ── Task 4.2: direct-chat backends signal degraded on retry exhaustion ──


class TestDirectChatSignalsDegraded:
    """Each direct-chat backend's exhausted-retry fallback sets the flag."""

    @staticmethod
    def _run_and_read_flag(coro_factory):
        """Run *coro_factory* and read the flag inside the same asyncio Task.

        ``asyncio.run()`` wraps its coroutine in a fresh ``Task``, which
        snapshots a COPY of the current context (contextvars semantics).
        Setting/reading the ContextVar from outside that Task — before or
        after ``asyncio.run()`` — sees a different copy and would silently
        observe no mutation. Set, await, and read all inside one coroutine
        so they share the same Task context.
        """
        async def _wrapped():
            token = _degradation_flag.set(False)
            try:
                result = await coro_factory()
                return result, _degradation_flag.get()
            finally:
                _degradation_flag.reset(token)

        return asyncio.run(_wrapped())

    def test_llamacpp_exhausted_retries_signals_degraded(self, monkeypatch) -> None:
        monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
        from rag_mcp.core.metadata.llamacpp import _extract_llamacpp_chat_async

        settings = EffectiveSettings(metadata=MetadataBlock(classify_max_attempts=1))
        result, degraded = self._run_and_read_flag(
            lambda: _extract_llamacpp_chat_async("text", "f.txt", settings)
        )
        assert result["category"] == "uncategorised"
        assert degraded is True

    def test_ollama_exhausted_retries_signals_degraded(self, monkeypatch) -> None:
        monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
        from rag_mcp.core.metadata.ollama import _extract_ollama_async

        settings = EffectiveSettings(metadata=MetadataBlock(classify_max_attempts=1))
        result, degraded = self._run_and_read_flag(
            lambda: _extract_ollama_async("text", "f.txt", settings)
        )
        assert result["category"] == "uncategorised"
        assert degraded is True

    def test_openrouter_exhausted_retries_signals_degraded(self, monkeypatch) -> None:
        monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
        from rag_mcp.core.metadata.openrouter import _extract_openrouter_chat_async

        settings = EffectiveSettings(metadata=MetadataBlock(classify_max_attempts=1))
        result, degraded = self._run_and_read_flag(
            lambda: _extract_openrouter_chat_async("text", "f.txt", settings)
        )
        assert result["category"] == "uncategorised"
        assert degraded is True

    def test_llamacpp_success_does_not_signal_degraded(self, monkeypatch) -> None:
        """A successful classification never sets the degradation flag."""
        monkeypatch.setattr("httpx.AsyncClient", _AlwaysSucceedsClient)
        from rag_mcp.core.metadata.llamacpp import _extract_llamacpp_chat_async

        settings = EffectiveSettings(metadata=MetadataBlock(classify_max_attempts=1))
        result, degraded = self._run_and_read_flag(
            lambda: _extract_llamacpp_chat_async("text", "f.txt", settings)
        )
        assert result["category"] == "ai"
        assert degraded is False


# ── Task 4.2: llamaindex.py signals degraded at both abandon points ─────


class TestLlamaIndexSignalsDegraded:
    """The ImportError and except-Exception branches both set the flag."""

    def test_import_error_signals_degraded(self, monkeypatch) -> None:
        original_import = __import__

        def _fake_import(name, *args, **kwargs):
            if name == "llama_index.llms.ollama":
                raise ImportError("No module named 'llama_index.llms.ollama'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _fake_import)

        async def _fake_ollama(text, file_name="", settings=None) -> dict:
            return {"category": "ai", "keywords": [], "summary": ""}

        monkeypatch.setattr(
            "rag_mcp.core.metadata.ollama._extract_ollama_async", _fake_ollama
        )

        from rag_mcp.core.metadata.llamaindex import _extract_llamaindex_async

        settings = EffectiveSettings(local_backend="ollama")

        async def _run():
            token = _degradation_flag.set(False)
            try:
                await _extract_llamaindex_async("text", "f.txt", settings)
                return _degradation_flag.get()
            finally:
                _degradation_flag.reset(token)

        assert asyncio.run(_run()) is True

    def test_pipeline_exception_signals_degraded(self, monkeypatch) -> None:
        """Pipeline runs but ``arun()`` raises — the except branch fires."""
        import sys
        from unittest.mock import MagicMock

        monkeypatch.setitem(sys.modules, "llama_index.llms.ollama", MagicMock())
        monkeypatch.setattr(sys.modules["llama_index.llms.ollama"], "Ollama", MagicMock())

        mock_extractors = MagicMock()
        mock_extractors.TitleExtractor = MagicMock()
        mock_extractors.KeywordExtractor = MagicMock()
        mock_extractors.SummaryExtractor = MagicMock()
        monkeypatch.setitem(sys.modules, "llama_index.core.extractors", mock_extractors)
        monkeypatch.setitem(sys.modules, "llama_index.core.node_parser", MagicMock())

        mock_pipeline = MagicMock()
        mock_pipeline.arun.side_effect = RuntimeError("empty response")
        mock_ingestion = MagicMock()
        mock_ingestion.IngestionPipeline = MagicMock(return_value=mock_pipeline)
        monkeypatch.setitem(sys.modules, "llama_index.core.ingestion", mock_ingestion)

        async def _fake_ollama(text, file_name="", settings=None) -> dict:
            return {"category": "ai", "keywords": [], "summary": ""}

        monkeypatch.setattr(
            "rag_mcp.core.metadata.ollama._extract_ollama_async", _fake_ollama
        )

        from rag_mcp.core.metadata.llamaindex import _extract_llamaindex_async

        settings = EffectiveSettings(local_backend="ollama")

        async def _run():
            token = _degradation_flag.set(False)
            try:
                await _extract_llamaindex_async("text", "f.txt", settings)
                return _degradation_flag.get()
            finally:
                _degradation_flag.reset(token)

        assert asyncio.run(_run()) is True


# ── Task 4.1: extract_metadata_with_status_async detection rule ─────────


class TestExtractMetadataWithStatusAsync:
    """The wrapper applies the detection rule: LLM-backed mode + fallback tier."""

    def test_llamaindex_success_raises_no_signal(self, monkeypatch) -> None:
        """Scenario: successful extraction raises no degradation signal."""
        async def _fake_llamaindex(text, file_name="", settings=None) -> dict:
            return {"category": "ai", "keywords": ["x"], "summary": "s"}

        monkeypatch.setattr(
            "rag_mcp.core.metadata.llamaindex._extract_llamaindex_async",
            _fake_llamaindex,
        )

        from rag_mcp.core.metadata.extractor import extract_metadata_with_status_async

        settings = EffectiveSettings(metadata=MetadataBlock(extraction_mode="llamaindex"))
        metadata, degraded = asyncio.run(
            extract_metadata_with_status_async("text", "f.txt", settings)
        )
        assert metadata["category"] == "ai"
        assert degraded is False

    def test_llamaindex_fallback_signals_degraded(self, monkeypatch) -> None:
        """Scenario: timeout fallback is signalled."""
        async def _degrading_llamaindex(text, file_name="", settings=None) -> dict:
            from rag_mcp.core.metadata._common import _signal_degraded
            _signal_degraded()
            return {"category": "uncategorised", "keywords": [], "summary": ""}

        monkeypatch.setattr(
            "rag_mcp.core.metadata.llamaindex._extract_llamaindex_async",
            _degrading_llamaindex,
        )

        from rag_mcp.core.metadata.extractor import extract_metadata_with_status_async

        settings = EffectiveSettings(metadata=MetadataBlock(extraction_mode="llamaindex"))
        metadata, degraded = asyncio.run(
            extract_metadata_with_status_async("text", "f.txt", settings)
        )
        assert metadata["category"] == "uncategorised"
        assert degraded is True

    def test_local_mode_fallback_signals_degraded(self, monkeypatch) -> None:
        """Configured mode 'local' also counts as LLM-backed."""
        async def _degrading_ollama(text, file_name="", settings=None) -> dict:
            from rag_mcp.core.metadata._common import _signal_degraded
            _signal_degraded()
            return {"category": "uncategorised", "keywords": [], "summary": ""}

        monkeypatch.setattr(
            "rag_mcp.core.metadata.ollama._extract_ollama_async", _degrading_ollama
        )

        from rag_mcp.core.metadata.extractor import extract_metadata_with_status_async

        settings = EffectiveSettings(
            local_backend="ollama",
            metadata=MetadataBlock(extraction_mode="local"),
        )
        metadata, degraded = asyncio.run(
            extract_metadata_with_status_async("text", "f.txt", settings)
        )
        assert degraded is True

    def test_keyword_mode_never_degrades(self, monkeypatch) -> None:
        """Scenario constraint: keyword as the configured mode never degrades.

        Even if a leftover flag from a prior call were somehow left set,
        keyword mode never touches an LLM backend and the wrapper's
        detection rule excludes non-LLM-backed modes outright.
        """
        from rag_mcp.core.metadata.extractor import extract_metadata_with_status_async

        settings = EffectiveSettings(metadata=MetadataBlock(extraction_mode="keyword"))
        token = _degradation_flag.set(True)  # simulate leftover noise
        try:
            metadata, degraded = asyncio.run(
                extract_metadata_with_status_async("text", "f.txt", settings)
            )
            assert degraded is False
        finally:
            _degradation_flag.reset(token)

    def test_disabled_mode_never_degrades(self) -> None:
        from rag_mcp.core.metadata.extractor import extract_metadata_with_status_async

        settings = EffectiveSettings(metadata=MetadataBlock(extraction_mode="disabled"))
        metadata, degraded = asyncio.run(
            extract_metadata_with_status_async("text", "f.txt", settings)
        )
        assert metadata == {}
        assert degraded is False


# ── Task 4.3: chunker forwards settings (fixes chunker.py:168 bug) ──────


class TestChunkerForwardsSettings:
    """Regression test for the settings-drop bug at chunker.py:168.

    Before the fix, ``read_and_chunk_file_async`` called
    ``extract_metadata_async(file_text, file_path.name)`` with no
    ``settings`` argument, so extraction always saw the composition-root
    default (conftest installs ``extraction_mode="disabled"``) rather
    than the resolved profile settings. This test injects a distinct
    keyword rule that only the passed-in settings object knows about; if
    the settings-forwarding fix is reverted, the default
    ``extraction_mode="disabled"`` applies instead and no node gets a
    ``category`` key at all.
    """

    def test_custom_keyword_rule_reaches_extraction(self, sample_txt) -> None:
        custom_rules = json.dumps(
            [{"pattern": "capital|paris|berlin", "category": "geography"}]
        )
        settings = EffectiveSettings(
            metadata=MetadataBlock(extraction_mode="keyword", keyword_rules=custom_rules)
        )

        from rag_mcp.core.ingestion.chunker import read_and_chunk_file_async

        nodes = asyncio.run(read_and_chunk_file_async(sample_txt, settings=settings))
        assert len(nodes) > 0
        for node in nodes:
            assert node.metadata.get("category") == "geography"


# ── Task 4.4/4.5: pipeline.py aggregation ────────────────────────────────


class TestPipelineDegradationAggregation:
    """``ingest_path_async`` aggregates the per-file degradation flag.

    Uses an empty node list from the patched chunker so
    ``embed_and_write_async`` short-circuits — no real embedding model or
    vector store write is exercised; only the aggregation logic in
    ``core/ingestion/pipeline.py`` is under test.
    """

    def test_no_degradation_reports_zero(self, tmp_path, monkeypatch) -> None:
        """Scenario: no degradation reports zero."""
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")

        from rag_mcp.core.ingestion.chunker import _ChunkResult

        async def _fake_read_and_chunk(file_path, **kwargs):
            return _ChunkResult([], metadata_degraded=False)

        monkeypatch.setattr(
            "rag_mcp.core.ingestion.pipeline.read_and_chunk_file_async",
            _fake_read_and_chunk,
        )

        from rag_mcp.core.ingestion import ingest_path_async

        result = asyncio.run(
            ingest_path_async(str(tmp_path), collection_name="degr_zero_test")
        )
        assert result["status"] == "ok"
        assert result["metadata_degraded"] == 0
        assert all("metadata_degraded" not in fd for fd in result["file_details"])

    def test_one_file_degrades(self, tmp_path, monkeypatch) -> None:
        """Scenario: one file degrades — count 1, exactly that entry marked."""
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")
        (tmp_path / "c.txt").write_text("!")

        from rag_mcp.core.ingestion.chunker import _ChunkResult

        async def _fake_read_and_chunk(file_path, **kwargs):
            degraded = file_path.name == "b.txt"
            return _ChunkResult([], metadata_degraded=degraded)

        monkeypatch.setattr(
            "rag_mcp.core.ingestion.pipeline.read_and_chunk_file_async",
            _fake_read_and_chunk,
        )

        from rag_mcp.core.ingestion import ingest_path_async

        result = asyncio.run(
            ingest_path_async(str(tmp_path), collection_name="degr_one_test")
        )
        assert result["status"] == "ok"
        assert result["metadata_degraded"] == 1

        marked = [
            fd for fd in result["file_details"]
            if fd.get("metadata_degraded") is True
        ]
        assert len(marked) == 1
        assert marked[0]["file"] == "b.txt"

        unmarked = [fd for fd in result["file_details"] if fd["file"] != "b.txt"]
        assert all("metadata_degraded" not in fd for fd in unmarked)

    def test_embedding_error_preserves_degradation_count(self, tmp_path, monkeypatch) -> None:
        """Scenario: embedding failure preserves the degradation count.

        Files are read and metadata extracted (some degrading) before
        ``embed_and_write_async`` raises. The error result must still
        carry ``metadata_degraded`` so the caller knows degradation
        happened, even though the embedding step failed.
        """
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")

        from rag_mcp.core.ingestion.chunker import _ChunkResult

        async def _fake_read_and_chunk(file_path, **kwargs):
            degraded = file_path.name == "b.txt"
            return _ChunkResult([], metadata_degraded=degraded)

        monkeypatch.setattr(
            "rag_mcp.core.ingestion.pipeline.read_and_chunk_file_async",
            _fake_read_and_chunk,
        )

        async def _failing_embed(*args, **kwargs):
            raise RuntimeError("embedding backend down")

        monkeypatch.setattr(
            "rag_mcp.core.ingestion.pipeline.embed_and_write_async",
            _failing_embed,
        )

        from rag_mcp.core.ingestion import ingest_path_async

        result = asyncio.run(
            ingest_path_async(str(tmp_path), collection_name="degr_embed_err")
        )
        assert result["status"] == "error"
        assert result["error_type"] == "embedding"
        assert result["metadata_degraded"] == 1

    def test_path_not_found_includes_zero_degraded(self, monkeypatch) -> None:
        """Every result dict includes ``metadata_degraded``, even early exits."""
        from rag_mcp.core.ingestion import ingest_path_async

        result = asyncio.run(
            ingest_path_async("/nonexistent/path", collection_name="degr_404")
        )
        assert result["status"] == "error"
        assert result["metadata_degraded"] == 0


# ── Task 4.5: metadata dict shape is unchanged by the degradation signal ─


class TestMetadataShapeUnchanged:
    """Scenario: degradation signal does not alter metadata shape."""

    def test_degraded_extraction_keeps_category_no_extra_key(self, monkeypatch, sample_txt) -> None:
        monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

        settings = EffectiveSettings(
            local_backend="llamacpp",
            metadata=MetadataBlock(
                extraction_mode="local", classify_max_attempts=1
            ),
        )

        from rag_mcp.core.ingestion.chunker import read_and_chunk_file_async

        nodes = asyncio.run(read_and_chunk_file_async(sample_txt, settings=settings))
        assert len(nodes) > 0
        assert nodes.metadata_degraded is True
        for node in nodes:
            assert node.metadata.get("category") == "uncategorised"
            assert "metadata_degraded" not in node.metadata
            assert "_degraded" not in node.metadata
