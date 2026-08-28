"""Paged collection reads and row-ID deletion for the Chroma store.

Extracted from ``chroma.py`` to respect the 500-line file ceiling. These
methods operate on duck-typed Chroma collection handles, keeping the direct
``chromadb`` import confined to ``chroma.py``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

logger = logging.getLogger(__name__)


class PagedReadMixin:
    """Bounded-page reads plus stable-ID deletion over Chroma collections."""

    # Supplied by the concrete store.
    _get_collection: Callable[[str], Any]
    _default_page_size: Callable[[], int]
    bump_generation: Callable[[str], None]

    def _resolve_page_size(self, page_size: int | None) -> int:
        """Resolve the effective page size, validating it is positive."""
        if page_size is None:
            page_size = self._default_page_size()
        if page_size <= 0:
            raise ValueError("CHROMA_SCAN_PAGE_SIZE must be a positive integer")
        return page_size

    def iter_metadatas(
        self,
        collection_name: str,
        page_size: int | None = None,
    ) -> Iterator[dict | None]:
        """Yield per-chunk metadata using bounded ChromaDB pages."""
        collection = self._get_collection(collection_name)
        if collection is None:
            return

        effective_page_size = self._resolve_page_size(page_size)
        offset = 0
        while True:
            result = collection.get(
                include=["metadatas"],
                limit=effective_page_size,
                offset=offset,
            )
            metadatas = result.get("metadatas") or []
            if not metadatas:
                break
            yield from metadatas
            if len(metadatas) < effective_page_size:
                break
            offset += len(metadatas)

    def fetch_all(
        self,
        collection_name: str,
        include: list[str],
    ) -> dict[str, list] | None:
        """Return every chunk's requested fields in one payload."""
        try:
            collection = self._get_collection(collection_name)
        except Exception as exc:
            logger.warning(
                "Could not open collection %r for bulk read: %s",
                collection_name,
                exc,
            )
            return None
        if collection is None:
            return None
        try:
            if collection.count() == 0:
                logger.debug("Collection %r is empty", collection_name)
                return None
            return collection.get(include=include)
        except Exception as exc:
            logger.warning("Bulk read of collection %r failed: %s", collection_name, exc)
            return None

    def iter_documents(
        self,
        collection_name: str,
        page_size: int | None = None,
    ) -> Iterator[tuple[str, str, dict]]:
        """Yield ``(id, text, metadata)`` tuples using bounded pages."""
        collection = self._get_collection(collection_name)
        if collection is None:
            return

        effective_page_size = self._resolve_page_size(page_size)
        offset = 0
        while True:
            batch = collection.get(
                include=["documents", "metadatas"],
                limit=effective_page_size,
                offset=offset,
            )
            ids = batch.get("ids") or []
            docs = batch.get("documents") or []
            metas = batch.get("metadatas") or []
            if not ids:
                break
            for idx, doc_id in enumerate(ids):
                metadata = metas[idx] if idx < len(metas) and isinstance(metas[idx], dict) else {}
                text = docs[idx] if idx < len(docs) and docs[idx] is not None else ""
                yield (str(doc_id), str(text), dict(metadata))
            if len(ids) < effective_page_size:
                break
            offset += len(ids)

    def delete_ids(self, collection_name: str, ids: list[str]) -> None:
        """Delete stable row IDs and advance generation exactly once.

        Empty ID lists and absent collections are no-ops. Selection of the IDs
        is performed by store-neutral ingestion logic, so this operation does
        not inherit backend-specific missing-metadata filter semantics.
        """
        if not ids:
            return
        collection = self._get_collection(collection_name)
        if collection is None:
            return
        collection.delete(ids=ids)
        self.bump_generation(collection_name)
