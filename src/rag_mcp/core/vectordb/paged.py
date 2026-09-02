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


def _chroma_where(where: dict) -> dict:
    """Translate a store-neutral equality filter into ChromaDB ``where`` form.

    ChromaDB accepts a single ``{key: value}`` dict as shorthand for one
    equality condition, but rejects multi-key dicts outright ("Expected
    where to have exactly one operator"). The store-neutral filtered-read
    contract passes plain equality dicts, so compound filters are wrapped
    in ``{"$and": [...]}`` with one clause per key, preserving key order.

    Args:
        where: Non-empty dict of metadata equality conditions.

    Returns:
        A ChromaDB-valid ``where`` clause for the same conditions.
    """
    if len(where) == 1:
        return dict(where)
    return {"$and": [{key: value} for key, value in where.items()]}


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

    def iter_filtered_documents(
        self,
        collection_name: str,
        where: dict,
        page_size: int | None = None,
    ) -> Iterator[tuple[str, str, dict]]:
        """Yield ``(id, text, metadata)`` rows matching *where*, filter pushed down.

        ``where`` is a store-neutral equality dict translated to
        ChromaDB's ``where`` form (multi-key dicts wrapped in
        ``{"$and": [...]}``) so the server filters before paging —
        the bounded-read contract the lineage navigator and
        source-scoped stale selection depend on.

        Args:
            collection_name: Collection to read.
            where: Non-empty dict of metadata equality conditions;
                empty filters are rejected because an unfiltered scan
                is what ``iter_documents`` is for.
            page_size: Optional page size for bounded batches.

        Yields:
            ``(id, text, metadata)`` tuples for matching rows;
            nothing for an absent collection or no matches.

        Raises:
            ValueError: When *where* is empty.
        """
        if not where:
            raise ValueError(
                f"iter_filtered_documents on {collection_name!r} requires a "
                "non-empty where filter; use iter_documents for unfiltered scans."
            )
        chroma_where = _chroma_where(where)
        collection = self._get_collection(collection_name)
        if collection is None:
            return

        effective_page_size = self._resolve_page_size(page_size)
        offset = 0
        while True:
            batch = collection.get(
                include=["documents", "metadatas"],
                where=chroma_where,
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
