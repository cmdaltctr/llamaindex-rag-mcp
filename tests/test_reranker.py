"""Unit tests for the cross-encoder reranker module.

Tests cover:
- _sigmoid() edge cases and monotonicity
- _select_onnx_variant() model-aware variant selection (ModernBERT + legacy)
- CrossEncoderReranker plain-class DI + process-wide model cache and graceful fallback
- Rerank with mocked ONNX session for score normalisation
- Module docstring model reference
- Tokenizer max_length configuration
"""

from __future__ import annotations

import builtins
import logging
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from rag_mcp.core.retrieval.reranker import (
    TOKENIZER_MAX_LENGTH,
    CrossEncoderReranker,
    _select_onnx_variant,
    _sigmoid,
    reset_model_cache,
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
    """Tests for model-aware ONNX model variant selection."""

    # ── ModernBERT models (new default) ──────────────────────────────

    def test_modernbert_prefers_quantized_on_arm64(self) -> None:
        """ModernBERT models prefer model_quantized.onnx on ARM64."""
        with patch("rag_mcp.core.retrieval.reranker.platform.machine", return_value="arm64"):
            result = _select_onnx_variant("Alibaba-NLP/gte-reranker-modernbert-base")
        assert result[0] == "onnx/model_quantized.onnx"

    def test_modernbert_prefers_quantized_on_x86(self) -> None:
        """ModernBERT models prefer model_quantized.onnx on x86_64."""
        with patch("rag_mcp.core.retrieval.reranker.platform.machine", return_value="x86_64"):
            result = _select_onnx_variant("Alibaba-NLP/gte-reranker-modernbert-base")
        assert result[0] == "onnx/model_quantized.onnx"

    def test_modernbert_fallback_chain(self) -> None:
        """ModernBERT variant list includes the full fallback chain."""
        result = _select_onnx_variant("Alibaba-NLP/gte-reranker-modernbert-base")
        assert result == [
            "onnx/model_quantized.onnx",
            "onnx/model_int8.onnx",
            "onnx/model_fp16.onnx",
            "onnx/model.onnx",
        ]

    def test_variant_selection_requires_an_explicit_model_id(self) -> None:
        """Omitting model_id is a programming error, not a silent settings read."""
        import pytest as _pytest

        with _pytest.raises(ValueError, match="model_id is required"):
            _select_onnx_variant(None)

    def test_modernbert_model_id_selects_modernbert_variants(self) -> None:
        """A ModernBERT model ID selects the ModernBERT variant chain.

        Previously this patched ``config.settings.retrieval.rerank_model`` and called
        ``_select_onnx_variant()`` with no argument. The model ID is now an
        explicit parameter, so the test states it directly — which is also
        what it was actually testing all along.
        """
        result = _select_onnx_variant("Alibaba-NLP/gte-reranker-modernbert-base")
        assert result[0] == "onnx/model_quantized.onnx"
        assert "onnx/model.onnx" in result

    @patch("rag_mcp.core.retrieval.reranker.platform.machine", return_value="aarch64")
    def test_minilm_arm64_selects_quantised(self, mock_machine: MagicMock) -> None:
        """MiniLM on ARM64 selects the ARM-tuned quantised variant."""
        result = _select_onnx_variant("cross-encoder/ms-marco-MiniLM-L-6-v2")
        assert result[0] == "onnx/model_qint8_arm64.onnx"

    @patch("rag_mcp.core.retrieval.reranker.platform.machine", return_value="aarch64")
    def test_minilm_aarch64_selects_quantised(self, mock_machine: MagicMock) -> None:
        """MiniLM on AArch64 selects the ARM-tuned quantised variant."""
        result = _select_onnx_variant("cross-encoder/ms-marco-MiniLM-L-6-v2")
        assert result[0] == "onnx/model_qint8_arm64.onnx"

    @patch("rag_mcp.core.retrieval.reranker.platform.machine", return_value="x86_64")
    def test_minilm_x86_64_selects_generic(self, mock_machine: MagicMock) -> None:
        """MiniLM on x86_64 falls back to the generic fp32 model."""
        result = _select_onnx_variant("cross-encoder/ms-marco-MiniLM-L-6-v2")
        assert result == ["onnx/model.onnx"]

    @patch("rag_mcp.core.retrieval.reranker.platform.machine", return_value="AMD64")
    def test_minilm_unknown_platform_selects_generic(self, mock_machine: MagicMock) -> None:
        """MiniLM on unknown platforms falls back to the generic model."""
        result = _select_onnx_variant("cross-encoder/ms-marco-MiniLM-L-6-v2")
        assert result == ["onnx/model.onnx"]


# ── Module docstring tests ─────────────────────────────────────────────────


class TestModuleDocstring:
    """Tests for the module docstring model reference."""

    def test_docstring_references_default_model(self) -> None:
        """Module docstring must reference the default MiniLM model."""
        import rag_mcp.core.retrieval.reranker as reranker_mod

        assert reranker_mod.__doc__ is not None
        assert "ms-marco-MiniLM-L-6-v2" in reranker_mod.__doc__
        assert "cross-encoder" in reranker_mod.__doc__


# ── CrossEncoderReranker tests ─────────────────────────────────────────────


class TestCrossEncoderRerankerSingleton:
    """Tests for plain-class construction + process-wide model cache."""

    def setup_method(self) -> None:
        """Reset the process-wide model cache before each test."""
        reset_model_cache()

    def teardown_method(self) -> None:
        """Reset the process-wide model cache after each test."""
        reset_model_cache()

    def test_plain_class_constructs_distinct_instances(self) -> None:
        """Two constructions must return distinct objects (not a singleton)."""
        a = CrossEncoderReranker()
        b = CrossEncoderReranker()
        assert a is not b

    def test_initial_state_not_loaded(self) -> None:
        """New instance must have _loaded=False."""
        reranker = CrossEncoderReranker()
        assert reranker._loaded is False

    def test_default_model_id_matches_settings_default(self) -> None:
        """An unspecified model_id falls back to the documented default.

        Production never takes this path — ``compose.build_reranker()`` always
        injects the model ID. The fallback exists for direct construction and
        MUST stay in step with ``RetrievalSettings.rerank_model``.
        """
        from rag_mcp.core.retrieval.reranker import DEFAULT_RERANK_MODEL
        from rag_mcp.core.retrieval.settings import RetrievalSettings

        reranker = CrossEncoderReranker()
        assert reranker._model_id == DEFAULT_RERANK_MODEL
        assert DEFAULT_RERANK_MODEL == RetrievalSettings().rerank_model

    def test_model_id_comes_from_the_composition_root(self) -> None:
        """The model ID is injected, not read from a process-wide singleton.

        Replaces the old test that patched ``config.settings.retrieval.rerank_model``
        and expected the reranker to observe it. That coupling is exactly what
        the DI refactor removed: the reranker no longer imports config at all.
        """
        import rag_mcp.core.retrieval.reranker as reranker_mod
        from rag_mcp import compose

        assert not hasattr(reranker_mod, "settings"), (
            "reranker must not hold a module-level settings object"
        )
        built = compose.build_reranker()
        assert built._model_id == compose.get_settings().retrieval.rerank_model

    def test_injected_model_id_is_honoured(self) -> None:
        """A caller-provided model_id must override the settings default."""
        reranker = CrossEncoderReranker(model_id="custom/model")
        assert reranker._model_id == "custom/model"

    def test_process_wide_cache_shares_loaded_model(self) -> None:
        """A successful load must populate the cache for reuse by other instances.

        Simulates the load-once semantics: the first instance loads and
        caches the session/tokenizer; a second instance with the same
        model ID reuses them without re-downloading.
        """
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
                            first = CrossEncoderReranker(model_id="cache-test/model")
                            first._load_model()

        assert first._loaded is True

        # Second instance, same model ID: must be served from the cache.
        second = CrossEncoderReranker(model_id="cache-test/model")
        with patch("rag_mcp.core.retrieval.reranker._select_onnx_variant") as variant_mock:
            second._load_model()
            variant_mock.assert_not_called()

        assert second._loaded is True
        assert second._session is mock_session
        assert second._tokenizer is mock_tokenizer

    def test_reset_model_cache_forces_reload(self) -> None:
        """After reset_model_cache(), a new instance must reload from scratch."""
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
                            first = CrossEncoderReranker(model_id="cache-reset/model")
                            first._load_model()

        assert first._loaded is True
        reset_model_cache()

        second = CrossEncoderReranker(model_id="cache-reset/model")
        with patch(
            "rag_mcp.core.retrieval.reranker._select_onnx_variant", return_value=["onnx/model.onnx"]
        ) as variant_mock:
            with patch("huggingface_hub.hf_hub_download", return_value="/fake/model.onnx"):
                with patch("tokenizers.Tokenizer.from_pretrained", return_value=mock_tokenizer):
                    with patch("onnxruntime.InferenceSession", return_value=mock_session):
                        with patch(
                            "rag_mcp.core.retrieval.reranker._read_max_position_embeddings",
                            return_value=512,
                        ):
                            second._load_model()
            variant_mock.assert_called_once()

        assert second._loaded is True


class TestCrossEncoderRerankerFallback:
    """Tests for graceful fallback when the model is unavailable."""

    def setup_method(self) -> None:
        """Reset the singleton before each test."""
        reset_model_cache()

    def teardown_method(self) -> None:
        """Reset the singleton after each test."""
        reset_model_cache()

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

    def test_rerank_empty_resets_stale_failure_reason(self) -> None:
        """An empty-results call must not leak a prior call's failure reason.

        The MCP server reuses one reranker instance across searches, so a
        stale ``last_failure_reason`` from a prior failed call would otherwise
        surface in a later call's diagnostics even though that call did not
        fail. ``rerank()`` resets it at the start of every call.
        """
        reranker = CrossEncoderReranker()
        reranker.last_failure_reason = "inference failed: stale from prior call"
        result = reranker.rerank("test query", [], top_k=5)
        assert result == []
        assert reranker.last_failure_reason is None

    def test_rerank_fallback_truncates_to_top_k(self) -> None:
        """When model not loaded, rerank() returns first top_k results."""
        reranker = self._make_unloaded_reranker()
        with patch.object(reranker, "_load_model"):
            results = [{"text": f"result {i}", "score": 0.5} for i in range(5)]
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
        reset_model_cache()

    def teardown_method(self) -> None:
        """Reset the singleton after each test."""
        reset_model_cache()

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

    def test_rerank_single_result_batch_of_one(self) -> None:
        """A single input result must produce a single output (batch-1 edge case).

        ONNX may return shape (1,) or (1, 1) for batch size 1.  The squeeze
        must handle both without error.
        """
        reranker = CrossEncoderReranker()

        mock_session = MagicMock()
        # Shape (1, 1) — single pair, logit = 5.0 → sigmoid ≈ 0.993
        mock_session.run.return_value = [np.array([[5.0]])]

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2, 3]]),
            "attention_mask": np.array([[1, 1, 1]]),
        }

        reranker._session = mock_session
        reranker._tokenizer = mock_tokenizer
        reranker._loaded = True

        results = [{"text": "only result", "score": 0.4}]
        out = reranker.rerank("query", results, top_k=5)

        assert len(out) == 1
        assert 0.99 < out[0]["score"] < 1.0
        assert out[0]["_reranked"] is True

    def test_rerank_top_k_truncation(self) -> None:
        """Results must be truncated to top_k even when there are more."""
        reranker = CrossEncoderReranker()

        mock_session = MagicMock()
        # 5 logits → 5 reranked results
        mock_session.run.return_value = [np.array([[4.0], [3.0], [2.0], [1.0], [0.0]])]

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2]]),
            "attention_mask": np.array([[1, 1]]),
        }

        reranker._session = mock_session
        reranker._tokenizer = mock_tokenizer
        reranker._loaded = True

        results = [{"text": f"doc {i}", "score": 0.1} for i in range(5)]
        out = reranker.rerank("query", results, top_k=2)

        assert len(out) == 2
        # Best score first (logit 4.0 → sigmoid ≈ 0.98)
        assert out[0]["score"] > out[1]["score"]

    def test_rerank_inference_failure_returns_originals(self) -> None:
        """When ONNX inference throws, return original results un-reranked."""
        reranker = CrossEncoderReranker()

        mock_session = MagicMock()
        mock_session.run.side_effect = RuntimeError("ONNX engine crashed")

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2]]),
            "attention_mask": np.array([[1, 1]]),
        }

        reranker._session = mock_session
        reranker._tokenizer = mock_tokenizer
        reranker._loaded = True

        results = [
            {"text": "first", "score": 0.9},
            {"text": "second", "score": 0.7},
        ]
        out = reranker.rerank("query", results, top_k=5)

        assert len(out) == 2
        assert all(r["_reranked"] is False for r in out)
        # Original scores preserved
        assert out[0]["score"] == 0.9
        assert out[1]["score"] == 0.7

    def test_rerank_handles_unexpected_output_shape(self) -> None:
        """ONNX returning a 1-D array (instead of 2-D) should still work.

        squeeze(-1) on shape (3,) is a no-op, so the code still works.
        """
        reranker = CrossEncoderReranker()

        mock_session = MagicMock()
        # 1-D array instead of 2-D — tests squeeze(-1) on already-flat data
        mock_session.run.return_value = [np.array([2.0, -1.0, 0.5])]

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2]]),
            "attention_mask": np.array([[1, 1]]),
        }

        reranker._session = mock_session
        reranker._tokenizer = mock_tokenizer
        reranker._loaded = True

        results = [
            {"text": "a", "score": 0.5},
            {"text": "b", "score": 0.5},
            {"text": "c", "score": 0.5},
        ]
        out = reranker.rerank("query", results, top_k=3)

        assert len(out) == 3
        for r in out:
            assert 0.0 < r["score"] < 1.0
            assert r["_reranked"] is True
        # Must be sorted descending
        scores = [r["score"] for r in out]
        assert scores == sorted(scores, reverse=True)

    def test_tokenizer_max_length_is_2048(self) -> None:
        """Tokenizer must be called with max_length=TOKENIZER_MAX_LENGTH (2048)."""
        assert TOKENIZER_MAX_LENGTH == 2048

        reranker = CrossEncoderReranker()

        mock_session = MagicMock()
        mock_session.run.return_value = [np.array([[1.0]])]

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2]]),
            "attention_mask": np.array([[1, 1]]),
        }

        reranker._session = mock_session
        reranker._tokenizer = mock_tokenizer
        reranker._loaded = True

        results = [{"text": "doc", "score": 0.5}]
        reranker.rerank("query", results, top_k=1)

        # In the tokenizers API, truncation/padding are configured on the
        # tokenizer object during _load_model, not passed per-call.
        # Verify the effective max length is set to TOKENIZER_MAX_LENGTH.
        assert reranker._effective_max_length == 2048


