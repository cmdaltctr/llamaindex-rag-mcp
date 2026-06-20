"""Semantic search over the ChromaDB-backed vector index."""

from __future__ import annotations

import functools
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import chromadb
from llama_index.core import Settings

from .config import (
    CHROMA_PERSIST_DIR,
    HYBRID_ENABLED,
    HYBRID_RRF_K,
    SIMILARITY_THRESHOLD,
    TOP_K,
)
from .chroma_utils import iter_collection_metadatas
from .reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)
_warned_collections: set[str] = set()
_warned_native_fallback_collections: set[str] = set()


# ── Query embedding cache ──────────────────────────────────────────────
# Process-local LRU cache so repeated identical queries (common in
# agentic loops) do not re-hit Ollama for the embedding step.  The cache
# is keyed by ``(query, embed_model_name)`` so a model swap (e.g. via
# ``Settings.embed_model = ...`` in tests) automatically invalidates
# entries from the previous model.  See ADR-016 / OpenSpec change
# ``rag-retrieval-quality-improvements`` Decision 4.
_QUERY_EMBED_CACHE_MAXSIZE = 128


@functools.lru_cache(maxsize=_QUERY_EMBED_CACHE_MAXSIZE)
def _cached_query_embedding(
    query: str,
    embed_model_name: str,
) -> tuple[float, ...]:
    """Return the query embedding, cached by ``(query, embed_model_name)``.

    The result is a tuple so it is hashable and immutable; callers
    convert to a list before passing to ChromaDB.

    Args:
        query: The user's search query string.
        embed_model_name: The current ``Settings.embed_model.model_name``,
            included in the key so that swapping models invalidates the
            cache automatically.

    Returns:
        The embedding vector as a tuple of floats.
    """
    vec = Settings.embed_model.get_query_embedding(query)
    return tuple(vec)


def _embed_query(query: str) -> list[float]:
    """Embed a query, using the LRU cache when available.

    Falls back gracefully to a direct embed call if the configured
    embed model does not expose ``model_name`` (rare; e.g. some test
    mocks).  Returns a fresh list so callers may safely mutate it.

    Args:
        query: The user's search query string.

    Returns:
        Embedding vector as a list of floats.
    """
    embed_model = Settings.embed_model
    model_name = getattr(embed_model, "model_name", None)
    if model_name is None:
        # Uncacheable model — bypass the cache rather than risk
        # collisions across instances.
        return list(embed_model.get_query_embedding(query))
    return list(_cached_query_embedding(query, model_name))


def _resolve_fetch_k(
    top_k: int,
    rerank: bool,
    collection_count: int,
) -> int:
    """Compute the candidate pool size, applying the reranker fetch rules.

    When ``rerank`` is False, ``fetch_k`` equals ``top_k`` (the original
    behaviour).  When ``rerank`` is True, the pool follows the
    "Wide Net, Tight Filter" pattern:

        fetch_k = max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)

    The result is clamped to ``min(fetch_k, collection_count)`` so an
    unbounded ``top_k`` on a small collection does not produce a fetch
    larger than the collection itself.  See ADR-016 / OpenSpec change
    ``rag-retrieval-quality-improvements`` Decision 2.

    Args:
        top_k: Final number of results requested by the caller.
        rerank: Whether the cross-encoder reranker is active.
        collection_count: ``collection.count()`` for the target
            ChromaDB collection.

    Returns:
        The effective candidate pool size to fetch from the vector store.
    """
    if rerank:
        # Re-read env-derived values from config at call time so tests
        # that monkeypatch ``rag_mcp.config.RERANK_*`` are honoured.
        from . import config as _config

        fetch_k = max(
            _config.RERANK_MAX_FETCH,
            top_k * _config.RERANK_FETCH_MULTIPLIER,
        )
    else:
        fetch_k = top_k

    if collection_count > 0:
        fetch_k = min(fetch_k, collection_count)
    # Always fetch at least 1 candidate so an empty result set is the
    # only zero-result scenario.
    return max(fetch_k, 1)


