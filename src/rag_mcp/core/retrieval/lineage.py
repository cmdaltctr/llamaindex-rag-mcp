"""Chunk lineage navigation over persisted metadata (the docstore equivalent).

Provides neighbour, span and ordered-set lookup for stored chunks using
only the lineage metadata ingestion already persists — ``source_id``,
``source_version``, ``chunk_id``, ``source_chunk_index`` and
``source_chunk_count`` — read through the store-neutral filtered
row-read contract (:meth:`VectorStore.iter_filtered_documents`).

This module is deliberately not a document store (design decision D2 of
``fix-retrieval-freshness-and-context-assembly-2``): a second store
would have to be kept consistent with the vector store across every
failure path in the replacement pipeline.  Persisted lineage is strictly
more capable here because it can be queried directly through
backend-pushed filters, whereas a relationship can only be walked.

Adjacency is keyed on ``(source_id, source_version)`` — never
``source_id`` alone — so chunks from two versions of one document are
never treated as neighbours.  Rows lacking lineage (for example
experiment precomputed rows) are inert: they are skipped rather than
raised over, and the retrieved row itself stays with the caller.

Reads are bounded by construction: one backend-pushed equality read per
requested index, so the number of rows materialised is bounded by the
requested window and the result count.  The collection is never scanned
and no concrete store adapter is imported here.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from ..vectordb.base import VectorStore

__all__ = ["is_adjacent", "neighbours", "span"]

logger = logging.getLogger(__name__)

# Lineage metadata keys persisted by ingestion and surfaced on retrieval
# result rows.  Duplicated here rather than imported from the ingestion
# layer: ingestion and retrieval share only settings (architecture
# invariant: no cross-imports between the two packages).
SOURCE_ID_KEY = "source_id"
SOURCE_VERSION_KEY = "source_version"
CHUNK_ID_KEY = "chunk_id"
SOURCE_CHUNK_INDEX_KEY = "source_chunk_index"
SOURCE_CHUNK_COUNT_KEY = "source_chunk_count"

# Stores without the filtered row-read capability warn once per process
# rather than once per read.
_UNFILTERED_WARNED: set[str] = set()


def _lineage_get(row: Mapping[str, Any], key: str) -> Any:
    """Return one lineage value from a result row or bare metadata dict.

    Retrieval result rows carry the lineage fields at the top level;
    raw store rows and bare metadata dicts carry them inside their
    ``metadata`` mapping.  Both shapes are accepted so the navigator
    works on whatever the caller already holds.

    Args:
        row: A retrieval result row or a metadata mapping.
        key: The lineage metadata key to read.

    Returns:
        The value, or ``None`` when absent on both levels.
    """
    if key in row:
        return row[key]
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata.get(key)
    return None


def _valid_index(value: Any) -> bool:
    """Return whether *value* is a usable zero-based chunk index."""
    return _is_int(value) and value >= 0


def _valid_count(value: Any) -> bool:
    """Return whether *value* is a usable chunk count."""
    return _is_int(value) and value > 0


def _is_int(value: Any) -> bool:
    """Return whether *value* is an integer and not a boolean in disguise."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_adjacent(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Return whether two stored chunks are adjacent in their source.

    Adjacency means the two rows share ``source_id`` AND
    ``source_version`` and carry ``source_chunk_index`` values that
    differ by exactly one.  Chunks of different sources and chunks of
    different source versions are never adjacent, whatever their
    indices.  No input raises: rows lacking usable lineage are simply
    not adjacent.

    Args:
        a: A retrieval result row or metadata dict.
        b: A retrieval result row or metadata dict.

    Returns:
        True when *a* and *b* are consecutive chunks of one source
        version; False otherwise.
    """
    a_source = _lineage_get(a, SOURCE_ID_KEY)
    if a_source is None or a_source != _lineage_get(b, SOURCE_ID_KEY):
        return False
    a_version = _lineage_get(a, SOURCE_VERSION_KEY)
    if a_version is None or a_version != _lineage_get(b, SOURCE_VERSION_KEY):
        return False
    a_index = _lineage_get(a, SOURCE_CHUNK_INDEX_KEY)
    b_index = _lineage_get(b, SOURCE_CHUNK_INDEX_KEY)
    if not _valid_index(a_index) or not _valid_index(b_index):
        return False
    # Indices live in [0, source_chunk_count); when both rows carry a
    # usable count, rows outside that range have corrupt lineage and are
    # inert rather than adjacent.
    a_count = _lineage_get(a, SOURCE_CHUNK_COUNT_KEY)
    b_count = _lineage_get(b, SOURCE_CHUNK_COUNT_KEY)
    if _valid_count(a_count) and _valid_count(b_count):
        if a_count != b_count:
            return False
        if a_index >= a_count or b_index >= b_count:
            return False
    return abs(a_index - b_index) == 1


def _chunk_row(row_id: str, text: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt one store row into the canonical lineage-navigation row.

    The shape mirrors the retrieval result row's additive lineage
    fields so downstream assembly can treat retrieved and expanded rows
    uniformly.  No score is attached: scoring is a retrieval-policy
    decision that belongs to the caller.

    Args:
        row_id: The store row identifier.
        text: The stored chunk text.
        metadata: The row's persisted metadata.

    Returns:
        A dict with ``id``, ``text``, ``metadata`` and the stable
        lineage fields read from *metadata*.
    """
    meta = dict(metadata)
    return {
        "id": row_id,
        "text": text,
        "metadata": meta,
        SOURCE_ID_KEY: meta.get(SOURCE_ID_KEY),
        SOURCE_VERSION_KEY: meta.get(SOURCE_VERSION_KEY),
        CHUNK_ID_KEY: meta.get(CHUNK_ID_KEY),
        SOURCE_CHUNK_INDEX_KEY: meta.get(SOURCE_CHUNK_INDEX_KEY),
        SOURCE_CHUNK_COUNT_KEY: meta.get(SOURCE_CHUNK_COUNT_KEY),
    }


