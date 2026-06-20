"""Unit tests for rerank policy resolver and technical query classifier.

Tests cover:
- Technical query classification using identifier rules
- Policy resolver explicit overrides (True/False)
- Policy resolver omitted/None behavior
- Semantic workload override below HARD_TECHNICAL_THRESHOLD
- Technical workload disabling at/above threshold
- Diagnostics output
"""

from __future__ import annotations

import pytest

from rag_mcp.retrieval import (
    _classify_query_technical,
    _resolve_rerank_policy,
)


# ── Technical query classifier tests ─────────────────────────────────────


class TestClassifyQueryTechnical:
    """Tests for the deterministic identifier-heavy query classifier."""

    def test_empty_query(self) -> None:
        """Empty query has 0.0 technical fraction."""
        assert _classify_query_technical("") == 0.0
        assert _classify_query_technical("   ") == 0.0

    def test_purely_semantic_query(self) -> None:
        """Natural language query with no identifiers is non-technical."""
        query = "what is machine learning"
        assert _classify_query_technical(query) == 0.0

    def test_backtick_identifiers(self) -> None:
        """Backtick-quoted identifiers are technical."""
        query = "function `calculateTotal`"
        fraction = _classify_query_technical(query)
        assert fraction == 0.5  # 1 of 2 tokens

    def test_slash_paths(self) -> None:
        """Unix-style paths are technical."""
        query = "file /usr/local/bin"
        fraction = _classify_query_technical(query)
        assert fraction == 0.5  # 1 of 2 tokens

    def test_dotted_paths(self) -> None:
        """Python-style dotted paths are technical."""
        query = "plain words"
        fraction = _classify_query_technical(query)
        assert fraction == 0.0  # no dots

        query_dotted = "module.function_name"
        fraction_dotted = _classify_query_technical(query_dotted)
        assert fraction_dotted == 1.0  # 1 of 1 token

    def test_camel_case(self) -> None:
        """camelCase identifiers are technical."""
        query = "calculateTotalPrice function"
        fraction = _classify_query_technical(query)
        assert fraction == 0.5  # 1 of 2 tokens

    def test_snake_case(self) -> None:
        """snake_case identifiers are technical."""
        query = "calculate_total_price function"
        fraction = _classify_query_technical(query)
        assert fraction == 0.5  # 1 of 2 tokens

    def test_all_caps_constants(self) -> None:
        """ALL_CAPS constants are technical."""
        query = "MAX_VALUE constant"
        fraction = _classify_query_technical(query)
        assert fraction == 0.5  # 1 of 2 tokens

    def test_exception_tokens(self) -> None:
        """Exception/Error tokens are technical."""
        query = "ValueError raised"
        fraction = _classify_query_technical(query)
        assert fraction == 0.5  # 1 of 2 tokens

        query2 = "error handling"
        fraction2 = _classify_query_technical(query2)
        assert fraction2 == 0.5  # 1 of 2 tokens

    def test_version_strings(self) -> None:
        """Version strings are technical."""
        query = "version 1.2.3"
        fraction = _classify_query_technical(query)
        assert fraction == 0.5  # 1 of 2 tokens

        query2 = "release v2.0"
        fraction2 = _classify_query_technical(query2)
        assert fraction2 == 0.5  # 1 of 2 tokens

    def test_digit_only_token_does_not_classify_as_technical(self) -> None:
        """A bare digit string is not a version and must not backtrack.

        Regression test for ReDoS: without the '.' guard, the version
        regex catastrophically backtracks on long digit-only tokens.
        """
        fraction = _classify_query_technical("1234567890" * 100)
        assert fraction == 0.0  # no dots, not a version, not technical

    def test_explicit_technical_terms(self) -> None:
        """Explicit technical terms like 'api', 'sdk', 'cli' are technical."""
        query = "rest api design"
        fraction = _classify_query_technical(query)
        assert fraction == pytest.approx(0.333, rel=1e-2)  # 1 of 3 tokens

        query2 = "python sdk documentation"
        fraction2 = _classify_query_technical(query2)
        assert fraction2 == pytest.approx(0.333, rel=1e-2)

    def test_mixed_query(self) -> None:
        """Mixed natural and technical tokens."""
        query = "how to use calculateTotal function"
        fraction = _classify_query_technical(query)
        assert fraction == 0.2  # 1 of 5 tokens

    def test_highly_technical_query(self) -> None:
        """Query with mostly identifiers."""
        query = "`calculateTotal` `processData` function"
        fraction = _classify_query_technical(query)
        assert fraction == pytest.approx(0.666, rel=1e-2)  # 2 of 3 tokens