def _effective_threshold(
    similarity_threshold: float,
    rerank: bool,
) -> float:
    """Compute the effective score threshold, accounting for reranker scores.

    Cross-encoder sigmoid scores occupy a different range than cosine
    similarity.  Valid reranker results can score as low as 0.01–0.05,
    while cosine similarity rarely goes below 0.3 for relevant matches.

    When reranking is active, the threshold is scaled down by 30× so
    that a ``similarity_threshold=0.3`` becomes 0.01 — roughly equivalent
    to "keep anything the reranker considers a match, filter clear noise".

    The 30× factor was calibrated from experiment data:
    - Strong reranker matches: 0.79–1.0
    - Weak but correct matches: 0.015 (Colosseum query)
    - Clear noise: < 0.003

    Args:
        similarity_threshold: User-supplied threshold (0.0 = no filtering).
        rerank: Whether the cross-encoder reranker is active.

    Returns:
        The effective threshold to apply to scores.
    """
    if similarity_threshold <= 0.0:
        return 0.0
    return similarity_threshold / 30 if rerank else similarity_threshold


def _distance_to_score(distance: float | None) -> float:
    """Convert a ChromaDB L2 distance to a 0–1 similarity score.

    The single canonical conversion shared by every non-reranked
    retrieval path: ``score = 1.0 / (1.0 + distance)``.  Closer distance
    yields higher score.  See ADR-015 / OpenSpec change
    ``rag-reliability-correctness-fixes`` Decision 3.

    Args:
        distance: Raw L2 distance from ChromaDB (``None`` is treated as 0).

    Returns:
        Float in ``(0, 1]``.
    """
    if distance is None:
        return 0.0
    return 1.0 / (1.0 + distance)


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    k: int = HYBRID_RRF_K,
) -> dict[str, float]:
    """Fuse ranked doc-id lists with Reciprocal Rank Fusion."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return fused


def rrf_with_metadata(
    dense_ranked: list[dict],
    sparse_ranked: list[dict],
    k: int = HYBRID_RRF_K,
) -> list[dict]:
    """Return sorted fused result dicts with score and rank diagnostics."""
    dense_ids = [str(row["id"]) for row in dense_ranked]
    sparse_ids = [str(row["id"]) for row in sparse_ranked]
    scores = reciprocal_rank_fusion([dense_ids, sparse_ids], k=k)

    by_id: dict[str, dict] = {}
    dense_rank: dict[str, int] = {}
    sparse_rank: dict[str, int] = {}

    for rank, row in enumerate(dense_ranked, start=1):
        doc_id = str(row["id"])
        dense_rank[doc_id] = rank
        by_id.setdefault(doc_id, dict(row))
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
        row["dense_rank"] = dense_rank.get(doc_id)
        row["sparse_rank"] = sparse_rank.get(doc_id)
        fused_rows.append(row)

    fused_rows.sort(key=lambda row: row["fused_score"], reverse=True)
    for rank, row in enumerate(fused_rows, start=1):
        row["fused_rank"] = rank
    return fused_rows


def _result_source(meta: dict) -> str:
    return meta.get("file_path") or meta.get("file_name") or "unknown"


def _dense_query_rows(
    collection: Any,
    query: str,
    fetch_k: int,
    metadata_filter: dict | None = None,
) -> list[dict]:
    query_kwargs: dict = {
        "query_embeddings": [_embed_query(query)],
        "n_results": fetch_k,
        "include": ["metadatas", "documents", "distances"],
    }
    if metadata_filter:
        query_kwargs["where"] = metadata_filter

    raw = collection.query(**query_kwargs)
    ids = raw.get("ids", [[]])[0]
    documents = raw.get("documents", [[]])[0]
    metadatas = raw.get("metadatas", [[]])[0]
    distances = raw.get("distances", [[]])[0]

    rows: list[dict] = []
    for i, chunk_id in enumerate(ids):
        meta = metadatas[i] if i < len(metadatas) and isinstance(metadatas[i], dict) else {}
        text = documents[i] if i < len(documents) else ""
        distance = distances[i] if i < len(distances) else None
        rows.append({
            "id": str(chunk_id),
            "score": _distance_to_score(distance),
            "source": _result_source(meta),
            "page_label": meta.get("page_label"),
            "text": text,
            "metadata": dict(meta),
            "reranked": False,
        })
    return rows


def _selected_sparse_backend() -> str:
    from . import config as _config

    return getattr(
        _config,
        "RESOLVED_HYBRID_SPARSE_BACKEND",
        getattr(_config, "HYBRID_SPARSE_BACKEND", "bm25"),
    )


def _sparse_bm25_query(
    collection_name: str,
    collection: Any,
    query: str,
    fetch_k: int,
) -> list[dict]:
    from .sparse_retriever import BM25SparseRetriever

    rows = BM25SparseRetriever(collection_name, collection=collection).query(query, fetch_k)
    return [
        {
            "id": doc_id,
            "source": _result_source(metadata),
            "page_label": metadata.get("page_label"),
            "text": text,
            "metadata": dict(metadata),
            "reranked": False,
        }
        for _rank, doc_id, text, metadata in rows
    ]


def _emit_mixed_coverage_warning(collection_name: str, collection: Any) -> None:
    if collection_name in _warned_collections:
        return
    total = 0
    covered = 0
    try:
        for meta in iter_collection_metadatas(collection):
            total += 1
            if isinstance(meta, dict) and meta.get("has_sparse_vector"):
                covered += 1
    except Exception:
        return
    if 0 < covered < total:
        _warned_collections.add(collection_name)
        logger.warning(
            "Hybrid native sparse retrieval on collection '%s' has mixed "
            "coverage: %d/%d chunks have sparse vectors. Re-ingest the "
            "collection for full hybrid coverage.",
            collection_name,
            covered,
            total,
        )


def _native_sparse_query(
    collection_name: str,
    collection: Any,
    query: str,
    fetch_k: int,
) -> list[dict]:
    """Return sparse results for native mode, falling back safely in v1."""
    if collection_name not in _warned_native_fallback_collections:
        _warned_native_fallback_collections.add(collection_name)
        logger.warning(
            "Native ChromaDB sparse retrieval is selected for collection '%s', "
            "but this runtime cannot issue a native sparse query. Falling "
            "back to the BM25 sparse retriever so hybrid retrieval does not "
            "silently degrade to dense-only results.",
            collection_name,
        )
    return _sparse_bm25_query(collection_name, collection, query, fetch_k)


def _hybrid_query_rows(
    collection: Any,
    collection_name: str,
    query: str,
    fetch_k: int,
    metadata_filter: dict | None = None,
) -> list[dict]:
    backend = _selected_sparse_backend()
    with ThreadPoolExecutor(max_workers=2) as executor:
        dense_future = executor.submit(
            _dense_query_rows, collection, query, fetch_k, metadata_filter,
        )
        if backend == "native":
            _emit_mixed_coverage_warning(collection_name, collection)
            sparse_future = executor.submit(
                _native_sparse_query, collection_name, collection, query, fetch_k,
            )
        else:
            sparse_future = executor.submit(
                _sparse_bm25_query, collection_name, collection, query, fetch_k,
            )
        dense_rows = dense_future.result()
        sparse_rows = sparse_future.result()

    return rrf_with_metadata(dense_rows, sparse_rows, k=HYBRID_RRF_K)[:fetch_k]


def _strip_internal_result_fields(result: dict) -> dict:
    """Remove retrieval diagnostics that are not public API by default."""
    public = dict(result)
    for key in ("id", "fused_score", "dense_rank", "sparse_rank", "fused_rank"):
        public.pop(key, None)
    return public


# ── Technical query classifier ──────────────────────────────────────────────
# Deterministic identifier-heavy rules from Experiment 9a/10: backticks,
# slash paths, dotted paths, camelCase, snake_case, all-caps constants,
# exception/error tokens, version strings, and explicit package/API names.


def _classify_query_technical(query: str) -> float:
    """Estimate the technical fraction of a query (0.0–1.0).

    Uses deterministic identifier-heavy rules from Experiment 9a/10:
    - Backticks: `identifier`
    - Slash paths: /path/to/file
    - Dotted paths: module.class.method
    - camelCase identifiers
    - snake_case identifiers
    - ALL_CAPS constants
    - Exception/Error tokens
    - Version strings: v1.2.3, 1.0.0
    - Package/API names

    Args:
        query: The search query string.

    Returns:
        Float in [0.0, 1.0] representing the fraction of tokens that are
        identifier-heavy technical content.
    """
    import re

    if not query.strip():
        return 0.0

    tokens = query.split()
    if not tokens:
        return 0.0

    technical_count = 0
    for token in tokens:
        # Backtick-quoted identifiers
        if "`" in token:
            technical_count += 1
            continue
        # Slash paths (Unix-style)
        if "/" in token and len(token) > 1:
            technical_count += 1
            continue
        # Dotted paths (Python-style: module.class.method)
        if "." in token and re.search(r"[a-zA-Z_]\.[a-zA-Z_]", token):
            technical_count += 1
            continue
        # camelCase (lowercase followed by uppercase)
        if re.search(r"[a-z][A-Z]", token):
            technical_count += 1
            continue
        # snake_case (lowercase with underscores)
        if re.search(r"[a-z]_[a-z]", token):
            technical_count += 1
            continue
        # ALL_CAPS constants (at least 2 uppercase letters with underscores)
        if re.search(r"[A-Z]{2,}", token) and "_" in token:
            technical_count += 1
            continue
        # Exception/Error tokens
        if re.search(r"(Exception|Error|err|exc)", token, re.IGNORECASE):
            technical_count += 1
            continue
        # Version strings (v1.2.3 or 1.0.0)
        if re.search(r"v?\d+\.\d+(\.\d+)?", token):
            technical_count += 1
            continue
        # Explicit package/API/tooling terms and HTTP-ish API tokens.
        if token.lower().strip(".,:;()[]{}") in {
            "api", "sdk", "cli", "package", "module", "import",
            "endpoint", "http", "json", "yaml", "pip", "npm",
        }:
            technical_count += 1
            continue

    return technical_count / len(tokens)


def _resolve_rerank_policy(
    rerank: bool | None,
    query: str,
    technical_fraction: float | None = None,
) -> tuple[bool, str]:
    """Resolve effective rerank behaviour from explicit intent and policy.

    Implements tri-state rerank logic:
    - ``rerank=True``: force reranking (explicit opt-in)
    - ``rerank=False``: force no reranking (explicit opt-out)
    - ``rerank=None``: apply config/policy defaults

    Policy resolution for omitted rerank:
    1. If ``RERANK_ENABLED=True``, rerank by default.
    2. If ``RERANK_ENABLED=False`` and ``RERANK_ENABLED_FOR_SEMANTIC=False``,
       do not rerank.
    3. If ``RERANK_ENABLED=False`` and ``RERANK_ENABLED_FOR_SEMANTIC=True``:
       - Classify the query as technical or semantic.
       - If technical fraction >= ``HARD_TECHNICAL_THRESHOLD``, do not rerank.
       - Otherwise, enable reranking (semantic workload override).

    Args:
        rerank: Explicit rerank value (True/False) or None for policy.
        query: The search query (used for technical classification).
        technical_fraction: Optional pre-computed technical fraction. If
            None, the query is classified on demand.

    Returns:
        Tuple of ``(effective_rerank, reason)`` where ``effective_rerank``
        is the resolved boolean and ``reason`` is a diagnostic string.
    """
    # Re-read config at call time so tests that monkeypatch are honoured.
    from . import config as _config

    # Explicit override: True forces reranking.
    if rerank is True:
        return (True, "explicit rerank=True override")

    # Explicit override: False disables reranking.
    if rerank is False:
        return (False, "explicit rerank=False override")

    # Omitted/None: apply policy.
    # Step 1: Check global default.
    if _config.RERANK_ENABLED:
        return (True, "global default RERANK_ENABLED=true")

    # Step 2: Global is off. Check semantic policy.
    if not _config.RERANK_ENABLED_FOR_SEMANTIC:
        return (False, "disabled by default (RERANK_ENABLED_FOR_SEMANTIC=false)")

    # Step 3: Semantic policy is enabled. Classify the query.
    if technical_fraction is None:
        technical_fraction = _classify_query_technical(query)

    threshold = _config.HARD_TECHNICAL_THRESHOLD
    if technical_fraction >= threshold:
        return (
            False,
            f"disabled by technical policy (fraction={technical_fraction:.2f} "
            f">= threshold={threshold})",
        )

    # Below threshold: semantic workload override.
    return (
        True,
        f"enabled by semantic policy (fraction={technical_fraction:.2f} "
        f"< threshold={threshold})",
    )


def search(
    query: str,
    top_k: int = TOP_K,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    rerank: bool | None = None,
    hybrid: bool = HYBRID_ENABLED,
    collection_name: str = "documents",
    metadata_filter: dict | None = None,
    include_diagnostics: bool = False,
    technical_fraction: float | None = None,
) -> list[dict]:
    """Run a semantic similarity search over every indexed document.

    Args:
        query: Free-text search query.
        top_k: Maximum number of chunks to return (default from env or 5).
        similarity_threshold: Minimum score to include a result
            (0.0 = no filtering, default from env).  When ``rerank``
            is True the threshold is scaled down by 30× because
            cross-encoder sigmoid scores occupy a lower range than
            cosine similarity.  For example, 0.3 becomes 0.01.
        rerank: Tri-state rerank control:
            - ``True``: force reranking (explicit opt-in)
            - ``False``: force no reranking (explicit opt-out)
            - ``None``: apply policy resolver (default)
            The policy resolver checks ``RERANK_ENABLED``, then
            ``RERANK_ENABLED_FOR_SEMANTIC`` and ``HARD_TECHNICAL_THRESHOLD``
            to decide whether to enable reranking based on query type.
        hybrid: If True, fuse dense vector results with sparse BM25/native
            sparse rankings via Reciprocal Rank Fusion before reranking.
        collection_name: Name of the ChromaDB collection to search
            (default ``"documents"`` for backward compatibility).
        metadata_filter: Optional ChromaDB ``where`` clause to filter
            results by metadata fields (e.g. ``{"category": "AI"}``).
            When provided, the filter is applied server-side via
            ChromaDB's native ``where`` parameter — only matching
            chunks are returned from the vector store.
        include_diagnostics: If True, preserve hybrid rank diagnostic
            fields (``id``, ``fused_score``, ``dense_rank``, ``sparse_rank``,
            ``fused_rank``) and policy resolution reason for experiments.
            Public MCP/CLI callers leave this False so result shape stays stable.
        technical_fraction: Optional workload-level identifier-heavy fraction
            (0.0–1.0). When provided, it overrides the single-query classifier
            for policy resolution.

    Returns:
        A list of dicts sorted by descending relevance score, each with:
            score      – float (0–1, vector similarity or reranker score)
            source     – source file path
            page_label – page number (or None)
            text       – the chunk text
            reranked   – bool (True if cross-encoder re-scored the result)

        When ``include_diagnostics=True``, each result also includes:
            rerank_reason – string explaining the policy decision

    Raises:
        ValueError: If ``metadata_filter`` is rejected by ChromaDB
            (unsupported operator, type mismatch, etc.).  Other
            ChromaDB-side failures propagate as their original
            exception types so the MCP layer can classify them.
    """
    # Resolve effective rerank behaviour from policy.
    effective_rerank, rerank_reason = _resolve_rerank_policy(
        rerank, query, technical_fraction=technical_fraction,
    )

    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    try:
        collection = db.get_collection(collection_name)
    except Exception:
        return []

    if collection.count() == 0:
        return []

    # Fetch more candidates when reranking so the cross-encoder
    # has a meaningful pool to re-score.  See ADR-016 Decision 2.
    fetch_k = _resolve_fetch_k(top_k, effective_rerank, collection.count())

    if hybrid:
        results = _hybrid_query_rows(
            collection, collection_name, query, fetch_k, metadata_filter,
        )
    else:
        results = _dense_query_rows(
            collection, query, fetch_k, metadata_filter,
        )

    # Optional: re-score with cross-encoder reranker.
    if effective_rerank and results:
        reranker = CrossEncoderReranker()
        results = reranker.rerank(query, results, top_k=top_k)
        # Propagate the reranked flag from the internal _reranked key.
        for r in results:
            r["reranked"] = r.pop("_reranked", False)

    # Filter by similarity threshold (applies after reranking).
    #
    # Reranker scores are sigmoid-normalised and occupy a different range
    # than cosine similarity.  A cosine threshold of 0.3 is a weak match,
    # but the reranker may assign a valid result only 0.015 (sigmoid).
    # Scale the threshold down by 30× when reranking to avoid over-filtering.
    effective_threshold = _effective_threshold(similarity_threshold, effective_rerank)
    if effective_threshold > 0.0:
        results = [
            r for r in results if r["score"] >= effective_threshold
        ]

    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[:top_k]

    # Attach policy diagnostics when requested.
    if include_diagnostics:
        for r in results:
            r["rerank_reason"] = rerank_reason

    if not include_diagnostics:
        results = [_strip_internal_result_fields(r) for r in results]
    return results


def list_collections() -> list[dict]:
    """List all ChromaDB collections with document and chunk counts.

    Returns:
        A list of dicts, each with:
        - ``name`` — collection name
        - ``document_count`` — approximate number of unique source files
        - ``chunk_count`` — total number of chunks in the collection
    """
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    collections: list[dict] = []
    for coll in db.list_collections():
        try:
            chunk_count = coll.count()
            # Estimate unique documents by counting distinct file_path/file_name
            # values in metadata.
            doc_sources: set[str] = set()
            if chunk_count > 0:
                for meta in iter_collection_metadatas(coll):
                    if meta is None:
                        continue
                    source = (
                        meta.get("file_path")
                        or meta.get("file_name")
                        or "unknown"
                    )
                    doc_sources.add(source)

            collections.append({
                "name": coll.name,
                "document_count": len(doc_sources),
                "chunk_count": chunk_count,
            })
        except Exception:
            # Skip collections that can't be accessed
            continue

    return sorted(collections, key=lambda c: c["name"])
