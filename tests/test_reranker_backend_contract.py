"""Cross-backend contract tests for reranker backends (tasks 8.1, 8.2, 8.5).

Asserts every backend produces scores on the same (0, 1) scale, returns
results sorted descending, sets _reranked, and truncates to top_k.
The cross-backend agreement test compares score values within a tolerance
to catch a double-sigmoid bug, which preserves monotonicity and stays in
(0, 1) but compresses the score scale.

Torch-backend tests are marked ``@pytest.mark.slow`` so the fast suite
stays torch-free (task 8.5).
"""

from __future__ import annotations

import pytest

from rag_mcp.core.retrieval.reranker import CrossEncoderReranker, reset_model_cache

# Shared fixture data — small enough to run quickly, large enough to
# exercise sorting and top_k truncation.
_FIXTURE_QUERY = "What is machine learning?"
_FIXTURE_CANDIDATES = [
    {"text": "Machine learning is a subset of artificial intelligence.", "score": 0.8},
    {"text": "The weather is sunny today.", "score": 0.3},
    {"text": "Deep learning uses neural networks with many layers.", "score": 0.7},
    {"text": "Python is a popular programming language.", "score": 0.2},
    {"text": "Neural networks are inspired by biological neurons.", "score": 0.6},
]
_FIXTURE_TOP_K = 3


@pytest.fixture(autouse=True)
def _isolate_cache():
    """Clear the model cache before and after each test."""
    reset_model_cache()
    yield
    reset_model_cache()


# ── Torch backend fallback (fast, no torch required) ─────────────────────
# These tests exercise the graceful-degradation path: when torch is not
# installed, _load_model catches ImportError, _loaded stays False, and
# rerank() returns un-reranked results. They are NOT slow-marked because
# they never import torch — the ImportError fires before the module loads.


def test_torch_backend_fallback_returns_un_reranked() -> None:
    """Without torch installed, rerank SHALL return un-reranked results."""
    from rag_mcp.core.retrieval.reranker_torch import SentenceTransformerReranker

    reranker = SentenceTransformerReranker()
    results = [
        {"text": "doc one", "score": 0.8},
        {"text": "doc two", "score": 0.3},
    ]
    out = reranker.rerank("query", list(results), top_k=2)
    assert len(out) == 2
    assert all(r.get("_reranked") is False for r in out)


def test_torch_backend_fallback_sets_failure_reason() -> None:
    """Without torch, last_failure_reason SHALL be set."""
    from rag_mcp.core.retrieval.reranker_torch import SentenceTransformerReranker

    reranker = SentenceTransformerReranker()
    reranker.rerank("query", [{"text": "doc", "score": 0.5}], top_k=1)
    assert reranker.last_failure_reason is not None
    assert "model load failed" in reranker.last_failure_reason


def test_torch_backend_empty_returns_empty() -> None:
    """Empty results SHALL return empty without loading the model."""
    from rag_mcp.core.retrieval.reranker_torch import SentenceTransformerReranker

    reranker = SentenceTransformerReranker()
    assert reranker.rerank("query", [], top_k=5) == []


def test_torch_backend_fallback_truncates_to_top_k() -> None:
    """Fallback SHALL truncate results to top_k."""
    from rag_mcp.core.retrieval.reranker_torch import SentenceTransformerReranker

    reranker = SentenceTransformerReranker()
    results = [{"text": f"doc {i}", "score": 0.5} for i in range(5)]
    out = reranker.rerank("query", results, top_k=2)
    assert len(out) == 2


def test_torch_backend_backend_name_is_torch() -> None:
    """The backend_name attribute SHALL be 'torch'."""
    from rag_mcp.core.retrieval.reranker_torch import SentenceTransformerReranker

    reranker = SentenceTransformerReranker()
    assert reranker.backend_name == "torch"


def test_torch_backend_constructor_accepts_model_id() -> None:
    """Constructor SHALL accept a model_id override."""
    from rag_mcp.core.retrieval.reranker_torch import SentenceTransformerReranker

    reranker = SentenceTransformerReranker(model_id="custom/model")
    assert reranker._model_id == "custom/model"


