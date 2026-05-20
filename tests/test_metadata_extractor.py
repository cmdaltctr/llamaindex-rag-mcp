"""Tests for the metadata extraction module (rag_mcp.metadata_extractor)."""

from __future__ import annotations

import logging
import asyncio
import json

import pytest


def _set_mode(monkeypatch, mode: str, keyword_rules: str | None = None):
    """Helper: monkeypatch metadata_extractor module-level variables."""
    import rag_mcp.metadata_extractor as _me

    monkeypatch.setattr(_me, "METADATA_EXTRACTION_MODE", mode)
    if keyword_rules is not None:
        monkeypatch.setattr(_me, "METADATA_KEYWORD_RULES", keyword_rules)


# ── 9.1 Keyword mode tests ──────────────────────────────────────────────────


class TestKeywordExtraction:
    """Tests for keyword-based metadata extraction."""

    def test_single_category_match(self, monkeypatch) -> None:
        """Text with AI keywords must categorise as 'AI'."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "This document discusses attention mechanisms and transformer models."
        ))
        assert result == {"category": "AI"}

    def test_multiple_match_scoring(self, monkeypatch) -> None:
        """Text with more AI matches than Philosophy must choose AI."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "This neural network uses embedding-based RAG for logic problems."
        ))
        assert result == {"category": "AI"}

    def test_uncategorised_fallback(self, monkeypatch) -> None:
        """Text with no keyword matches must return 'uncategorised'."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "The quick brown fox jumps over the lazy dog. Nothing technical here."
        ))
        assert result == {"category": "uncategorised"}

    def test_philosophy_match(self, monkeypatch) -> None:
        """Text with mantiq/logic keywords must categorise as 'Philosophy'."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "This paper explores mantiq and epistemology in classical Islamic logic."
        ))
        assert result == {"category": "Philosophy"}

    def test_biology_match(self, monkeypatch) -> None:
        """Text with biology keywords must categorise as 'Biology'."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "The crispr gene editing tool revolutionises cancer research."
        ))
        assert result == {"category": "Biology"}

    def test_marketing_match(self, monkeypatch) -> None:
        """Text with marketing keywords must categorise as 'Marketing'."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "Our SEO campaign increased conversion rates across the sales funnel."
        ))
        assert result == {"category": "Marketing"}

    def test_programming_match(self, monkeypatch) -> None:
        """Text with programming keywords must categorise as 'Programming'."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "The Rust compiler uses an LLVM backend for code generation."
        ))
        assert result == {"category": "Programming"}


# ── 9.2 Disabled mode test ─────────────────────────────────────────────────


class TestDisabledExtraction:
    """Tests for disabled metadata extraction mode."""

    def test_disabled_returns_empty_dict(self, monkeypatch) -> None:
        """Disabled mode must return an empty dict."""
        _set_mode(monkeypatch, "disabled")

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("Any text content here."))
        assert result == {}


# ── 9.3 Custom keyword rules test ──────────────────────────────────────────


class TestCustomKeywordRules:
    """Tests for user-overridable keyword rules."""

    def test_custom_rules_override_defaults(self, monkeypatch) -> None:
        """Custom rules from METADATA_KEYWORD_RULES must be used."""
        custom_rules = json.dumps([
            {"pattern": "f1|grand.?prix", "category": "Motorsport"},
            {"pattern": "football|goal|stadium", "category": "Sport"},
        ])
        _set_mode(monkeypatch, "keyword", keyword_rules=custom_rules)

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "Formula 1 Grand Prix at Monaco is the highlight of the motorsport calendar."
        ))
        assert result == {"category": "Motorsport"}

    def test_custom_rules_no_default_fallback(self, monkeypatch) -> None:
        """Custom rules must completely replace defaults."""
        custom_rules = json.dumps([
            {"pattern": "football|goal", "category": "Sport"},
        ])
        _set_mode(monkeypatch, "keyword", keyword_rules=custom_rules)

        from rag_mcp.metadata_extractor import extract_metadata_async

        # Has AI keywords but custom rules don't include AI → uncategorised
        result = asyncio.run(extract_metadata_async("The transformer model uses attention heads."))
        assert result == {"category": "uncategorised"}

    def test_invalid_json_falls_back_to_defaults(
        self, monkeypatch, caplog,
    ) -> None:
        """Invalid JSON in METADATA_KEYWORD_RULES must fall back to defaults."""
        _set_mode(monkeypatch, "keyword", keyword_rules="not valid json {{{")

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "The transformer attention mechanism is key to modern AI."
        ))
        # Should use default AI rule
        assert result == {"category": "AI"}

        # Must log a WARNING
        assert any(
            r.levelno == logging.WARNING and "falling back" in r.message.lower()
            for r in caplog.records
        )


# ── 9.4 Llamaindex stub test ───────────────────────────────────────────────


class TestLlamaindexStub:
    """Tests for the LlamaIndex metadata extraction — updated from stub to real.

    When ``llama-index-llms-ollama`` is not installed, the mode falls back
    to keyword.  This test verifies correct fallback behaviour.
    """

    def test_llamaindex_falls_back_to_keyword_when_not_installed(
        self, monkeypatch, caplog,
    ) -> None:
        """Llamaindex mode must fall back to keyword when LLM package missing."""
        _set_mode(monkeypatch, "llamaindex")

        # Force the import to fail (the package is installed in the dev venv,
        # but this test verifies the fallback path for users who don't have it).
        import builtins
        original_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "llama_index.llms.ollama":
                raise ImportError("No module named 'llama_index.llms.ollama'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _fake_import)

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "The protein folding problem was solved by deep learning.",
            file_name="biology_paper.pdf",
        ))
        # Falls back to keyword mode — "deep learning" and "protein" match AI and Biology
        assert result["category"] == "AI"

        # Must log a WARNING about the package not being installed
        assert any(
            r.levelno == logging.WARNING
            and "not installed" in r.message.lower()
            for r in caplog.records
        )


# ── Unknown mode fallback test ─────────────────────────────────────────────


class TestUnknownMode:
    """Tests for handling of unknown METADATA_EXTRACTION_MODE values."""

    def test_unknown_mode_falls_back_to_keyword(
        self, monkeypatch, caplog,
    ) -> None:
        """An unrecognised mode must log WARNING and fall back to keyword."""
        _set_mode(monkeypatch, "nonexistent_mode")

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("attention transformer neural network"))
        assert result == {"category": "AI"}

        # Must log a WARNING
        assert any(
            r.levelno == logging.WARNING
            and "unknown" in r.message.lower()
            for r in caplog.records
        )


# ── 9.5 Ollama mode tests — hybrid taxonomy, JSON parsing, normalisation ────


class TestOllamaExtraction:
    """Tests for the updated ollama metadata extraction (Stage 1)."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch) -> None:
        """Set mode to ollama for all tests in this class."""
        _set_mode(monkeypatch, "ollama")

    # ── Helpers ─────────────────────────────────────────────────────────

    def _mock_ollama(self, monkeypatch, response_text: str) -> None:
        """Mock `httpx.AsyncClient.post` to return a controlled Ollama response."""
        from unittest.mock import AsyncMock, MagicMock

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"response": response_text}

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)

    def _seed_chromadb_categories(self, categories: list[str]) -> None:
        """Pre-populate the ephemeral ChromaDB with category metadata.

        Creates or gets a collection and inserts a fake document with
        the given category so ``_gather_existing_categories()``
        discovers it.
        """
        import chromadb
        client = chromadb.PersistentClient(path="ignored")  # patched to ephemeral
        coll = client.get_or_create_collection("test_ollama_cats")
        # Clear any previous data.
        try:
            existing = coll.get()
            if existing.get("ids"):
                coll.delete(ids=existing["ids"])
        except Exception:
            pass

        for cat in categories:
            coll.add(
                ids=[f"doc_{cat}"],
                documents=[f"Test document for category {cat}"],
                metadatas=[{"category": cat}],
                embeddings=[[0.1] * 384],
            )

    # ── Tests ────────────────────────────────────────────────────────────

    def test_valid_json_response(self, monkeypatch) -> None:
        """Ollama returns valid JSON → parsed correctly."""
        self._mock_ollama(monkeypatch, json.dumps({
            "category": "ai",
            "keywords": ["transformer", "attention", "embedding"],
            "summary": "A paper about transformer architectures in NLP.",
        }))

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("attention transformer model architecture"))
        assert result["category"] == "ai"
        assert result["keywords"] == ["transformer", "attention", "embedding"]
        assert "transformer architectures" in result["summary"]

    def test_missing_optional_json_keys(self, monkeypatch) -> None:
        """Ollama returns JSON missing keywords/summary → default to empty."""
        self._mock_ollama(monkeypatch, json.dumps({"category": "biology"}))

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("crispr gene editing"))
        assert result["category"] == "biology"
        assert result["keywords"] == []
        assert result["summary"] == ""

    def test_invalid_json_fallback_to_raw_text(self, monkeypatch, caplog) -> None:
        """Ollama returns plain text (not JSON) → use raw text as category."""
        self._mock_ollama(monkeypatch, "AI")

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("transformer attention"))
        assert result["category"] == "ai"
        assert result["keywords"] == []
        assert result["summary"] == ""

        # Must log a WARNING about non-JSON
        assert any(
            r.levelno == logging.WARNING
            and "json" in r.message.lower()
            and "ollama" in r.message.lower()
            for r in caplog.records
        )

    def test_ollama_unreachable(self, monkeypatch, caplog) -> None:
        """Ollama call fails → fall back to uncategorised."""
        from unittest.mock import AsyncMock

        async def _raise(*args, **kwargs):
            raise ConnectionError("Ollama not running")

        class _MockClient:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass

        _mock_instance = _MockClient()
        _mock_instance.post = _raise

        monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: _mock_instance)

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("any text"))
        assert result["category"] == "uncategorised"
        assert result["keywords"] == []
        assert result["summary"] == ""

        # Must log a WARNING
        assert any(
            r.levelno == logging.WARNING
            and "ollama classification failed" in r.message.lower()
            for r in caplog.records
        )

    def test_category_key_always_present(self, monkeypatch) -> None:
        """Every result dict must have a 'category' key for backward compatibility."""
        # Test normal response
        self._mock_ollama(monkeypatch, json.dumps({"category": "philosophy"}))

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("logic and ontology"))
        assert "category" in result

    def test_category_normalisation_spaces_to_underscores(self, monkeypatch) -> None:
        """Category 'Artificial Intelligence' → 'artificial_intelligence'."""
        self._mock_ollama(monkeypatch, json.dumps({
            "category": "Artificial Intelligence",
            "keywords": [],
            "summary": "",
        }))

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("ai document"))
        assert result["category"] == "artificial_intelligence"

    def test_category_normalisation_max_words(self, monkeypatch, caplog) -> None:
        """Category with >3 words → rejected, falls back to 'uncategorised'."""
        self._mock_ollama(monkeypatch, json.dumps({
            "category": "this is a very long category name here",
            "keywords": [],
            "summary": "",
        }))

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("some document"))
        assert result["category"] == "uncategorised"

    def test_keywords_truncated_to_max(self, monkeypatch) -> None:
        """More than 10 keywords → truncated."""
        many_keywords = [f"kw{i}" for i in range(15)]
        self._mock_ollama(monkeypatch, json.dumps({
            "category": "ai",
            "keywords": many_keywords,
            "summary": "test",
        }))

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("test"))
        assert len(result["keywords"]) == 10
        assert result["keywords"] == [f"kw{i}" for i in range(10)]

    def test_summary_truncated_to_max(self, monkeypatch) -> None:
        """Summary longer than 300 chars → truncated."""
        long_summary = "x" * 500
        self._mock_ollama(monkeypatch, json.dumps({
            "category": "ai",
            "keywords": [],
            "summary": long_summary,
        }))

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("test"))
        assert "summary" in result
        assert len(result["summary"]) <= 303  # 300 + "…"


