"""Sparse retrieval helpers for optional hybrid search.

The v1 sparse path is an in-memory BM25 fallback.  It scans all chunks in
the target collection on first use, builds a process-local BM25 index,
and reuses that index until the collection's cache-validity token
changes.  Memory footprint is therefore proportional to the number of
chunks in the active collection: tokenised chunk text, metadata, IDs,
and BM25 document-frequency tables are retained in Python for each
queried collection.  This is acceptable for the local single-user MCP
server and is deliberately not persisted to disk in v1.

Cache validity is a **tagged token** resolved per query
(:func:`_resolve_validity_token`): the store's durable data version
when it exposes one — so writes made by *other* processes, such as the
watch daemon, invalidate the cache — otherwise the process-local
generation counter with a one-shot warning naming the reduced
guarantee.  A rebuild reads the token before fetching rows and again
before publishing, and discards any build whose tokens differ, so a
mutation landing mid-build cannot be cached.

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

from .filters import matches_metadata_filter

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
    """Small BM25Okapi fallback used when ``rank_bm25`` is not installed.

    Mirrors the IDF formula and epsilon clipping of ``rank_bm25.BM25Okapi``
    so the fallback does not mask scoring divergences on tiny corpora.
    """

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
        # RSJ IDF: log((N - df + 0.5) / (df + 0.5)) — same as rank_bm25.
        # Negative IDFs (term in more than half the corpus) are clipped to
        # epsilon * average_idf, matching rank_bm25's default epsilon=0.25.
        idf_sum = 0.0
        negative_idfs: list[str] = []
        self.idf: dict[str, float] = {}
        for term, freq in nd.items():
            idf = math.log(corpus_size - freq + 0.5) - math.log(freq + 0.5)
            self.idf[term] = idf
            idf_sum += idf
            if idf < 0:
                negative_idfs.append(term)
        avg_idf = idf_sum / len(self.idf) if self.idf else 0.0
        eps = 0.25 * avg_idf
        for term in negative_idfs:
            self.idf[term] = eps

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


#: Prefix tagging the process-local fallback validity token so it can
#: never compare equal to a store's durable data-version token: a
#: capability transition (a legacy table gaining an epoch, or the
#: reverse) is itself cache invalidation (design decision D1).
_LOCAL_TOKEN_PREFIX = "-".join(("bm25", "local", "v1"))  # noqa: S105 — a tag, not a secret

#: Bounded retry policy for rebuilds whose validity token changes between
#: the pre-fetch and pre-publish reads: an unstable build is discarded and
#: retried at most this many times before the best-effort build is served
#: uncached (spec: retry behaviour MUST be bounded).
_MAX_BUILD_ATTEMPTS = 3

# One-shot warning state (per process): the local-fallback warning fires
# at most once per collection, naming the reduced guarantee.
_warned_fallback_collections: set[str] = set()


def reset_fallback_warning_state() -> set[str]:
    """Clear the local-fallback warning state (test isolation helper)."""
    _warned_fallback_collections.clear()
    return _warned_fallback_collections


def _resolve_validity_token(store: Any, collection_name: str) -> str:
    """Resolve the tagged cache-validity token for one collection.

    Prefers the store's durable data version (``get_data_version``),
    which changes for cross-process mutations, overwrite rebuilds and
    recreations.  Falls back to the process-local generation counter,
    warning once per collection per process that the guarantee is
    reduced to same-process mutations only.

    Both token shapes carry an explicit tag, so a transition between
    the fallback and durable modes compares unequal and invalidates
    the cache even when their numeric members happen to match.

    Args:
        store: Vector store (or test double) owning the collection.
        collection_name: Collection whose validity token is resolved.

    Returns:
        The opaque tagged token for the collection's current state.
    """
    getter = getattr(store, "get_data_version", None)
    if callable(getter):
        durable = getter(collection_name)
        if durable is not None:
            return str(durable)
    generation = store.get_generation(collection_name)
    if collection_name not in _warned_fallback_collections:
        _warned_fallback_collections.add(collection_name)
        logger.warning(
            "BM25 sparse cache: %s exposes no durable data version for this "
            "collection, so the process-local generation counter is used. "
            "Reduced guarantee: only mutations made by this process "
            "invalidate the cache; writes from other processes (for "
            "example the watch daemon) are not visible to sparse "
            "retrieval until this process rebuilds or restarts.",
            type(store).__name__,
        )
    return f"{_LOCAL_TOKEN_PREFIX}:{generation}"


@dataclass
class _CachedBM25:
    validity_token: str
    index: Any
    rows: list[_ChunkRow]


class BM25SparseRetriever:
    """Validity-token-aware BM25 retriever for one collection."""

    _cache: dict[tuple[object, str], _CachedBM25] = {}
    _cache_lock = threading.Lock()

    def __init__(
        self,
        collection_name: str,
        store: Any | None = None,
    ) -> None:
        self.collection_name = collection_name
        self._store = store

    def query(
        self,
        query_text: str,
        top_n: int,
        metadata_filter: dict | None = None,
    ) -> list[tuple[int, str, str, dict]]:
        """Return filtered BM25 matches in rank order.

        Args:
            query_text: Sparse query text.
            top_n: Maximum number of eligible matches.
            metadata_filter: Store-neutral query constraint evaluated before
                truncation so forbidden rows cannot consume the candidate
                budget or re-enter through RRF.
        """
        if top_n <= 0:
            return []
        query_tokens = tokenize_english(query_text)
        if not query_tokens:
            return []

        cached = self._get_or_build_index()
        if not cached.rows:
            return []

        scores = cached.index.get_scores(query_tokens)
        ranked = [
            (idx, float(score))
            for idx, score in enumerate(scores)
            if float(score) > 0.0
            and matches_metadata_filter(cached.rows[idx].metadata, metadata_filter)
        ]
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

    def _validity_token(self) -> str:
        """Resolve the current tagged validity token for the collection."""
        return _resolve_validity_token(self._get_store(), self.collection_name)

    def _cache_key(self) -> tuple[object, str]:
        store = self._get_store()
        identity = getattr(store, "cache_identity", store)
        return identity, self.collection_name

    def _get_or_build_index(self) -> _CachedBM25:
        store = self._get_store()
        cache_key = self._cache_key()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            token = self._validity_token()
            if cached is not None and cached.validity_token == token:
                return cached

            # Slow path: fetch rows, then re-read the token before
            # publishing.  A mutation landing between the two reads —
            # including one made by another process — makes the build
            # unstable, so it is discarded and retried within the
            # bounded policy rather than cached (spec: mutation during
            # a BM25 build is not cached).
            rows: list[_ChunkRow] = []
            for _attempt in range(_MAX_BUILD_ATTEMPTS):
                rows = _read_collection_rows(store, self.collection_name)
                end_token = self._validity_token()
                if end_token == token:
                    tokenised = [tokenize_english(row.text) for row in rows]
                    index = _make_bm25(tokenised)
                    published = _CachedBM25(validity_token=end_token, index=index, rows=rows)
                    self._cache[cache_key] = published
                    return published
                token = end_token

            # Retries exhausted under continuous mutation: serve the
            # last best-effort build WITHOUT publishing it, so the next
            # quiet query rebuilds from a stable token rather than
            # inheriting a build that may mix two dataset incarnations.
            logger.debug(
                "BM25 rebuild for collection '%s' saw the validity token "
                "change on %d consecutive attempts; serving an uncached "
                "build.",
                self.collection_name,
                _MAX_BUILD_ATTEMPTS,
            )
            index = _make_bm25([tokenize_english(row.text) for row in rows])
            return _CachedBM25(validity_token=token, index=index, rows=rows)


def _read_collection_rows(store: Any, collection_name: str) -> list[_ChunkRow]:
    """Read all collection chunks into row objects with bounded paging."""
    count = store.count(collection_name)
    if count == 0:
        return []

    rows: list[_ChunkRow] = []
    for doc_id, text, metadata in store.iter_documents(collection_name):
        rows.append(_ChunkRow(doc_id, text, metadata))
    return rows
