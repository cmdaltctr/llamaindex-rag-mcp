"""LanceDB implementation of the :class:`VectorStore` ABC.

One ``lancedb.connect(uri)`` connection backs the store; each RAG
"collection" maps to one LanceDB table (``{uri}/{name}.lance``) whose
name is validated as a single safe path component before table access
can touch disk (:func:`.lance_table_name.validate_table_name`).
Writes go through a throwaway LlamaIndex ``LanceDBVectorStore``
adapter per table with ``mode="create"`` so a fresh adapter can never
overwrite a populated table (the default mode is ``"overwrite"``).

Table creation is lazy: LanceDB cannot create a table without data
or a schema, so the vector dimension is fixed on first write exactly
as the ChromaDB dimension lock behaves.  ``create_collection``
records intent (a process-local set) so existence checks and
listings match ChromaDB's create-on-demand semantics.

Collection metadata (profile tags and the embedding-identity triple)
lives in the table's durable Arrow schema metadata, written through
pylance's ``update_schema_metadata`` (read-merge-write); that seam
and the identity guards live in :mod:`.lance_meta`.  Schema metadata
is the durable key-value bag that survives reconnection and adapter
writes (verified against lancedb 0.37.1 / pylance 10.0.0).

This is one of the only modules that imports ``lancedb`` directly
(the other is ``lance_filter.py``); all pipeline code goes through
the ABC.
"""

from __future__ import annotations

import io
import json
import math
from contextlib import redirect_stdout
from typing import Any

import lancedb
import pyarrow as pa
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.vector_stores.lancedb import (
    LanceDBVectorStore as _LlamaLanceVectorStore,
)

from .base import VectorStore
from .identity import EmbeddingIdentity, embedding_identity_from_settings
from .lance_filter import translate_where
from .lance_meta import LanceTableMetadataMixin, infer_arrow_type, metadata_field_names
from .lance_node_schema import evolve_for_nodes
from .lance_paged import LancePagedReadMixin, strip_internal_metadata
from .lance_rows import rows_to_arrow, upsert_schema
from .lance_table_name import validate_table_name
from .score import DENSE_SCORE_KIND, canonical_score_from_l2
from .validation import materialise_and_validate_node_embeddings, validate_embedding_batch

__all__ = ["LanceVectorStore", "build_vector_store_from_settings"]


