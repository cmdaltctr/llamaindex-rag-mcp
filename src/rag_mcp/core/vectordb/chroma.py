"""ChromaDB implementation of the :class:`VectorStore` ABC.

Absorbs all logic from the former ``chroma_utils.py`` (paged metadata
scans) and the ChromaDB-specific collection management formerly in the
ingestion writer (collection creation, dimension locking via ChromaDB's
first-write inference, generation bumping, metadata filter translation).

This is the only module outside the test suite that imports
``chromadb`` directly.  All pipeline code goes through the ABC.

Construction lives in the composition root (``compose.build_vector_store``);
the ``build_chroma_vector_store`` factory is the lazy fallback used by
``vectordb.get_default_store`` when no store has been registered yet.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import chromadb
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.vector_stores.chroma import (
    ChromaVectorStore as _LlamaChromaVectorStore,
)

from .base import VectorStore

logger = logging.getLogger(__name__)


class ChromaVectorStore(VectorStore):
    """ChromaDB-backed vector store (the default and only implementation).

    Wraps a ``chromadb.PersistentClient`` (or the ``EphemeralClient``
    injected by tests via ``conftest._patch_chromadb``).  Owns the
    process-local generation counter dict that the BM25 sparse retriever
    reads for cache invalidation.

    The vector dimension is locked by ChromaDB on the first write to a
    collection (ADR-003).  This implementation does not pass an explicit
    dimension at creation time — ChromaDB infers it from the first
    embedding.  A subsequent write with a mismatched dimension raises
    ChromaDB's native dimension-mismatch error.
    """

    def __init__(self, persist_dir: str | None = None) -> None:
        """Initialise the ChromaDB client and generation counter.

        Args:
            persist_dir: Override for the ChromaDB persist directory.
                When omitted, reads ``settings.chroma_persist_dir`` at
                call time so tests and env-driven config can override.
        """
        self._persist_dir = persist_dir
        self._client: chromadb.api.ClientAPI | None = None
        # Process-local generation counters (BM25 cache invalidation).
        # Formerly lived in ``core/ingestion/_state.py``; moved here so
        # the store owns the write→invalidate contract end-to-end.
        self._generations: dict[str, int] = {}

    # ── Client access ───────────────────────────────────────────────

    def _get_client(self) -> chromadb.api.ClientAPI:
        """Return the ChromaDB client, constructing it lazily.

        ``chromadb.PersistentClient`` is patched to an
        ``EphemeralClient`` singleton by ``conftest._patch_chromadb``
        during tests, so this returns the shared in-memory client.
        """
        if self._client is None:
            if self._persist_dir is None:
                from ...config import settings

                persist_dir = settings.chroma_persist_dir
            else:
                persist_dir = self._persist_dir
            self._client = chromadb.PersistentClient(path=persist_dir)
        return self._client

    def _get_collection(self, name: str):
        """Return the raw ChromaDB collection, or ``None`` if absent."""
        client = self._get_client()
        try:
            return client.get_collection(name)
        except Exception:
            return None

    # ── Collection lifecycle ────────────────────────────────────────

    def create_collection(self, name: str) -> None:
        client = self._get_client()
        client.get_or_create_collection(name)

    def collection_exists(self, name: str) -> bool:
        return self._get_collection(name) is not None

    def delete_collection(self, name: str) -> None:
        client = self._get_client()
        client.delete_collection(name)

    def list_collections(self) -> list[str]:
        client = self._get_client()
        return [c.name for c in client.list_collections()]

    # ── Document write (upsert via LlamaIndex) ─────────────────────

    def write_nodes(self, nodes: list[Any], collection_name: str) -> None:
        """Embed and write nodes via LlamaIndex's ChromaVectorStore adapter.

        The embedding uses the LlamaIndex global ``Settings.embed_model``
        (assigned by ``compose.ensure_runtime_setup``).  ChromaDB locks
        the vector dimension on the first write to the collection; a
        mismatched subsequent write raises ChromaDB's native error.
        """
        client = self._get_client()
        collection = client.get_or_create_collection(collection_name)
        vector_store = _LlamaChromaVectorStore(chroma_collection=collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        VectorStoreIndex(
            nodes,
            storage_context=storage_context,
            show_progress=False,
        )

    # ── Query ───────────────────────────────────────────────────────

    def query_dense(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int,
        where: dict | None = None,
    ) -> list[dict]:
        """Dense vector query returning raw ChromaDB result rows.

        Returns dicts with ``id``, ``distance``, ``document``, and
        ``metadata`` so the caller (``dense._dense_query_rows``) can
        convert the distance to a similarity score without knowing the
        store type.
        """
        collection = self._get_collection(collection_name)
        if collection is None:
            return []

        query_kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["metadatas", "documents", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        raw = collection.query(**query_kwargs)
        ids = raw.get("ids", [[]])[0]
        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        rows: list[dict] = []
        for i, chunk_id in enumerate(ids):
            meta = (
                metadatas[i]
                if i < len(metadatas) and isinstance(metadatas[i], dict)
                else {}
            )
            text = documents[i] if i < len(documents) else ""
            distance = distances[i] if i < len(distances) else None
            rows.append({
                "id": str(chunk_id),
                "distance": distance,
                "document": text,
                "metadata": dict(meta),
            })
        return rows

    # ── Paged reads ─────────────────────────────────────────────────

    def _resolve_page_size(self, page_size: int | None) -> int:
        """Resolve the effective page size, validating it is positive."""
        if page_size is None:
            from ...config import settings

            page_size = settings.chroma_scan_page_size
        if page_size <= 0:
            raise ValueError("CHROMA_SCAN_PAGE_SIZE must be a positive integer")
        return page_size

    def iter_metadatas(
        self,
        collection_name: str,
        page_size: int | None = None,
    ) -> Iterator[dict | None]:
        """Yield per-chunk metadata using bounded ChromaDB pages.

        Absorbed from the former ``chroma_utils.iter_collection_metadatas``.
        """
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

    def iter_documents(
        self,
        collection_name: str,
        page_size: int | None = None,
    ) -> Iterator[tuple[str, str, dict]]:
        """Yield ``(id, text, metadata)`` tuples using bounded pages.

        Absorbed from the former ``sparse._read_collection_rows`` logic.
        """
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
                metadata = (
                    metas[idx]
                    if idx < len(metas) and isinstance(metas[idx], dict)
                    else {}
                )
                text = (
                    docs[idx]
                    if idx < len(docs) and docs[idx] is not None
                    else ""
                )
                yield (str(doc_id), str(text), dict(metadata))
            if len(ids) < effective_page_size:
                break
            offset += len(ids)

    # ── Count ───────────────────────────────────────────────────────

    def count(self, collection_name: str) -> int:
        collection = self._get_collection(collection_name)
        if collection is None:
            return 0
        try:
            return collection.count()
        except Exception:
            return 0

    def count_where(self, collection_name: str, where: dict) -> int:
        collection = self._get_collection(collection_name)
        if collection is None:
            return 0
        result = collection.get(where=where, include=[])
        return len(result.get("ids", []))

    # ── Delete ──────────────────────────────────────────────────────

    def delete_where(self, collection_name: str, where: dict) -> None:
        collection = self._get_collection(collection_name)
        if collection is None:
            return
        collection.delete(where=where)

    # ── Collection metadata (Phase 4 profile tags) ─────────────────

    def get_collection_metadata(self, collection_name: str) -> dict | None:
        """Return the collection-level metadata dict, or ``None``."""
        collection = self._get_collection(collection_name)
        if collection is None:
            return None
        return collection.metadata

    def update_collection_metadata(
        self, collection_name: str, metadata: dict
    ) -> None:
        """Merge ``metadata`` into the collection's existing metadata.

        ChromaDB's ``modify(metadata=...)`` replaces the entire dict
        rather than merging, so we read the current metadata, merge,
        and write the combined dict back.
        """
        collection = self._get_collection(collection_name)
        if collection is None:
            client = self._get_client()
            collection = client.get_or_create_collection(collection_name)
        existing = dict(collection.metadata or {})
        existing.update(metadata)
        collection.modify(metadata=existing)

    # ── Generation counter (BM25 cache invalidation) ───────────────

    def bump_generation(self, collection_name: str) -> None:
        """Advance the process-local generation counter."""
        self._generations[collection_name] = (
            self._generations.get(collection_name, 0) + 1
        )

    def get_generation(self, collection_name: str) -> int:
        """Return the current generation counter (0 if never written)."""
        return self._generations.get(collection_name, 0)


# ── Factory ───────────────────────────────────────────────────────────


def build_chroma_vector_store(persist_dir: str | None = None) -> ChromaVectorStore:
    """Construct a ``ChromaVectorStore`` from resolved settings.

    Args:
        persist_dir: Optional override for the ChromaDB persist dir.
            When omitted, the store reads ``settings.chroma_persist_dir``
            lazily on first client access.

    Returns:
        A :class:`ChromaVectorStore` instance.
    """
    return ChromaVectorStore(persist_dir=persist_dir)


def detect_native_sparse_capability() -> bool:
    """Return whether the active ChromaDB runtime can serve native sparse queries.

    Conservative: this project uses ChromaDB ``PersistentClient`` where native
    sparse retrieval is not available for the local embedded path.  Returning
    ``False`` keeps the v1 default on BM25 and makes ``native`` fall back with
    a warning.

    The check is runtime-dynamic (not a hardcoded ``False``) so it will
    automatically return ``True`` when a future ChromaDB release adds
    native sparse query support to ``PersistentClient``.

    This is a capability probe (``hasattr`` on the class), not a client
    instantiation or API call — the only ``chromadb`` import outside
    ``_get_client`` in this module.
    """
    try:
        return hasattr(chromadb.PersistentClient, "query_sparse")
    except Exception:
        return False
