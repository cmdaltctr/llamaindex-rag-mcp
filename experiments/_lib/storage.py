"""Shared experiment storage configuration for the calibration harnesses.

One helper backs all six active ``calibrate-rag-retrieval-defaults``
runners (experiments 10b, 10.1, 12, 9a-rerun, 13, 14).  It derives the
deterministic immutable-index collection name, resolves the storage
mode from normal runtime settings (``CHROMA_MODE``, never a new
selector), and produces JSON-safe checkpoint metadata that carries
identifiers but never the API key.

The store itself is always constructed through the production factory
(``rag_mcp.core.vectordb.chroma.build_chroma_vector_store``) — no
harness touches ``chromadb`` directly.  Local mode keeps one persist
directory per index; cloud mode shares one database with per-index
collection names.  One writer builds each immutable index;
retrieval-only cells and repetitions reuse it read-only because the
BM25 invalidation counter is process-local.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from rag_mcp.config import Settings
from rag_mcp.core.vectordb.chroma import (
    EmbeddingIdentity,
    build_chroma_vector_store,
)
from rag_mcp.core.vectordb.naming import experiment_collection_name

if TYPE_CHECKING:
    from rag_mcp.core.vectordb.base import VectorStore


@dataclass(frozen=True)
class ExperimentStorageConfig:
    """Secret-free storage plan for one immutable experiment index.

    Attributes:
        collection_name: Deterministic name identifying the immutable
            index (experiment, corpus/config, provider, model, parser,
            chunking).  Cell IDs and repetitions are deliberately not
            part of it.
        mode: ``"local"`` or ``"cloud"`` — resolved from runtime
            settings, independent of the embedding provider axis.
        persist_dir: Local-mode persist directory (``None`` in cloud
            mode, or when the settings default applies).
        cloud_tenant: Cloud tenant identifier, when configured.
        cloud_database: Cloud database identifier, when configured.
        embed_provider: Embedding backend recorded in the index identity.
        embed_model: Embedding model recorded in the index identity.
        checkpoint_metadata: JSON-safe dict for ``--resume`` files —
            identifiers and configuration only, never the API key.
    """

    collection_name: str
    mode: str
    persist_dir: str | None
    cloud_tenant: str | None
    cloud_database: str | None
    embed_provider: str
    embed_model: str
    checkpoint_metadata: dict[str, Any] = field(default_factory=dict)

    def build_store(self, settings: Settings | None = None) -> VectorStore:
        """Construct the store through the production factory path.

        Args:
            settings: Settings supplying the cloud API key in cloud
                mode; defaults to a fresh ``Settings()`` read from the
                environment.  The key is used for construction only
                and never stored on this config.

        Returns:
            A :class:`VectorStore` bound to the resolved deployment,
                with the index identity attached for stamping and
                enforcement.
        """
        if settings is None:
            settings = Settings()
        identity = EmbeddingIdentity(
            provider=self.embed_provider,
            model=self.embed_model,
            index_identity=self.collection_name,
        )
        if self.mode == "cloud":
            return build_chroma_vector_store(
                mode="cloud",
                cloud_api_key=settings.chroma_cloud_api_key,
                cloud_tenant=self.cloud_tenant,
                cloud_database=self.cloud_database,
                embedding_identity=identity,
            )
        return build_chroma_vector_store(
            mode="local",
            persist_dir=self.persist_dir or settings.chroma_persist_dir,
            embedding_identity=identity,
        )


def experiment_storage_config(
    *,
    experiment_id: str,
    corpus: str,
    provider: str,
    model: str,
    parser: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    persist_dir: str | None = None,
    settings: Settings | None = None,
) -> ExperimentStorageConfig:
    """Resolve the storage plan for one immutable experiment index.

    Args:
        experiment_id: Experiment identifier, e.g. ``exp14``.
        corpus: Corpus/config identity, e.g. ``qasper``.  Include a
            version tag when the corpus content changes.
        provider: Effective embedding backend name.
        model: Embedding model identifier.
        parser: Document parser, when it changes the indexed text.
        chunk_size: Chunk size used to build the index.
        chunk_overlap: Chunk overlap used to build the index.
        persist_dir: Local-mode persist directory override; defaults
            to ``settings.chroma_persist_dir``.  Ignored in cloud mode.
        settings: Settings to resolve the mode and identifiers from;
            defaults to a fresh ``Settings()`` read from the
            environment (``.env`` included).

    Returns:
        The frozen :class:`ExperimentStorageConfig`.
    """
    if settings is None:
        settings = Settings()
    mode = settings.chroma_mode
    resolved_persist = str(persist_dir) if persist_dir is not None else settings.chroma_persist_dir
    tenant = settings.chroma_cloud_tenant or None
    database = settings.chroma_cloud_database or None
    collection_name = experiment_collection_name(
        experiment_id=experiment_id,
        corpus=corpus,
        provider=provider,
        model=model,
        parser=parser,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    checkpoint_metadata: dict[str, Any] = {
        "experiment_id": experiment_id,
        "corpus": corpus,
        "embed_provider": provider,
        "embed_model": model,
        "parser": parser,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "collection_name": collection_name,
        "chroma_mode": mode,
        "chroma_cloud_tenant": tenant,
        "chroma_cloud_database": database,
        "persist_dir": resolved_persist if mode == "local" else None,
    }
    return ExperimentStorageConfig(
        collection_name=collection_name,
        mode=mode,
        persist_dir=resolved_persist if mode == "local" else None,
        cloud_tenant=tenant,
        cloud_database=database,
        embed_provider=provider,
        embed_model=model,
        checkpoint_metadata=checkpoint_metadata,
    )


class CollectionReader:
    """Duck-typed collection view over the ``VectorStore`` ABC.

    ``core.documents.doc_graph`` and its similarity helpers accept a raw
    Chroma collection handle with a single ``get(include=...)`` method;
    this adapter satisfies that contract via :meth:`VectorStore.fetch_all`
    so experiment runners never import ``chromadb`` (task 4.1 mapping).
    """

    def __init__(self, store: VectorStore, collection_name: str) -> None:
        """Bind the reader to one collection on one store.

        Args:
            store: Store serving the reads.
            collection_name: Collection to expose.
        """
        self._store = store
        self._collection_name = collection_name

    def get(self, include: list[str]) -> dict[str, list]:
        """Return every row's requested fields (ABC ``fetch_all``)."""
        result = self._store.fetch_all(self._collection_name, include=include)
        if result is None:
            return {"ids": []}
        return result
