"""Unit tests for the cross-encoder reranker module.

Tests cover:
- _sigmoid() edge cases and monotonicity
- _select_onnx_variant() platform-aware model selection
- CrossEncoderReranker singleton pattern and graceful fallback
- Rerank with mocked ONNX session for score normalisation
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from rag_mcp.reranker import (
    CrossEncoderReranker,
    _select_onnx_variant,
    _sigmoid,
)


# ── _sigmoid tests ─────────────────────────────────────────────────────────


class TestSigmoid:
    """Tests for the _sigmoid() normalisation function."""

    def test_zero_returns_half(self) -> None:
        """sigmoid(0) must be exactly 0.5."""
        assert _sigmoid(0.0) == 0.5

    def test_large_positive_near_one(self) -> None:
        """sigmoid(10) must be very close to 1.0 without overflow."""
        result = _sigmoid(10.0)
        assert result > 0.999
        assert result <= 1.0

    def test_large_negative_near_zero(self) -> None:
        """sigmoid(-10) must be very close to 0.0 without overflow."""
        result = _sigmoid(-10.0)
        assert result < 0.001
        assert result >= 0.0

    def test_monotonicity(self) -> None:
        """sigmoid must be monotonically increasing."""
        values = [-100.0, -10.0, -1.0, 0.0, 1.0, 10.0, 100.0]
        results = [_sigmoid(v) for v in values]
        for i in range(len(results) - 1):
            assert results[i] < results[i + 1], (
                f"_sigmoid({values[i]}) = {results[i]} >= "
                f"_sigmoid({values[i + 1]}) = {results[i + 1]}"
            )

    def test_boundary_values(self) -> None:
        """Very large positive and negative values must not overflow."""
        assert _sigmoid(1000.0) == 1.0
        assert _sigmoid(-1000.0) == 0.0


# ── _select_onnx_variant tests ─────────────────────────────────────────────


class TestSelectOnnxVariant:
    """Tests for platform-aware ONNX model variant selection."""

    @patch("rag_mcp.reranker.platform.machine", return_value="arm64")
    def test_arm64_selects_quantised(self, mock_machine: MagicMock) -> None:
        """ARM64 platforms should select the quantised model variant."""
        result = _select_onnx_variant()
        assert result == "onnx/model_qint8_arm64.onnx"

    @patch("rag_mcp.reranker.platform.machine", return_value="aarch64")
    def test_aarch64_selects_quantised(self, mock_machine: MagicMock) -> None:
        """AArch64 platforms should select the quantised model variant."""
        result = _select_onnx_variant()
        assert result == "onnx/model_qint8_arm64.onnx"

    @patch("rag_mcp.reranker.platform.machine", return_value="x86_64")
    def test_x86_64_selects_generic(self, mock_machine: MagicMock) -> None:
        """x86_64 platforms should select the generic fp32 model."""
        result = _select_onnx_variant()
        assert result == "onnx/model.onnx"

    @patch("rag_mcp.reranker.platform.machine", return_value="AMD64")
    def test_unknown_platform_selects_generic(self, mock_machine: MagicMock) -> None:
        """Unknown platforms should fall back to the generic model."""
        result = _select_onnx_variant()
        assert result == "onnx/model.onnx"


# ── CrossEncoderReranker tests ─────────────────────────────────────────────


class TestCrossEncoderRerankerSingleton:
    """Tests for the singleton pattern."""

    def setup_method(self) -> None:
        """Reset the singleton before each test."""
        CrossEncoderReranker._instance = None

    def teardown_method(self) -> None:
        """Reset the singleton after each test."""
        CrossEncoderReranker._instance = None

    def test_singleton_identity(self) -> None:
        """Two instantiations must return the same object."""
        a = CrossEncoderReranker()
        b = CrossEncoderReranker()
        assert a is b

    def test_initial_state_not_loaded(self) -> None:
        """New instance must have _loaded=False."""
        reranker = CrossEncoderReranker()
        assert reranker._loaded is False


class TestCrossEncoderRerankerFallback:
    """Tests for graceful fallback when the model is unavailable."""

    def setup_method(self) -> None:
        """Reset the singleton before each test."""
        CrossEncoderReranker._instance = None

    def teardown_method(self) -> None:
        """Reset the singleton after each test."""
        CrossEncoderReranker._instance = None

    def _make_unloaded_reranker(self) -> CrossEncoderReranker:
        """Create a reranker that fails to load (simulates unavailable model)."""
        reranker = CrossEncoderReranker()
        reranker._loaded = False
        reranker._load_attempted = True
        reranker._load_error = "Test: model intentionally unavailable"
        return reranker

    def test_rerank_empty_returns_empty(self) -> None:
        """rerank() with empty list must return empty list."""
        reranker = CrossEncoderReranker()
        result = reranker.rerank("test query", [], top_k=5)
        assert result == []

    def test_rerank_fallback_truncates_to_top_k(self) -> None:
        """When model not loaded, rerank() returns first top_k results."""
        reranker = self._make_unloaded_reranker()
        with patch.object(reranker, "_load_model"):
            results = [
                {"text": f"result {i}", "score": 0.5}
                for i in range(5)
            ]
            out = reranker.rerank("query", results, top_k=3)
            assert len(out) == 3
            assert all(r["_reranked"] is False for r in out)

    def test_rerank_fallback_preserves_originals(self) -> None:
        """Fallback must return the original result dicts."""
        reranker = self._make_unloaded_reranker()
        with patch.object(reranker, "_load_model"):
            results = [
                {"text": "first", "score": 0.9},
                {"text": "second", "score": 0.7},
            ]
            out = reranker.rerank("query", results, top_k=5)
            assert len(out) == 2
            assert out[0]["text"] == "first"
            assert out[0]["_reranked"] is False


class TestCrossEncoderRerankerMockedInference:
    """Tests for score normalisation with mocked ONNX session."""

    def setup_method(self) -> None:
        """Reset the singleton before each test."""
        CrossEncoderReranker._instance = None

    def teardown_method(self) -> None:
        """Reset the singleton after each test."""
        CrossEncoderReranker._instance = None

    def test_rerank_normalises_scores(self) -> None:
        """With mocked ONNX session, scores must be in (0, 1) range."""
        # Create instance and manually set up mock internals
        reranker = CrossEncoderReranker()

        # Mock the ONNX session
        mock_session = MagicMock()
        # Return logits that span positive and negative ranges
        mock_session.run.return_value = [np.array([[2.5], [-1.0], [0.3]])]

        # Mock the tokenizer
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2, 3]]),
            "attention_mask": np.array([[1, 1, 1]]),
        }

        reranker._session = mock_session
        reranker._tokenizer = mock_tokenizer
        reranker._loaded = True

        results = [
            {"text": "first", "score": 0.5},
            {"text": "second", "score": 0.5},
            {"text": "third", "score": 0.5},
        ]

        out = reranker.rerank("query", results, top_k=3)
        assert len(out) == 3

        # All scores must be in (0, 1)
        for r in out:
            assert 0.0 < r["score"] < 1.0, f"Score {r['score']} not in (0, 1)"
            assert r["_reranked"] is True

    def test_rerank_sorts_descending(self) -> None:
        """Results must be sorted by score in descending order."""
        reranker = CrossEncoderReranker()

        mock_session = MagicMock()
        # Logits: [3.0, -2.0, 0.5] → after sigmoid: [~0.95, ~0.12, ~0.62]
        mock_session.run.return_value = [np.array([[3.0], [-2.0], [0.5]])]

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2]]),
            "attention_mask": np.array([[1, 1]]),
        }

        reranker._session = mock_session
        reranker._tokenizer = mock_tokenizer
        reranker._loaded = True

        results = [
            {"text": "low", "score": 0.5},
            {"text": "high", "score": 0.5},
            {"text": "medium", "score": 0.5},
        ]

        out = reranker.rerank("query", results, top_k=3)
        scores = [r["score"] for r in out]
        assert scores == sorted(scores, reverse=True)
