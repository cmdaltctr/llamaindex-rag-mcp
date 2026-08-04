"""Retrieval settings — pure data model, no upward imports.

Declares the configuration knobs and defaults for the retrieval
subpackage.  Consumed by the root ``Settings`` resolver in
``rag_mcp.config``.  MUST NOT import from ``config``, ``compose``, or
any other ``core/`` module (enforced by import-linter).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator


def _parse_legacy_bool(value: object) -> object:
    """Parse booleans using legacy ``.lower() == "true"`` semantics."""
    if isinstance(value, str):
        return value.lower() == "true"
    return value


LegacyBool = Annotated[bool, BeforeValidator(_parse_legacy_bool)]


class RetrievalSettings(BaseModel):
    """Configuration knobs for the retrieval pipeline.

    Defaults mirror the pre-refactor ``config.py`` values exactly.
    Reranker is disabled by default after Experiment 10 (see ADR-018
    and ``config.py`` inline comments).
    """

    # ── Top-level retrieval ──────────────────────────────────────────

    # Default number of chunks to return from search().
    top_k: int = 10

    # Minimum vector-similarity score for a result to be included.
    similarity_threshold: float = 0.0

    # ── Reranker ─────────────────────────────────────────────────────

    # Global reranker enable flag.  Off by default — Experiment 10
    # showed the cross-encoder degrades Coverage@20 by 19-27% on
    # identifier-heavy technical docs.
    rerank_enabled: LegacyBool = False

    # When ``rerank_enabled`` is False, allow the policy resolver to
    # still enable reranking for semantic workloads.
    rerank_enabled_for_semantic: LegacyBool = True

    # Fraction of identifier-heavy queries above which the reranker is
    # auto-disabled (Experiment 10: harmful at ≥30%).
    hard_technical_threshold: float = 0.3

    # Candidate pool sizing for the "Wide Net, Tight Filter" pattern.
    # Effective fetch = max(rerank_max_fetch, top_k * rerank_fetch_multiplier).
    rerank_fetch_multiplier: int = 3
    rerank_max_fetch: int = 100

    # Reranker model HuggingFace ID.
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ── Hybrid retrieval ────────────────────────────────────────────

    # Enable dense + sparse fusion via Reciprocal Rank Fusion.
    hybrid_enabled: LegacyBool = False

    # RRF constant (higher = more weight to lower-ranked results).
    hybrid_rrf_k: int = 60

    # Sparse backend: "bm25" (in-process), "native" (ChromaDB), "auto".
    hybrid_sparse_backend: str = "bm25"