def _read_chunk_index(
    store: VectorStore,
    collection: str,
    source_id: str,
    source_version: str,
    chunk_index: int,
) -> tuple[str, str, dict] | None:
    """Return the row at one index of one source version, or ``None``.

    Performs one backend-pushed equality read on
    ``(source_id, source_version, source_chunk_index)`` — never a
    collection scan.  During a transient replacement attempt two rows
    can share that triple (identical content re-ingested under a new
    attempt id); the lowest row id wins so the choice stays
    deterministic.

    Args:
        store: The vector store to read through.
        collection: The collection holding the chunks.
        source_id: The stable source identity.
        source_version: The exact source version.
        chunk_index: The zero-based chunk index to read.

    Returns:
        The ``(row_id, text, metadata)`` tuple, or ``None`` when the
        index does not exist or the store cannot serve filtered reads.
    """
    where = {
        SOURCE_ID_KEY: source_id,
        SOURCE_VERSION_KEY: source_version,
        SOURCE_CHUNK_INDEX_KEY: chunk_index,
    }
    try:
        matches = list(store.iter_filtered_documents(collection, where))
    except NotImplementedError as exc:
        store_name = type(store).__name__
        if store_name not in _UNFILTERED_WARNED:
            _UNFILTERED_WARNED.add(store_name)
            logger.warning(
                "%s cannot serve chunk lineage reads (%s); neighbour and "
                "span lookup return nothing for it",
                store_name,
                exc,
            )
        return None
    if not matches:
        return None
    return min(matches, key=lambda row: row[0])


def neighbours(
    rows: Iterable[Mapping[str, Any]],
    store: VectorStore,
    collection: str,
    window: int,
) -> list[dict[str, Any]]:
    """Return the neighbour chunks of a result set in ascending index order.

    For every row carrying usable lineage, the chunks of the same
    ``(source_id, source_version)`` with ``source_chunk_index`` in
    ``[i - window, i + window]`` are fetched — excluding the retrieved
    rows' own indices, clamped to ``[0, source_chunk_count)`` when the
    count is known, and never crossing a source or version boundary.
    Rows without lineage are skipped without raising, and the retrieved
    rows themselves stay with the caller.

    Args:
        rows: Retrieval result rows (or metadata dicts) to expand.
        store: The vector store holding the chunks.
        collection: The collection to read neighbours from.
        window: Neighbours requested per side of each chunk; zero or
            less returns nothing.

    Returns:
        Neighbour rows — ``id``, ``text``, ``metadata`` plus the stable
        lineage fields — deduplicated across the result set, with
        sources in first-appearance order and indices ascending within
        each source.
    """
    if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
        return []
    retrieved: dict[tuple[str, str], set[int]] = {}
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        source_id = _lineage_get(row, SOURCE_ID_KEY)
        source_version = _lineage_get(row, SOURCE_VERSION_KEY)
        index = _lineage_get(row, SOURCE_CHUNK_INDEX_KEY)
        if source_id is None or source_version is None or not _valid_index(index):
            continue  # Inert: rows without lineage never raise.
        key = (source_id, source_version)
        retrieved.setdefault(key, set()).add(index)
        count = _lineage_get(row, SOURCE_CHUNK_COUNT_KEY)
        if key not in counts and _valid_count(count):
            counts[key] = count
    expanded: list[dict[str, Any]] = []
    for (source_id, source_version), indices in retrieved.items():
        count = counts.get((source_id, source_version))
        targets: set[int] = set()
        for index in indices:
            low = max(index - window, 0)
            high = index + window
            if count is not None:
                high = min(high, count - 1)
            targets.update(range(low, high + 1))
        targets -= indices
        for target in sorted(targets):
            match = _read_chunk_index(store, collection, source_id, source_version, target)
            if match is not None:
                expanded.append(_chunk_row(*match))
    return expanded


def span(
    store: VectorStore,
    collection: str,
    source_id: str,
    source_version: str,
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    """Return the contiguous chunk span ``[start, end]`` of one source version.

    The range is clamped to ``[0, source_chunk_count)`` — the count is
    learned from the row at the clamped start — and rows are returned
    in ascending index order.  The full ordered chunk set of a source
    version is therefore ``span(..., 0, count - 1)``.  Absent sources,
    versions or indices yield an empty list rather than an error, and
    no read ever scans the collection.

    Args:
        store: The vector store holding the chunks.
        collection: The collection to read the span from.
        source_id: The stable source identity.
        source_version: The exact source version to reconstruct.
        start: First chunk index requested (clamped to zero).
        end: Last chunk index requested (clamped to the chunk count).

    Returns:
        Span rows — ``id``, ``text``, ``metadata`` plus the stable
        lineage fields — in ascending index order.
    """
    if not source_id or source_version is None:
        return []
    # Negative bounds are clamped, not rejected; only non-integer bounds
    # are unusable.
    if not _is_int(start) or not _is_int(end):
        return []
    low = max(start, 0)
    if end < low:
        return []
    first = _read_chunk_index(store, collection, source_id, source_version, low)
    if first is None:
        return []
    count = first[2].get(SOURCE_CHUNK_COUNT_KEY)
    high = min(end, count - 1) if _valid_count(count) else end
    rows = [_chunk_row(*first)]
    for index in range(low + 1, high + 1):
        match = _read_chunk_index(store, collection, source_id, source_version, index)
        if match is not None:
            rows.append(_chunk_row(*match))
    return rows
