"""Table-metadata seam and embedding-identity guard for the LanceDB store.

Collection metadata (profile tags and the embedding-identity triple)
lives in the table's durable Arrow schema metadata, written through
pylance's ``update_schema_metadata`` (read-merge-write).  The Python
SDK exposes neither ``update_config`` nor a post-hoc table-level
``replace_schema_metadata``; schema metadata is the durable
key-value bag that survives reconnection and adapter writes
(verified against lancedb 0.37.1 / pylance 10.0.0).  This module is
the LanceDB counterpart of the ChromaDB ``identity.py`` seam,
reusing its pure helpers so the legacy-stamp-then-reject rule stays
identical across backends.

The concrete store supplies ``_identity``, ``_pending_metadata``,
``_open_table`` and ``_get_connection``; this module owns the
read-merge-write and mismatch-rejection logic, plus the metadata
struct evolution below.  The store also supplies the dataset-epoch
helpers from :mod:`.lance_epoch` (``ensure_dataset_epoch`` and
``fresh_epoch_metadata``): every ``mode="overwrite"`` rebuild in
this module bakes a freshly minted epoch into the rewritten schema,
so one epoch always identifies one incarnation of the dataset.

LanceDB fixes the Arrow ``metadata`` struct on the first write, and
pylance 10 has no nested ``add_columns`` (dotted paths are rejected
by lance-core), so a later write introducing new metadata keys cannot
grow the struct in place.  :meth:`LanceTableMetadataMixin.evolve_metadata_fields`
therefore rebuilds the table: read every row, cast to the expanded
schema (old rows gain nulls — the same "key absent" state ChromaDB
gives a row without the key), and overwrite in place, carrying the
schema metadata (identity, profile tags) across the rewrite.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import pyarrow as pa

from .identity import (
    IDENTITY_INDEX_KEY,
    IDENTITY_MODEL_KEY,
    IDENTITY_PROVIDER_KEY,
    build_identity_mismatch_error,
    identities_match,
)

#: Schema-metadata key holding the OMRG-owned dataset epoch UUID
#: (see :mod:`.lance_epoch`).  Defined at this seam so both modules
#: share one constant without a circular import.
OMRG_EPOCH_KEY = "omrg_dataset_epoch"

__all__ = [
    "LanceTableMetadataMixin",
    "OMRG_EPOCH_KEY",
    "infer_arrow_type",
    "read_dataset_epoch",
    "read_table_metadata",
]

logger = logging.getLogger(__name__)

# Column the LlamaIndex adapter uses for user metadata.
_METADATA_COLUMN = "metadata"

# The adapter's top-level scalar columns; every schema the adapter or
# ``upsert_schema`` creates types them as string.
_ADAPTER_STRING_COLUMNS = frozenset({"id", "doc_id", "text"})


def decode_schema_metadata_entries(raw: dict) -> dict[str, str]:
    """Return schema-metadata entries as plain strings.

    Arrow returns bytes keys and values; some bindings return ``str``.
    Both readers below use this one tolerant rule so a ``str``-returning
    binding cannot break a metadata write with ``AttributeError``.
    """
    entries: dict[str, str] = {}
    for key, value in raw.items():
        name = key.decode() if isinstance(key, bytes) else key
        text = value.decode() if isinstance(value, bytes) else value
        entries[name] = text
    return entries


def read_table_metadata(table: Any) -> dict[str, Any]:
    """Return a table's schema-metadata bag with value types restored.

    Values are stored JSON-encoded so non-string profile values
    (ints, floats, bools) round-trip like ChromaDB metadata; a value
    that fails to decode falls back to the raw string.
    """
    decoded: dict[str, Any] = {}
    for name, text in decode_schema_metadata_entries(table.schema.metadata or {}).items():
        try:
            decoded[name] = json.loads(text)
        except (ValueError, TypeError):
            decoded[name] = text
    return decoded


def read_dataset_epoch(table: Any) -> str | None:
    """Return the dataset epoch stored in a table's schema metadata.

    Lives here (not in :mod:`.lance_epoch`) so the epoch read shares
    this module's tolerant decode and the import direction stays
    one-way: ``lance_epoch`` imports from this seam, never the
    reverse.  Duck-typed calls (``self.ensure_dataset_epoch``,
    ``self.fresh_epoch_metadata``) need no import at all.

    Args:
        table: An open LanceDB table handle.

    Returns:
        The epoch UUID string, or ``None`` when the table carries no
        epoch (absent, legacy, or externally recreated unmarked).
    """
    metadata = read_table_metadata(table)
    epoch = metadata.get(OMRG_EPOCH_KEY)
    return str(epoch) if epoch is not None else None


def metadata_field_names(table: Any) -> set[str]:
    """Return the field names inside the table's metadata struct.

    Tables without a ``metadata`` struct column (none the store or the
    adapter create, but a hand-made table could) yield an empty set, so
    every filter field folds to its absent-field constant instead of
    reaching the planner.
    """
    schema: pa.Schema = table.schema
    if _METADATA_COLUMN not in schema.names:
        return set()
    struct_type = schema.field(_METADATA_COLUMN).type
    if not pa.types.is_struct(struct_type):
        return set()
    return {field.name for field in struct_type}


def infer_arrow_type(values: list[Any]) -> pa.DataType:
    """Infer the Arrow type for a new metadata field from sample values.

    Follows the adapter's own inference shape: homogeneous bool →
    boolean, homogeneous int → int64, mixed int/float → float64,
    everything else (strings, mixed) → string.  An all-null sample
    defaults to string, matching how a null-typed field would be
    unusable for later writes.
    """
    non_null = [value for value in values if value is not None]
    if not non_null:
        return pa.string()
    if all(isinstance(value, bool) for value in non_null):
        return pa.bool_()
    if all(isinstance(value, int) and not isinstance(value, bool) for value in non_null):
        return pa.int64()
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in non_null):
        return pa.float64()
    return pa.string()


class LanceTableMetadataMixin:
    """Read-merge-write table metadata plus write/query identity guards.

    The concrete store supplies ``_identity``
    (:class:`~.identity.EmbeddingIdentity` or ``None``),
    ``_pending_metadata`` (the intent-collection parking dict),
    ``_open_table`` and ``_get_connection``.
    """

    # Supplied by the concrete store.
    _identity: Any
    _pending_metadata: dict[str, dict[str, str]]
    _open_table: Callable[[str], Any]
    _get_connection: Callable[[], Any]
    ensure_dataset_epoch: Callable[[str], None]
    fresh_epoch_metadata: Callable[[], dict[str, str]]

    def _read_table_metadata(self, table: Any) -> dict[str, Any]:
        """Return the table's metadata bag with types restored."""
        return read_table_metadata(table)

    def _write_table_metadata(self, name: str, updates: dict[str, str]) -> None:
        """Merge *updates* into the table's durable schema metadata.

        Opens a fresh table handle: LanceDB handles pin a version, so
        a handle opened before another write would read stale metadata.
        Skips the write when every value is already current, avoiding
        a new manifest version per no-op write.
        """
        table = self._get_connection().open_table(name)
        current = decode_schema_metadata_entries(table.schema.metadata or {})
        if all(current.get(key) == value for key, value in updates.items()):
            return
        table.to_lance().update_schema_metadata(updates, replace=False)

    def _stored_identity(self, table: Any) -> tuple[str | None, str | None, str | None]:
        """Return the ``(provider, model, index_identity)`` stored on a table."""
        metadata = self._read_table_metadata(table)
        return (
            metadata.get(IDENTITY_PROVIDER_KEY),
            metadata.get(IDENTITY_MODEL_KEY),
            metadata.get(IDENTITY_INDEX_KEY),
        )

    def _reject_identity_mismatch(
        self,
        collection_name: str,
        stored: tuple[str | None, str | None, str | None],
    ) -> None:
        """Raise unless the stored identity matches the active one."""
        identity = self._identity
        if identity is None or identities_match(stored, identity):
            return
        raise build_identity_mismatch_error(collection_name, stored, identity)

    def _reject_conflicting_identity(self, collection_name: str) -> None:
        """Shared guard body: reject a conflicting stored identity.

        Both write and query paths apply the same rule — no active
        identity, absent table, and legacy unstamped table pass; a
        stored identity that conflicts with the active one raises.
        """
        if self._identity is None:
            return
        table = self._open_table(collection_name)
        if table is None:
            return
        stored = self._stored_identity(table)
        if stored[0] is not None:
            self._reject_identity_mismatch(collection_name, stored)

    def _check_or_stamp_identity(self, collection_name: str) -> None:
        """Write-path rule: reject mismatches; stamping happens post-write.

        Legacy tables without a stored identity are stamped after the
        write creates/extends the table (see ``_flush_after_write``).
        The pre-write half of the rule also installs a dataset epoch
        on an existing unmarked table, so the next OMRG-controlled
        mutation marks it *before* its rows change.
        """
        self._reject_conflicting_identity(collection_name)
        self.ensure_dataset_epoch(collection_name)

    def _guard_query_identity(self, collection_name: str) -> None:
        """Query-path rule: reject mismatches before the query is issued.

        Legacy tables without a stored identity query normally;
        stamping never happens on the read path.
        """
        self._reject_conflicting_identity(collection_name)

    def _flush_after_write(self, collection_name: str) -> None:
        """Stamp identity and flush pending profile tags after a write.

        Applies the identity.py read-merge-write rule: existing keys
        such as profile tags are preserved because the merge happens
        server-side in ``update_schema_metadata``.  A table that still
        carries no dataset epoch — one the write just created, or a
        legacy table the row mutation already marked — mints one here:
        table creation is exactly when a new epoch is written, and the
        guarded metadata write keeps ordinary writes on epoched tables
        version-stable.
        """
        updates: dict[str, str] = {}
        pending = self._pending_metadata.pop(collection_name, None)
        if pending:
            updates.update(pending)
        identity = self._identity
        if identity is not None:
            updates[IDENTITY_PROVIDER_KEY] = json.dumps(identity.provider)
            updates[IDENTITY_MODEL_KEY] = json.dumps(identity.model)
            if identity.index_identity is not None:
                updates[IDENTITY_INDEX_KEY] = json.dumps(identity.index_identity)
        table = self._open_table(collection_name)
        if table is not None and read_dataset_epoch(table) is None:
            updates.update(self.fresh_epoch_metadata())
        if updates:
            self._write_table_metadata(collection_name, updates)

    # ── Metadata struct evolution ────────────────────────────────────

    def evolve_metadata_fields(
        self,
        collection_name: str,
        new_fields: dict[str, pa.DataType],
    ) -> bool:
        """Extend the table's metadata struct with *new_fields*.

        LanceDB fixes the struct on the first write and pylance 10 has
        no nested ``add_columns`` (dotted paths are rejected by
        lance-core), so this rebuilds the table: every row is read,
        cast to the expanded schema (old rows gain nulls — ChromaDB's
        "key absent" state), and written back with
        ``create_table(mode="overwrite")``.  The schema metadata bag
        (identity triple, profile tags) is carried across the rewrite,
        the table's version history restarts at the new write, and a
        freshly minted dataset epoch replaces the previous one — an
        overwrite rebuild is a new incarnation of the dataset.

        Args:
            collection_name: Table to evolve.
            new_fields: Field name → Arrow type for fields absent from
                the current struct.  Fields already present with a
                concrete type are skipped; a field locked null-only is
                upgraded to the batch's type.  An empty effective set
                is a no-op.

        Returns:
            ``True`` when the table was rewritten.

        Raises:
            ValueError: When the table exists but carries no ``metadata``
                struct column.  Neither the store nor the adapter creates
                such tables; a hand-made one cannot have its user-metadata
                struct grown, so the only remedy is to rebuild the
                collection through a store write.
        """
        table = self._open_table(collection_name)
        if table is None:
            # First write defines the struct from the batch itself.
            return False
        schema: pa.Schema = table.schema
        if _METADATA_COLUMN not in schema.names or not pa.types.is_struct(
            schema.field(_METADATA_COLUMN).type
        ):
            raise ValueError(
                f"Table {collection_name!r} has no metadata struct column, so its "
                "metadata fields cannot be grown. Rebuild the collection with a "
                "store write to attach one."
            )
        existing_types = {field.name: field.type for field in schema.field(_METADATA_COLUMN).type}
        # A field needs the rewrite when absent, or when it was locked
        # null-only and this batch carries a concrete type for it.
        missing = {
            name: field_type
            for name, field_type in new_fields.items()
            if name not in existing_types
            or (pa.types.is_null(existing_types[name]) and not pa.types.is_null(field_type))
        }
        if not missing:
            return False
        # Fresh handle: handles pin a version, and the read must see
        # the latest schema metadata so the rewrite carries it over.
        table = self._get_connection().open_table(collection_name)
        arrow = table.to_arrow()
        old_struct: pa.StructType = arrow.schema.field(_METADATA_COLUMN).type
        # An upgraded null-only field is replaced in place; genuinely
        # new fields are appended (a plain append of an upgrade would
        # duplicate the field name and fail struct construction).
        fields = [
            pa.field(field.name, missing[field.name]) if field.name in missing else field
            for field in old_struct
        ]
        existing_names = {field.name for field in old_struct}
        fields += [
            pa.field(name, missing[name]) for name in sorted(missing) if name not in existing_names
        ]
        expanded = pa.struct(fields)
        new_schema = pa.schema(
            [
                (pa.field(_METADATA_COLUMN, expanded) if field.name == _METADATA_COLUMN else field)
                for field in arrow.schema
            ],
            metadata={
                **decode_schema_metadata_entries(arrow.schema.metadata or {}),
                **self.fresh_epoch_metadata(),
            },
        )
        self._get_connection().create_table(
            collection_name, arrow.cast(new_schema), mode="overwrite"
        )
        logger.info(
            "Evolved metadata struct of %r: added %s",
            collection_name,
            sorted(missing),
        )
        return True

    def _widen_null_adapter_columns(self, collection_name: str) -> bool:
        """Re-type null-typed top-level adapter columns to string (TDR-012).

        The LlamaIndex adapter types a top-level column as Arrow Null when
        the first write carries None for it — reachable only for nodes
        without a SOURCE relationship, which the pipeline never produces.
        A Null-typed column then rejects every later typed write
        (``cannot cast field 'doc_id' from Utf8 to Null``), and LanceDB
        0.37 offers no in-place repair: ``alter_columns`` refuses the
        Null→Utf8 cast and the SDK has no ``add_column``. Following
        :meth:`evolve_metadata_fields`, the table is rebuilt with the
        column re-typed as string. A Null-typed column holds only nulls,
        so the re-type is lossless. The schema metadata bag (identity
        triple, profile tags) is carried across the rewrite, and a
        freshly minted dataset epoch replaces the previous one, as in
        :meth:`evolve_metadata_fields`.
        """
        table = self._open_table(collection_name)
        if table is None:
            return False
        widen = [
            field.name
            for field in table.schema
            if field.name in _ADAPTER_STRING_COLUMNS and pa.types.is_null(field.type)
        ]
        if not widen:
            return False
        # Fresh handle: handles pin a version; the rebuild must read the
        # latest schema so its metadata bag carries across the overwrite.
        table = self._get_connection().open_table(collection_name)
        arrow = table.to_arrow()
        new_schema = pa.schema(
            [
                (pa.field(field.name, pa.string()) if field.name in widen else field)
                for field in arrow.schema
            ],
            metadata={
                **decode_schema_metadata_entries(arrow.schema.metadata or {}),
                **self.fresh_epoch_metadata(),
            },
        )
        self._get_connection().create_table(
            collection_name, arrow.cast(new_schema), mode="overwrite"
        )
        logger.warning(
            "Widened null-typed column(s) %s in %r to string (TDR-012)",
            sorted(widen),
            collection_name,
        )
        return True