class LanceVectorStore(LanceTableMetadataMixin, LancePagedReadMixin, VectorStore):
    """LanceDB-backed vector store (embedded, local-first).

    Wraps a lazily constructed ``lancedb.DBConnection``.  Owns a
    process-local generation counter dict (BM25 cache invalidation)
    and a process-local intent set backing lazy table creation.

    The vector dimension is fixed by the table schema on first write;
    a mismatched subsequent write raises LanceDB's cast error.
    When an :class:`EmbeddingIdentity` is attached, embedding-space
    identity is additionally stamped into / enforced from the table's
    schema metadata before any write or query.
    """

    def __init__(
        self,
        uri: str | None = None,
        connection: Any | None = None,
        embedding_identity: EmbeddingIdentity | None = None,
    ) -> None:
        """Initialise the store with an optional injected connection.

        Args:
            uri: Override for the LanceDB parent directory.  Used only
                by the lazy fallback when ``connection`` is omitted;
                when omitted too, the composition root's
                ``LANCEDB_URI`` default is read at call time.
            connection: Pre-constructed ``lancedb.DBConnection``.  When
                supplied, it serves every table operation and no
                connection is constructed lazily.
            embedding_identity: Optional embedding configuration stamped
                into table metadata and enforced on write/query.
                ``None`` (the direct-call path) keeps the legacy
                behaviour: no stamping, no checks.
        """
        self._uri = uri
        self._connection = connection
        self._identity = embedding_identity
        # Process-local generation counters (BM25 cache invalidation) —
        # the same contract the ChromaDB store owns.
        self._generations: dict[str, int] = {}
        # Collections created via create_collection but not yet written.
        self._intents: set[str] = set()
        # Metadata parked for intent-only collections, flushed into the
        # table's schema metadata on first write.
        self._pending_metadata: dict[str, dict[str, str]] = {}

    # ── Connection / table access ───────────────────────────────────

    def _get_connection(self) -> Any:
        """Return the LanceDB connection, constructing it lazily."""
        if self._connection is None:
            if self._uri is None:
                from ..settings import get_default_effective_settings

                uri = get_default_effective_settings().lancedb_uri
            else:
                uri = self._uri
            self._connection = lancedb.connect(uri)
        return self._connection

    def _list_table_names(self) -> list[str]:
        """Return every table name, draining list_tables pagination."""
        connection = self._get_connection()
        names: list[str] = []
        response = connection.list_tables()
        names.extend(response.tables)
        while response.page_token:
            response = connection.list_tables(page_token=response.page_token)
            names.extend(response.tables)
        return names

    def _open_table(self, name: str) -> Any:
        """Return the raw LanceDB table, or ``None`` if absent.

        Opens directly: lancedb (>= 0.37) maps a missing table to a
        ``ValueError`` carrying the standardised "was not found" phrase,
        so no name listing is needed on this per-page hot path.  Any
        other ``ValueError`` (corrupt or incomplete ``.lance`` data)
        re-raises instead of silently reading as absent.
        """
        validate_table_name(name)
        try:
            return self._get_connection().open_table(name)
        except ValueError as exc:
            if "was not found" in str(exc):
                return None
            raise

    def _default_page_size(self) -> int:
        """Return the composition root's default scan page size."""
        from ..settings import get_default_effective_settings

        return get_default_effective_settings().chroma_scan_page_size

    # ── Collection lifecycle ────────────────────────────────────────

    def create_collection(self, name: str) -> None:
        """Record creation intent; the table materialises on first write.

        LanceDB cannot create a table without data or a schema, so the
        vector dimension is fixed by the schema on the first write —
        the same create-on-first-write behaviour as ChromaDB.
        """
        self._intents.add(validate_table_name(name))

    def collection_exists(self, name: str) -> bool:
        return name in self._intents or name in self._list_table_names()

    def delete_collection(self, name: str) -> None:
        """Drop the table and any recorded intent for *name*.

        The generation counter advances on every successful drop —
        including intent-only deletions — so a cached BM25 index built
        over the collection is invalidated even when the store is
        called directly, without the ingestion writer's bump
        (the ``VectorStore`` contract's collection-drop rule).

        Raises:
            ValueError: If the collection does not exist.
        """
        was_intent = name in self._intents
        self._intents.discard(name)
        self._pending_metadata.pop(name, None)
        if name in self._list_table_names():
            self._get_connection().drop_table(validate_table_name(name))
            self.bump_generation(name)
            return
        if not was_intent:
            raise ValueError(f"Collection {name!r} does not exist.")
        self.bump_generation(name)

    def list_collections(self) -> list[str]:
        return sorted(set(self._list_table_names()) | self._intents)

    def get_collection_dimension(self, name: str) -> int | None:
        """Return the fixed Arrow vector width without creating a table."""
        table = self._open_table(name)
        if table is None or "vector" not in table.schema.names:
            return None
        vector_type = table.schema.field("vector").type
        return vector_type.list_size if pa.types.is_fixed_size_list(vector_type) else None

    # ── Document write ──────────────────────────────────────────────

    def write_nodes(self, nodes: list[Any], collection_name: str) -> None:
        """Embed and write nodes via LlamaIndex's LanceDB adapter.

        The embedding uses the LlamaIndex global ``Settings.embed_model``
        (assigned by ``compose.ensure_runtime_setup``).  stdout is
        redirected because the adapter prints a notice to stdout when
        it lazily creates a table — stdout is the MCP protocol channel
        and must stay clean.

        The ``metadata`` struct is fixed on the first write, so a batch
        introducing new metadata keys grows the struct first (old rows
        gain nulls); the adapter's internal keys are included because
        the adapter writes them into the same struct.
        """
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
        self._check_or_stamp_identity(collection_name)
        self._widen_null_adapter_columns(collection_name)
        self._evolve_for_nodes(collection_name, nodes)
        connection = self._get_connection()
        with redirect_stdout(io.StringIO()):
            vector_store = _LlamaLanceVectorStore(
                connection=connection,
                table_name=collection_name,
                mode="create",
            )
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            VectorStoreIndex(
                nodes,
                storage_context=storage_context,
                show_progress=False,
            )
        self._intents.discard(collection_name)
        self._flush_after_write(collection_name)
        self.bump_generation(collection_name)

    def _evolve_for_nodes(self, collection_name: str, nodes: list[Any]) -> None:
        """Grow the metadata struct to cover the batch's keys."""
        evolve_for_nodes(self, collection_name, nodes)

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

        Rows are merged on the ``id`` column (update matched, insert
        unmatched) through a pyarrow table built against the live
        schema, so upserts into adapter-written tables match whatever
        the adapter wrote.  When the table does not exist yet, it is
        created with a schema derived from the first batch — after
        which the vector dimension is locked.  A batch introducing new
        metadata keys grows the struct first so no key is silently
        dropped.  An empty batch is a no-op: creating a table from it
        would lock a zero-dimension vector column that no later write
        could satisfy.
        """
        validate_embedding_batch(
            ids,
            embeddings,
            collection_name=collection_name,
            embedding_identity=embedding_identity,
            existing_dimension=self.get_collection_dimension(collection_name),
        )
        self._check_or_stamp_identity(collection_name)
        table = self._open_table(collection_name)
        if table is None:
            dim = len(embeddings[0])
            schema = upsert_schema(dim, metadatas)
            table = self._get_connection().create_table(
                collection_name, schema=schema, mode="create"
            )
        else:
            new_fields = {
                key: infer_arrow_type([m.get(key) for m in metadatas])
                for key in {k for m in metadatas for k in m}
            }
            if self.evolve_metadata_fields(collection_name, new_fields):
                # The rebuild pinned a new version; read through a
                # fresh handle so the live schema includes the growth.
                table = self._get_connection().open_table(collection_name)
        missing = {
            key for meta in metadatas for key in meta if key not in metadata_field_names(table)
        }
        if missing:
            # Belt-and-braces: rows are built against the live schema,
            # and an unknown key there would be silently discarded.
            raise ValueError(
                f"Metadata fields {sorted(missing)} are absent from the table "
                f"schema of {collection_name!r} and could not be added."
            )
        source = rows_to_arrow(table.schema, ids, documents, metadatas, embeddings)
        (
            table.merge_insert("id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(source)
        )
        self._intents.discard(collection_name)
        self._flush_after_write(collection_name)
        self.bump_generation(collection_name)

    # ── Query ───────────────────────────────────────────────────────

    def query_dense(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int,
        where: dict | None = None,
    ) -> list[dict]:
        """Dense vector query returning store-neutral result rows.

        Guard order: the absent-table check runs first (an absent
        collection reads as empty, matching the ABC), and the identity
        guard runs only when the table exists — the reverse of
        ``write_nodes``, which guards identity before writing.

        Args:
            collection_name: Collection (table) to query.
            query_embedding: The query vector.
            n_results: Maximum rows to return.
            where: Optional ChromaDB-style metadata filter.

        Returns:
            Result rows with canonical ``score``/``score_kind`` plus the
            store-neutral content fields. LanceDB's default search metric is
            L2, reported natively as *squared* L2; its ``_distance`` is
            retained only as a diagnostic.
        """
        table = self._open_table(collection_name)
        if table is None:
            return []
        self._guard_query_identity(collection_name)
        # Pin L2 explicitly instead of relying on LanceDB's current default;
        # the adapter's canonical transform is defined only for L2 distance.
        builder = table.search(query_embedding).distance_type("l2").limit(n_results)
        if where:
            builder = builder.where(
                translate_where(
                    where,
                    metadata_column="metadata",
                    known_fields=metadata_field_names(table),
                )
            )
        rows = builder.to_list()
        results: list[dict] = []
        for row in rows:
            text = row.get("text")
            native_distance = row.get("_distance")
            results.append(
                {
                    "id": str(row.get("id")),
                    "document": text if text is not None else "",
                    "metadata": strip_internal_metadata(row.get("metadata")),
                    # LanceDB's l2 metric reports *squared* L2; the canonical
                    # contract consumes the true distance, so root it here.
                    "score": canonical_score_from_l2(
                        None if native_distance is None else math.sqrt(native_distance),
                        backend="LanceDB",
                    ),
                    "score_kind": DENSE_SCORE_KIND,
                    "native_distance": native_distance,
                }
            )
        return results

    # ── Count ───────────────────────────────────────────────────────

    def count(self, collection_name: str) -> int:
        """Return the row count, or 0 when the table is absent."""
        table = self._open_table(collection_name)
        if table is None:
            return 0
        return table.count_rows()

    def count_where(self, collection_name: str, where: dict) -> int:
        table = self._open_table(collection_name)
        if table is None:
            return 0
        return table.count_rows(
            translate_where(
                where,
                metadata_column="metadata",
                known_fields=metadata_field_names(table),
            )
        )

    # ── Delete ──────────────────────────────────────────────────────

    def delete_where(self, collection_name: str, where: dict) -> None:
        """Delete rows matching the translated filter, then bump generation.

        An absent collection is a no-op — the ChromaDB store returns the
        same way before its filter reaches the engine — so filter
        validation applies only when the collection exists.

        Args:
            collection_name: Collection (table) to delete from.
            where: ChromaDB-style filter dict.

        Raises:
            ValueError: When *where* translates to no filter and the
                collection exists — an empty clause would otherwise
                delete every row.  ChromaDB rejects the same call
                ("Expected where to have exactly one operator"), so
                parity demands rejection here.
        """
        table = self._open_table(collection_name)
        if table is None:
            return
        filter_sql = translate_where(
            where,
            metadata_column="metadata",
            known_fields=metadata_field_names(table),
        )
        if filter_sql is None:
            raise ValueError(
                f"delete_where on {collection_name!r} requires a non-empty where filter."
            )
        table.delete(filter_sql)
        self.bump_generation(collection_name)

    # ── Collection metadata (Phase 4 profile tags) ─────────────────

    def get_collection_metadata(self, collection_name: str) -> dict | None:
        """Return the table's metadata bag, or ``None`` when absent.

        Intent-only collections surface their pending metadata so
        profile tags written before the first write round-trip.
        """
        table = self._open_table(collection_name)
        if table is None:
            pending = self._pending_metadata.get(collection_name)
            if not pending:
                return None
            return {key: json.loads(value) for key, value in pending.items()}
        metadata = self._read_table_metadata(table)
        return metadata or None

    def update_collection_metadata(self, collection_name: str, metadata: dict) -> None:
        """Merge *metadata* into the table's schema metadata.

        Collections not yet materialised park the merge in the
        process-local pending dict, flushed into the table on first
        write — the read-merge-write rule applied at both levels.
        """
        table = self._open_table(collection_name)
        updates = {str(key): json.dumps(value) for key, value in metadata.items()}
        if table is None:
            self._intents.add(collection_name)
            merged = {**self._pending_metadata.get(collection_name, {}), **updates}
            self._pending_metadata[collection_name] = merged
            return
        self._write_table_metadata(collection_name, updates)

    # ── Generation counter (BM25 cache invalidation) ───────────────

    def bump_generation(self, collection_name: str) -> None:
        """Advance the process-local generation counter."""
        self._generations[collection_name] = self._generations.get(collection_name, 0) + 1

    def get_generation(self, collection_name: str) -> int:
        """Return the current generation counter (0 if never written)."""
        return self._generations.get(collection_name, 0)


# ── Factory ───────────────────────────────────────────────────────────


def build_vector_store_from_settings(settings: Any) -> LanceVectorStore:
    """Construct a :class:`LanceVectorStore` from resolved settings.

    Registered in ``core/vectordb/registry.py`` under ``"lancedb"``;
    called by ``compose.build_vector_store`` through the registry.
    """
    return LanceVectorStore(
        uri=settings.lancedb_uri,
        embedding_identity=embedding_identity_from_settings(settings),
    )