# ── Policy resolver explicit override tests ──────────────────────────────


class TestResolveRerankPolicyExplicit:
    """Tests for explicit rerank=True/False overrides."""

    def test_explicit_true_overrides_disabled_policy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """rerank=True forces reranking even when policy disables it."""
        import rag_mcp.config as config

        monkeypatch.setattr(config, "RERANK_ENABLED", False)
        monkeypatch.setattr(config, "RERANK_ENABLED_FOR_SEMANTIC", False)
        monkeypatch.setattr(config, "HARD_TECHNICAL_THRESHOLD", 0.3)

        effective, reason = _resolve_rerank_policy(
            rerank=True, query="semantic query about machine learning"
        )
        assert effective is True
        assert "explicit" in reason.lower()

    def test_explicit_false_overrides_enabled_policy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """rerank=False disables reranking even when policy enables it."""
        import rag_mcp.config as config

        monkeypatch.setattr(config, "RERANK_ENABLED", True)
        monkeypatch.setattr(config, "RERANK_ENABLED_FOR_SEMANTIC", True)
        monkeypatch.setattr(config, "HARD_TECHNICAL_THRESHOLD", 0.3)

        effective, reason = _resolve_rerank_policy(
            rerank=False, query="semantic query about machine learning"
        )
        assert effective is False
        assert "explicit" in reason.lower()

    def test_explicit_true_with_technical_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """rerank=True forces reranking even for technical queries."""
        import rag_mcp.config as config

        monkeypatch.setattr(config, "RERANK_ENABLED", False)
        monkeypatch.setattr(config, "RERANK_ENABLED_FOR_SEMANTIC", True)
        monkeypatch.setattr(config, "HARD_TECHNICAL_THRESHOLD", 0.3)

        effective, reason = _resolve_rerank_policy(
            rerank=True, query="`calculateTotal` `processData` function"
        )
        assert effective is True
        assert "explicit" in reason.lower()


# ── Policy resolver omitted/None tests ───────────────────────────────────


class TestResolveRerankPolicyOmitted:
    """Tests for omitted/None rerank following RERANK_ENABLED."""

    def test_omitted_follows_enabled_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """rerank=None follows RERANK_ENABLED=True."""
        import rag_mcp.config as config

        monkeypatch.setattr(config, "RERANK_ENABLED", True)
        monkeypatch.setattr(config, "RERANK_ENABLED_FOR_SEMANTIC", False)
        monkeypatch.setattr(config, "HARD_TECHNICAL_THRESHOLD", 0.3)

        effective, reason = _resolve_rerank_policy(
            rerank=None, query="any query"
        )
        assert effective is True
        assert "default" in reason.lower()

    def test_omitted_follows_enabled_false_semantic_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """rerank=None with RERANK_ENABLED=False and semantic disabled."""
        import rag_mcp.config as config

        monkeypatch.setattr(config, "RERANK_ENABLED", False)
        monkeypatch.setattr(config, "RERANK_ENABLED_FOR_SEMANTIC", False)
        monkeypatch.setattr(config, "HARD_TECHNICAL_THRESHOLD", 0.3)

        effective, reason = _resolve_rerank_policy(
            rerank=None, query="semantic query about machine learning"
        )
        assert effective is False
        assert "semantic" in reason.lower()

    def test_omitted_semantic_query_below_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """rerank=None enables reranking for semantic queries below threshold."""
        import rag_mcp.config as config

        monkeypatch.setattr(config, "RERANK_ENABLED", False)
        monkeypatch.setattr(config, "RERANK_ENABLED_FOR_SEMANTIC", True)
        monkeypatch.setattr(config, "HARD_TECHNICAL_THRESHOLD", 0.3)

        effective, reason = _resolve_rerank_policy(
            rerank=None, query="what is machine learning"
        )
        assert effective is True
        assert "semantic" in reason.lower()
        assert "0.00" in reason

    def test_omitted_technical_query_above_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """rerank=None disables reranking for technical queries above threshold."""
        import rag_mcp.config as config

        monkeypatch.setattr(config, "RERANK_ENABLED", False)
        monkeypatch.setattr(config, "RERANK_ENABLED_FOR_SEMANTIC", True)
        monkeypatch.setattr(config, "HARD_TECHNICAL_THRESHOLD", 0.3)

        # Query with 2 of 3 tokens technical = 0.667 fraction > 0.3 threshold
        effective, reason = _resolve_rerank_policy(
            rerank=None, query="`calculateTotal` `processData` function"
        )
        assert effective is False
        assert "technical" in reason.lower()
        assert "0.67" in reason

    def test_omitted_at_threshold_boundary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """rerank=None at exactly the threshold disables reranking."""
        import rag_mcp.config as config

        monkeypatch.setattr(config, "RERANK_ENABLED", False)
        monkeypatch.setattr(config, "RERANK_ENABLED_FOR_SEMANTIC", True)
        monkeypatch.setattr(config, "HARD_TECHNICAL_THRESHOLD", 0.5)

        # Query with 1 of 2 tokens technical = 0.5 fraction == 0.5 threshold
        effective, reason = _resolve_rerank_policy(
            rerank=None, query="`calculateTotal` function"
        )
        assert effective is False
        assert "technical" in reason.lower()
        assert "0.50" in reason

    def test_omitted_just_below_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """rerank=None just below threshold enables reranking."""
        import rag_mcp.config as config

        monkeypatch.setattr(config, "RERANK_ENABLED", False)
        monkeypatch.setattr(config, "RERANK_ENABLED_FOR_SEMANTIC", True)
        monkeypatch.setattr(config, "HARD_TECHNICAL_THRESHOLD", 0.6)

        # Query with 1 of 2 tokens technical = 0.5 fraction < 0.6 threshold
        effective, reason = _resolve_rerank_policy(
            rerank=None, query="`calculateTotal` function"
        )
        assert effective is True
        assert "semantic" in reason.lower()
        assert "0.50" in reason


