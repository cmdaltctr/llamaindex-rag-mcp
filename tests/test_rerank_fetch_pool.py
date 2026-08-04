"""Tests for the reranker fetch-pool sizing in `retrieval._resolve_fetch_k`.

Covers Section 2 of the rag-retrieval-quality-improvements OpenSpec change:
- Default pool when reranking is enabled (max(100, top_k * 3)).
- Env-var-overridden pool sizing.
- Small-collection clamp behaviour (min(fetch_k, collection.count())).
- Reranking disabled keeps fetch_k == top_k.
"""

from __future__ import annotations

import pytest

from rag_mcp import config as _config
from rag_mcp.core.retrieval.policy import _resolve_fetch_k


# ── Defaults ────────────────────────────────────────────────────────────────


def test_default_pool_is_at_least_50_when_reranking() -> None:
    """With defaults (max=100, multiplier=3), top_k=5 → fetch_k=100."""
    fetch_k = _resolve_fetch_k(top_k=5, rerank=True, collection_count=1000)
    assert fetch_k == 100


def test_default_pool_grows_with_top_k() -> None:
    """top_k=10 with multiplier=10 yields fetch_k=100, above the floor."""
    fetch_k = _resolve_fetch_k(top_k=10, rerank=True, collection_count=1000)
    assert fetch_k == 100


def test_rerank_disabled_uses_top_k_directly() -> None:
    """Without reranking, fetch_k SHALL equal top_k (original behaviour)."""
    fetch_k = _resolve_fetch_k(top_k=5, rerank=False, collection_count=1000)
    assert fetch_k == 5


# ── Env-var overrides ──────────────────────────────────────────────────────


def test_env_overrides_pool_size(monkeypatch: pytest.MonkeyPatch) -> None:
    """RERANK_FETCH_MULTIPLIER and RERANK_MAX_FETCH SHALL be respected."""
    monkeypatch.setattr(_config.settings, "rerank_fetch_multiplier", 4)
    monkeypatch.setattr(_config.settings, "rerank_max_fetch", 20)

    # Spec scenario: top_k=3 → max(20, 3*4) = 20
    fetch_k = _resolve_fetch_k(top_k=3, rerank=True, collection_count=1000)
    assert fetch_k == 20

    # Multiplier wins when it exceeds the floor: top_k=10, mult=4 → 40
    fetch_k = _resolve_fetch_k(top_k=10, rerank=True, collection_count=1000)
    assert fetch_k == 40


# ── Small-collection clamp ─────────────────────────────────────────────────


def test_small_collection_clamps_fetch_k() -> None:
    """If the collection has fewer chunks than the pool, clamp to the count."""
    fetch_k = _resolve_fetch_k(top_k=5, rerank=True, collection_count=12)
    assert fetch_k == 12


def test_clamp_floors_at_one() -> None:
    """A non-empty collection always fetches at least 1 candidate."""
    # collection_count=0 represents "unknown / skip clamp" — falls back to
    # the computed pool. Empty collections short-circuit earlier in
    # ``search()`` before this helper is called.
    fetch_k = _resolve_fetch_k(top_k=0, rerank=True, collection_count=10)
    assert fetch_k >= 1


# ── fetch_k_override (experiment escape hatch) ────────────────────────────


def test_override_bypasses_formula() -> None:
    """An explicit fetch_k_override SHALL bypass the max() formula.

    This is the fix for the Experiment 10 confound where labelled pool
    sizes 50, 200, 500 all collapsed to effective fetch_k=500 because
    ``max(50/200/500, 50×10) = 500``.
    """
    # With defaults (max=100, mult=3), top_k=50 would compute fetch_k=150.
    # Override to 50 → must get 50, not 150.
    fetch_k = _resolve_fetch_k(
        top_k=50, rerank=True, collection_count=10000,
        fetch_k_override=50,
    )
    assert fetch_k == 50

    # Override to 200 → must get 200.
    fetch_k = _resolve_fetch_k(
        top_k=50, rerank=True, collection_count=10000,
        fetch_k_override=200,
    )
    assert fetch_k == 200


def test_override_distinct_values_no_collapse() -> None:
    """The four Exp 10b pool sizes SHALL all produce distinct effective values.

    Regression test for the Experiment 10 design flaw.  Before the override,
    all four values collapsed to 500.  With the override, each is distinct.
    """
    values = [
        _resolve_fetch_k(
            top_k=50, rerank=True, collection_count=10000,
            fetch_k_override=v,
        )
        for v in (50, 100, 200, 500)
    ]
    assert values == [50, 100, 200, 500]
    assert len(set(values)) == 4, f"Pool sizes collapsed: {values}"


def test_override_still_clamps_to_collection() -> None:
    """An override larger than the collection SHALL be clamped down."""
    fetch_k = _resolve_fetch_k(
        top_k=50, rerank=True, collection_count=30,
        fetch_k_override=500,
    )
    assert fetch_k == 30


def test_override_none_preserves_formula() -> None:
    """When fetch_k_override is None, the formula SHALL be used (backward compat)."""
    # Same as test_default_pool_is_at_least_50_when_reranking but with
    # explicit fetch_k_override=None to prove the default path is unchanged.
    fetch_k = _resolve_fetch_k(
        top_k=5, rerank=True, collection_count=1000,
        fetch_k_override=None,
    )
    assert fetch_k == 100
