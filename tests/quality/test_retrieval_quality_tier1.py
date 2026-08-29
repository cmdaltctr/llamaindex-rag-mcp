"""Deterministic Tier 1 retrieval-quality regression gate."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterator
from typing import Any

import pytest
from llama_index.core import Settings as LlamaIndexSettings
from llama_index.core.embeddings import MockEmbedding
from tests.quality.runner import (
    CORPUS_DIR,
    assert_metric_floors,
    load_baseline,
    load_golden_queries,
    measure_rows,
    measurement_record,
    validate_baseline,
)

from rag_mcp.core.retrieval import search
from rag_mcp.core.retrieval.dense import _cached_query_embedding
from rag_mcp.core.settings import EffectiveSettings, RetrievalBlock
from rag_mcp.core.vectordb.score import (
    DENSE_SCORE_KIND,
    canonical_score_from_l2,
)

pytestmark = pytest.mark.slow

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_COLLECTION = "quality_tier1"
_DIMENSION = 128
_EMBEDDING_ID = "deterministic-fake-v1"


def _token_features(text: str) -> list[str]:
    tokens = _TOKEN_RE.findall(text.casefold())
    return tokens + [f"{left}:{right}" for left, right in zip(tokens, tokens[1:], strict=False)]


def _stable_vector(text: str) -> list[float]:
    """Return a stable, unit-normalised BLAKE2b feature vector."""
    vector = [0.0] * _DIMENSION
    for feature in _token_features(text):
        digest = hashlib.blake2b(feature.encode(), digest_size=16).digest()
        bucket = int.from_bytes(digest[:8], "big") % _DIMENSION
        vector[bucket] += -1.0 if digest[8] & 1 else 1.0
    norm = math.sqrt(math.fsum(value * value for value in vector))
    if norm == 0.0:
        vector[0] = 1.0
        return vector
    return [value / norm for value in vector]


class DeterministicFakeEmbedding(MockEmbedding):
    """Test-only BLAKE2b embedding with no process-salted state."""

    model_name: str = _EMBEDDING_ID

    def _get_query_embedding(self, query: str) -> list[float]:
        return _stable_vector(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return _stable_vector(text)


class ControlledQualityStore:
    """In-memory rows whose dense boundary uses the production score converter."""

    def __init__(self) -> None:
        self.rows = [
            {
                "id": path.name,
                "document": path.read_text(encoding="utf-8"),
                "metadata": {"file_path": str(path)},
            }
            for path in sorted(CORPUS_DIR.glob("*.txt"))
        ]
        self.embeddings = {row["id"]: _stable_vector(str(row["document"])) for row in self.rows}

    @property
    def cache_identity(self) -> object:
        return self

    def count(self, collection_name: str) -> int:
        assert collection_name == _COLLECTION
        return len(self.rows)

    def get_generation(self, collection_name: str) -> int:
        assert collection_name == _COLLECTION
        return 1

    def iter_documents(
        self,
        collection_name: str,
        page_size: int | None = None,
    ) -> Iterator[tuple[str, str, dict[str, Any]]]:
        assert collection_name == _COLLECTION
        del page_size
        for row in self.rows:
            yield str(row["id"]), str(row["document"]), dict(row["metadata"])

    def query_dense(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        assert collection_name == _COLLECTION
        assert where is None
        ranked: list[dict[str, Any]] = []
        for row in self.rows:
            distance = math.sqrt(
                math.fsum(
                    (left - right) ** 2
                    for left, right in zip(
                        query_embedding,
                        self.embeddings[str(row["id"])],
                        strict=True,
                    )
                )
            )
            ranked.append(
                {
                    **row,
                    "score": canonical_score_from_l2(
                        distance,
                        backend="tier1-controlled",
                    ),
                    "score_kind": DENSE_SCORE_KIND,
                }
            )
        ranked.sort(key=lambda row: float(row["score"]), reverse=True)
        return ranked[:n_results]


def _settings() -> EffectiveSettings:
    return EffectiveSettings(
        collection_name=_COLLECTION,
        retrieval=RetrievalBlock(
            top_k=10,
            similarity_threshold=0.0,
            rerank_enabled=False,
            rerank_enabled_for_semantic=False,
            hybrid_enabled=True,
            hybrid_rrf_k=60,
            hybrid_sparse_backend="bm25",
        ),
    )


def _search(
    query: str,
    *,
    similarity_threshold: float = 0.0,
) -> list[dict[str, Any]]:
    LlamaIndexSettings.embed_model = DeterministicFakeEmbedding(embed_dim=_DIMENSION)
    _cached_query_embedding.cache_clear()
    return search(
        query=query,
        top_k=10,
        similarity_threshold=similarity_threshold,
        rerank=False,
        hybrid=True,
        collection_name=_COLLECTION,
        include_diagnostics=True,
        store=ControlledQualityStore(),
        effective_settings=_settings(),
    )


def _run_golden(
    *,
    similarity_threshold: float = 0.0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for query in load_golden_queries():
        results = _search(
            query["query"],
            similarity_threshold=similarity_threshold,
        )
        rows.append(
            {
                "id": query["id"],
                "query": query["query"],
                "expected_sources": query["expected_sources"],
                "sources": [result["source"] for result in results],
            }
        )
    return rows


def test_tier1_quality_floors() -> None:
    """Recall@10 and MRR@10 remain above deterministic committed floors."""
    rows = _run_golden()
    actual = measure_rows(rows)
    baseline = load_baseline()
    print(
        "TIER1_MEASUREMENT="
        + json.dumps(
            measurement_record(
                rows,
                extra={"embedding_id": _EMBEDDING_ID},
            ),
            sort_keys=True,
        )
    )
    validate_baseline(baseline, require_tier1=True, require_tier2=False)
    assert baseline["tier1"]["embedding_id"] == _EMBEDDING_ID
    assert_metric_floors(tier="tier1", actual=actual, baseline=baseline)


def test_production_score_fusion_threshold_and_ranking() -> None:
    """The gate traverses score conversion, RRF, thresholding, and sorting."""
    results = _search(load_golden_queries()[0]["query"])
    assert results
    assert [row["score"] for row in results] == sorted(
        (row["score"] for row in results),
        reverse=True,
    )

    overlap = next(
        row for row in results if row["dense_rank"] is not None and row["sparse_rank"] is not None
    )
    expected_fused = 1.0 / (60 + overlap["dense_rank"]) + 1.0 / (60 + overlap["sparse_rank"])
    assert overlap["fused_score"] == pytest.approx(expected_fused)
    assert overlap["score"] == pytest.approx(expected_fused)
    assert overlap["dense_score_kind"] == DENSE_SCORE_KIND

    assert (
        _search(
            load_golden_queries()[0]["query"],
            similarity_threshold=1.000001,
        )
        == []
    )


def test_controlled_threshold_perturbation_reduces_quality() -> None:
    """A deliberately strict threshold trips at least one guarded metric."""
    normal = measure_rows(_run_golden())
    perturbed = measure_rows(_run_golden(similarity_threshold=0.99))
    assert perturbed["recall@10"] < normal["recall@10"]
    assert perturbed["mrr@10"] < normal["mrr@10"]
