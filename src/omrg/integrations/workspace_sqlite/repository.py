"""Standard-library SQLite implementation of the workspace repository.

This module is an integration leaf. It does not import ``omrg.core``; it
returns plain dictionaries that match the records in
``omrg.core.workspace.records``. Tests keep the duplicated status sets and
hash form in step with the core contract.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Collection, Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from omrg.integrations.workspace_sqlite import rows as codec
from omrg.integrations.workspace_sqlite.deletion import delete_finished_runs
from omrg.integrations.workspace_sqlite.pipeline_sql import (
    insert_pipeline,
    insert_revision,
    new_id,
    read_connection,
    write_transaction,
)
from omrg.integrations.workspace_sqlite.schema import (
    SCHEMA_MIGRATIONS,
    Migration,
    make_private_dirs,
    migrate,
    touch_private,
    validate_migrations,
)

TERMINAL_RUN_STATUSES: frozenset[str] = frozenset(
    {"succeeded", "failed", "cancelled", "interrupted"}
)
NONTERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"queued", "running", "cancelling"})
RUN_STATUSES: frozenset[str] = TERMINAL_RUN_STATUSES | NONTERMINAL_RUN_STATUSES
RUN_ORIGINS: frozenset[str] = frozenset({"submit", "repeat", "retry"})
PLUGIN_COMPATIBILITY: frozenset[str] = frozenset({"unchecked", "compatible", "incompatible"})

# Allowed status changes. Terminal states have no exit.
_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running"}) | TERMINAL_RUN_STATUSES,
    "running": frozenset({"cancelling"}) | TERMINAL_RUN_STATUSES,
    "cancelling": TERMINAL_RUN_STATUSES,
}

Record = codec.Record


def _default_clock() -> datetime:
    return datetime.now(UTC)


class SqliteWorkspaceRepository:
    """Workspace records in one SQLite file, separate from vector data.

    Each call opens a short-lived connection, so one instance is safe to use
    from several threads. Writes run in ``BEGIN IMMEDIATE`` transactions.

    Args:
        path: The workspace database file. Missing parent directories are
            created with owner-only permissions.
        clock: Returns the current time; injected for deterministic tests.
        migrations: Ordered schema migrations. Defaults to the shipped set.

    Raises:
        ValueError: If the migrations are not ordered from version 1.
        WorkspaceSchemaError: If the database cannot be opened or upgraded.
    """

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], datetime] = _default_clock,
        migrations: Sequence[Migration] = SCHEMA_MIGRATIONS,
    ) -> None:
        validate_migrations(migrations)
        self.path = Path(path)
        self._clock = clock
        make_private_dirs(self.path.parent)
        touch_private(self.path)
        migrate(self.path, migrations, self._clock())

    # --- infrastructure --------------------------------------------------

    def _now(self) -> str:
        return self._clock().isoformat()

    def _read(self) -> AbstractContextManager[sqlite3.Connection]:
        return read_connection(self.path)

    def _write(self) -> AbstractContextManager[sqlite3.Connection]:
        """Return a connection inside one transaction; roll back on any error."""
        return write_transaction(self.path)

    @staticmethod
    def _one(conn: sqlite3.Connection, sql: str, key: str, label: str) -> sqlite3.Row:
        row = conn.execute(sql, (key,)).fetchone()
        if row is None:
            raise KeyError(f"unknown {label}: {key}")
        return row

    # --- pipelines and revisions ----------------------------------------

    def create_pipeline(self, title: str, *, layout: Mapping[str, Any] | None = None) -> Record:
        """Create a pipeline with no revision yet."""
        pipeline_id, now, layout_json = new_id(), self._now(), codec.dumps(dict(layout or {}))
        with self._write() as conn:
            insert_pipeline(conn, pipeline_id, title, layout_json, now)
        return self.get_pipeline(pipeline_id)

    def get_pipeline(self, pipeline_id: str) -> Record:
        """Return one pipeline."""
        with self._read() as conn:
            sql = "SELECT * FROM pipelines WHERE pipeline_id = ?"
            return codec.pipeline_record(self._one(conn, sql, pipeline_id, "pipeline"))

    def list_pipelines(self) -> list[Record]:
        """Return all pipelines in creation order."""
        with self._read() as conn:
            rows = conn.execute("SELECT * FROM pipelines ORDER BY rowid").fetchall()
        return [codec.pipeline_record(row) for row in rows]

    def save_layout(self, pipeline_id: str, layout: Mapping[str, Any]) -> Record:
        """Replace the presentation layout without creating a revision."""
        layout_json, now = codec.dumps(dict(layout)), self._now()
        with self._write() as conn:
            cursor = conn.execute(
                "UPDATE pipelines SET layout_json = ?, updated_at = ? WHERE pipeline_id = ?",
                (layout_json, now, pipeline_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"unknown pipeline: {pipeline_id}")
        return self.get_pipeline(pipeline_id)

    def save_revision(
        self, pipeline_id: str, document: Mapping[str, Any], *, schema_version: int
    ) -> Record:
        """Store an execution document and make it the current revision.

        Identical content returns the existing revision and only moves the
        pipeline's current-revision pointer back to it.

        Raises:
            KeyError: If the pipeline does not exist.
            ValueError: If the document is not JSON-compatible, or identical
                content was stored under another schema version.
        """
        document_json = codec.dumps(dict(document))
        now = self._now()
        with self._write() as conn:
            revision_id = insert_revision(conn, pipeline_id, document_json, schema_version, now)
        return self.get_revision(revision_id)

    def get_revision(self, revision_id: str) -> Record:
        """Return one revision."""
        with self._read() as conn:
            sql = "SELECT * FROM pipeline_revisions WHERE revision_id = ?"
            return codec.revision_record(self._one(conn, sql, revision_id, "revision"))

    def list_revisions(self, pipeline_id: str) -> list[Record]:
        """Return a pipeline's revisions by revision number."""
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM pipeline_revisions WHERE pipeline_id = ? ORDER BY revision_number",
                (pipeline_id,),
            ).fetchall()
        return [codec.revision_record(row) for row in rows]

    # --- runs and events -------------------------------------------------

    def create_run(
        self,
        revision_id: str,
        *,
        settings: Mapping[str, Any],
        resources: Mapping[str, Any],
        inputs: Mapping[str, Any],
        origin: str = "submit",
        source_run_id: str | None = None,
    ) -> Record:
        """Admit a queued run of a revision and write event sequence 1.

        Raises:
            KeyError: If the revision or source run does not exist.
            ValueError: If the origin is unknown or a value is not JSON.
        """
        if origin not in RUN_ORIGINS:
            raise ValueError(f"unknown run origin: {origin}")
        payload = (
            codec.dumps(dict(settings)),
            codec.dumps(dict(resources)),
            codec.dumps(dict(inputs)),
        )
        event_json = codec.dumps({"status": "queued"})
        run_id, now = new_id(), self._now()
        with self._write() as conn:
            revision = self._one(
                conn,
                "SELECT pipeline_id, content_hash FROM pipeline_revisions WHERE revision_id = ?",
                revision_id,
                "revision",
            )
            if source_run_id is not None:
                self._one(conn, "SELECT 1 FROM runs WHERE run_id = ?", source_run_id, "run")
            conn.execute(
                "INSERT INTO runs VALUES "
                "(?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, NULL, NULL, 1, ?, NULL, NULL)",
                (
                    run_id,
                    revision["pipeline_id"],
                    revision_id,
                    revision["content_hash"],
                    origin,
                    source_run_id,
                    *payload,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO run_events VALUES (?, 1, 'run.status', NULL, NULL, ?, ?)",
                (run_id, event_json, now),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> Record:
        """Return one run."""
        with self._read() as conn:
            return codec.run_record(
                self._one(conn, "SELECT * FROM runs WHERE run_id = ?", run_id, "run")
            )

    def list_runs(
        self,
        *,
        pipeline_id: str | None = None,
        statuses: Collection[str] | None = None,
        limit: int | None = None,
    ) -> list[Record]:
        """Return runs, newest first, optionally filtered.

        Raises:
            ValueError: If a status filter names an unknown status.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if pipeline_id is not None:
            clauses.append("pipeline_id = ?")
            params.append(pipeline_id)
        if statuses is not None:
            unknown = set(statuses) - RUN_STATUSES
            if unknown:
                raise ValueError(f"unknown run statuses: {sorted(unknown)}")
            clauses.append(f"status IN ({', '.join('?' * len(statuses))})")
            params.extend(statuses)
        sql = "SELECT * FROM runs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY rowid DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._read() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [codec.run_record(row) for row in rows]

    def record_update(
        self,
        run_id: str,
        *,
        kind: str,
        summary: Mapping[str, Any],
        status: str | None = None,
        node_id: str | None = None,
        unit_id: str | None = None,
        failure: Mapping[str, Any] | None = None,
        result_ref: str | None = None,
    ) -> tuple[Record, Record]:
        """Apply a run update and append its event in one transaction.

        Entering ``running`` sets ``started_at``; entering a terminal status
        sets ``finished_at``. A terminal run accepts no further updates.

        Raises:
            KeyError: If the run does not exist.
            ValueError: If the kind is empty, the transition is not allowed,
                the run is terminal, or a value is not JSON-compatible.
        """
        if not kind:
            raise ValueError("event kind must not be empty")
        if status is not None and status not in RUN_STATUSES:
            raise ValueError(f"unknown run status: {status}")
        summary_json = codec.dumps(dict(summary))
        failure_json = None if failure is None else codec.dumps(dict(failure))
        now = self._now()
        with self._write() as conn:
            row = self._one(
                conn, "SELECT status, last_sequence FROM runs WHERE run_id = ?", run_id, "run"
            )
            current = row["status"]
            if current in TERMINAL_RUN_STATUSES:
                raise ValueError(f"run {run_id} is {current} and accepts no updates")
            if status is not None and status not in _TRANSITIONS[current]:
                raise ValueError(f"run {run_id} cannot move from {current} to {status}")
            sequence = row["last_sequence"] + 1
            conn.execute(
                "UPDATE runs SET last_sequence = ?, status = COALESCE(?, status), "
                "failure_json = COALESCE(?, failure_json), "
                "result_ref = COALESCE(?, result_ref), "
                "started_at = CASE WHEN ? = 'running' THEN ? ELSE started_at END, "
                "finished_at = CASE WHEN ? THEN ? ELSE finished_at END "
                "WHERE run_id = ?",
                (
                    sequence,
                    status,
                    failure_json,
                    result_ref,
                    status,
                    now,
                    status in TERMINAL_RUN_STATUSES,
                    now,
                    run_id,
                ),
            )
            conn.execute(
                "INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, sequence, kind, node_id, unit_id, summary_json, now),
            )
            run = codec.run_record(
                conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            )
        event = {
            "run_id": run_id,
            "sequence": sequence,
            "kind": kind,
            "node_id": node_id,
            "unit_id": unit_id,
            "summary": codec.loads(summary_json),
            "created_at": now,
        }
        return run, event

    def list_events(
        self, run_id: str, *, after_sequence: int = 0, limit: int | None = None
    ) -> list[Record]:
        """Return a run's events after a sequence number, in order.

        Raises:
            KeyError: If the run does not exist.
        """
        sql = "SELECT * FROM run_events WHERE run_id = ? AND sequence > ? ORDER BY sequence"
        params: list[Any] = [run_id, int(after_sequence)]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._read() as conn:
            self._one(conn, "SELECT 1 FROM runs WHERE run_id = ?", run_id, "run")
            rows = conn.execute(sql, params).fetchall()
        return [codec.event_record(row) for row in rows]

    def delete_runs(self, run_ids: Collection[str]) -> dict[str, int]:
        """Delete finished runs and their events in one transaction.

        Pipelines, revisions and plugin registrations stay.

        Raises:
            KeyError: If a run does not exist. Nothing is deleted.
            ValueError: If a run is active, or a kept run refers to it as
                its retry source. Nothing is deleted.
        """
        with self._write() as conn:
            return delete_finished_runs(conn, run_ids, TERMINAL_RUN_STATUSES)

    # --- plugin registrations -------------------------------------------

    def register_plugin(
        self,
        name: str,
        *,
        manifest_ref: str,
        executable_ref: str,
        manifest_hash: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> Record:
        """Record or replace an approved plugin; compatibility resets.

        ``detail`` (for example the approved executable identity) is stored
        in the same write; without it the detail resets to ``{}``.
        """
        now, detail_json = self._now(), codec.dumps(dict(detail or {}))
        with self._write() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO plugin_registrations "
                "VALUES (?, ?, ?, ?, 'unchecked', ?, ?, NULL)",
                (name, manifest_ref, executable_ref, manifest_hash, detail_json, now),
            )
        return self.get_plugin(name)

    def unregister_plugin(self, name: str) -> Record:
        """Remove a plugin registration and return the removed record.

        Raises:
            KeyError: If the plugin is not registered.
        """
        record = self.get_plugin(name)
        with self._write() as conn:
            cursor = conn.execute("DELETE FROM plugin_registrations WHERE name = ?", (name,))
            if cursor.rowcount == 0:
                raise KeyError(f"unknown plugin: {name}")
        return record

    def set_plugin_compatibility(
        self, name: str, status: str, *, detail: Mapping[str, Any] | None = None
    ) -> Record:
        """Record the result of a plugin compatibility check.

        Raises:
            KeyError: If the plugin is not registered.
            ValueError: If the status is unknown.
        """
        if status not in PLUGIN_COMPATIBILITY:
            raise ValueError(f"unknown compatibility status: {status}")
        detail_json, now = codec.dumps(dict(detail or {})), self._now()
        with self._write() as conn:
            cursor = conn.execute(
                "UPDATE plugin_registrations SET compatibility_status = ?, detail_json = ?, "
                "checked_at = ? WHERE name = ?",
                (status, detail_json, now, name),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"unknown plugin: {name}")
        return self.get_plugin(name)

    def get_plugin(self, name: str) -> Record:
        """Return one plugin registration."""
        with self._read() as conn:
            sql = "SELECT * FROM plugin_registrations WHERE name = ?"
            return codec.plugin_record(self._one(conn, sql, name, "plugin"))

    def list_plugins(self) -> list[Record]:
        """Return all plugin registrations by name."""
        with self._read() as conn:
            rows = conn.execute("SELECT * FROM plugin_registrations ORDER BY name").fetchall()
        return [codec.plugin_record(row) for row in rows]