def test_torch_backend_score_processing_with_mocked_cross_encoder() -> None:
    """The score-processing path (sigmoid, sort, truncation) SHALL work.

    Mocks _loaded=True and _cross_encoder to exercise the inference
    success path without requiring the torch extra.  The actual
    import torch / predict call is excluded from coverage; this test
    covers everything after it: sigmoid normalisation, sorting,
    top_k truncation, and the _reranked flag.
    """
    import sys
    from unittest.mock import MagicMock

    import numpy as np

    from rag_mcp.core.retrieval.reranker_torch import SentenceTransformerReranker

    reranker = SentenceTransformerReranker()
    reranker._loaded = True

    # Mock the cross_encoder.predict to return raw logits.
    # sigmoid(3.0) ≈ 0.95, sigmoid(-2.0) ≈ 0.12, sigmoid(0.5) ≈ 0.62
    mock_cross_encoder = MagicMock()
    mock_cross_encoder.predict.return_value = np.array([3.0, -2.0, 0.5])
    reranker._cross_encoder = mock_cross_encoder

    # Mock torch in sys.modules so the `import torch` inside rerank succeeds.
    mock_torch = MagicMock()
    with __import__("unittest.mock", fromlist=["patch"]).patch.dict(
        sys.modules, {"torch": mock_torch}
    ):
        results = [
            {"text": "low", "score": 0.5},
            {"text": "high", "score": 0.5},
            {"text": "medium", "score": 0.5},
        ]
        out = reranker.rerank("query", results, top_k=3)

    assert len(out) == 3
    assert all(r["_reranked"] is True for r in out)
    # Sorted descending by score
    scores = [r["score"] for r in out]
    assert scores == sorted(scores, reverse=True)
    # Sigmoid values are in (0, 1)
    assert all(0.0 < s < 1.0 for s in scores)


def test_torch_backend_inference_failure_returns_un_reranked() -> None:
    """When inference raises, rerank SHALL return un-reranked results."""
    import sys
    from unittest.mock import MagicMock, patch

    from rag_mcp.core.retrieval.reranker_torch import SentenceTransformerReranker

    reranker = SentenceTransformerReranker()
    reranker._loaded = True

    mock_cross_encoder = MagicMock()
    mock_cross_encoder.predict.side_effect = RuntimeError("inference boom")
    reranker._cross_encoder = mock_cross_encoder

    mock_torch = MagicMock()
    with patch.dict(sys.modules, {"torch": mock_torch}):
        results = [{"text": "doc", "score": 0.5}]
        out = reranker.rerank("query", results, top_k=1)

    assert len(out) == 1
    assert out[0]["_reranked"] is False
    assert reranker.last_failure_reason is not None
    assert "inference failed" in reranker.last_failure_reason


def test_torch_backend_score_cardinality_mismatch() -> None:
    """Score cardinality mismatch SHALL return un-reranked results."""
    import sys
    from unittest.mock import MagicMock, patch

    import numpy as np

    from rag_mcp.core.retrieval.reranker_torch import SentenceTransformerReranker

    reranker = SentenceTransformerReranker()
    reranker._loaded = True

    # Return 2 logits for 3 results → cardinality mismatch
    mock_cross_encoder = MagicMock()
    mock_cross_encoder.predict.return_value = np.array([1.0, 2.0])
    reranker._cross_encoder = mock_cross_encoder

    mock_torch = MagicMock()
    with patch.dict(sys.modules, {"torch": mock_torch}):
        results = [
            {"text": "a", "score": 0.5},
            {"text": "b", "score": 0.5},
            {"text": "c", "score": 0.5},
        ]
        out = reranker.rerank("query", results, top_k=3)

    assert len(out) == 3
    assert all(r["_reranked"] is False for r in out)


def test_torch_backend_cache_hit_reuses_model() -> None:
    """Cache hit SHALL reuse the cached cross-encoder without reloading."""
    from unittest.mock import MagicMock

    from rag_mcp.core.retrieval._reranker_cache import _MODEL_CACHE
    from rag_mcp.core.retrieval.reranker_torch import SentenceTransformerReranker

    reranker = SentenceTransformerReranker()
    mock_ce = MagicMock()
    _MODEL_CACHE[("torch", reranker._model_id)] = (mock_ce,)

    reranker._load_model()
    assert reranker._loaded is True
    assert reranker._cross_encoder is mock_ce
    assert reranker.last_failure_reason is None


