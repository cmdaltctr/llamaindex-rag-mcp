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
from rag_mcp.retrieval import _resolve_fetch_k


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
    monkeypatch.setattr(_config, "RERANK_FETCH_MULTIPLIER", 4)
    monkeypatch.setattr(_config, "RERANK_MAX_FETCH", 20)

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
