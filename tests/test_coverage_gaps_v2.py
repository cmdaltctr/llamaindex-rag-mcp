"""Coverage for modules the v2 refactor created, moved, or reshaped.

Task 12.2/12.3. The relocations and splits left several paths untested —
either because the code moved to a new module (openrouter metadata, the
codebase-map renderer, the store default holder) or because it is new
(the composition-root capability probes).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag_mcp.core.settings import (
    EffectiveSettings,
    MetadataBlock,
    RetrievalBlock,
)


# ── core/metadata/extractor.py: the OpenRouter cloud path ───────────────


class TestOpenRouterExtraction:
    """The cloud metadata backend, reachable via metadata_llm_provider=cloud."""

    def _mock_openrouter(self, monkeypatch, payload: str, fail_times: int = 0):
        calls = {"n": 0}

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": payload}}]
        }

        async def _post(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] <= fail_times:
                raise ConnectionError("transient")
            return response

        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = _post
        monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)
        return calls

    def _settings(self, **kw) -> EffectiveSettings:
        return EffectiveSettings(
            metadata=MetadataBlock(
                extraction_mode="local", ollama_classify_max_attempts=kw.pop("attempts", 1)
            ),
            metadata_llm_provider="cloud",
            cloud_backend="openrouter",
            openrouter_api_key="test-key",
            openrouter_llm_model="test/model",
            **kw,
        )

    async def test_valid_response_is_parsed(self, monkeypatch) -> None:
        """A well-formed OpenRouter reply produces parsed metadata."""
        from rag_mcp.core.metadata.extractor import _extract_openrouter_chat_async

        self._mock_openrouter(
            monkeypatch,
            json.dumps(
                {"category": "ai", "keywords": ["transformer"], "summary": "ok"}
            ),
        )
        result = await _extract_openrouter_chat_async(
            "text", "f.txt", self._settings()
        )
        assert result["category"] == "ai"
        assert "transformer" in result["keywords"]

    async def test_unreachable_falls_back_to_uncategorised(self, monkeypatch) -> None:
        """A total failure degrades rather than raising into the pipeline."""
        from rag_mcp.core.metadata.extractor import _extract_openrouter_chat_async

        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(side_effect=ConnectionError("down"))
        monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)

        async def _no_sleep(_s):
            return None

        monkeypatch.setattr("rag_mcp.core.metadata.ollama._retry_sleep", _no_sleep)
        result = await _extract_openrouter_chat_async(
            "text", "f.txt", self._settings()
        )
        assert result["category"] == "uncategorised"

    async def test_cloud_provider_routes_to_openrouter(self, monkeypatch) -> None:
        """metadata_llm_provider=cloud selects the openrouter strategy."""
        from rag_mcp.core.metadata import extractor as ext

        mock = AsyncMock(return_value={"category": "x", "keywords": [], "summary": ""})
        with patch.dict(ext._metadata_get.__globals__["_cache"], {}, clear=False), \
             patch(
                 "rag_mcp.core.metadata.extractor._extract_openrouter_chat_async",
                 mock,
             ):
            settings = self._settings()
            assert ext._local_strategy_name(settings) == "openrouter"


# ── core/codebase/format.py: the renderer ───────────────────────────────


class TestCodebaseMapRendering:
    """format_codebase_map renders each optional section."""

    def _map(self, **kw):
        from rag_mcp.core.codebase.codebase_map import CodebaseMap, FileInventory

        return CodebaseMap(
            inventory=FileInventory(type_counts={"code/python": 2}), **kw
        )

    def test_renders_code_communities(self) -> None:
        from rag_mcp.core.codebase.format import format_codebase_map

        text = format_codebase_map(
            self._map(
                code_communities=[
                    {
                        "label": "Core",
                        "files": ["a.py", "b.py"],
                        "file_count": 2,
                        "edge_count": 1,
                    }
                ]
            )
        )
        assert "Core" in text

    def test_renders_hubs(self) -> None:
        from rag_mcp.core.codebase.format import format_codebase_map

        text = format_codebase_map(
            self._map(hubs=[{"file": "core.py", "in_degree": 5, "out_degree": 1}])
        )
        assert "core.py" in text

    def test_renders_doc_communities_and_cross_links(self) -> None:
        from rag_mcp.core.codebase.format import format_codebase_map

        text = format_codebase_map(
            self._map(
                doc_communities=[
                    {"label": "Guides", "chunks": ["c1"], "chunk_count": 1,
                     "category": "docs"}
                ],
                cross_links=[
                    {"code": "a.py", "doc": "a.md", "relation": "filename_match"}
                ],
            )
        )
        assert "Guides" in text
        assert "a.md" in text

    def test_empty_map_still_renders(self) -> None:
        """A map with no graph data must produce text, not raise."""
        from rag_mcp.core.codebase.format import format_codebase_map

        assert isinstance(format_codebase_map(self._map()), str)


# ── core/vectordb/__init__.py: the default store holder ─────────────────


class TestDefaultStoreHolder:
    """set/reset/get semantics for the composition-root store."""

    def test_reset_clears_the_default(self) -> None:
        from rag_mcp.core.vectordb import (
            get_default_store,
            reset_default_store,
            set_default_store,
        )

        sentinel = MagicMock()
        set_default_store(sentinel)
        assert get_default_store() is sentinel

        reset_default_store()
        # After reset the holder must rebuild rather than hand back the old one.
        assert get_default_store() is not sentinel


# ── compose.py: the capability probes ───────────────────────────────────


class TestCapabilityProbes:
    """The probes moved out of config in task 7.10."""

    def _settings(self, backend: str):
        from rag_mcp.config import Settings
        from rag_mcp.core.retrieval.settings import RetrievalSettings

        return Settings(
            _env_file=None,
            retrieval=RetrievalSettings(hybrid_sparse_backend=backend),
        )

    def test_bm25_needs_no_probe(self, monkeypatch) -> None:
        """An explicit bm25 selection short-circuits before probing."""
        import rag_mcp.compose as compose
        import rag_mcp.core.retrieval.sparse as sparse

        def _boom():  # pragma: no cover - must not run
            raise AssertionError("probe ran for an explicit bm25 selection")

        monkeypatch.setattr(sparse, "_detect_native_sparse_capability", _boom)
        assert compose.resolve_sparse_backend(self._settings("bm25")) == "bm25"

    @pytest.mark.parametrize(
        "available, expected", [(True, "native"), (False, "bm25")]
    )
    def test_auto_follows_the_probe(self, monkeypatch, available, expected) -> None:
        import rag_mcp.compose as compose
        import rag_mcp.core.retrieval.sparse as sparse

        monkeypatch.setattr(
            sparse, "_detect_native_sparse_capability", lambda: available
        )
        assert compose.resolve_sparse_backend(self._settings("auto")) == expected

    def test_pdf_reader_explicit_value_is_returned(self) -> None:
        """An explicit reader bypasses the LiteParse probe."""
        import rag_mcp.compose as compose
        from rag_mcp.config import Settings

        settings = Settings(_env_file=None, pdf_reader="pypdf")
        assert compose.resolve_pdf_reader(settings) == "pypdf"


# ── core/chunking/sentence.py: settings resolution at the boundary ──────


class TestSentenceChunkerSettings:
    """The sentence strategy resolves its own settings when called directly."""

    async def test_explicit_sizes_win_over_injected(self) -> None:
        from llama_index.core import Document

        from rag_mcp.core.chunking.sentence import chunk_sentence_file_async

        nodes = await chunk_sentence_file_async(
            [Document(text="one two three. " * 50)],
            "f.txt",
            is_markdown=False,
            chunk_size=64,
            chunk_overlap=8,
            settings=EffectiveSettings(),
        )
        assert nodes

    async def test_injected_settings_supply_the_defaults(self) -> None:
        from llama_index.core import Document

        from rag_mcp.core.chunking.sentence import chunk_sentence_file_async

        nodes = await chunk_sentence_file_async(
            [Document(text="alpha beta gamma. " * 40)],
            "f.md",
            is_markdown=True,
            settings=EffectiveSettings(),
        )
        assert nodes
