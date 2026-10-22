"""SQLite store for user profiles and the pipelines they own.

This module is an integration leaf. It does not import ``omrs.core``; it
returns plain dictionaries that match ``omrs.core.workspace.records.ProfileRecord``.

Two classes share the ``profiles`` table:

* :class:`SqliteProfileRepository` creates, renames and deletes profiles. The
  web server uses it.
* :class:`SqliteProfileCatalogue` only reads. Every process that resolves a
  collection tag uses it.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from omrs.integrations.workspace_sqlite import rows as codec
from omrs.integrations.workspace_sqlite.pipeline_sql import (
    insert_pipeline,
    insert_revision,
    new_id,
    read_connection,
    write_transaction,
)
from omrs.integrations.workspace_sqlite.schema import (
    APPLICATION_ID,
    SCHEMA_MIGRATIONS,
    WorkspaceSchemaError,
)

Record = codec.Record

SLOTS: tuple[str, ...] = ("ingest", "search", "answer")
BASES: tuple[str, ...] = ("documents", "codebase")
# The id column of each slot. The names are fixed here, never taken from a caller.
_SLOT_COLUMNS: dict[str, str] = {slot: f"{slot}_pipeline_id" for slot in SLOTS}
_RESERVED_IDS = frozenset({"documents", "codebase", "hybrid"})
_MAX_ID = 64


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _slug(title: str) -> str:
    """Return the id stem for a title: lower case ``a-z0-9`` runs joined by ``-``."""
    stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:_MAX_ID].strip("-")
    return stem or "profile"


def _candidate(stem: str, number: int) -> str:
    """Return ``stem`` for number 1, else ``stem-<number>`` inside the length limit."""
    if number == 1:
        return stem
    suffix = f"-{number}"
    return stem[: _MAX_ID - len(suffix)].strip("-") + suffix


def _clean_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        raise ValueError("A profile needs a title that is not empty.")
    return cleaned


class SqliteProfileRepository:
    """Create, rename and delete user profiles in the workspace database.

    The database must already be migrated: construct
    ``SqliteWorkspaceRepository`` for the same file first. Each call opens a
    short-lived connection, so one instance is safe to use from several threads.

    Args:
        path: The workspace database file.
        clock: Returns the current time; injected for deterministic tests.
    """

    def __init__(self, path: Path, *, clock: Callable[[], datetime] = _default_clock) -> None:
        self.path = Path(path)
        self._clock = clock

    def _now(self) -> str:
        return self._clock().isoformat()

    def create_profile(
        self,
        title: str,
        *,
        base_profile: str,
        slots: Mapping[str, Mapping[str, Any] | str | None],
        schema_version: int,
        description: str = "",
        layouts: Mapping[str, Mapping[str, Any]] | None = None,
        embedding: tuple[str, str, int | None] | None = None,
    ) -> Record:
        """Create a profile, its pipelines and their first revisions at once.

        See ``omrs.core.workspace.ProfileRepository.create_profile``.
        """
        title = _clean_title(title)
        if base_profile not in BASES:
            raise ValueError(f"The base profile must be one of {', '.join(BASES)}.")
        if set(slots) != set(SLOTS):
            raise ValueError(f"A profile needs exactly these slots: {', '.join(SLOTS)}.")
        documents = {
            slot: codec.dumps(dict(value))
            for slot, value in slots.items()
            if isinstance(value, Mapping)
        }
        layout_json = {slot: codec.dumps(dict((layouts or {}).get(slot) or {})) for slot in SLOTS}
        provider, model, dimensions = embedding or (None, None, None)
        now = self._now()
        try:
            with write_transaction(self.path) as conn:
                pipeline_ids = {
                    slot: self._slot_pipeline(
                        conn, slot, slots[slot], documents, layout_json[slot], schema_version, now
                    )
                    for slot in SLOTS
                }
                profile_id = self._free_id(conn, _slug(title))
                conn.execute(
                    "INSERT INTO profiles (profile_id, title, description, base_profile, "
                    "ingest_pipeline_id, search_pipeline_id, answer_pipeline_id, "
                    "created_at, updated_at, embed_provider, embed_model, embed_dimensions) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        profile_id,
                        title,
                        description,
                        base_profile,
                        pipeline_ids["ingest"],
                        pipeline_ids["search"],
                        pipeline_ids["answer"],
                        now,
                        now,
                        provider,
                        model,
                        dimensions,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A pipeline fills one slot of one profile only: {exc}") from exc
        return self.get_profile(profile_id)

    @staticmethod
    def _slot_pipeline(
        conn: sqlite3.Connection,
        slot: str,
        value: Mapping[str, Any] | str | None,
        documents: Mapping[str, str],
        layout_json: str,
        schema_version: int,
        now: str,
    ) -> str:
        """Return the pipeline id of one slot, creating the pipeline when needed."""
        if isinstance(value, str):
            row = conn.execute("SELECT 1 FROM pipelines WHERE pipeline_id = ?", (value,)).fetchone()
            if row is None:
                raise KeyError(f"unknown pipeline: {value}")
            return value
        pipeline_id = new_id()
        insert_pipeline(conn, pipeline_id, slot.capitalize(), layout_json, now)
        if value is not None:
            insert_revision(conn, pipeline_id, documents[slot], schema_version, now)
        return pipeline_id

    @staticmethod
    def _free_id(conn: sqlite3.Connection, stem: str) -> str:
        """Return the first id from the stem that is not reserved or taken.

        Archived profiles keep their rows, so their ids stay taken.
        """
        number = 1
        while True:
            candidate = _candidate(stem, number)
            taken = conn.execute(
                "SELECT 1 FROM profiles WHERE profile_id = ?", (candidate,)
            ).fetchone()
            if candidate not in _RESERVED_IDS and taken is None:
                return candidate
            number += 1

    def get_profile(self, profile_id: str) -> Record:
        """Return one profile, deleted or not."""
        with read_connection(self.path) as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE profile_id = ?", (profile_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown profile: {profile_id}")
        return codec.profile_record(row)

    def list_profiles(self, *, include_archived: bool = False) -> list[Record]:
        """Return profiles in creation order; deleted ones only on request."""
        sql = "SELECT * FROM profiles ORDER BY rowid"
        if not include_archived:
            sql = "SELECT * FROM profiles WHERE archived_at IS NULL ORDER BY rowid"
        with read_connection(self.path) as conn:
            rows = conn.execute(sql).fetchall()
        return [codec.profile_record(row) for row in rows]

    def update_profile(
        self, profile_id: str, *, title: str | None = None, description: str | None = None
    ) -> Record:
        """Change the title or the description. The id never changes."""
        new_title = None if title is None else _clean_title(title)
        with write_transaction(self.path) as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE profile_id = ?", (profile_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown profile: {profile_id}")
            conn.execute(
                "UPDATE profiles SET title = ?, description = ?, updated_at = ? "
                "WHERE profile_id = ?",
                (
                    row["title"] if new_title is None else new_title,
                    row["description"] if description is None else description,
                    self._now(),
                    profile_id,
                ),
            )
        return self.get_profile(profile_id)

    def set_profile_embedding(
        self,
        profile_id: str,
        *,
        provider: str | None,
        model: str | None,
        dimensions: int | None,
    ) -> Record:
        """Save the embedding choice. Both names set, or both ``None`` for the default."""
        if (provider is None) != (model is None):
            raise ValueError("Set the provider and the model together, or neither.")
        with write_transaction(self.path) as conn:
            cursor = conn.execute(
                "UPDATE profiles SET embed_provider = ?, embed_model = ?, "
                "embed_dimensions = ?, updated_at = ? WHERE profile_id = ?",
                (
                    provider,
                    model,
                    None if provider is None else dimensions,
                    self._now(),
                    profile_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"unknown profile: {profile_id}")
        return self.get_profile(profile_id)

    def archive_profile(self, profile_id: str) -> Record:
        """Soft-delete a profile. Archiving twice keeps the first time."""
        now = self._now()
        with write_transaction(self.path) as conn:
            cursor = conn.execute(
                "UPDATE profiles SET archived_at = ?, updated_at = ? "
                "WHERE profile_id = ? AND archived_at IS NULL",
                (now, now, profile_id),
            )
            if cursor.rowcount == 0:
                known = conn.execute(
                    "SELECT 1 FROM profiles WHERE profile_id = ?", (profile_id,)
                ).fetchone()
                if known is None:
                    raise KeyError(f"unknown profile: {profile_id}")
        return self.get_profile(profile_id)

    def find_profile_by_pipeline(self, pipeline_id: str) -> tuple[Record, str] | None:
        """Return the profile and the slot a pipeline fills, or ``None``."""
        with read_connection(self.path) as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE ingest_pipeline_id = ?1 "
                "OR search_pipeline_id = ?1 OR answer_pipeline_id = ?1",
                (pipeline_id,),
            ).fetchone()
        if row is None:
            return None
        slot = next(s for s, column in _SLOT_COLUMNS.items() if row[column] == pipeline_id)
        return codec.profile_record(row), slot


class SqliteProfileCatalogue:
    """Read user profiles and their current pipeline graphs.

    This is the lookup that profile resolution uses in every process. It opens
    the database read-only (``mode=ro``). It never creates, migrates or writes
    the file, so it is safe in a process that does not own the workspace.

    A file with a schema older than the profiles table, or an empty file,
    holds no user profiles: every read answers "none". A newer schema, a file
    that is not an OMRS workspace, or a missing file raises
    ``WorkspaceSchemaError`` with the path.

    Args:
        path: The workspace database file.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a read-only connection after the schema checks pass.

        Raises:
            WorkspaceSchemaError: If the file is missing, not an OMRS
                workspace, or has a newer schema.
        """
        try:
            conn = sqlite3.connect(
                f"{self.path.resolve().as_uri()}?mode=ro", uri=True, timeout=30.0
            )
        except sqlite3.Error as exc:
            raise WorkspaceSchemaError(
                f"cannot read the workspace database {self.path}: {exc}"
            ) from exc
        conn.row_factory = sqlite3.Row
        try:
            try:
                version = int(conn.execute("PRAGMA user_version").fetchone()[0])
                app_id = int(conn.execute("PRAGMA application_id").fetchone()[0])
                tables = conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
            except sqlite3.DatabaseError as exc:
                raise WorkspaceSchemaError(
                    f"{self.path} is not an OMRS workspace database"
                ) from exc
            if tables and app_id != APPLICATION_ID:
                raise WorkspaceSchemaError(f"{self.path} is not an OMRS workspace database")
            latest = SCHEMA_MIGRATIONS[-1][0]
            if version > latest:
                raise WorkspaceSchemaError(
                    f"{self.path} has schema version {version}, newer than supported {latest}"
                )
            yield conn
        finally:
            conn.close()

    def _fetch(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """Run a read and return the rows; no rows when the profiles table is absent."""
        with self.connection() as conn:
            has_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'profiles'"
            ).fetchone()
            return conn.execute(sql, params).fetchall() if has_table else []

    def get_profile(self, profile_id: str) -> Record | None:
        """Return the profile record, deleted or not, or ``None`` when unknown."""
        rows = self._fetch("SELECT * FROM profiles WHERE profile_id = ?", (profile_id,))
        return codec.profile_record(rows[0]) if rows else None

    def list_profiles(self) -> list[Record]:
        """Return the profiles that are not deleted, in creation order."""
        rows = self._fetch("SELECT * FROM profiles WHERE archived_at IS NULL ORDER BY rowid")
        return [codec.profile_record(row) for row in rows]

    def slot_revision(self, profile_id: str, slot: str) -> Record | None:
        """Return the current revision of one slot pipeline, or ``None``.

        ``None`` means the profile or the slot is unknown, or the pipeline has
        no saved revision.
        """
        if slot not in SLOTS:
            return None
        rows = self._fetch(
            "SELECT r.* FROM profiles p "
            "JOIN pipelines pl ON pl.pipeline_id = CASE ?2 "
            "WHEN 'ingest' THEN p.ingest_pipeline_id "
            "WHEN 'search' THEN p.search_pipeline_id "
            "ELSE p.answer_pipeline_id END "
            "JOIN pipeline_revisions r ON r.revision_id = pl.current_revision_id "
            "WHERE p.profile_id = ?1",
            (profile_id, slot),
        )
        return codec.revision_record(rows[0]) if rows else None

    def slot_document(self, profile_id: str, slot: str) -> dict[str, Any] | None:
        """Return the current graph document of one slot pipeline, or ``None``."""
        revision = self.slot_revision(profile_id, slot)
        return None if revision is None else revision["document"]
