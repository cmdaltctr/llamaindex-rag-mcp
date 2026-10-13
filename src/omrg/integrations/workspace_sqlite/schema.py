"""Versioned schema, backups and owner-only files for the workspace database.

The migrations touch application records only. They never open or migrate a
vector store.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

# "OMRW" in ASCII. It marks a database file as an OMRG workspace.
APPLICATION_ID = 0x4F4D5257

Migration = tuple[int, Sequence[str]]

_IMMUTABLE = "pipeline revisions are immutable"

SCHEMA_MIGRATIONS: tuple[Migration, ...] = (
    (
        1,
        (
            """CREATE TABLE pipelines (
                pipeline_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                current_revision_id TEXT,
                layout_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE pipeline_revisions (
                revision_id TEXT PRIMARY KEY,
                pipeline_id TEXT NOT NULL REFERENCES pipelines(pipeline_id),
                revision_number INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                document_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (pipeline_id, content_hash),
                UNIQUE (pipeline_id, revision_number)
            )""",
            f"""CREATE TRIGGER pipeline_revisions_no_update
                BEFORE UPDATE ON pipeline_revisions
                BEGIN SELECT RAISE(ABORT, '{_IMMUTABLE}'); END""",
            f"""CREATE TRIGGER pipeline_revisions_no_delete
                BEFORE DELETE ON pipeline_revisions
                BEGIN SELECT RAISE(ABORT, '{_IMMUTABLE}'); END""",
            """CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                pipeline_id TEXT NOT NULL REFERENCES pipelines(pipeline_id),
                revision_id TEXT NOT NULL REFERENCES pipeline_revisions(revision_id),
                graph_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                origin TEXT NOT NULL,
                source_run_id TEXT REFERENCES runs(run_id),
                settings_json TEXT NOT NULL,
                resources_json TEXT NOT NULL,
                inputs_json TEXT NOT NULL,
                failure_json TEXT,
                result_ref TEXT,
                last_sequence INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            )""",
            "CREATE INDEX runs_by_status ON runs (status)",
            "CREATE INDEX runs_by_pipeline ON runs (pipeline_id)",
            """CREATE TABLE run_events (
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                sequence INTEGER NOT NULL,
                kind TEXT NOT NULL,
                node_id TEXT,
                unit_id TEXT,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence)
            )""",
            """CREATE TABLE plugin_registrations (
                name TEXT PRIMARY KEY,
                manifest_ref TEXT NOT NULL,
                executable_ref TEXT NOT NULL,
                manifest_hash TEXT,
                compatibility_status TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                checked_at TEXT
            )""",
        ),
    ),
)


class WorkspaceSchemaError(RuntimeError):
    """Raised when the workspace database cannot be opened or upgraded safely."""


def validate_migrations(migrations: Sequence[Migration]) -> None:
    """Check that migration versions run 1, 2, 3 ... without gaps.

    Args:
        migrations: The ordered migrations.

    Raises:
        ValueError: If the versions are empty, unordered or have gaps.
    """
    versions = [version for version, _ in migrations]
    if versions != list(range(1, len(versions) + 1)):
        raise ValueError(f"migration versions must be 1..n in order, got {versions}")


def make_private_dirs(directory: Path) -> None:
    """Create missing directories with owner-only permissions.

    Existing directories keep their permissions, because the operator may
    have chosen a shared parent.

    Args:
        directory: The directory that must exist.
    """
    missing: list[Path] = []
    current = directory
    while not current.exists():
        missing.append(current)
        current = current.parent
    for path in reversed(missing):
        path.mkdir(mode=0o700)
        os.chmod(path, 0o700)


def touch_private(path: Path) -> None:
    """Create a file with owner-only permissions, or tighten an existing one.

    Args:
        path: The file path.
    """
    if not path.exists():
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    os.chmod(path, 0o600)


def connect(path: Path) -> sqlite3.Connection:
    """Open a connection in autocommit mode with foreign keys enforced.

    Callers start explicit transactions with ``BEGIN IMMEDIATE``.

    Args:
        path: The database file.

    Returns:
        An open connection with ``sqlite3.Row`` rows.
    """
    conn = sqlite3.connect(path, isolation_level=None, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _backup(conn: sqlite3.Connection, path: Path, current: int, target: int, now: str) -> Path:
    """Copy the database to an owner-only backup file next to it."""
    stamp = now.replace(":", "").replace("-", "").replace("+", "_")
    backup_path = path.with_name(f"{path.name}.v{current}-to-v{target}.{stamp}.bak")
    touch_private(backup_path)
    target_conn = sqlite3.connect(backup_path)
    try:
        conn.backup(target_conn)
    finally:
        target_conn.close()
    return backup_path


def migrate(path: Path, migrations: Sequence[Migration], now: datetime) -> None:
    """Bring the database at ``path`` to the latest schema version.

    An existing database is backed up before any change. All pending
    migrations run in one transaction; on failure the transaction rolls back
    and the original records stay unchanged.

    Args:
        path: The workspace database file.
        migrations: Ordered migrations, validated by ``validate_migrations``.
        now: The time used to name a backup file.

    Raises:
        WorkspaceSchemaError: If the file is not an OMRG workspace, has a
            newer schema, or a migration fails.
    """
    target = migrations[-1][0]
    conn = connect(path)
    try:
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        app_id = int(conn.execute("PRAGMA application_id").fetchone()[0])
        tables = conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
        if tables and app_id != APPLICATION_ID:
            raise WorkspaceSchemaError(f"{path} is not an OMRG workspace database")
        if current > target:
            raise WorkspaceSchemaError(
                f"{path} has schema version {current}, newer than supported {target}"
            )
        if current == target:
            return
        backup_path = _backup(conn, path, current, target, now.isoformat()) if current else None
        try:
            conn.execute("BEGIN IMMEDIATE")
            for version, statements in migrations:
                if version <= current:
                    continue
                for statement in statements:
                    conn.execute(statement)
            conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            conn.execute(f"PRAGMA user_version = {int(target)}")
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            conn.execute("ROLLBACK")
            where = f"; backup at {backup_path}" if backup_path else ""
            raise WorkspaceSchemaError(
                f"schema upgrade v{current} to v{target} failed and was rolled back; "
                f"original records unchanged{where}: {exc}"
            ) from exc
    finally:
        conn.close()
