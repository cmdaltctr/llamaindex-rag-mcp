"""Internal ChromaDB helpers shared across RAG operations."""

from __future__ import annotations

from collections.abc import Iterator


def iter_collection_metadatas(
    collection,
    page_size: int | None = None,
) -> Iterator[dict | None]:
    """Yield collection metadata entries using bounded ChromaDB pages.

    Args:
        collection: A ChromaDB collection-like object with ``get``.
        page_size: Optional page size override. When omitted, the current
            ``rag_mcp.config.CHROMA_SCAN_PAGE_SIZE`` value is read at call time
            so tests and environment-driven configuration can override it.

    Yields:
        Metadata dictionaries, or ``None`` entries if ChromaDB returns them.

    Raises:
        ValueError: If the effective page size is not positive.
    """
    if page_size is None:
        from .config import CHROMA_SCAN_PAGE_SIZE

        page_size = CHROMA_SCAN_PAGE_SIZE

    if page_size <= 0:
        raise ValueError("CHROMA_SCAN_PAGE_SIZE must be a positive integer")

    offset = 0
    while True:
        result = collection.get(
            include=["metadatas"],
            limit=page_size,
            offset=offset,
        )
        metadatas = result.get("metadatas") or []
        if not metadatas:
            break

        yield from metadatas

        if len(metadatas) < page_size:
            break
        offset += len(metadatas)
