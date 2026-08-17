"""Paged and bulk collection reads for the LanceDB vector store.

Mirrors :mod:`.paged` (the ChromaDB equivalent) over LanceDB's scanner:
bounded, snapshot-consistent batches for the iterators, one full scan
for :meth:`fetch_all`. The BM25 sparse retriever builds its index
through ``iter_documents`` and never touches this module directly.

The concrete store supplies ``_open_table(name)`` returning the raw
LanceDB table handle or ``None`` when absent, and resolves the default
page size through ``_default_page_size()`` (the shared
``CHROMA_SCAN_PAGE_SIZE`` setting).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

__all__ = ["INTERNAL_METADATA_KEYS", "LancePagedReadMixin", "strip_internal_metadata"]

logger = logging.getLogger(__name__)

# The LlamaIndex adapter writes user metadata into an Arrow struct
# alongside these node-internal fields.  Reads surface only the user's
# keys, matching what the ChromaDB adapter stores.  The store's
# schema-evolution path also uses this set: a later adapter write into
# an upsert-created table needs these fields present in the struct.
INTERNAL_METADATA_KEYS = frozenset(
    {
        "_node_content",
        "_node_type",
        "document_id",
        "doc_id",
        "ref_doc_id",
    }
)


def strip_internal_metadata(metadata: dict | None) -> dict:
    """Drop adapter-internal keys from a metadata struct row.

    Args:
        metadata: The raw ``metadata`` struct value of one row (or
            ``None``).

    Returns:
        A plain dict holding only the user's metadata keys.
    """
    if not metadata:
        return {}
    return {
        key: value
        for key, value in metadata.items()
        if key not in INTERNAL_METADATA_KEYS and not key.startswith("_node")
    }


class LancePagedReadMixin:
    """Bounded-page and full-collection reads over LanceDB tables.

    The concrete store supplies ``_open_table(name)`` and
    ``_default_page_size()``; this module owns the pagination loop and
    the row shapes the ``VectorStore`` ABC docstrings specify.
    """

    # Supplied by the concrete store.
    _open_table: Callable[[str], Any]
    _default_page_size: Callable[[], int]

    def _resolve_page_size(self, page_size: int | None) -> int:
        """Resolve the effective page size, validating it is positive."""
        if page_size is None:
            page_size = self._default_page_size()
        if page_size <= 0:
            raise ValueError("CHROMA_SCAN_PAGE_SIZE must be a positive integer")
        return page_size

    def _iter_rows(
        self,
        collection_name: str,
        columns: list[str],
        page_size: int,
    ) -> Iterator[dict]:
        """Yield the table's rows of the given columns in bounded batches.

        One dataset scanner backs every batch: table handles pin a
        version, so paging through a single scanner cannot duplicate
        or skip rows when a write lands mid-iteration (offset paging
        through a fresh handle per page could, since each handle sees
        the latest version).

        Args:
            collection_name: Table to scan.
            columns: Columns to project.
            page_size: Batch row bound (the memory bound).

        Yields:
            The table's rows as dicts; yields nothing when the table
            is absent or empty.
        """
        table = self._open_table(collection_name)
        if table is None:
            return
        scanner = table.to_lance().scanner(columns=columns, batch_size=page_size)
        for batch in scanner.to_batches():
            yield from batch.to_pylist()

    def iter_metadatas(
        self,
        collection_name: str,
        page_size: int | None = None,
    ) -> Iterator[dict | None]:
        """Yield per-chunk user metadata in bounded, consistent batches."""
        effective_page_size = self._resolve_page_size(page_size)
        for row in self._iter_rows(collection_name, ["metadata"], effective_page_size):
            yield strip_internal_metadata(row.get("metadata"))

    def iter_documents(
        self,
        collection_name: str,
        page_size: int | None = None,
    ) -> Iterator[tuple[str, str, dict]]:
        """Yield ``(id, text, metadata)`` tuples in bounded, consistent batches.

        The BM25 sparse retriever builds its in-memory index from these
        tuples; the shape matches the ChromaDB implementation exactly.
        """
        effective_page_size = self._resolve_page_size(page_size)
        columns = ["id", "text", "metadata"]
        for row in self._iter_rows(collection_name, columns, effective_page_size):
            text = row.get("text")
            yield (
                str(row.get("id")),
                str(text) if text is not None else "",
                strip_internal_metadata(row.get("metadata")),
            )

    def fetch_all(
        self,
        collection_name: str,
        include: list[str],
    ) -> dict[str, list] | None:
        """Return every chunk's requested fields in one store-neutral payload.

        ``None`` when the collection does not exist or is empty, so
        callers (the document-similarity graph) degrade gracefully.
        """
        try:
            table = self._open_table(collection_name)
        except Exception as exc:
            logger.warning("Could not open table %r for bulk read: %s", collection_name, exc)
            return None
        if table is None:
            return None
        try:
            if table.count_rows() == 0:
                logger.debug("Table %r is empty", collection_name)
                return None
            arrow = table.to_arrow()
        except Exception as exc:
            logger.warning("Bulk read of table %r failed: %s", collection_name, exc)
            return None
        payload: dict[str, list] = {"ids": arrow.column("id").to_pylist()}
        if "metadatas" in include:
            payload["metadatas"] = [
                strip_internal_metadata(row) for row in arrow.column("metadata").to_pylist()
            ]
        if "documents" in include:
            payload["documents"] = arrow.column("text").to_pylist()
        if "embeddings" in include:
            payload["embeddings"] = arrow.column("vector").to_pylist()
        return payload