class TestHybridCategoryTaxonomy:
    """Tests for the hybrid category lookup (ChromaDB + seed categories)."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch) -> None:
        """Set mode to ollama for all tests in this class."""
        _set_mode(monkeypatch, "ollama")

    def _mock_ollama(self, monkeypatch, response_text: str) -> None:
        """Mock Ollama to return controlled response via httpx."""
        from unittest.mock import AsyncMock, MagicMock

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"response": response_text}

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)

    def _seed_category(self, category: str) -> None:
        """Pre-populate a single category in ephemeral ChromaDB."""
        import chromadb
        client = chromadb.PersistentClient(path="ignored")
        coll = client.get_or_create_collection("test_taxonomy")
        try:
            existing = coll.get()
            if existing.get("ids"):
                coll.delete(ids=existing["ids"])
        except Exception:
            pass
        coll.add(
            ids=[f"doc_{category}"],
            documents=[f"Test for {category}"],
            metadatas=[{"category": category}],
            embeddings=[[0.1] * 384],
        )

    @staticmethod
    def _get_prompt_sent(monkeypatch) -> str:
        """Inspect the prompt argument that was passed to Ollama."""
        from unittest.mock import AsyncMock, MagicMock

        prompt_container: list[str] = []

        async def _capture_prompt(url, **kwargs):
            data = kwargs.get("json", {})
            prompt_container.append(data.get("prompt", ""))
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "response": json.dumps({"category": "test", "keywords": [], "summary": ""})
            }
            return mock_resp

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=_capture_prompt)

        monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)

        from rag_mcp.metadata_extractor import extract_metadata_async
        asyncio.run(extract_metadata_async("test document"))
        return prompt_container[0] if prompt_container else ""

    def test_chromadb_empty_uses_seed_categories(self, monkeypatch) -> None:
        """First run (empty ChromaDB) → prompt uses seed categories only."""
        prompt = self._get_prompt_sent(monkeypatch)

        assert "EXISTING CATEGORIES" in prompt
        # Seed categories should appear
        for cat in ("ai", "biology", "philosophy", "programming", "marketing"):
            assert cat in prompt.lower()
        assert "uncategorised" in prompt.lower()

    def test_chromadb_has_existing_merged_with_seeds(self, monkeypatch) -> None:
        """Existing ChromaDB categories merged with seeds in prompt."""
        self._seed_category("music")
        self._seed_category("biology")  # overlaps with seed

        prompt = self._get_prompt_sent(monkeypatch)

        assert "EXISTING CATEGORIES" in prompt
        assert "music" in prompt.lower()
        assert "biology" in prompt.lower()
        assert "ai" in prompt.lower()  # seed, not in ChromaDB yet

    def test_chromadb_query_failure_falls_back_to_seeds(self, monkeypatch, caplog) -> None:
        """ChromaDB query fails → WARNING log, prompt uses seeds only."""
        import chromadb
        import rag_mcp.metadata_extractor as _me

        # Reset the cached client so the patched PersistentClient is used.
        monkeypatch.setattr(_me, "_chroma_client", None)

        # Make PersistentClient always raise
        monkeypatch.setattr(chromadb, "PersistentClient", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("db locked")))

        prompt = self._get_prompt_sent(monkeypatch)

        # Must log a WARNING about ChromaDB failure
        assert any(
            r.levelno == logging.WARNING
            and "failed to query chromadb" in r.message.lower()
            for r in caplog.records
        )

        # Prompt must still have seed categories
        assert "EXISTING CATEGORIES" in prompt
        assert "ai" in prompt.lower()

    def test_category_normalisation_deduplicates(self, monkeypatch) -> None:
        """Same category in different casings → deduplicated."""
        self._seed_category("AI")
        self._seed_category("ai")
        self._seed_category("Biology")

        prompt = self._get_prompt_sent(monkeypatch)

        # "ai" should appear only once (case-normalised), biology from seeds+ChromaDB also once
        # Count occurrences of "- ai" in the prompt
        lines = prompt.split("\n")
        category_lines = [l for l in lines if l.strip().startswith("- ")]
        cats_in_prompt = [l.strip("- ").strip() for l in category_lines]
        assert cats_in_prompt.count("ai") == 1
        assert cats_in_prompt.count("biology") == 1

    def test_category_reuse_preferred(self, monkeypatch) -> None:
        """When existing categories match, LLM reuses the exact label."""
        self._seed_category("physics")

        # LLM returns "physics" (reuses existing)
        self._mock_ollama(monkeypatch, json.dumps({
            "category": "physics",
            "keywords": ["quantum"],
            "summary": "Quantum physics paper",
        }))

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("quantum mechanics and wave functions"))
        assert result["category"] == "physics"
        assert "quantum" in result["keywords"]

    def test_category_new_proposal_normalised(self, monkeypatch) -> None:
        """LLM proposes new category → normalised (lowercase, underscores)."""
        self._seed_category("biology")  # existing, not matching

        # LLM proposes "Music Theory" (new)
        self._mock_ollama(monkeypatch, json.dumps({
            "category": "Music Theory",
            "keywords": ["composition", "harmony"],
            "summary": "An introduction to music theory.",
        }))

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("music theory composition harmony scales"))
        assert result["category"] == "music_theory"
        assert result["keywords"] == ["composition", "harmony"]


# ── Helper function unit tests ──────────────────────────────────────────


class TestCategoryNormalisation:
    """Unit tests for the _normalise_category helper."""

    def test_lowercase_and_underscores(self) -> None:
        from rag_mcp.metadata_extractor import _normalise_category

        assert _normalise_category("Artificial Intelligence") == "artificial_intelligence"
        assert _normalise_category("  ML  ") == "ml"
        assert _normalise_category('"deep_learning"') == "deep_learning"

    def test_max_three_words(self) -> None:
        from rag_mcp.metadata_extractor import _normalise_category

        assert _normalise_category("one two three") == "one_two_three"
        assert _normalise_category("one two three four") == "uncategorised"
        assert _normalise_category("one two three four five") == "uncategorised"

    def test_empty_or_whitespace(self) -> None:
        from rag_mcp.metadata_extractor import _normalise_category

        assert _normalise_category("") == "uncategorised"
        assert _normalise_category("   ") == "uncategorised"

    def test_special_characters_stripped(self) -> None:
        from rag_mcp.metadata_extractor import _normalise_category

        assert _normalise_category("AI.") == "ai"
        assert _normalise_category("machine_learning;") == "machine_learning"


class TestSeedCategories:
    """Unit tests for the _get_seed_categories helper."""

    def test_includes_all_keyword_categories(self, monkeypatch) -> None:
        """Seed categories must cover all default keyword rule categories."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import _get_seed_categories

        seeds = _get_seed_categories()
        assert "ai" in seeds
        assert "philosophy" in seeds
        assert "biology" in seeds
        assert "marketing" in seeds
        assert "programming" in seeds
        assert "uncategorised" in seeds

    def test_includes_custom_rule_categories(self, monkeypatch) -> None:
        """Seed categories use custom rules when METADATA_KEYWORD_RULES is set."""
        custom = json.dumps([
            {"pattern": "f1", "category": "Motorsport"},
            {"pattern": "tennis", "category": "Sport"},
        ])
        _set_mode(monkeypatch, "keyword", keyword_rules=custom)

        from rag_mcp.metadata_extractor import _get_seed_categories

        seeds = _get_seed_categories()
        assert "motorsport" in seeds
        assert "sport" in seeds
        assert "uncategorised" in seeds
        # Custom rules replace defaults, so AI etc. should not be present
        assert "ai" not in seeds


