"""ChromaDB implementation of the :class:`VectorStore` ABC.

Absorbs the former ``chroma_utils.py`` (paged metadata scans — now
:mod:`.paged`) and the ChromaDB-specific collection management formerly
in the ingestion writer (collection creation, dimension locking via
ChromaDB's first-write inference, generation bumping, metadata filter
translation). This is the only module outside the test suite that
touches ``chromadb`` directly — the single construction site for both
the local ``PersistentClient`` and the cloud ``CloudClient``. All
pipeline code goes through the ABC; construction lives in the
composition root (``compose.build_vector_store``), and
embedding-identity stamping and enforcement live in :mod:`.identity`.

Task 5.1: both Chroma imports are lazy so the module stays importable
in the chroma-free base install (source-inspection contracts and the
registry depend on that).
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

from llama_index.core import StorageContext, VectorStoreIndex

from .base import VectorStore
from .chroma_cloud import construct_cloud_client
from .identity import (
    EmbeddingIdentity,
    IdentityGuardMixin,
    embedding_identity_from_settings,
)
from .paged import PagedReadMixin
from .score import DENSE_SCORE_KIND, canonical_score_from_l2, require_l2_metric
from .validation import materialise_and_validate_node_embeddings, validate_embedding_batch

if TYPE_CHECKING:
    import chromadb

__all__ = [
    "ChromaVectorStore",
    "EmbeddingIdentity",
    "build_chroma_vector_store",
    "build_vector_store_from_settings",
]

logger = logging.getLogger(__name__)


class ChromaVectorStore(IdentityGuardMixin, PagedReadMixin, VectorStore):
    """ChromaDB-backed vector store (optional ``chroma`` extra backend).

    Wraps an injected :class:`chromadb.api.ClientAPI` — a local
    ``PersistentClient``, a cloud ``CloudClient``, or the
    ``EphemeralClient`` injected by tests.  Owns the process-local
    generation counter dict that the BM25 sparse retriever reads for
    cache invalidation.

    The vector dimension is locked by ChromaDB on the first write to a
    collection (ADR-003); a mismatched subsequent write raises
    ChromaDB's native dimension-mismatch error.  An attached
    :class:`EmbeddingIdentity` additionally rejects a same-dimension
    model swap before any query or write (see :mod:`.identity`).

    ``get_data_version`` deliberately stays on the ABC default of
    ``None``: ChromaDB exposes no durable, cross-process collection
    version — no commit counter or dataset identity a second process
    could observe — and returning the process-local generation counter
    under a durable name would break the explicit-unavailability
    contract (``vectordb-abstraction`` spec, unsupported-backends
    scenario).  Callers fall back to the local counter with the
    reduced guarantee stated in their own contract.
    """

    def __init__(
        self,
        persist_dir: str | None = None,
        client: chromadb.api.ClientAPI | None = None,
        embedding_identity: EmbeddingIdentity | None = None,
        scan_page_size: int | None = None,
    ) -> None:
        """Initialise the store with an optional injected client.

        Args:
            persist_dir: Override for the ChromaDB persist directory
                (local lazy fallback only).
            client: Pre-constructed Chroma client (local persistent,
                cloud, or test double).  When supplied, it serves every
                collection operation and no client is constructed
                lazily.
            embedding_identity: Optional embedding configuration stamped
                into collection metadata and enforced on write/query.
                ``None`` (the default, direct-call path) keeps the
                pre-cloud behaviour: no stamping, no checks.
            scan_page_size: Bounded scan page size resolved at
                construction time.  Defaults to 10000 when omitted.
        """
        self._persist_dir = persist_dir
        self._client = client
        self._identity = embedding_identity
        self._scan_page_size = scan_page_size or 10000
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
            import chromadb

            self._client = chromadb.PersistentClient(path=self._persist_dir)
        return self._client

    def _get_collection(self, name: str):
        """Return the raw ChromaDB collection, or ``None`` if absent.

        Catches only the not-found case so genuine DB errors (corruption,
        I/O, tenant issues) propagate to the caller rather than being
        silently masked as "collection missing".
        """
        client = self._get_client()
        try:
            return client.get_collection(name)
        except Exception as exc:
            # ChromaDB raises NotFoundError (newer versions) or
            # ValueError (older versions) for missing collections.
            # Narrow to these so real DB errors propagate.
            if isinstance(exc, (KeyError, ValueError)):
                return None
            # Check for chromadb.errors.NotFoundError without importing
            # the errors module at module level (keeps the import lazy).
            if type(exc).__name__ == "NotFoundError":
                return None
            raise

    def _default_page_size(self) -> int:
        """Return the construction-time scan page size."""
        return self._scan_page_size

    # ── Collection lifecycle ────────────────────────────────────────

    def create_collection(self, name: str) -> None:
        client = self._get_client()
        client.get_or_create_collection(name)

    def collection_exists(self, name: str) -> bool:
        return self._get_collection(name) is not None

    def delete_collection(self, name: str) -> None:
        client = self._get_client()
        client.delete_collection(name)
        self.bump_generation(name)

    def list_collections(self) -> list[str]:
        client = self._get_client()
        return [c.name for c in client.list_collections()]

    def get_collection_dimension(self, name: str) -> int | None:
        """Return the stored vector dimension without creating a collection."""
        collection = self._get_collection(name)
        if collection is None:
            return None
        embeddings = collection.get(limit=1, include=["embeddings"]).get("embeddings", [])
        return len(embeddings[0]) if len(embeddings) else None

    # ── Document write (upsert via LlamaIndex) ─────────────────────

    def write_nodes(
        self, nodes: list[Any], collection_name: str, *, embed_model: Any = None
    ) -> None:
        """Embed and write nodes via LlamaIndex's ChromaVectorStore adapter.

        Embedding uses the injected *embed_model* (the engine's embedder);
        only the direct-call path without one falls back to the LlamaIndex
        global. When an embedding identity is attached, the collection's
        stored identity is stamped (legacy collections) or verified first.
        """
        if embed_model is None:
            from llama_index.core import Settings

            embed_model = Settings.embed_model
        identity = self._identity or EmbeddingIdentity(
            provider=type(embed_model).__name__,
            model=str(getattr(embed_model, "model_name", type(embed_model).__name__)),
        )
        materialise_and_validate_node_embeddings(
            nodes,
            collection_name=collection_name,
            embedding_identity=identity,
            existing_dimension=self.get_collection_dimension(collection_name),
            embed_model=embed_model,
        )
        client = self._get_client()
        collection = client.get_or_create_collection(collection_name)
        self._check_or_stamp_identity(collection)
        from llama_index.vector_stores.chroma import (
            ChromaVectorStore as _LlamaChromaVectorStore,
        )

        vector_store = _LlamaChromaVectorStore(chroma_collection=collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        # embed_model is passed explicitly: the constructor resolves
        # ``embed_model or Settings.embed_model`` BEFORE processing the
        # (already embedded) nodes, so omitting it reads the global.
        VectorStoreIndex(
            nodes,
            storage_context=storage_context,
            show_progress=False,
            embed_model=embed_model,
        )
        self.bump_generation(collection_name)

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
        """Upsert rows whose embeddings the caller already computed.

        Calibration harnesses embed corpora through their own batched
        clients (custom timeouts, count-based resume); this is the one
        verified contract method the previous ABC could not express
        (design decision 7).

        Args:
            collection_name: Target collection (created when absent).
            ids: Stable row identifiers.
            documents: Row texts.
            metadatas: Per-row metadata dicts.
            embeddings: Caller-computed embedding vectors, one per row.
        """
        validate_embedding_batch(
            ids,
            embeddings,
            collection_name=collection_name,
            embedding_identity=embedding_identity,
            existing_dimension=self.get_collection_dimension(collection_name),
        )
        client = self._get_client()
        collection = client.get_or_create_collection(collection_name)
        self._check_or_stamp_identity(collection)
        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        self.bump_generation(collection_name)

    # ── Query ───────────────────────────────────────────────────────

    def query_dense(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int,
        where: dict | None = None,
    ) -> list[dict]:
        """Query L2 and convert it to canonical higher-is-better scores."""
        collection = self._get_collection(collection_name)
        if collection is None:
            return []
        self._guard_query_identity(collection_name, collection)
        metadata = dict(getattr(collection, "metadata", None) or {})
        require_l2_metric(
            metadata.get("hnsw:space"),
            backend="ChromaDB collection",
            setting="hnsw:space",
        )

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
            meta = metadatas[i] if i < len(metadatas) and isinstance(metadatas[i], dict) else {}
            text = documents[i] if i < len(documents) else ""
            distance = distances[i] if i < len(distances) else None
            rows.append(
                {
                    "id": str(chunk_id),
                    "document": text,
                    "metadata": dict(meta),
                    # ChromaDB's l2 space reports *squared* L2; the canonical
                    # contract consumes the true distance, so root it here.
                    "score": canonical_score_from_l2(
                        None if distance is None else math.sqrt(distance),
                        backend="ChromaDB",
                    ),
                    "score_kind": DENSE_SCORE_KIND,
                    "native_distance": distance,
                }
            )
        return rows

    # ── Count ───────────────────────────────────────────────────────

    def count(self, collection_name: str) -> int:
        """Return the total number of chunks in a collection.

        Returns 0 if the collection does not exist.  Other errors
        propagate so callers can distinguish "absent" from "broken".
        """
        collection = self._get_collection(collection_name)
        if collection is None:
            return 0
        return collection.count()

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
        self.bump_generation(collection_name)

    # ── Collection metadata (Phase 4 profile tags) ─────────────────

    def get_collection_metadata(self, collection_name: str) -> dict | None:
        """Return the collection-level metadata dict, or ``None``."""
        collection = self._get_collection(collection_name)
        if collection is None:
            return None
        return collection.metadata

    def update_collection_metadata(self, collection_name: str, metadata: dict) -> None:
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

    def close(self) -> None:
        """Release process-local state; the client itself needs no teardown.

        ChromaDB's ``ClientAPI`` exposes no public close (local persistent
        and ephemeral clients release storage when garbage-collected, and a
        shared cloud client must keep serving other callers). Clearing the
        generation counters drops this instance's BM25-invalidation state.
        """
        self._generations.clear()

    def bump_generation(self, collection_name: str) -> None:
        """Advance the process-local generation counter."""
        self._generations[collection_name] = self._generations.get(collection_name, 0) + 1

    def get_generation(self, collection_name: str) -> int:
        """Return the current generation counter (0 if never written)."""
        return self._generations.get(collection_name, 0)


# ── Factory ───────────────────────────────────────────────────────────


def _resolve_local_persist_dir(persist_dir: str | None) -> str:
    """Resolve the local persist directory, defaulting to the composition root."""
    if persist_dir is not None:
        return persist_dir
    from ..settings import get_default_effective_settings

    return get_default_effective_settings().chroma_persist_dir


def build_chroma_vector_store(
    persist_dir: str | None = None,
    *,
    mode: str = "local",
    cloud_api_key: str | None = None,
    cloud_tenant: str | None = None,
    cloud_database: str | None = None,
    embedding_identity: EmbeddingIdentity | None = None,
    scan_page_size: int | None = None,
) -> ChromaVectorStore:
    """Construct a :class:`ChromaVectorStore` from resolved settings.

    This is the single production construction site for both Chroma
    deployments: local mode builds a ``PersistentClient`` over the
    resolved persist directory, cloud mode builds and validates a
    ``CloudClient``.  Following upstream LlamaIndex's
    client-construction/VectorStore split, the constructed client is
    injected into the store, which remains deployment-agnostic.

    Args:
        persist_dir: Optional override for the local ChromaDB persist
            directory.  Ignored in cloud mode.
        mode: ``"local"`` (default) or ``"cloud"``.
        cloud_api_key: Chroma Cloud API key (cloud mode only).
        cloud_tenant: Optional tenant identifier (cloud mode only).
        cloud_database: Optional database identifier (cloud mode only).
        embedding_identity: Optional identity stamped into and enforced
            on collections written through the returned store.

    Returns:
        A :class:`ChromaVectorStore` instance bound to the selected
        client.

    Raises:
        ValueError: On an unrecognised mode, a missing cloud key, or a
            half tenant/database pair.
        RuntimeError: When the cloud connection check fails (redacted).
    """
    if mode == "cloud":
        client = construct_cloud_client(cloud_api_key, cloud_tenant, cloud_database)
        return ChromaVectorStore(
            client=client,
            embedding_identity=embedding_identity,
            scan_page_size=scan_page_size,
        )
    if mode != "local":
        raise ValueError(f"CHROMA_MODE={mode!r} is not recognised. Accepted values: local, cloud.")
    import chromadb

    client = chromadb.PersistentClient(path=_resolve_local_persist_dir(persist_dir))
    return ChromaVectorStore(
        client=client,
        embedding_identity=embedding_identity,
        scan_page_size=scan_page_size,
    )


def build_vector_store_from_settings(settings: Any) -> ChromaVectorStore:
    """Construct a :class:`ChromaVectorStore` from resolved settings.

    Registered in ``core/vectordb/registry.py`` under ``"chroma"``;
    credentials pass only as construction-time primitives.
    """
    return build_chroma_vector_store(
        mode=settings.chroma_mode,
        persist_dir=settings.chroma_persist_dir,
        cloud_api_key=settings.chroma_cloud_api_key or None,
        cloud_tenant=settings.chroma_cloud_tenant or None,
        cloud_database=settings.chroma_cloud_database or None,
        embedding_identity=embedding_identity_from_settings(settings),
        scan_page_size=settings.chroma_scan_page_size,
    )
