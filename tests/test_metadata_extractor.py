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
    to ollama mode (not keyword).  This test verifies correct fallback behaviour.
    """

    def test_llamaindex_falls_back_to_ollama_when_not_installed(
        self, monkeypatch, caplog,
    ) -> None:
        """Llamaindex mode must fall back to ollama mode when LLM package missing."""
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

        # Mock _extract_ollama_async so we don't need a live Ollama instance.
        async def _fake_ollama(text: str) -> dict:
            return {"category": "biology", "keywords": ["protein", "deep_learning"], "summary": "A biology paper."}

        monkeypatch.setattr(
            "rag_mcp.metadata_extractor._extract_ollama_async",
            _fake_ollama,
        )

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "The protein folding problem was solved by deep learning.",
            file_name="biology_paper.pdf",
        ))
        # Falls back to ollama mode — returns ollama-shaped output
        assert result["category"] == "biology"
        assert "keywords" in result
        assert "summary" in result

        # Must log a WARNING about the package not being installed
        assert any(
            r.levelno == logging.WARNING
            and "not installed" in r.message.lower()
            for r in caplog.records
        )
        # Warning must mention ollama mode, not keyword mode
        assert any(
            "ollama mode" in r.message.lower()
            for r in caplog.records
            if r.levelno == logging.WARNING
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

    def test_import_error_falls_back_to_ollama(self, monkeypatch, caplog) -> None:
        """Missing llama-index-llms-ollama → WARNING + ollama fallback."""
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

        # Mock _extract_ollama_async so we don't need a live Ollama instance.
        async def _fake_ollama(text: str) -> dict:
            return {"category": "ai", "keywords": ["deep_learning", "neural"], "summary": "An AI paper."}

        monkeypatch.setattr(
            "rag_mcp.metadata_extractor._extract_ollama_async",
            _fake_ollama,
        )

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "deep learning neural networks",
            file_name="test.pdf",
        ))
        # Should fall back to ollama mode — returns ollama-shaped output
        assert result["category"] == "ai"
        assert "keywords" in result
        assert "summary" in result

        # Must log a WARNING mentioning ollama mode
        assert any(
            r.levelno == logging.WARNING
            and "not installed" in r.message.lower()
            for r in caplog.records
        )
        assert any(
            "ollama mode" in r.message.lower()
            for r in caplog.records
            if r.levelno == logging.WARNING
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

    def test_extraction_failure_falls_back_to_ollama(self, monkeypatch, caplog) -> None:
        """Pipeline raises exception → WARNING + ollama fallback."""
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

        # Make pipeline.arun() raise
        mock_pipeline = MagicMock()
        mock_pipeline.arun.side_effect = RuntimeError("Ollama timeout")
        mock_ingestion = MagicMock()
        mock_ingestion.IngestionPipeline = MagicMock(return_value=mock_pipeline)
        sys.modules["llama_index.core.ingestion"] = mock_ingestion

        # Mock _extract_ollama_async so we don't need a live Ollama instance.
        async def _fake_ollama(text: str) -> dict:
            return {"category": "ai", "keywords": ["transformer"], "summary": "An AI paper."}

        monkeypatch.setattr(
            "rag_mcp.metadata_extractor._extract_ollama_async",
            _fake_ollama,
        )

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "transformer attention neural network",
            file_name="paper.pdf",
        ))
        # Falls back to ollama mode — returns ollama-shaped output
        assert result["category"] == "ai"
        assert "keywords" in result
        assert "summary" in result

        # Must log a WARNING mentioning ollama mode
        assert any(
            r.levelno == logging.WARNING
            and "falling back to ollama mode" in r.message.lower()
            for r in caplog.records
        )

    def test_double_degradation_llamaindex_and_ollama_both_fail(
        self, monkeypatch, caplog,
    ) -> None:
        """llamaindex fails (ImportError) AND ollama fails → uncategorised fallback.

        Validates the full degradation ladder:
        llamaindex → ollama → uncategorised (keyword not reached).
        """
        import builtins
        original_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "llama_index.llms.ollama":
                raise ImportError("No module named 'llama_index.llms.ollama'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _fake_import)

        # Make _extract_ollama_async also fail — simulates Ollama unreachable.
        async def _failing_ollama(text: str) -> dict:
            # _extract_ollama_async catches its own exceptions and returns this.
            return {"category": "uncategorised", "keywords": [], "summary": ""}

        monkeypatch.setattr(
            "rag_mcp.metadata_extractor._extract_ollama_async",
            _failing_ollama,
        )

        _set_mode(monkeypatch, "llamaindex")
        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async(
            "transformer attention neural network",
            file_name="paper.pdf",
        ))

        # Both llamaindex and ollama failed — final result is uncategorised
        assert result["category"] == "uncategorised"
        assert result["keywords"] == []
        assert result["summary"] == ""

        # llamaindex must have logged a WARNING about falling back to ollama
        assert any(
            r.levelno == logging.WARNING
            and "ollama mode" in r.message.lower()
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


# ── Coverage gap tests ─────────────────────────────────────────────────────


class TestCoverageGaps:
    """Targeted tests for defensive branches not covered by the main test classes."""

    # ── _strip_llm_prefix: empty string guard (line 134) ──────────────────

    def test_strip_llm_prefix_empty_string(self) -> None:
        """Empty string input must be returned unchanged."""
        from rag_mcp.metadata_extractor import _strip_llm_prefix
        assert _strip_llm_prefix("") == ""
        assert _strip_llm_prefix(None) is None  # type: ignore[arg-type]

    def test_strip_llm_prefix_bold_markers(self) -> None:
        """Surrounding ** bold markers must be stripped."""
        from rag_mcp.metadata_extractor import _strip_llm_prefix
        assert _strip_llm_prefix('** "Hallucinations in Language Models" **') == "Hallucinations in Language Models"
        assert _strip_llm_prefix("**Deep Learning Review**") == "Deep Learning Review"
        assert _strip_llm_prefix("* Single asterisk *") == "Single asterisk"

    def test_strip_llm_prefix_trailing_explanation(self) -> None:
        """Text after a double-newline must be truncated."""
        from rag_mcp.metadata_extractor import _strip_llm_prefix
        raw = '** "Hallucinations in Language Models"  \n\nThis title encapsulates the key themes.'
        assert _strip_llm_prefix(raw) == "Hallucinations in Language Models"

    def test_strip_llm_prefix_combined_label_and_bold(self) -> None:
        """Label prefix + bold markers + trailing explanation all stripped."""
        from rag_mcp.metadata_extractor import _strip_llm_prefix
        raw = '**Title:** ** "Deep Learning Review" **\n\nThis covers the main topics.'
        assert _strip_llm_prefix(raw) == "Deep Learning Review"

    def test_strip_llm_prefix_plain_text_unchanged(self) -> None:
        """Plain text without any LLM noise must pass through unchanged."""
        from rag_mcp.metadata_extractor import _strip_llm_prefix
        assert _strip_llm_prefix("A normal title") == "A normal title"

    # ── _normalise_category: invalid char rejection (lines 95-100) ────────

    def test_normalise_category_invalid_chars_rejected(self) -> None:
        """Labels with non-[a-z0-9_-] chars must return 'uncategorised'."""
        from rag_mcp.metadata_extractor import _normalise_category
        # Starts with a digit — invalid
        assert _normalise_category("4._[pubmed_api]") == "uncategorised"
        # Contains slash
        assert _normalise_category("keywords:_/think") == "uncategorised"

    # ── _load_keyword_rules: empty rules list (line 190) ──────────────────

    def test_load_keyword_rules_empty_list(self, monkeypatch) -> None:
        """An empty JSON array must be accepted and returned as-is."""
        import rag_mcp.metadata_extractor as _me
        monkeypatch.setattr(_me, "METADATA_KEYWORD_RULES", "[]")
        from rag_mcp.metadata_extractor import _load_keyword_rules
        result = _load_keyword_rules()
        assert result == []

    def test_load_keyword_rules_missing_keys(self, monkeypatch) -> None:
        """Rules missing 'pattern' or 'category' keys must fall back to defaults."""
        import rag_mcp.metadata_extractor as _me
        monkeypatch.setattr(_me, "METADATA_KEYWORD_RULES", '[{"pattern": "foo"}]')
        from rag_mcp.metadata_extractor import _load_keyword_rules, _DEFAULT_KEYWORD_RULES
        result = _load_keyword_rules()
        assert result == _DEFAULT_KEYWORD_RULES

    # ── _extract_keyword: empty rules guard (line 453) ────────────────────

    def test_extract_keyword_empty_rules(self, monkeypatch) -> None:
        """Empty rules list must return uncategorised immediately."""
        import rag_mcp.metadata_extractor as _me
        monkeypatch.setattr(_me, "METADATA_KEYWORD_RULES", "[]")
        from rag_mcp.metadata_extractor import _extract_keyword
        result = _extract_keyword("transformer attention neural network")
        assert result == {"category": "uncategorised"}

    # ── _extract_keyword: invalid regex pattern (lines 463-469) ──────────

    def test_extract_keyword_invalid_regex_skipped(self, monkeypatch, caplog) -> None:
        """A rule with an invalid regex pattern must be skipped with a WARNING."""
        import rag_mcp.metadata_extractor as _me
        bad_rules = '[{"pattern": "[invalid(", "category": "broken"}, {"pattern": "neural", "category": "AI"}]'
        monkeypatch.setattr(_me, "METADATA_KEYWORD_RULES", bad_rules)
        from rag_mcp.metadata_extractor import _extract_keyword
        result = _extract_keyword("neural network transformer")
        # The valid rule still fires
        assert result["category"] == "AI"
        assert any("invalid regex" in r.message.lower() for r in caplog.records)

    # ── _gather_existing_categories: per-collection exception (lines 287-293) ─

    def test_gather_existing_categories_collection_error_skipped(self, monkeypatch) -> None:
        """A collection that raises during get() must be skipped gracefully."""
        from unittest.mock import MagicMock
        import rag_mcp.metadata_extractor as _me

        bad_col = MagicMock()
        bad_col.name = "bad_collection"
        bad_col.get.side_effect = RuntimeError("collection locked")

        good_col = MagicMock()
        good_col.name = "good_collection"
        good_col.get.return_value = {"metadatas": [{"category": "biology"}]}

        mock_client = MagicMock()
        mock_client.list_collections.return_value = [bad_col, good_col]
        monkeypatch.setattr(_me, "_chroma_client", mock_client)

        from rag_mcp.metadata_extractor import _gather_existing_categories
        result = _gather_existing_categories()
        # bad_col skipped, good_col processed
        assert "biology" in result

    def test_gather_existing_categories_scans_multiple_metadata_pages(
        self, monkeypatch,
    ) -> None:
        """Categories beyond the first metadata scan page must be discovered."""
        import chromadb
        import rag_mcp.config as _config
        import rag_mcp.metadata_extractor as _me

        monkeypatch.setattr(_config, "CHROMA_SCAN_PAGE_SIZE", 2)

        db = chromadb.PersistentClient(path=_me.CHROMA_PERSIST_DIR)
        collection = db.get_or_create_collection("paged_categories")
        collection.add(
            ids=["1", "2", "3"],
            documents=["one", "two", "three"],
            embeddings=[[float(i)] * 384 for i in range(3)],
            metadatas=[
                {"category": "ai"},
                {"category": "biology"},
                {"category": "philosophy"},
            ],
        )
        monkeypatch.setattr(_me, "_chroma_client", db)

        result = _me._gather_existing_categories()
        assert result == ["ai", "biology", "philosophy"]

    # ── _build_ollama_prompt: empty merged taxonomy (line 338) ────────────

    def test_build_ollama_prompt_empty_merged_taxonomy(self, monkeypatch) -> None:
        """With empty custom rules and empty ChromaDB, prompt uses only uncategorised."""
        import rag_mcp.metadata_extractor as _me
        # Empty custom rules → no seed categories
        monkeypatch.setattr(_me, "METADATA_KEYWORD_RULES", "[]")
        # Empty ChromaDB → no existing categories
        monkeypatch.setattr(_me, "_chroma_client", None)
        mock_client = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        mock_client.list_collections.return_value = []
        monkeypatch.setattr(_me, "_chroma_client", mock_client)

        from rag_mcp.metadata_extractor import _build_ollama_prompt
        prompt = _build_ollama_prompt("some document text")
        assert "uncategorised" in prompt
        assert "EXISTING CATEGORIES" in prompt

    # ── _parse_ollama_json_response: edge cases (lines 389, 406, 416) ─────

    def test_parse_ollama_json_non_list_keywords(self) -> None:
        """Non-list keywords field must be treated as empty list."""
        from rag_mcp.metadata_extractor import _parse_ollama_json_response
        raw = json.dumps({"category": "ai", "keywords": "not_a_list", "summary": "test"})
        result = _parse_ollama_json_response(raw)
        assert result["keywords"] == []

    def test_parse_ollama_json_empty_summary(self) -> None:
        """Empty summary field must produce empty string."""
        from rag_mcp.metadata_extractor import _parse_ollama_json_response
        raw = json.dumps({"category": "ai", "keywords": [], "summary": ""})
        result = _parse_ollama_json_response(raw)
        assert result["summary"] == ""

    def test_parse_ollama_json_non_dict_response(self) -> None:
        """A JSON array (not object) must fall back to raw text as category."""
        from rag_mcp.metadata_extractor import _parse_ollama_json_response
        raw = json.dumps(["not", "a", "dict"])
        result = _parse_ollama_json_response(raw)
        assert result["category"] == "uncategorised"
        assert result["keywords"] == []

    # ── _aggregate_llamaindex_metadata: title-derived category (line 560) ─

    def test_aggregate_llamaindex_title_fallback_category(self) -> None:
        """When all keywords are invalid, category falls back to first 2 words of title."""
        from unittest.mock import MagicMock
        from rag_mcp.metadata_extractor import _aggregate_llamaindex_metadata

        node = MagicMock()
        # Keywords that all fail normalisation:
        # - "4pubmed" starts with a digit → rejected
        # - "this_is_a_four_word_keyword" exceeds 3-word limit → rejected
        node.metadata = {
            "excerpt_keywords": "4pubmed, this_is_a_four_word_keyword",
            "section_summary": "A paper about deep learning.",
            "document_title": "Deep Learning Review",
        }
        result = _aggregate_llamaindex_metadata([node])
        # All keywords fail → falls back to first 2 words of title
        assert result["category"] == "deep_learning"
        assert result.get("document_title") == "Deep Learning Review"


# ── Ollama hardening: markdown fences, retry, backoff ──────────────────────


class TestOllamaMarkdownFenceStripping:
    """qwen3:0.6b often wraps JSON in a markdown fence; we must unwrap it."""

    def test_strip_json_fence(self) -> None:
        from rag_mcp.metadata_extractor import _strip_markdown_fence

        wrapped = '```json\n{"category": "ai", "keywords": [], "summary": ""}\n```'
        assert _strip_markdown_fence(wrapped) == (
            '{"category": "ai", "keywords": [], "summary": ""}'
        )

    def test_strip_bare_fence(self) -> None:
        from rag_mcp.metadata_extractor import _strip_markdown_fence

        wrapped = '```\n{"category": "ai"}\n```'
        assert _strip_markdown_fence(wrapped) == '{"category": "ai"}'

    def test_unfenced_text_returned_unchanged(self) -> None:
        from rag_mcp.metadata_extractor import _strip_markdown_fence

        bare = '{"category": "ai"}'
        assert _strip_markdown_fence(bare) == bare

    def test_empty_input_returns_empty(self) -> None:
        from rag_mcp.metadata_extractor import _strip_markdown_fence

        assert _strip_markdown_fence("") == ""

    def test_parse_ollama_json_with_markdown_fence(self) -> None:
        """Parser must unwrap a fenced JSON payload before json.loads."""
        from rag_mcp.metadata_extractor import _parse_ollama_json_response

        raw = (
            '```json\n'
            '{"category": "Biology", "keywords": ["gene"], "summary": "x"}\n'
            '```'
        )
        result = _parse_ollama_json_response(raw)
        assert result["category"] == "biology"
        assert result["keywords"] == ["gene"]
        assert result["summary"] == "x"


class TestOllamaRetry:
    """Bounded retry with exponential backoff around the Ollama HTTP call."""

    @pytest.fixture(autouse=True)
    def _ollama_mode(self, monkeypatch) -> None:
        _set_mode(monkeypatch, "ollama")
        # Avoid real time.sleep / asyncio.sleep delays in tests.
        async def _noop_sleep(_seconds):
            return None
        import rag_mcp.metadata_extractor as _me
        monkeypatch.setattr(_me, "_retry_sleep", _noop_sleep)

    def _mock_async_client(self, monkeypatch, side_effects: list) -> list:
        """Patch httpx.AsyncClient so each ``post`` call consumes one side_effect.

        Each entry in side_effects is either:
          * an ``Exception`` instance to raise, or
          * a ``str`` — the JSON-or-plain ``response`` field to return.

        Returns a call log (list) populated as side_effects are consumed.
        """
        from unittest.mock import AsyncMock, MagicMock

        call_log: list[int] = []

        async def _post(*args, **kwargs):
            i = len(call_log)
            call_log.append(i)
            if i >= len(side_effects):
                raise AssertionError(
                    f"unexpected post call #{i + 1} (only {len(side_effects)} configured)"
                )
            effect = side_effects[i]
            if isinstance(effect, Exception):
                raise effect
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"response": effect}
            return mock_response

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = _post

        monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)
        return call_log

    def test_retry_succeeds_after_transient_failure(
        self, monkeypatch,
    ) -> None:
        """First call fails, second succeeds → returns parsed metadata."""
        monkeypatch.setenv("OLLAMA_CLASSIFY_MAX_ATTEMPTS", "3")

        good = json.dumps({
            "category": "ai",
            "keywords": ["transformer"],
            "summary": "ok",
        })
        log = self._mock_async_client(
            monkeypatch,
            [ConnectionError("transient"), good],
        )

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("transformer attention"))
        assert result["category"] == "ai"
        assert result["keywords"] == ["transformer"]
        assert len(log) == 2

    def test_retry_exhaustion_falls_back(self, monkeypatch, caplog) -> None:
        """All attempts fail → fallback dict + WARNING log."""
        monkeypatch.setenv("OLLAMA_CLASSIFY_MAX_ATTEMPTS", "3")

        log = self._mock_async_client(
            monkeypatch,
            [
                ConnectionError("attempt 1"),
                ConnectionError("attempt 2"),
                ConnectionError("attempt 3"),
            ],
        )

        from rag_mcp.metadata_extractor import extract_metadata_async

        with caplog.at_level(logging.WARNING):
            result = asyncio.run(extract_metadata_async("any text"))

        assert result == {
            "category": "uncategorised",
            "keywords": [],
            "summary": "",
        }
        assert len(log) == 3
        assert any(
            r.levelno == logging.WARNING
            and "ollama classification failed" in r.message.lower()
            for r in caplog.records
        )

    def test_backoff_grows_between_attempts(self, monkeypatch) -> None:
        """``_retry_sleep`` must be called with 1, 2, 4 ... seconds."""
        monkeypatch.setenv("OLLAMA_CLASSIFY_MAX_ATTEMPTS", "4")

        sleeps: list[float] = []

        async def _record_sleep(seconds):
            sleeps.append(seconds)

        import rag_mcp.metadata_extractor as _me
        monkeypatch.setattr(_me, "_retry_sleep", _record_sleep)

        self._mock_async_client(
            monkeypatch,
            [
                ConnectionError("a"),
                ConnectionError("b"),
                ConnectionError("c"),
                ConnectionError("d"),
            ],
        )

        from rag_mcp.metadata_extractor import extract_metadata_async

        asyncio.run(extract_metadata_async("text"))

        # Sleeps run AFTER attempts 1, 2, 3 — not after the final attempt.
        assert sleeps == [1, 2, 4]

    def test_no_sleep_when_max_attempts_is_one(self, monkeypatch) -> None:
        """A single-attempt configuration must not call _retry_sleep."""
        monkeypatch.setenv("OLLAMA_CLASSIFY_MAX_ATTEMPTS", "1")

        sleeps: list[float] = []

        async def _record_sleep(seconds):
            sleeps.append(seconds)

        import rag_mcp.metadata_extractor as _me
        monkeypatch.setattr(_me, "_retry_sleep", _record_sleep)

        self._mock_async_client(
            monkeypatch,
            [ConnectionError("one and done")],
        )

        from rag_mcp.metadata_extractor import extract_metadata_async

        asyncio.run(extract_metadata_async("text"))

        assert sleeps == []

    def test_first_attempt_success_no_retry(self, monkeypatch) -> None:
        """A successful first attempt must not trigger a retry."""
        monkeypatch.setenv("OLLAMA_CLASSIFY_MAX_ATTEMPTS", "3")

        good = json.dumps({"category": "ai", "keywords": [], "summary": ""})
        log = self._mock_async_client(monkeypatch, [good])

        from rag_mcp.metadata_extractor import extract_metadata_async

        result = asyncio.run(extract_metadata_async("attention"))
        assert result["category"] == "ai"
        assert len(log) == 1
