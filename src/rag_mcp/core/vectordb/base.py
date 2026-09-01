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

from .identity import EmbeddingIdentity


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

    def get_collection_dimension(self, name: str) -> int | None:
        """Return an established vector dimension without creating state.

        The default keeps older third-party stores instantiable. Native
        adapters override it when their backend exposes a durable dimension.
        """
        return None

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
        *,
        embedding_identity: EmbeddingIdentity,
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

    def query_native_sparse(
        self,
        collection_name: str,
        query: str,
        n_results: int,
        where: dict | None = None,
    ) -> list[dict]:
        """Return canonical higher-is-better native sparse (FTS) result rows.

        The capability method for store-native full-text sparse queries
        (design decision 1, ``implement-native-sparse-backend-strategy``).
        Result rows mirror :meth:`query_dense`'s canonical shape:
        ``id``, ``document``, ``metadata``, ``score`` and ``score_kind``,
        with ``score`` being the engine's native higher-is-better
        sparse score (``native_fts_v1``).

        Stores without a native sparse engine fail honestly through
        this explicit unsupported response instead of returning an
        empty ranking that would read upstream as "no matches" — the
        retrieval layer treats this exception as capability absence
        and falls back to BM25 with a visible warning.

        Raises:
            NotImplementedError: When the store cannot issue native
                sparse queries.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support native sparse queries")

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

    def iter_filtered_documents(
        self,
        collection_name: str,
        where: dict,
        page_size: int | None = None,
    ) -> Iterator[tuple[str, str, dict]]:
        """Yield ``(id, text, metadata)`` rows matching metadata equality filters.

        The store-neutral filtered row-read operation used by lineage
        navigation and source-scoped stale selection.  Implementations
        MUST push *where* into the backend rather than materialising the
        whole collection in Python, and MUST preserve each row's
        persisted metadata verbatim.

        An empty *where* is rejected: an unfiltered read would silently
        scan the collection, which is exactly the cost this operation
        exists to avoid.  Callers wanting an unbounded scan use
        :meth:`iter_documents`.

        Args:
            collection_name: Collection to read.
            where: ChromaDB-style filter dict; the supported scope is
                metadata equality (compound keys AND together).
            page_size: Optional backend page size for bounded batches.

        Yields:
            ``(id, text, metadata)`` tuples for matching rows; nothing
            for an absent collection or a filter with no matches.

        Raises:
            ValueError: When *where* is empty.
            NotImplementedError: When the store does not implement the
                operation.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support filtered row reads")

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

    # Durable data version.

    def get_data_version(self, collection_name: str) -> str | None:
        """Return a durable collection data-version token, or ``None``.

        The token is opaque and tagged.  When a store supports the
        capability it SHALL change whenever the collection's rows or
        dataset identity change — including overwrite-based schema
        evolution and recreation — and it SHALL be observable by any
        process reading the same underlying data.  A numeric version
        whose history can restart is not sufficient alone, which is why
        durable implementations combine a persistent dataset identity
        with the backend commit counter.

        Returning ``None`` reports the capability as unavailable: an
        absent collection, or a backend that offers no durable version.
        Stores on such backends MUST NOT return the process-local
        generation counter (from :meth:`get_generation`) under this
        durable name; callers fall back to it themselves with the
        reduced guarantee stated in their own contract.

        Reads through this method MUST NOT mutate the collection.

        Args:
            collection_name: Collection to version.

        Returns:
            The opaque durable token, or ``None`` when unavailable or
            the collection is absent.
        """
        return None
