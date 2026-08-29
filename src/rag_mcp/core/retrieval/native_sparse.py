"""Native sparse retrieval backend (store-backed full-text queries).

The retrieval-level execution strategy registered under ``"native"``
in the sparse-backend registry.  Mirrors
:class:`~rag_mcp.core.retrieval.sparse.BM25SparseRetriever` exactly —
one ``query`` returning ``(rank, doc_id, text, metadata)`` tuples —
so the hybrid pipeline dispatches to either registered backend
through the same contract without backend-specific code (task 2.3).

Execution delegates to the vector store's native sparse capability
(:meth:`~rag_mcp.core.vectordb.base.VectorStore.query_native_sparse`)
so LanceDB specifics stay confined to the adapter seam (ADR-034:
this module never imports ``lancedb``).  Failures intentionally
propagate: the fallback to BM25 lives at the pipeline dispatch
boundary (design decision 3), not inside the strategy.
"""

from __future__ import annotations

from typing import Any


class NativeSparseRetriever:
    """Store-native full-text sparse retriever for one collection."""

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
        """Return filtered native sparse matches in rank order.

        Args:
            query_text: Free-text sparse query.
            top_n: Maximum number of matches.
            metadata_filter: Store-neutral query constraint composed
                with the full-text ranking by the engine.

        Raises:
            NotImplementedError: When the selected store cannot issue
                native sparse queries (capability absence).
            Exception: Whatever the store raises on lifecycle or query
                failure — the pipeline's fallback net catches it.
        """
        if top_n <= 0:
            return []
        store = self._get_store()
        rows = store.query_native_sparse(
            self.collection_name,
            query_text,
            top_n,
            where=metadata_filter,
        )
        return [
            (rank, str(row["id"]), row["document"], dict(row["metadata"]))
            for rank, row in enumerate(rows[:top_n], start=1)
        ]

    def _get_store(self):
        if self._store is not None:
            return self._store
        from ..vectordb import get_default_store

        return get_default_store()
