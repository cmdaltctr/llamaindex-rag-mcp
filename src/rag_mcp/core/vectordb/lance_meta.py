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
read-merge-write and mismatch-rejection logic.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .identity import (
    IDENTITY_INDEX_KEY,
    IDENTITY_MODEL_KEY,
    IDENTITY_PROVIDER_KEY,
    build_identity_mismatch_error,
    identities_match,
)

__all__ = ["LanceTableMetadataMixin", "read_table_metadata"]


def read_table_metadata(table: Any) -> dict[str, Any]:
    """Return a table's schema-metadata bag with value types restored.

    Values are stored JSON-encoded so non-string profile values
    (ints, floats, bools) round-trip like ChromaDB metadata; a value
    that fails to decode falls back to the raw string.
    """
    raw = table.schema.metadata or {}
    decoded: dict[str, Any] = {}
    for key, value in raw.items():
        name = key.decode() if isinstance(key, bytes) else key
        text = value.decode() if isinstance(value, bytes) else value
        try:
            decoded[name] = json.loads(text)
        except (ValueError, TypeError):
            decoded[name] = text
    return decoded


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
        current = {
            key.decode(): value.decode() for key, value in (table.schema.metadata or {}).items()
        }
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

    def _check_or_stamp_identity(self, collection_name: str) -> None:
        """Write-path rule: reject mismatches; stamping happens post-write.

        Legacy tables without a stored identity are stamped after the
        write creates/extends the table (see ``_flush_after_write``).
        """
        if self._identity is None:
            return
        table = self._open_table(collection_name)
        if table is None:
            return
        stored = self._stored_identity(table)
        if stored[0] is not None:
            self._reject_identity_mismatch(collection_name, stored)

    def _guard_query_identity(self, collection_name: str) -> None:
        """Query-path rule: reject mismatches before the query is issued.

        Legacy tables without a stored identity query normally;
        stamping never happens on the read path.
        """
        if self._identity is None:
            return
        table = self._open_table(collection_name)
        if table is None:
            return
        stored = self._stored_identity(table)
        if stored[0] is not None:
            self._reject_identity_mismatch(collection_name, stored)

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
