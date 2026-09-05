"""Reciprocal Rank Fusion for hybrid retrieval.

Fuses dense and sparse ranked result lists using RRF.  Extracted from
the original ``retrieval.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

RRF_SCORE_KIND = "rrf_v1"


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    k: int = 60,
) -> dict[str, float]:
    """Fuse ranked doc-id lists with Reciprocal Rank Fusion.

    Args:
        rankings: Ranked doc-id lists to fuse.
        k: RRF damping constant. Supplied by the caller from the injected
            ``EffectiveSettings``; the literal default is the ADR-017 value
            and exists only so direct unit tests need not build settings.
    """
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return fused


def rrf_with_metadata(
    dense_ranked: list[dict],
    sparse_ranked: list[dict],
    k: int = 60,
) -> list[dict]:
    """Return sorted fused result dicts with score and rank diagnostics.

    Args:
        dense_ranked: Dense-retriever results in rank order.
        sparse_ranked: Sparse-retriever results in rank order.
        k: RRF damping constant, supplied by the caller from the injected
            ``EffectiveSettings``.
    """
    dense_ids = [str(row["id"]) for row in dense_ranked]
    sparse_ids = [str(row["id"]) for row in sparse_ranked]
    scores = reciprocal_rank_fusion([dense_ids, sparse_ids], k=k)

    by_id: dict[str, dict] = {}
    dense_rank: dict[str, int] = {}
    sparse_rank: dict[str, int] = {}

    for rank, row in enumerate(dense_ranked, start=1):
        doc_id = str(row["id"])
        dense_rank[doc_id] = rank
        dense_row = dict(row)
        if "score" in row:
            dense_row["dense_score"] = row["score"]
        if "score_kind" in row:
            dense_row["dense_score_kind"] = row["score_kind"]
        by_id.setdefault(doc_id, dense_row)
    for rank, row in enumerate(sparse_ranked, start=1):
        doc_id = str(row["id"])
        sparse_rank[doc_id] = rank
        by_id.setdefault(doc_id, dict(row))

    fused_rows: list[dict] = []
    for doc_id, score in scores.items():
        row = dict(by_id[doc_id])
        row["id"] = doc_id
        row["fused_score"] = score
        row["score"] = score
        row["score_kind"] = RRF_SCORE_KIND
        row["dense_rank"] = dense_rank.get(doc_id)
        row["sparse_rank"] = sparse_rank.get(doc_id)
        fused_rows.append(row)

    fused_rows.sort(key=lambda row: row["fused_score"], reverse=True)
    for rank, row in enumerate(fused_rows, start=1):
        row["fused_rank"] = rank
    return fused_rows
