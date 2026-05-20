"""Tests for the metadata extraction module (rag_mcp.metadata_extractor)."""

from __future__ import annotations

import logging
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

        from rag_mcp.metadata_extractor import extract_metadata

        result = extract_metadata(
            "This document discusses attention mechanisms and transformer models."
        )
        assert result == {"category": "AI"}

    def test_multiple_match_scoring(self, monkeypatch) -> None:
        """Text with more AI matches than Philosophy must choose AI."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata

        result = extract_metadata(
            "This neural network uses embedding-based RAG for logic problems."
        )
        assert result == {"category": "AI"}

    def test_uncategorised_fallback(self, monkeypatch) -> None:
        """Text with no keyword matches must return 'uncategorised'."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata

        result = extract_metadata(
            "The quick brown fox jumps over the lazy dog. Nothing technical here."
        )
        assert result == {"category": "uncategorised"}

    def test_philosophy_match(self, monkeypatch) -> None:
        """Text with mantiq/logic keywords must categorise as 'Philosophy'."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata

        result = extract_metadata(
            "This paper explores mantiq and epistemology in classical Islamic logic."
        )
        assert result == {"category": "Philosophy"}

    def test_biology_match(self, monkeypatch) -> None:
        """Text with biology keywords must categorise as 'Biology'."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata

        result = extract_metadata(
            "The crispr gene editing tool revolutionises cancer research."
        )
        assert result == {"category": "Biology"}

    def test_marketing_match(self, monkeypatch) -> None:
        """Text with marketing keywords must categorise as 'Marketing'."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata

        result = extract_metadata(
            "Our SEO campaign increased conversion rates across the sales funnel."
        )
        assert result == {"category": "Marketing"}

    def test_programming_match(self, monkeypatch) -> None:
        """Text with programming keywords must categorise as 'Programming'."""
        _set_mode(monkeypatch, "keyword")

        from rag_mcp.metadata_extractor import extract_metadata

        result = extract_metadata(
            "The Rust compiler uses an LLVM backend for code generation."
        )
        assert result == {"category": "Programming"}


# ── 9.2 Disabled mode test ─────────────────────────────────────────────────


class TestDisabledExtraction:
    """Tests for disabled metadata extraction mode."""

    def test_disabled_returns_empty_dict(self, monkeypatch) -> None:
        """Disabled mode must return an empty dict."""
        _set_mode(monkeypatch, "disabled")

        from rag_mcp.metadata_extractor import extract_metadata

        result = extract_metadata("Any text content here.")
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

        from rag_mcp.metadata_extractor import extract_metadata

        result = extract_metadata(
            "Formula 1 Grand Prix at Monaco is the highlight of the motorsport calendar."
        )
        assert result == {"category": "Motorsport"}

    def test_custom_rules_no_default_fallback(self, monkeypatch) -> None:
        """Custom rules must completely replace defaults."""
        custom_rules = json.dumps([
            {"pattern": "football|goal", "category": "Sport"},
        ])
        _set_mode(monkeypatch, "keyword", keyword_rules=custom_rules)

        from rag_mcp.metadata_extractor import extract_metadata

        # Has AI keywords but custom rules don't include AI → uncategorised
        result = extract_metadata("The transformer model uses attention heads.")
        assert result == {"category": "uncategorised"}

    def test_invalid_json_falls_back_to_defaults(
        self, monkeypatch, caplog,
    ) -> None:
        """Invalid JSON in METADATA_KEYWORD_RULES must fall back to defaults."""
        _set_mode(monkeypatch, "keyword", keyword_rules="not valid json {{{")

        from rag_mcp.metadata_extractor import extract_metadata

        result = extract_metadata(
            "The transformer attention mechanism is key to modern AI."
        )
        # Should use default AI rule
        assert result == {"category": "AI"}

        # Must log a WARNING
        assert any(
            r.levelno == logging.WARNING and "falling back" in r.message.lower()
            for r in caplog.records
        )


# ── 9.4 Llamaindex stub test ───────────────────────────────────────────────


class TestLlamaindexStub:
    """Tests for the LlamaIndex MetadataExtractor stub mode."""

    def test_llamaindex_falls_back_to_keyword(
        self, monkeypatch, caplog,
    ) -> None:
        """Llamaindex mode must log INFO and fall back to keyword."""
        _set_mode(monkeypatch, "llamaindex")

        import logging
        logging.getLogger("rag_mcp.metadata_extractor").setLevel(logging.DEBUG)
        caplog.set_level(logging.DEBUG)

        from rag_mcp.metadata_extractor import extract_metadata

        result = extract_metadata(
            "The protein folding problem was solved by deep learning.",
            file_name="biology_paper.pdf",
        )
        # Should fall back to keyword mode — "deep learning" and "protein" match AI and Biology
        assert result == {"category": "AI"}

        # Must log INFO about not yet implemented
        assert any(
            r.levelno == logging.INFO
            and "not yet implemented" in r.message.lower()
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

        from rag_mcp.metadata_extractor import extract_metadata

        result = extract_metadata("attention transformer neural network")
        assert result == {"category": "AI"}

        # Must log a WARNING
        assert any(
            r.levelno == logging.WARNING
            and "unknown" in r.message.lower()
            for r in caplog.records
        )