# ── Task 8.1: every backend returns normalised scores ──────────────────


@pytest.mark.slow
@pytest.mark.parametrize(
    "backend_name,backend_cls",
    [
        ("onnx", CrossEncoderReranker),
    ],
    ids=lambda x: x if isinstance(x, str) else x.__name__,
)
def test_backend_scores_in_range(backend_name, backend_cls) -> None:
    """Every backend SHALL return scores in (0, 1]."""
    reranker = backend_cls()
    results = reranker.rerank(_FIXTURE_QUERY, list(_FIXTURE_CANDIDATES), top_k=_FIXTURE_TOP_K)
    for r in results:
        assert 0.0 < r["score"] <= 1.0, f"Score {r['score']} outside (0, 1]"


@pytest.mark.slow
def test_onnx_backend_sorted_descending() -> None:
    """ONNX backend SHALL return results sorted by descending score."""
    reranker = CrossEncoderReranker()
    results = reranker.rerank(_FIXTURE_QUERY, list(_FIXTURE_CANDIDATES), top_k=_FIXTURE_TOP_K)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True), "Results not sorted descending"


@pytest.mark.slow
def test_onnx_backend_reranked_flag_set() -> None:
    """ONNX backend SHALL set _reranked=True on every result."""
    reranker = CrossEncoderReranker()
    results = reranker.rerank(_FIXTURE_QUERY, list(_FIXTURE_CANDIDATES), top_k=_FIXTURE_TOP_K)
    assert all(r.get("_reranked") is True for r in results), "_reranked not set"


@pytest.mark.slow
def test_onnx_backend_top_k_truncation() -> None:
    """ONNX backend SHALL truncate to top_k."""
    reranker = CrossEncoderReranker()
    results = reranker.rerank(_FIXTURE_QUERY, list(_FIXTURE_CANDIDATES), top_k=_FIXTURE_TOP_K)
    assert len(results) == _FIXTURE_TOP_K


# ── Task 8.2: cross-backend agreement (score values, not just ranking) ──
# Torch-backend tests are marked slow so the fast suite stays torch-free.
# They only run when the torch extra is installed and -m "slow" is used.


@pytest.mark.slow
def test_cross_backend_top_ranked_matches() -> None:
    """ONNX and torch backends agree on the top-ranked document.

    Checks the top-ranked document matches AND score values agree within
    a tolerance. A ranking-only or range-only test would miss a double-
    sigmoid bug, which preserves monotonicity and stays in (0, 1) but
    compresses the score scale.

    Skipped when the torch extra is not installed.
    """
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        pytest.skip("torch extra not installed — run 'uv sync --extra torch'")

    from rag_mcp.core.retrieval.reranker_torch import SentenceTransformerReranker

    onnx = CrossEncoderReranker()
    torch_backend = SentenceTransformerReranker()

    candidates_a = [dict(c) for c in _FIXTURE_CANDIDATES]
    candidates_b = [dict(c) for c in _FIXTURE_CANDIDATES]

    onnx_results = onnx.rerank(_FIXTURE_QUERY, candidates_a, top_k=_FIXTURE_TOP_K)
    torch_results = torch_backend.rerank(_FIXTURE_QUERY, candidates_b, top_k=_FIXTURE_TOP_K)

    # Top-ranked document must match
    assert onnx_results[0]["text"] == torch_results[0]["text"], (
        f"Top-ranked mismatch: ONNX chose {onnx_results[0]['text']!r}, "
        f"torch chose {torch_results[0]['text']!r}"
    )

    # Score values must agree within tolerance — this catches double-sigmoid
    onnx_score = onnx_results[0]["score"]
    torch_score = torch_results[0]["score"]
    assert abs(onnx_score - torch_score) < 0.01, (
        f"Score value mismatch: ONNX={onnx_score:.6f}, torch={torch_score:.6f}, "
        f"delta={abs(onnx_score - torch_score):.6f}. "
        f"A large delta suggests double-sigmoid (activation_fn not overridden)."
    )