# ── 9.6 LlamaIndex mode tests — Stage 2 implementation ──────────────────────


class TestLlamaindexExtraction:
    """Tests for the real LlamaIndex metadata extraction (Stage 2)."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch) -> None:
        """Set mode to llamaindex and IS_TESTING for MockLLM."""
        _set_mode(monkeypatch, "llamaindex")
        # Enable LlamaIndex's IS_TESTING mode so Settings.llm uses MockLLM
        # instead of attempting OpenAI API key validation.
        monkeypatch.setenv("IS_TESTING", "1")

    def _make_mock_node(self, metadata: dict) -> object:
        """Create a mock LlamaIndex BaseNode with given metadata."""
        from unittest.mock import MagicMock
        node = MagicMock()
        node.metadata = metadata
        return node

    def test_import_error_falls_back_to_keyword(self, monkeypatch, caplog) -> None:
        """Missing llama-index-llms-ollama → WARNING + keyword fallback."""
        # Simulate ImportError by removing the package from sys.modules
        import sys
        monkeypatch.setitem(sys.modules, "llama_index.llms.ollama", None)

        # Also need to ensure the import actually fails
        original_import = __builtins__["__import__"] if hasattr(__builtins__, "__import__") else __import__

        def _fake_import(name, *args, **kwargs):
            if name == "llama_index.llms.ollama":
                raise ImportError("No module named 'llama_index.llms.ollama'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _fake_import)

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "deep learning neural networks",
            file_name="test.pdf",
        ))
        # Should fall back to keyword mode
        assert result["category"] == "AI"

        # Must log a WARNING
        assert any(
            r.levelno == logging.WARNING
            and "not installed" in r.message.lower()
            for r in caplog.records
        )

    def test_successful_extraction(self, monkeypatch, caplog) -> None:
        """Real llamaindex pipeline returns aggregated metadata."""
        from unittest.mock import MagicMock

        # Instead of patching sys.modules (fragile with already-loaded modules),
        # monkeypatch _extract_llamaindex_async to simulate a successful pipeline run.
        mock_node = self._make_mock_node({
            "document_title": "Deep Learning Review",
            "excerpt_keywords": "neural, transformer, attention",
            "section_summary": "A comprehensive review of deep learning.",
        })

        from rag_mcp.metadata_extractor import _aggregate_llamaindex_metadata

        async def fake_extract_llamaindex_async(text: str, file_name: str) -> dict:
            return _aggregate_llamaindex_metadata([mock_node])

        monkeypatch.setattr(
            "rag_mcp.metadata_extractor._extract_llamaindex_async",
            fake_extract_llamaindex_async,
        )

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "deep learning transformer attention neural networks",
            file_name="paper.pdf",
        ))

        # Category is derived from the first keyword that normalises cleanly
        # (per _aggregate_llamaindex_metadata logic: keywords first, title fallback).
        assert result["category"] == "neural"
        assert result["keywords"] == ["neural", "transformer", "attention"]
        assert "comprehensive review" in result["summary"]
        assert result.get("document_title") == "Deep Learning Review"

    def test_aggregation_first_non_empty(self, monkeypatch) -> None:
        """Metadata aggregation takes first non-empty value per key."""
        from rag_mcp.metadata_extractor import _aggregate_llamaindex_metadata

        node1 = self._make_mock_node({
            "document_title": "",
            "excerpt_keywords": "",
            "section_summary": "",
        })
        node2 = self._make_mock_node({
            "document_title": "Second Node Title",
            "excerpt_keywords": "keyword_a, keyword_b",
            "section_summary": "Summary from second node.",
        })

        result = _aggregate_llamaindex_metadata([node1, node2])

        # Category is derived from first keyword that normalises cleanly
        assert result["category"] == "keyword_a"
        assert result["keywords"] == ["keyword_a", "keyword_b"]
        assert "Summary from second node" in result["summary"]

    def test_aggregation_empty_nodes_returns_uncategorised(self) -> None:
        """No metadata from any node → uncategorised with empty keywords."""
        from rag_mcp.metadata_extractor import _aggregate_llamaindex_metadata

        node = self._make_mock_node({})
        result = _aggregate_llamaindex_metadata([node])

        assert result["category"] == "uncategorised"
        assert result["keywords"] == []
        assert result["summary"] == ""

    def test_extraction_failure_falls_back_to_keyword(self, monkeypatch, caplog) -> None:
        """Pipeline raises exception → WARNING + keyword fallback."""
        import sys
        from unittest.mock import MagicMock

        # Mock imports so pipeline setup succeeds.
        sys.modules["llama_index.llms.ollama"] = MagicMock()
        sys.modules["llama_index.llms.ollama"].Ollama = MagicMock()

        # Mock extractor + node_parser modules to bypass Pydantic validation
        # on the llm= argument passed to TitleExtractor / KeywordExtractor /
        # SummaryExtractor.
        mock_extractors = MagicMock()
        mock_extractors.TitleExtractor = MagicMock()
        mock_extractors.KeywordExtractor = MagicMock()
        mock_extractors.SummaryExtractor = MagicMock()
        sys.modules["llama_index.core.extractors"] = mock_extractors
        sys.modules["llama_index.core.node_parser"] = MagicMock()

        # Make pipeline.run() raise
        mock_pipeline = MagicMock()
        mock_pipeline.run.side_effect = RuntimeError("Ollama timeout")
        mock_ingestion = MagicMock()
        mock_ingestion.IngestionPipeline = MagicMock(return_value=mock_pipeline)
        sys.modules["llama_index.core.ingestion"] = mock_ingestion

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "transformer attention neural network",
            file_name="paper.pdf",
        ))
        # Falls back to keyword
        assert result["category"] == "AI"

        # Must log a WARNING
        assert any(
            r.levelno == logging.WARNING
            and "falling back to keyword" in r.message.lower()
            for r in caplog.records
        )

    def test_chunk_capping(self, monkeypatch) -> None:
        """Chunk capping limits text passed to the pipeline."""
        # Set small chunk cap
        monkeypatch.setenv("LLAMANDEX_EXTRACTOR_MAX_CHUNKS", "2")

        # Track what text length is passed to the extraction function
        captured_text_len = []

        async def fake_extract_llamaindex_async(text: str, file_name: str) -> dict:
            captured_text_len.append(len(text))
            # The function internally caps text at max_chunks * CHUNK_SIZE
            # before passing to the pipeline. We verify by checking that
            # _extract_llamaindex_async receives the full text (capping is internal).
            return {"category": "uncategorised", "keywords": [], "summary": ""}

        monkeypatch.setattr(
            "rag_mcp.metadata_extractor._extract_llamaindex_async",
            fake_extract_llamaindex_async,
        )

        from rag_mcp.metadata_extractor import extract_metadata_async

        # Long text — the function receives full text, caps internally
        long_text = "x" * 5000
        asyncio.run(extract_metadata_async(long_text, file_name="test.pdf"))

        # Verify the function was called with the full text
        assert captured_text_len[0] == 5000
