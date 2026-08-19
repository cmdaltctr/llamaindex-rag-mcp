"""Abstract vector-store contract used by RAG core business logic.

The interface keeps backend construction and native APIs behind one semantic
boundary. Chroma-shaped metadata filters remain the store-neutral filter
language, while concrete adapters own score conversion, paging, mutation, and
generation invalidation semantics.

See ADR-034 and ADR-047 for the abstraction and semantic-compatibility
rationale.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class VectorStore(ABC):
    """Abstract contract for a vector store backing the RAG pipeline."""

    @property
    def cache_identity(self) -> object:
        """Return a stable opaque process-local identity for derivative caches."""
        return self

    # Collection lifecycle.

    @abstractmethod
    def create_collection(self, name: str) -> None:
        """Create *name* if it does not already exist."""

    @abstractmethod
    def collection_exists(self, name: str) -> bool:
        """Return whether *name* exists in the store."""

    @abstractmethod
    def delete_collection(self, name: str) -> None:
        """Permanently delete a collection and all of its rows."""

    @abstractmethod
    def list_collections(self) -> list[str]:
        """Return every collection name."""

    # Writes.

    @abstractmethod
    def write_nodes(self, nodes: list[Any], collection_name: str) -> None:
        """Embed/write LlamaIndex nodes and bump generation exactly once."""

    def upsert_precomputed(
        self,
        collection_name: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        """Upsert rows whose embeddings were computed by the caller.

        Stores that do not support this calibration-harness operation raise
        ``NotImplementedError`` rather than silently changing the write path.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support precomputed-embedding upserts"
        )

    # Query.

    @abstractmethod
    def query_dense(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int,
        where: dict | None = None,
    ) -> list[dict]:
        """Return canonical higher-is-better dense result rows."""

    # Reads.

    @abstractmethod
    def iter_metadatas(
        self,
        collection_name: str,
        page_size: int | None = None,
    ) -> Iterator[dict | None]:
        """Yield metadata dictionaries using bounded pages."""

    @abstractmethod
    def fetch_all(
        self,
        collection_name: str,
        include: list[str],
    ) -> dict[str, list] | None:
        """Return the requested fields for every row, or ``None`` when absent/empty."""

    @abstractmethod
    def iter_documents(
        self,
        collection_name: str,
        page_size: int | None = None,
    ) -> Iterator[tuple[str, str, dict]]:
        """Yield ``(id, text, metadata)`` rows using bounded pages."""

    # Counts.

    @abstractmethod
    def count(self, collection_name: str) -> int:
        """Return total rows, or zero when the collection is absent."""

    @abstractmethod
    def count_where(self, collection_name: str, where: dict) -> int:
        """Return the number of rows matching a Chroma-shaped metadata filter."""

    # Deletes.

    @abstractmethod
    def delete_where(self, collection_name: str, where: dict) -> None:
        """Delete rows matching a Chroma-shaped metadata filter."""

    def delete_ids(self, collection_name: str, ids: list[str]) -> None:
        """Delete rows by stable store-neutral row ID.

        Stage 3 failure-safe replacement uses this operation after a bounded
        metadata scan identifies stale rows. ID deletion is deliberately
        separate from metadata ``where`` semantics because backends differ in
        how filters treat a missing metadata key on legacy rows.

        Concrete stores that implement the operation MUST bump the collection
        generation exactly once for a successful non-empty mutation. The
        default keeps older third-party implementations instantiable while
        failing explicitly if they enter the Stage 3 replacement path.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support row-ID deletion")

    # Collection metadata.

    @abstractmethod
    def get_collection_metadata(self, collection_name: str) -> dict | None:
        """Return collection metadata, or ``None`` when absent."""

    @abstractmethod
    def update_collection_metadata(self, collection_name: str, metadata: dict) -> None:
        """Merge collection-level metadata."""

    # BM25 cache generation.

    @abstractmethod
    def bump_generation(self, collection_name: str) -> None:
        """Advance the process-local collection generation counter."""

    @abstractmethod
    def get_generation(self, collection_name: str) -> int:
        """Return the collection generation, defaulting to zero."""
