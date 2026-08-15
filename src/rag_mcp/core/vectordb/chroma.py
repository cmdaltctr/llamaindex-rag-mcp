"""ChromaDB implementation of the :class:`VectorStore` ABC.

Absorbs all logic from the former ``chroma_utils.py`` (paged metadata
scans — now :mod:`.paged`) and the ChromaDB-specific collection
management formerly in the ingestion writer (collection creation,
dimension locking via ChromaDB's first-write inference, generation
bumping, metadata filter translation).

This is the only module outside the test suite that imports
``chromadb`` directly, and therefore the single construction site for
both the local ``PersistentClient`` and the cloud ``CloudClient``.
All pipeline code goes through the ABC.

Construction lives in the composition root (``compose.build_vector_store``);
the ``build_chroma_vector_store`` factory is the lazy fallback used by
``vectordb.get_default_store`` when no store has been registered yet.
Embedding-identity stamping and enforcement live in :mod:`.identity`.
"""

from __future__ import annotations

import logging
from typing import Any

import chromadb
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.vector_stores.chroma import (
    ChromaVectorStore as _LlamaChromaVectorStore,
)

from .base import VectorStore
from .identity import EmbeddingIdentity, IdentityGuardMixin, redact_cloud_secrets
from .paged import PagedReadMixin

__all__ = [
    "ChromaVectorStore",
    "EmbeddingIdentity",
    "build_chroma_vector_store",
    "detect_native_sparse_capability",
]

logger = logging.getLogger(__name__)


class ChromaVectorStore(IdentityGuardMixin, PagedReadMixin, VectorStore):
    """ChromaDB-backed vector store (the default and only implementation).

    Wraps an injected :class:`chromadb.api.ClientAPI` — a local
    ``PersistentClient``, a cloud ``CloudClient``, or the
    ``EphemeralClient`` injected by tests via ``conftest._patch_chromadb``.
    Owns the process-local generation counter dict that the BM25 sparse
    retriever reads for cache invalidation.

    The vector dimension is locked by ChromaDB on the first write to a
    collection (ADR-003); a mismatched subsequent write raises
    ChromaDB's native dimension-mismatch error.  When an
    :class:`EmbeddingIdentity` is attached, embedding-space identity is
    additionally enforced: a same-dimension model swap is rejected
    before any query or write (see :mod:`.identity`).
    """

    def __init__(
        self,
        persist_dir: str | None = None,
        client: chromadb.api.ClientAPI | None = None,
        embedding_identity: EmbeddingIdentity | None = None,
    ) -> None:
        """Initialise the store with an optional injected client.

        Args:
            persist_dir: Override for the ChromaDB persist directory.
                Used only by the local lazy fallback when ``client`` is
                omitted; when omitted too, the composition root's
                default is read at call time.
            client: Pre-constructed Chroma client (local persistent,
                cloud, or test double).  When supplied, it serves every
                collection operation and no client is constructed
                lazily.
            embedding_identity: Optional embedding configuration stamped
                into collection metadata and enforced on write/query.
                ``None`` (the default, direct-call path) keeps the
                pre-cloud behaviour: no stamping, no checks.
        """
        self._persist_dir = persist_dir
        self._client = client
        self._identity = embedding_identity
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
                from ..settings import get_default_effective_settings

                persist_dir = get_default_effective_settings().chroma_persist_dir
            else:
                persist_dir = self._persist_dir
            self._client = chromadb.PersistentClient(path=persist_dir)
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
        """Return the composition root's default scan page size."""
        from ..settings import get_default_effective_settings

        return get_default_effective_settings().chroma_scan_page_size

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
        (assigned by ``compose.ensure_runtime_setup``).  When an
        embedding identity is attached, the collection's stored identity
        is stamped (legacy collections) or verified first.
        """
        client = self._get_client()
        collection = client.get_or_create_collection(collection_name)
        self._check_or_stamp_identity(collection)
        vector_store = _LlamaChromaVectorStore(chroma_collection=collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        VectorStoreIndex(
            nodes,
            storage_context=storage_context,
            show_progress=False,
        )

    def upsert_precomputed(
        self,
        collection_name: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
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
        client = self._get_client()
        collection = client.get_or_create_collection(collection_name)
        self._check_or_stamp_identity(collection)
        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
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
        self._guard_query_identity(collection_name, collection)

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
                    "distance": distance,
                    "document": text,
                    "metadata": dict(meta),
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


def _construct_cloud_client(
    cloud_api_key: str | None,
    cloud_tenant: str | None,
    cloud_database: str | None,
) -> chromadb.api.ClientAPI:
    """Construct and validate a ``chromadb.CloudClient``.

    The client receives exactly the resolved key (plus the
    tenant/database pair when both are supplied) and is validated with
    a lightweight ``heartbeat()`` round trip so authentication,
    network, and tenant/database mistakes surface at startup — never
    mid-run.

    Args:
        cloud_api_key: Chroma Cloud API key.
        cloud_tenant: Optional tenant identifier.
        cloud_database: Optional database identifier.

    Returns:
        A validated cloud client.

    Raises:
        ValueError: When the key is missing, or tenant/database arrive
            as a half pair (direct factory callers bypass Settings
            validation, so the guard is repeated here).
        RuntimeError: When construction or the connection check fails.
            The message is redacted and names the relevant variables.
    """
    key = (cloud_api_key or "").strip()
    if not key:
        raise ValueError(
            "CHROMA_MODE=cloud requires CHROMA_CLOUD_API_KEY to be set. "
            "Add it to your .env file (see .env.example); never commit the key."
        )
    kwargs: dict[str, str] = {"api_key": key}
    tenant = (cloud_tenant or "").strip()
    database = (cloud_database or "").strip()
    if tenant or database:
        if not (tenant and database):
            raise ValueError(
                "CHROMA_CLOUD_TENANT and CHROMA_CLOUD_DATABASE must be supplied "
                "together, or both omitted so the cloud client resolves them "
                "from the API key."
            )
        kwargs["tenant"] = tenant
        kwargs["database"] = database
    try:
        client = chromadb.CloudClient(**kwargs)
        client.heartbeat()
    except Exception as exc:
        raise RuntimeError(
            redact_cloud_secrets(
                f"CHROMA_MODE=cloud connection check failed "
                f"({type(exc).__name__}): {exc}. Verify CHROMA_CLOUD_API_KEY, "
                "CHROMA_CLOUD_TENANT, and CHROMA_CLOUD_DATABASE, and network "
                "reachability of Chroma Cloud. No local fallback is performed "
                "after an explicit cloud selection.",
                key,
                tenant,
                database,
            )
        ) from None
    return client


def build_chroma_vector_store(
    persist_dir: str | None = None,
    *,
    mode: str = "local",
    cloud_api_key: str | None = None,
    cloud_tenant: str | None = None,
    cloud_database: str | None = None,
    embedding_identity: EmbeddingIdentity | None = None,
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
        client = _construct_cloud_client(cloud_api_key, cloud_tenant, cloud_database)
        return ChromaVectorStore(client=client, embedding_identity=embedding_identity)
    if mode != "local":
        raise ValueError(f"CHROMA_MODE={mode!r} is not recognised. Accepted values: local, cloud.")
    client = chromadb.PersistentClient(path=_resolve_local_persist_dir(persist_dir))
    return ChromaVectorStore(client=client, embedding_identity=embedding_identity)


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