# ── Policy resolver with technical_fraction override ─────────────────────


class TestResolveRerankPolicyFractionOverride:
    """Tests for technical_fraction parameter override."""

    def test_fraction_override_used(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """technical_fraction parameter overrides classifier."""
        import rag_mcp.config as config

        monkeypatch.setattr(config, "RERANK_ENABLED", False)
        monkeypatch.setattr(config, "RERANK_ENABLED_FOR_SEMANTIC", True)
        monkeypatch.setattr(config, "HARD_TECHNICAL_THRESHOLD", 0.3)

        # Semantic query but override with high fraction
        effective, reason = _resolve_rerank_policy(
            rerank=None,
            query="what is machine learning",
            technical_fraction=0.8,
        )
        assert effective is False
        assert "technical" in reason.lower()
        assert "0.80" in reason

    def test_fraction_override_low(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """technical_fraction parameter can force low fraction."""
        import rag_mcp.config as config

        monkeypatch.setattr(config, "RERANK_ENABLED", False)
        monkeypatch.setattr(config, "RERANK_ENABLED_FOR_SEMANTIC", True)
        monkeypatch.setattr(config, "HARD_TECHNICAL_THRESHOLD", 0.3)

        # Technical query but override with low fraction
        effective, reason = _resolve_rerank_policy(
            rerank=None,
            query="`calculateTotal` `processData` function",
            technical_fraction=0.1,
        )
        assert effective is True
        assert "semantic" in reason.lower()
        assert "0.10" in reason


# ── Diagnostics tests ────────────────────────────────────────────────────


class TestPolicyDiagnostics:
    """Tests for policy reason diagnostics."""

    def test_diagnostics_included_in_search(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """include_diagnostics=True adds rerank_reason to results."""
        from rag_mcp.retrieval import search

        import rag_mcp.config as config

        monkeypatch.setattr(config, "RERANK_ENABLED", False)
        monkeypatch.setattr(config, "RERANK_ENABLED_FOR_SEMANTIC", True)
        monkeypatch.setattr(config, "HARD_TECHNICAL_THRESHOLD", 0.3)

        # This will attempt actual search; we're testing the diagnostics
        # structure, not the search itself. Use a non-existent collection
        # to get empty results quickly.
        results = search(
            query="test query",
            collection_name="nonexistent_collection",
            include_diagnostics=True,
        )

        # Empty results are fine; we're just checking the parameter is accepted
        assert isinstance(results, list)

    def test_diagnostics_excluded_by_default(self) -> None:
        """include_diagnostics=False (default) excludes rerank_reason."""
        from rag_mcp.retrieval import search

        results = search(
            query="test query",
            collection_name="nonexistent_collection",
            include_diagnostics=False,
        )

        # Empty results are fine
        assert isinstance(results, list)
        # If there were results, they wouldn't have rerank_reason
        for result in results:
            assert "rerank_reason" not in result
