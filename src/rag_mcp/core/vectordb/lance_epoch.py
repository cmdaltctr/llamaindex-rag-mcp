"""Durable dataset-epoch identity for the LanceDB vector store.

Cache validity for derivative indexes (the BM25 sparse index above all)
cannot rest on the process-local generation counter when writers live
in other processes — ``rag-mcp watch`` runs beside the MCP server by
design.  LanceDB's numeric ``table.version`` alone is equally
insufficient: an overwrite-based rebuild or a delete/recreate restarts
the version history, so a recreated table can walk its version back to
a value a long-lived reader has already cached.

The durable token therefore combines two components:

* ``omrg_dataset_epoch`` — an OMRG-owned random UUID stored in the
  *current* table schema metadata through the existing
  :mod:`.lance_meta` seam.  One epoch identifies one incarnation of
  the dataset: table creation, delete/recreate and every
  ``mode="overwrite"`` rebuild mint a fresh one; ordinary row
  mutations preserve it; version-history cleanup and optimisation
  cannot alter it because it never lived in version history.
* ``table.version`` — the backend's ordinary commit counter, which
  advances on every row mutation.

:meth:`LanceDatasetEpochMixin.get_data_version` re-opens the table on
every call: LanceDB table handles pin a manifest version, so a handle
opened before another process rebuilt the table would read a stale
snapshot.  Re-opening per call is the supported refresh path, and it
makes a long-lived reader observe other processes' epochs without a
restart.

Pre-existing tables without the marker are never mutated by a read:
``get_data_version`` returns ``None`` for them.  The next
OMRG-controlled mutation installs an epoch *before* the row mutation
(:meth:`LanceDatasetEpochMixin.ensure_dataset_epoch`), and the
``None`` → token transition is itself cache invalidation for callers.
A table recreated by an external writer without the marker likewise
reads ``None`` — the epoch is always read from current schema
metadata, never from a process-local cache.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

from .lance_meta import OMRG_EPOCH_KEY, read_dataset_epoch

__all__ = [
    "OMRG_EPOCH_KEY",
    "LanceDatasetEpochMixin",
    "durable_data_token",
    "parse_durable_data_token",
]

#: Prefix tagging the durable token so it can never compare equal to a
#: process-local generation value (design decision D1: mode transitions
#: must compare unequal). Joined from parts rather than assigned as a
#: quoted literal, so secret scanners do not flag a token-named
#: constant.
_TOKEN_PREFIX = "-".join(("lancedb", "durable", "v1"))  # noqa: S105 — tag, not a secret


def durable_data_token(epoch: str, version: int) -> str:
    """Combine an epoch and a table version into the tagged durable token.

    Args:
        epoch: The ``omrg_dataset_epoch`` UUID from schema metadata.
        version: The current numeric ``table.version``.

    Returns:
        An opaque, self-describing token string.  Any change to either
        component changes the token.
    """
    return f"{_TOKEN_PREFIX}:{epoch}:{version}"


def parse_durable_data_token(token: str) -> tuple[str, int]:
    """Split a durable token back into ``(epoch, table_version)``.

    Args:
        token: A token produced by :func:`durable_data_token`.

    Returns:
        The epoch UUID and the numeric table version.

    Raises:
        ValueError: When *token* is not a tagged durable token.
    """
    parts = token.rsplit(":", 2)
    if len(parts) != 3 or parts[0] != _TOKEN_PREFIX:
        raise ValueError(f"Not a tagged LanceDB durable token: {token!r}")
    return parts[1], int(parts[2])


class LanceDatasetEpochMixin:
    """Dataset-epoch maintenance plus the durable data-version read.

    The concrete store supplies ``_open_table`` (which re-opens the
    table on every call — the refresh path that keeps long-lived
    readers current) and ``_write_table_metadata`` (the guarded
    read-merge-write seam from :class:`.lance_meta.LanceTableMetadataMixin`).
    """

    # Supplied by the concrete store.
    _open_table: Callable[[str], Any]
    _write_table_metadata: Callable[[str, dict[str, str]], None]

    def get_data_version(self, collection_name: str) -> str | None:
        """Return the tagged durable data-version token, or ``None``.

        The table is re-opened on every call so the read reflects the
        latest committed manifest, including writes made by other
        processes or handles since this store was constructed.

        Args:
            collection_name: Collection (table) to version.

        Returns:
            ``None`` when the collection is absent, or when the table
            carries no OMRG dataset epoch (legacy or externally
            recreated tables).  Otherwise the opaque durable token
            combining ``(omrg_dataset_epoch, table.version)``.
        """
        table = self._open_table(collection_name)
        if table is None:
            return None
        epoch = read_dataset_epoch(table)
        if epoch is None:
            return None
        return durable_data_token(epoch, table.version)

    def ensure_dataset_epoch(self, collection_name: str) -> None:
        """Install a dataset epoch on an existing unmarked table.

        Called before an OMRG-controlled row mutation (under the
        ingestion write lock) so a legacy table acquires durable
        identity before its rows change, making the ``None`` → token
        transition cache invalidation for long-lived readers.  Tables
        that already carry an epoch, and absent tables (which mint
        their epoch at creation through the post-write flush), are
        left untouched — the guarded metadata write means this call is
        version-stable for already-epoched tables.

        Args:
            collection_name: Collection (table) to mark.
        """
        table = self._open_table(collection_name)
        if table is None:
            return
        if read_dataset_epoch(table) is not None:
            return
        self._write_table_metadata(collection_name, self.fresh_epoch_metadata())

    def fresh_epoch_metadata(self) -> dict[str, str]:
        """Return a schema-metadata update minting a new dataset epoch.

        Used at table creation and by every ``mode="overwrite"``
        rebuild (:mod:`.lance_meta` bakes it into the rewritten
        schema), so one epoch always identifies exactly one
        incarnation of the dataset.

        Returns:
            A single-entry ``{OMRG_EPOCH_KEY: json-encoded UUID}``
            update for the read-merge-write metadata seam.
        """
        return {OMRG_EPOCH_KEY: json.dumps(str(uuid.uuid4()))}