# ── Model loading tests ─────────────────────────────────────────────────────


class TestCrossEncoderRerankerModelLoading:
    """Tests for _load_model() behaviour: retry, failure, and skip paths."""

    def setup_method(self) -> None:
        """Reset the singleton before each test."""
        reset_model_cache()

    def teardown_method(self) -> None:
        """Reset the singleton after each test."""
        reset_model_cache()

    def test_load_model_skips_when_already_loaded(self) -> None:
        """_load_model() must return immediately if _loaded is True."""
        reranker = CrossEncoderReranker()
        reranker._loaded = True
        reranker._load_attempted = True

        # Should not attempt any imports or file I/O.
        reranker._load_model()
        assert reranker._loaded is True

    def test_load_model_failure_sets_error(self) -> None:
        """Failed model load must set _load_error and keep _loaded=False."""
        reranker = CrossEncoderReranker()

        # Use a selective mock that only blocks onnxruntime imports,
        # allowing RichHandler and other logging internals to work.
        real_import = builtins.__import__

        def _selective_import(name, *args, **kwargs):
            if name == "onnxruntime":
                raise ImportError("no onnxruntime")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_selective_import):
            reranker._load_model()

        assert reranker._loaded is False
        assert reranker._load_attempted is True
        assert reranker._load_error is not None

    def test_load_model_retry_after_failure(self) -> None:
        """After a failed load, next call must retry (transient recovery)."""
        reranker = CrossEncoderReranker()
        reranker._loaded = False
        reranker._load_attempted = True
        reranker._load_error = "previous failure"

        # Patch the heavy imports inside _load_model to simulate success
        mock_session = MagicMock()
        mock_tokenizer_cls = MagicMock()

        with patch(
            "rag_mcp.core.retrieval.reranker._select_onnx_variant", return_value=["onnx/model.onnx"]
        ):
            with patch(
                "huggingface_hub.hf_hub_download",
                return_value="/fake/model.onnx",
            ):
                with patch(
                    "tokenizers.Tokenizer.from_pretrained",
                    return_value=mock_tokenizer_cls,
                ):
                    with patch(
                        "onnxruntime.InferenceSession",
                        return_value=mock_session,
                    ):
                        with patch(
                            "rag_mcp.core.retrieval.reranker._read_max_position_embeddings",
                            return_value=512,
                        ):
                            reranker._load_model()

        assert reranker._loaded is True
        assert reranker._load_error is None
        assert reranker._session is mock_session


