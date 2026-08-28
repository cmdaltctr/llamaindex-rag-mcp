"""Paged reads and stable-ID deletion for the LanceDB vector store.

Mirrors :mod:`.paged` over LanceDB's scanner: bounded, snapshot-consistent
batches for iterators and one full scan for :meth:`fetch_all`. The concrete
store supplies ``_open_table`` and the shared default page size.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

from .lance_filter import translate_where

__all__ = ["INTERNAL_METADATA_KEYS", "LancePagedReadMixin", "strip_internal_metadata"]

logger = logging.getLogger(__name__)

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
    """Drop LlamaIndex adapter-internal keys from one metadata struct row."""
    if not metadata:
        return {}
    return {
        key: value
        for key, value in metadata.items()
        if key not in INTERNAL_METADATA_KEYS and not key.startswith("_node")
    }


class LancePagedReadMixin:
    """Bounded-page reads plus stable-ID deletion over LanceDB tables."""

    # Supplied by the concrete store.
    _open_table: Callable[[str], Any]
    _default_page_size: Callable[[], int]
    bump_generation: Callable[[str], None]

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
        """Yield projected rows in bounded, snapshot-consistent batches."""
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
        """Yield per-chunk user metadata in bounded batches."""
        effective_page_size = self._resolve_page_size(page_size)
        for row in self._iter_rows(collection_name, ["metadata"], effective_page_size):
            yield strip_internal_metadata(row.get("metadata"))

    def iter_documents(
        self,
        collection_name: str,
        page_size: int | None = None,
    ) -> Iterator[tuple[str, str, dict]]:
        """Yield ``(id, text, metadata)`` tuples in bounded batches."""
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
        """Return every requested field in one store-neutral payload."""
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

    def delete_ids(self, collection_name: str, ids: list[str]) -> None:
        """Delete stable row IDs and advance generation exactly once.

        Values are serialized by the existing LanceDB literal builder through
        :func:`translate_where`; no caller-controlled ID is interpolated into
        SQL directly.
        """
        if not ids:
            return
        table = self._open_table(collection_name)
        if table is None:
            return
        filter_sql = translate_where(
            {"id": {"$in": ids}},
            metadata_column=None,
            known_fields={"id"},
        )
        if filter_sql is None:
            raise RuntimeError("Non-empty row-ID deletion produced no LanceDB filter")
        table.delete(filter_sql)
        self.bump_generation(collection_name)
