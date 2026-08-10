"""Sparse retrieval helpers for optional hybrid search.

The v1 sparse path is an in-memory BM25 fallback.  It scans all chunks in
the target collection on first use, builds a process-local BM25 index,
and reuses that index until the collection generation counter in the
:class:`VectorStore` advances.  Memory footprint is therefore proportional
to the number of chunks in the active collection: tokenised chunk text,
metadata, IDs, and BM25 document-frequency tables are retained in Python
for each queried collection.  This is acceptable for the local
single-user MCP server and is deliberately not persisted to disk in v1.

The code is structured around a simple tokeniser function so a future
env-var-selected tokeniser can be plugged in without changing retrieval.
"""

from __future__ import annotations

import logging
import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "he",
        "her",
        "his",
        "i",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "she",
        "that",
        "the",
        "their",
        "them",
        "there",
        "these",
        "they",
        "this",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
        "you",
        "your",
    }
)


def tokenize_english(text: str) -> list[str]:
    """Lowercase, word-boundary tokenise, and remove common stop words."""
    return [
        token
        for token in re.findall(r"\b\w+\b", text.lower())
        if token and token not in _STOP_WORDS
    ]


class _SimpleBM25Okapi:
    """Small BM25Okapi fallback used when ``rank_bm25`` is not installed."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.corpus = corpus
        self.k1 = k1
        self.b = b
        self.doc_freqs = [Counter(doc) for doc in corpus]
        self.doc_len = [len(doc) for doc in corpus]
        self.avgdl = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        nd: Counter[str] = Counter()
        for freqs in self.doc_freqs:
            nd.update(freqs.keys())
        corpus_size = len(corpus)
        self.idf = {
            term: math.log(1 + (corpus_size - freq + 0.5) / (freq + 0.5))
            for term, freq in nd.items()
        }

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        scores: list[float] = []
        for freqs, doc_len in zip(self.doc_freqs, self.doc_len, strict=False):
            score = 0.0
            for token in query_tokens:
                tf = freqs.get(token, 0)
                if tf == 0:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * doc_len / (self.avgdl or 1.0))
                score += self.idf.get(token, 0.0) * (tf * (self.k1 + 1)) / denom
            scores.append(score)
        return scores


def _make_bm25(tokenised_corpus: list[list[str]]):
    if not tokenised_corpus:
        return _SimpleBM25Okapi([])
    try:
        from rank_bm25 import BM25Okapi

        return BM25Okapi(tokenised_corpus)
    except Exception:
        logger.debug("rank_bm25 unavailable; using internal BM25Okapi fallback")
        return _SimpleBM25Okapi(tokenised_corpus)


@dataclass(frozen=True)
class _ChunkRow:
    doc_id: str
    text: str
    metadata: dict[str, Any]


@dataclass
class _CachedBM25:
    generation: int
    index: Any
    rows: list[_ChunkRow]


def _detect_native_sparse_capability() -> bool:
    """Delegate to the vectordb module's capability probe.

    Kept as a thin wrapper so existing imports from
    ``config.resolve_sparse_backend`` continue to resolve without
    touching ChromaDB directly in this module.
    """
    from ..vectordb.chroma import detect_native_sparse_capability

    return detect_native_sparse_capability()


class BM25SparseRetriever:
    """Generation-aware BM25 retriever for one collection."""

    _cache: dict[str, _CachedBM25] = {}
    _cache_lock = threading.Lock()

    def __init__(
        self,
        collection_name: str,
        store: Any | None = None,
    ) -> None:
        self.collection_name = collection_name
        self._store = store

    @classmethod
    def clear_all_caches(cls) -> None:
        with cls._cache_lock:
            cls._cache.clear()

    def query(self, query_text: str, top_n: int) -> list[tuple[int, str, str, dict]]:
        """Return ``[(rank, doc_id, text, metadata), ...]`` for BM25 matches."""
        if top_n <= 0:
            return []
        query_tokens = tokenize_english(query_text)
        if not query_tokens:
            return []

        cached = self._get_or_build_index()
        if not cached.rows:
            return []

        scores = cached.index.get_scores(query_tokens)
        ranked = [(idx, float(score)) for idx, score in enumerate(scores) if float(score) > 0.0]
        ranked.sort(key=lambda item: item[1], reverse=True)

        results: list[tuple[int, str, str, dict]] = []
        for rank, (idx, _score) in enumerate(ranked[:top_n], start=1):
            row = cached.rows[idx]
            results.append((rank, row.doc_id, row.text, dict(row.metadata)))
        return results

    def _get_store(self):
        if self._store is not None:
            return self._store
        from ..vectordb import get_default_store

        return get_default_store()

    def _get_generation(self) -> int:
        return self._get_store().get_generation(self.collection_name)

    def _get_or_build_index(self) -> _CachedBM25:
        generation = self._get_generation()
        with self._cache_lock:
            cached = self._cache.get(self.collection_name)
            if cached is not None and cached.generation == generation:
                return cached

            store = self._get_store()
            rows = _read_collection_rows(store, self.collection_name)
            tokenised = [tokenize_english(row.text) for row in rows]
            index = _make_bm25(tokenised)
            cached = _CachedBM25(generation=generation, index=index, rows=rows)
            self._cache[self.collection_name] = cached
            return cached


def _read_collection_rows(store: Any, collection_name: str) -> list[_ChunkRow]:
    """Read all collection chunks into row objects with bounded paging."""
    count = store.count(collection_name)
    if count == 0:
        return []

    rows: list[_ChunkRow] = []
    for doc_id, text, metadata in store.iter_documents(collection_name):
        rows.append(_ChunkRow(doc_id, text, metadata))
    return rows