# ── Failure escalation tests (§1, ADR-029 decision #3) ──────────────────────


class TestFailureEscalation:
    """Tests for the module-level consecutive-failure escalation state."""

    def setup_method(self) -> None:
        """Reset the failure counter and model cache before each test."""
        reset_model_cache()

    def teardown_method(self) -> None:
        """Reset the failure counter and model cache after each test."""
        reset_model_cache()

    def _failing_reranker(self, message: str) -> CrossEncoderReranker:
        """Build a loaded reranker whose inference always raises ``message``."""
        reranker = CrossEncoderReranker()
        mock_session = MagicMock()
        mock_session.run.side_effect = RuntimeError(message)
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2]]),
            "attention_mask": np.array([[1, 1]]),
        }
        reranker._session = mock_session
        reranker._tokenizer = mock_tokenizer
        reranker._loaded = True
        return reranker

    def _succeeding_reranker(self) -> CrossEncoderReranker:
        """Build a loaded reranker whose inference always succeeds."""
        reranker = CrossEncoderReranker()
        mock_session = MagicMock()
        mock_session.run.return_value = [np.array([[1.0]])]
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2]]),
            "attention_mask": np.array([[1, 1]]),
        }
        reranker._session = mock_session
        reranker._tokenizer = mock_tokenizer
        reranker._loaded = True
        return reranker

    def test_single_failure_logs_warning_and_falls_back(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A single inference failure logs WARNING and falls back gracefully."""
        reranker = self._failing_reranker("boom")

        with caplog.at_level(logging.WARNING, logger="rag_mcp.core.retrieval.reranker"):
            out = reranker.rerank("query", [{"text": "doc", "score": 0.5}], top_k=5)

        assert out[0]["_reranked"] is False
        assert caplog.records
        assert caplog.records[-1].levelno == logging.WARNING

    def test_repeated_same_error_escalates_to_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """The same error signature repeated to the threshold escalates to ERROR."""
        with caplog.at_level(logging.WARNING, logger="rag_mcp.core.retrieval.reranker"):
            for _ in range(3):
                reranker = self._failing_reranker("persistent boom")
                reranker.rerank("query", [{"text": "doc", "score": 0.5}], top_k=5)

        levels = [r.levelno for r in caplog.records]
        assert levels == [logging.WARNING, logging.WARNING, logging.ERROR]

    def test_success_between_failures_resets_counter(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A success between failures resets the counter; the next failure warns."""
        with caplog.at_level(logging.WARNING, logger="rag_mcp.core.retrieval.reranker"):
            for _ in range(2):
                reranker = self._failing_reranker("flaky boom")
                reranker.rerank("query", [{"text": "doc", "score": 0.5}], top_k=5)

            success = self._succeeding_reranker()
            success.rerank("query", [{"text": "doc", "score": 0.5}], top_k=5)

            caplog.clear()
            reranker = self._failing_reranker("flaky boom")
            reranker.rerank("query", [{"text": "doc", "score": 0.5}], top_k=5)

        assert caplog.records
        assert caplog.records[-1].levelno == logging.WARNING

    def test_reset_model_cache_clears_failure_counter(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """reset_model_cache() clears the failure counter (task 1.12)."""
        with caplog.at_level(logging.WARNING, logger="rag_mcp.core.retrieval.reranker"):
            for _ in range(2):
                reranker = self._failing_reranker("cache-reset boom")
                reranker.rerank("query", [{"text": "doc", "score": 0.5}], top_k=5)

            reset_model_cache()

            caplog.clear()
            reranker = self._failing_reranker("cache-reset boom")
            reranker.rerank("query", [{"text": "doc", "score": 0.5}], top_k=5)

        assert caplog.records
        assert caplog.records[-1].levelno == logging.WARNING


# ── RERANK_ONNX_PROVIDER guard tests (§4) ────────────────────────────────────


class TestCoreMLProviderGuard:
    """Tests for the RERANK_ONNX_PROVIDER guard (previously untested)."""

    def setup_method(self) -> None:
        reset_model_cache()

    def teardown_method(self) -> None:
        reset_model_cache()

    def _load_with_providers(self, available: list[str]) -> list[str]:
        """Drive _load_model() and capture the providers passed to InferenceSession."""
        reranker = CrossEncoderReranker(model_id="test/coreml-model")
        mock_session = MagicMock()
        mock_tokenizer = MagicMock()

        captured: dict[str, list[str]] = {}

        def _capture_session(path, providers=None, **kwargs):
            captured["providers"] = providers
            return mock_session

        with patch(
            "rag_mcp.core.retrieval.reranker._select_onnx_variant",
            return_value=["onnx/model.onnx"],
        ):
            with patch("huggingface_hub.hf_hub_download", return_value="/fake/model.onnx"):
                with patch(
                    "tokenizers.Tokenizer.from_pretrained",
                    return_value=mock_tokenizer,
                ):
                    with patch(
                        "onnxruntime.get_available_providers",
                        return_value=available,
                    ):
                        with patch(
                            "onnxruntime.InferenceSession",
                            side_effect=_capture_session,
                        ):
                            with patch(
                                "rag_mcp.core.retrieval.reranker._read_max_position_embeddings",
                                return_value=512,
                            ):
                                reranker._load_model()

        assert reranker._loaded is True
        return captured["providers"]

    def test_provider_unset_uses_cpu_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No RERANK_ONNX_PROVIDER set → CPUExecutionProvider only."""
        monkeypatch.delenv("RERANK_ONNX_PROVIDER", raising=False)
        providers = self._load_with_providers(available=["CPUExecutionProvider"])
        assert providers == ["CPUExecutionProvider"]

    def test_coreml_requested_and_available_prefers_coreml(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RERANK_ONNX_PROVIDER=coreml with CoreML available → CoreML first."""
        monkeypatch.setenv("RERANK_ONNX_PROVIDER", "coreml")
        providers = self._load_with_providers(
            available=["CoreMLExecutionProvider", "CPUExecutionProvider"]
        )
        assert providers == ["CoreMLExecutionProvider", "CPUExecutionProvider"]

    def test_coreml_requested_but_unavailable_falls_back_to_cpu(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RERANK_ONNX_PROVIDER=coreml with CoreML unavailable → CPU only, no error."""
        monkeypatch.setenv("RERANK_ONNX_PROVIDER", "coreml")
        providers = self._load_with_providers(available=["CPUExecutionProvider"])
        assert providers == ["CPUExecutionProvider"]


# ── Cache-hit escalation regression (CodeRabbit/Greptile finding) ──────────


class TestCacheHitDoesNotResetFailureStreak:
    """A cache hit must not clear the process-wide failure counter.

    Regression guard for the bug where ``_load_model()``'s cache-hit
    branch called ``_reset_failure_state()``, defeating escalation when
    the model loads successfully once but inference persistently fails.
    In production, ``search()`` builds a fresh reranker per call, so each
    call hits the cache and would reset the counter before failing again.
    """

    def setup_method(self) -> None:
        reset_model_cache()

    def teardown_method(self) -> None:
        reset_model_cache()

    def test_cached_session_with_persistent_inference_failure_escalates(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Three fresh rerankers reusing a cached session must escalate to ERROR.

        Seeds ``_MODEL_CACHE`` with a session whose inference always fails,
        then builds three fresh instances whose ``_load_model()`` takes the
        cache-hit branch (no re-download).  Without the fix, each cache hit
        resets the streak and the level stays WARNING.
        """
        from rag_mcp.core.retrieval.reranker import (
            _MODEL_CACHE,
            CrossEncoderReranker,
        )

        # Seed the cache with a session that fails at inference time.
        # The cache key is now (backend_name, model_id) — a tuple — so
        # the cache-hit path finds the seeded entry.
        seed = CrossEncoderReranker()
        failing_session = MagicMock()
        failing_session.run.side_effect = RuntimeError("persistent cache-hit boom")
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.array([[1, 2]]),
            "attention_mask": np.array([[1, 1]]),
        }
        _MODEL_CACHE[("onnx", seed._model_id)] = (
            failing_session,
            mock_tokenizer,
            seed._effective_max_length,
        )

        # Build three fresh rerankers. Each _load_model() hits the cache,
        # picks up the failing session, then inference raises.
        with caplog.at_level(logging.WARNING, logger="rag_mcp.core.retrieval.reranker"):
            for _ in range(3):
                reranker = CrossEncoderReranker()
                reranker.rerank("query", [{"text": "doc", "score": 0.5}], top_k=5)

        levels = [r.levelno for r in caplog.records]
        assert levels == [logging.WARNING, logging.WARNING, logging.ERROR]
