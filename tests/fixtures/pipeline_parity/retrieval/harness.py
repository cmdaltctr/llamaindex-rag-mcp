"""Deterministic retrieval parity harness (task 3.1).

Loads the recorded corpus and cases in this directory and drives the
standard ``search()`` path with scripted dense scores, the real BM25
sparse backend, the real RRF fusion and a scripted reranker. A later
canonical graph template test reuses the same corpus, cases and
projection so both paths are compared against one recorded expectation.

The harness never reads process defaults on its own: callers pass the
``monkeypatch`` fixture and the conftest ``effective_settings`` factory.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent

#: Row fields compared between the recorded expectation and a run.
PROJECTED_FIELDS: tuple[str, ...] = (
    "id",
    "source",
    "score",
    "score_kind",
    "reranked",
    "dense_score",
    "dense_score_kind",
    "dense_rank",
    "sparse_rank",
    "fused_rank",
    "threshold_score_kind",
    "rerank_reason",
    "rerank_backend",
    "sparse_backend",
)


def load_corpus() -> dict[str, Any]:
    """Return the shared parity corpus."""
    return json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))


def load_cases() -> list[dict[str, Any]]:
    """Return every recorded parity case."""
    return json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]


class ParityStore:
    """In-memory store with the methods dense, BM25 and assembly read."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = chunks

    def count(self, name: str) -> int:
        """Return the number of chunks."""
        return len(self._chunks)

    def iter_documents(self, name: str, page_size: int | None = None) -> Iterator[tuple]:
        """Yield ``(id, text, metadata)`` for the BM25 index build."""
        for chunk in self._chunks:
            yield (chunk["id"], chunk["text"], dict(chunk["metadata"]))

    def iter_metadatas(self, name: str) -> Iterator[dict]:
        """Yield chunk metadata."""
        for chunk in self._chunks:
            yield dict(chunk["metadata"])

    def get_generation(self, name: str) -> int:
        """Return a constant generation (the corpus never changes)."""
        return 0

    def bump_generation(self, name: str) -> None:
        """Accept a generation bump without effect."""


def make_dense(chunks: list[dict[str, Any]]) -> Callable[..., list[dict]]:
    """Return a dense strategy that replays the recorded dense scores.

    Rows follow the ``dense._dense_query_rows`` shape, ordered by
    descending score and truncated to ``fetch_k``.
    """
    ordered = sorted(chunks, key=lambda c: c["dense_score"], reverse=True)

    def dense(store: Any, collection: str, query: str, fetch_k: int, *args: Any, **kw: Any):
        return [
            {
                "id": c["id"],
                "score": c["dense_score"],
                "score_kind": "dense_similarity_v1",
                "source": c["metadata"]["file_name"],
                "page_label": None,
                "text": c["text"],
                "metadata": dict(c["metadata"]),
                "reranked": False,
            }
            for c in ordered[:fetch_k]
        ]

    return dense


class ParityReranker:
    """Scripted reranker honouring the ``CrossEncoderReranker`` contract."""

    backend_name = "parity"

    def __init__(self, scores: dict[str, float], *, fail: bool) -> None:
        self._scores = scores
        self._fail = fail
        self.last_failure_reason: str | None = None

    def rerank(self, query: str, results: list[dict], top_k: int = 5) -> list[dict]:
        """Re-score rows, or fail like an inference error does."""
        self.last_failure_reason = None
        if not results:
            return results
        if self._fail:
            self.last_failure_reason = "inference failed: parity fixture"
            for row in results:
                row["_reranked"] = False
            return results[:top_k]
        for row in results:
            row["score"] = self._scores[row["id"]]
            row["_reranked"] = True
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]


def run_search(
    case: dict[str, Any],
    corpus: dict[str, Any],
    *,
    monkeypatch: Any,
    settings_factory: Callable[..., Any],
) -> list[dict]:
    """Run one recorded case through the standard ``search()`` path."""
    from omrs.core.retrieval import registry
    from omrs.core.retrieval.pipeline import search
    from omrs.core.settings import set_default_effective_settings

    chunks = [] if case.get("empty_collection") else corpus["chunks"]
    monkeypatch.setitem(registry._cache, "dense", make_dense(chunks))
    settings = settings_factory(**case.get("settings", {}))
    kwargs = dict(case["search"])
    if case.get("settings_via", "argument") == "default":
        set_default_effective_settings(settings)
        kwargs["effective_settings"] = None
    else:
        kwargs["effective_settings"] = settings
    mode = case.get("reranker", "success")
    if mode != "none":
        scores = {c["id"]: c["rerank_score"] for c in chunks}
        kwargs["reranker"] = ParityReranker(scores, fail=mode == "fail")
    query = kwargs.pop("query", corpus["query"])
    return search(
        query,
        store=ParityStore(chunks),
        collection_name="parity",
        **kwargs,
    )


def project(rows: list[dict]) -> list[dict]:
    """Return the compared subset of each row, keeping row order."""
    return [{k: row[k] for k in PROJECTED_FIELDS if k in row} for row in rows]


def public_keys(rows: list[dict]) -> list[list[str]]:
    """Return each row's sorted key set (public result shape)."""
    return [sorted(row) for row in rows]
