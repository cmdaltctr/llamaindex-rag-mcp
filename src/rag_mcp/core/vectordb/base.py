"""Abstract vector store contract (Phase 3 refactor, ADR-034).

Defines the :class:`VectorStore` ABC covering every vector-store operation
the RAG pipeline uses.  All pipeline code (ingestion writer, retrieval
pipeline, sparse retriever, metadata taxonomy) accesses the store through
this interface — never through ChromaDB APIs directly.

The contract deliberately encodes three ChromaDB-specific behaviours the
pipeline depends on, rather than hiding them behind a minimal put/get
interface:

* **Dimension locking** — the vector dimension is fixed when the first
  document is written to a collection.  Subsequent writes with a
  different dimension raise a clear error (ChromaDB dim-lock, ADR-003).
* **Metadata filter syntax** — queries accept a ``where`` clause (the
  ChromaDB filter shape) and the implementation translates it to the
  store's native filter syntax.
* **Generation bumping** — every write or delete advances a
  process-local generation counter so the BM25 sparse retriever knows
  when to rebuild its in-memory index.

Collection-level metadata read/update is part of the contract because
Phase 4's ``ProfileResolver`` stores profile tags
(``metadata={"profile": "codebase"}``) on collections and reads them
back through this interface.

See ``docs/adr/034-phase-3-refactor-vectordb-abstraction.md`` for the full
design rationale and the rejected minimal-interface alternative.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class VectorStore(ABC):
    """Abstract contract for a vector store backing the RAG pipeline.

    Every method corresponds to an operation enumerated from the
    pre-refactor ChromaDB call sites (Phase 3 task 1.3).  The ChromaDB
    implementation in ``core/vectordb/chroma.py`` is the first and
    currently only implementation; the ABC exists so future stores
    (LanceDB, Qdrant, pgvector) can be added behind the same interface.

    Contract behaviours
    -------------------
    * **Dimension locking**: a collection's vector dimension is fixed
      when the first document is written.  Writes with a mismatched
      dimension MUST raise a clear error.
    * **Metadata filtering**: the ``where`` parameter on query/delete
      follows the ChromaDB filter syntax (e.g. ``{"category": "AI"}``
      or ``{"$and": [...]}``).  Implementations translate it to their
      native filter representation.
    * **Generation bumping**: every mutating operation (write, delete,
      collection drop) advances the collection's generation counter via
      :meth:`bump_generation`.  The BM25 sparse retriever reads
      :meth:`get_generation` to invalidate its cached index.
    """

    # ── Collection lifecycle ────────────────────────────────────────

    @abstractmethod
    def create_collection(self, name: str) -> None:
        """Create the named collection if it does not already exist.

        The vector dimension is fixed when the first document is written
        (ChromaDB dim-lock, ADR-003).  Implementations MUST NOT require
        the dimension at creation time — ChromaDB infers it from the
        first write.

        Args:
            name: Collection name.
        """

    @abstractmethod
    def collection_exists(self, name: str) -> bool:
        """Return whether a named collection exists in the store."""

    @abstractmethod
    def delete_collection(self, name: str) -> None:
        """Permanently delete an entire collection and all its chunks.

        Raises:
            ValueError: If the collection does not exist (ChromaDB's
                native error type).
        """

    @abstractmethod
    def list_collections(self) -> list[str]:
        """Return the names of all collections in the store."""

    # ── Document write (upsert via LlamaIndex) ─────────────────────

    @abstractmethod
    def write_nodes(self, nodes: list[Any], collection_name: str) -> None:
        """Embed and write LlamaIndex nodes to a collection.

        Embedding uses the LlamaIndex global ``Settings.embed_model``
        (assigned by ``compose.ensure_runtime_setup``).  The write has
        upsert semantics at the pipeline level: callers delete old
        chunks for the same source file before writing new ones.

        The vector dimension is locked on the first write to the
        collection.  A subsequent write with a different embedding
        dimension MUST raise a clear error.

        Args:
            nodes: List of LlamaIndex ``TextNode`` objects.
            collection_name: Target collection (created if absent).
        """

    # ── Query ───────────────────────────────────────────────────────

    @abstractmethod
    def query_dense(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int,
        where: dict | None = None,
    ) -> list[dict]:
        """Run a dense vector query, returning scored result rows.

        Args:
            collection_name: Collection to query.
            query_embedding: Pre-computed query embedding vector.
            n_results: Maximum number of candidates to return.
            where: Optional ChromaDB ``where`` clause to filter by
                metadata fields.  Only matching chunks are returned.

        Returns:
            List of result dicts, each with keys ``id``, ``distance``,
            ``document``, and ``metadata``.  The caller converts the
            distance to a similarity score.
        """

    # ── Read (paged scans) ──────────────────────────────────────────

    @abstractmethod
    def iter_metadatas(
        self,
        collection_name: str,
        page_size: int | None = None,
    ) -> Iterator[dict | None]:
        """Yield per-chunk metadata dictionaries using bounded pages.

        Used for document listing, category taxonomy gathering, and
        mixed-coverage warnings.  Each page is fetched at ``page_size``
        so very large collections do not load all metadata at once.

        Args:
            collection_name: Collection to scan.
            page_size: Optional page size override.  When omitted the
                configured ``CHROMA_SCAN_PAGE_SIZE`` is read at call
                time.

        Yields:
            Metadata dictionaries, or ``None`` entries if the store
            returns them.

        Raises:
            ValueError: If the effective page size is not positive.
        """

    @abstractmethod
    def fetch_all(
        self,
        collection_name: str,
        include: list[str],
    ) -> dict[str, list] | None:
        """Return every chunk's requested fields in one store-neutral payload.

        Exists for the document-similarity graph, which needs embeddings
        alongside metadata — a combination no paged iterator exposes. It is
        deliberately the only bulk read on this interface: callers that can
        stream should use ``iter_metadatas`` / ``iter_documents`` instead.

        Args:
            collection_name: Collection to read.
            include: Field names to return. Supported values are
                ``"embeddings"``, ``"metadatas"`` and ``"documents"``.

        Returns:
            A mapping with an ``"ids"`` key plus one key per requested field,
            each a list aligned by index. ``None`` when the collection does
            not exist or is empty, so callers can degrade gracefully.
        """

    @abstractmethod
    def iter_documents(
        self,
        collection_name: str,
        page_size: int | None = None,
    ) -> Iterator[tuple[str, str, dict]]:
        """Yield ``(id, text, metadata)`` tuples using bounded pages.

        Used by the BM25 sparse retriever to build its in-memory index.

        Args:
            collection_name: Collection to scan.
            page_size: Optional page size override.

        Yields:
            Tuples of ``(chunk_id, document_text, metadata_dict)``.
        """

    # ── Count ───────────────────────────────────────────────────────

    @abstractmethod
    def count(self, collection_name: str) -> int:
        """Return the total number of chunks in a collection.

        Returns 0 if the collection does not exist.
        """

    @abstractmethod
    def count_where(self, collection_name: str, where: dict) -> int:
        """Return the number of chunks matching a metadata filter.

        Args:
            collection_name: Collection to count in.
            where: ChromaDB ``where`` clause.

        Returns:
            Number of matching chunks (0 if the collection is absent).
        """

    # ── Delete ──────────────────────────────────────────────────────

    @abstractmethod
    def delete_where(self, collection_name: str, where: dict) -> None:
        """Delete all chunks matching a metadata filter.

        Args:
            collection_name: Collection to delete from.
            where: ChromaDB ``where`` clause.
        """

    # ── Collection metadata (Phase 4 profile tags) ─────────────────

    @abstractmethod
    def get_collection_metadata(self, collection_name: str) -> dict | None:
        """Return collection-level metadata, or ``None`` if absent.

        Phase 4's ``ProfileResolver`` stores profile tags here
        (``{"profile": "codebase"}``) and reads them back through this
        method.
        """

    @abstractmethod
    def update_collection_metadata(
        self, collection_name: str, metadata: dict
    ) -> None:
        """Update collection-level metadata, merging with existing keys.

        Args:
            collection_name: Target collection.
            metadata: Metadata keys to set or overwrite.
        """

    # ── Generation counter (BM25 cache invalidation) ───────────────

    @abstractmethod
    def bump_generation(self, collection_name: str) -> None:
        """Advance the process-local generation counter for a collection.

        Called after every write or delete so the BM25 sparse retriever
        knows its cached index is stale and must be rebuilt.
        """

    @abstractmethod
    def get_generation(self, collection_name: str) -> int:
        """Return the current generation counter for a collection.

        Returns 0 for a collection that has never been written.
        """
