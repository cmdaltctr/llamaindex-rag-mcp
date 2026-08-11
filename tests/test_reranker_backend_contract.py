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
