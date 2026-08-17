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
struct evolution below.

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

__all__ = [
    "LanceTableMetadataMixin",
    "infer_arrow_type",
    "read_table_metadata",
]

logger = logging.getLogger(__name__)

# Column the LlamaIndex adapter uses for user metadata.
_METADATA_COLUMN = "metadata"


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
        """
        self._reject_conflicting_identity(collection_name)

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
        server-side in ``update_schema_metadata``.
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
        and the table's version history restarts at the new write.

        Args:
            collection_name: Table to evolve.
            new_fields: Field name → Arrow type for fields absent from
                the current struct.  Fields already present are
                skipped; an empty effective set is a no-op.

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
        existing = metadata_field_names(table)
        missing = {
            name: field_type for name, field_type in new_fields.items() if name not in existing
        }
        if not missing:
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
        # Fresh handle: handles pin a version, and the read must see
        # the latest schema metadata so the rewrite carries it over.
        table = self._get_connection().open_table(collection_name)
        arrow = table.to_arrow()
        old_struct: pa.StructType = arrow.schema.field(_METADATA_COLUMN).type
        expanded = pa.struct(
            list(old_struct) + [pa.field(name, missing[name]) for name in sorted(missing)]
        )
        new_schema = pa.schema(
            [
                (pa.field(_METADATA_COLUMN, expanded) if field.name == _METADATA_COLUMN else field)
                for field in arrow.schema
            ],
            metadata=arrow.schema.metadata,
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
