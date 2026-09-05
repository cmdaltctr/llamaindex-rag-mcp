"""Native full-text-search sparse queries for the LanceDB adapter.

Seam module owning the FTS lifecycle and native sparse query
execution (``implement-native-sparse-backend-strategy``, tasks
2.1-2.4) so ``lancedb.py`` stays inside the 500-line ceiling — the
``lance_rows``/``lance_filter``/``lance_meta`` seam precedent.

Lifecycle contract (feasibility-verified on lancedb 0.37.1 /
pylance 10.0.0; see the change's ``feasibility-notes.md`` and the
raw-API pins in ``tests/test_lancedb_native_fts_contract.py``):

- **Creation** is additive and explicitly triggered on first native
  use: ``create_index("text", config=FTS())`` indexes existing rows
  synchronously and leaves the collection queryable throughout.
  Collections without an index keep working through every other
  operation; only the native sparse query creates one.
- **Staleness** is a durable property observed through
  ``list_indices()`` statistics: rows written after the last index
  refresh appear as ``num_unindexed_rows > 0`` regardless of which
  process wrote them.  The process-local generation counter is NOT
  consulted here — it invalidates the in-memory BM25 cache only
  (PR #63 semantics, preserved untouched).
- **Refresh** runs before serving a native query whenever the
  durable statistics show lag (``table.optimize()`` folds unindexed
  rows into the index and compacts delete tombstones).  Engine
  queries are fresh-by-construction regardless — unindexed rows are
  scanned at query time and deletions are tombstoned — so a served
  native ranking never misses post-index writes; the refresh keeps
  the durable index tracking and the diagnostics honest.  Refresh
  failures raise here so the retrieval layer can warn and fall back
  to BM25 (the lifecycle failure path).
- **Coverage** (indexed versus unindexed rows) is reported
  separately from freshness via
  :meth:`LanceFTSMixin.native_sparse_coverage`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from lancedb.index import FTS

from .lance_filter import translate_where
from .lance_meta import metadata_field_names
from .lance_paged import strip_internal_metadata
from .score import NATIVE_SPARSE_SCORE_KIND

logger = logging.getLogger(__name__)

__all__ = [
    "LanceFTSMixin",
    "ensure_fts_index",
    "fts_index_stats",
    "probe_native_fts",
    "refresh_fts_index",
]


def fts_index_stats(table: Any) -> tuple[int, int] | None:
    """Return ``(num_indexed_rows, num_unindexed_rows)`` for the FTS index.

    ``None`` means the table has no FTS index on the ``text`` column
    (the pre-creation lifecycle state — distinct from any coverage
    value).
    """
    for index in table.list_indices():
        if index.index_type == "FTS" and "text" in index.columns:
            return int(index.num_indexed_rows), int(index.num_unindexed_rows)
    return None


def ensure_fts_index(table: Any) -> None:
    """Create the FTS index on ``text`` when absent (additive, explicit).

    Existing rows are indexed synchronously by the engine; the default
    ``replace=True`` makes a concurrent creation race safe (the later
    call replaces the earlier index with an equivalent one).

    Raises:
        Exception: Whatever the engine raises on creation failure —
            the retrieval layer's fallback path catches it, warns, and
            serves BM25 results instead.
    """
    if fts_index_stats(table) is not None:
        return
    logger.debug("Creating additive FTS index on text column of %r", table.name)
    table.create_index("text", config=FTS())


def refresh_fts_index(table: Any) -> None:
    """Fold unindexed rows and compact tombstones into the FTS index.

    This is the durable refresh operation: afterwards
    ``num_unindexed_rows`` is zero and deletion tombstones are
    compacted.  Raises whatever the engine raises on failure so the
    retrieval layer can fall back to BM25.
    """
    table.optimize()


def probe_native_fts() -> bool:
    """Real native-FTS capability probe for the selected runtime.

    Verifies the installed ``lancedb`` exposes the pinned FTS surface
    (the ``FTS`` index configuration and the ``query_type`` search
    parameter) rather than trusting the dependency version alone.
    Used by the composition root's ``auto`` resolution (task 3.2);
    imports lazily so a lancedb-free process reports ``False``
    instead of crashing.
    """
    try:
        import inspect

        import lancedb.table
        from lancedb.index import FTS  # noqa: F401  (surface presence)

        return "query_type" in inspect.signature(lancedb.table.Table.search).parameters
    except Exception:  # noqa: BLE001 - any import/signature drift means unavailable
        return False


class LanceFTSMixin:
    """Native sparse (FTS) capability for :class:`LanceVectorStore`.

    Supplies the :meth:`query_native_sparse` capability method and
    the coverage diagnostics required by the ABC contract (task 1.2
    shape); all execution stays inside the adapter seam so the
    retrieval pipeline never imports ``lancedb`` (ADR-034).
    """

    # Supplied by the concrete store.
    _open_table: Callable[[str], Any]
    _guard_query_identity: Callable[[str], None]

    def query_native_sparse(
        self,
        collection_name: str,
        query: str,
        n_results: int,
        where: dict | None = None,
    ) -> list[dict]:
        """Return canonical higher-is-better native FTS result rows.

        Guard order mirrors :meth:`~LanceVectorStore.query_dense`: an
        absent collection reads as empty, the embedding-identity guard
        runs before any lifecycle work (a store whose identity
        conflicts with the collection must not query it OR mutate it
        by creating/refreshing an FTS index), and lifecycle
        maintenance happens only when the table exists.

        Args:
            collection_name: Collection (table) to query.
            query: Free-text sparse query.
            n_results: Maximum rows to return.
            where: Optional ChromaDB-style metadata filter, composed
                with the FTS ranking by the engine.

        Returns:
            Result rows with canonical ``score``/``score_kind``
            (``native_fts_v1`` — the engine's raw higher-is-better
            score, untransformed) plus the store-neutral content
            fields (``id``, ``document``, ``metadata``).

        Raises:
            Exception: On identity conflict, index-creation, refresh,
                or query failure — the retrieval layer catches, warns,
                and falls back to BM25 (spec: "Native fails safely at
                query time").
        """
        table = self._open_table(collection_name)
        if table is None:
            return []
        self._guard_query_identity(collection_name)
        ensure_fts_index(table)
        stats = fts_index_stats(table)
        if stats is not None and stats[1] > 0:
            # Durable staleness (rows written since the last refresh,
            # by any process). Results are engine-fresh regardless;
            # this refresh keeps the durable index tracking so the
            # stale state is transient, observed, and reportable.
            logger.debug(
                "Refreshing stale FTS index on %r (%d unindexed rows)",
                collection_name,
                stats[1],
            )
            refresh_fts_index(table)
        builder = table.search(query, query_type="fts").limit(n_results)
        if where:
            builder = builder.where(
                translate_where(
                    where,
                    metadata_column="metadata",
                    known_fields=metadata_field_names(table),
                )
            )
        rows = builder.to_list()
        results: list[dict] = []
        for row in rows:
            text = row.get("text")
            results.append(
                {
                    "id": str(row.get("id")),
                    "document": text if text is not None else "",
                    "metadata": strip_internal_metadata(row.get("metadata")),
                    "score": float(row["_score"]),
                    "score_kind": NATIVE_SPARSE_SCORE_KIND,
                }
            )
        return results

    def native_sparse_coverage(self, collection_name: str) -> dict | None:
        """Return FTS coverage statistics, or ``None`` when undefined.

        ``None`` means no FTS index exists (or the collection is
        absent) — the pre-creation lifecycle state, distinct from any
        coverage value.  Otherwise the dict reports ``indexed`` /
        ``unindexed`` / ``total`` row counts.  ``indexed`` is clamped
        to the live row count because uncompacted tombstones can
        leave the index's own row count above the table's.
        """
        table = self._open_table(collection_name)
        if table is None:
            return None
        stats = fts_index_stats(table)
        if stats is None:
            return None
        indexed, _unindexed = stats
        total = int(table.count_rows())
        indexed = min(indexed, total)
        return {"indexed": indexed, "unindexed": total - indexed, "total": total}
