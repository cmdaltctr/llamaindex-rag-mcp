"""SQL shared by the pipeline repository and the profile store.

A profile is created together with its pipelines and their first revisions in
one transaction, so both stores use the same insert code. This module is an
integration leaf and does not import ``omrs.core``.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from omrs.integrations.workspace_sqlite.schema import connect


def new_id() -> str:
    """Return a new random identifier."""
    return uuid.uuid4().hex


@contextmanager
def read_connection(path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a short-lived connection for reads."""
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def write_transaction(path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a connection inside one ``BEGIN IMMEDIATE`` transaction.

    Any error rolls the transaction back before it propagates.
    """
    conn = connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()


def insert_pipeline(
    conn: sqlite3.Connection, pipeline_id: str, title: str, layout_json: str, now: str
) -> None:
    """Insert a pipeline with no revision yet."""
    conn.execute(
        "INSERT INTO pipelines VALUES (?, ?, NULL, ?, ?, ?)",
        (pipeline_id, title, layout_json, now, now),
    )


def insert_revision(
    conn: sqlite3.Connection,
    pipeline_id: str,
    document_json: str,
    schema_version: int,
    now: str,
) -> str:
    """Store a revision and make it the pipeline's current revision.

    Identical content returns the existing revision id and only moves the
    current-revision pointer back to it.

    Args:
        conn: A connection inside a write transaction.
        pipeline_id: The pipeline that owns the revision.
        document_json: Canonical JSON of the execution document.
        schema_version: The document schema version.
        now: The time stamp for new rows.

    Returns:
        The revision id.

    Raises:
        KeyError: If the pipeline does not exist.
        ValueError: If identical content was stored under another schema version.
    """
    if (
        conn.execute("SELECT 1 FROM pipelines WHERE pipeline_id = ?", (pipeline_id,)).fetchone()
        is None
    ):
        raise KeyError(f"unknown pipeline: {pipeline_id}")
    digest = hashlib.sha256(document_json.encode("utf-8")).hexdigest()
    existing = conn.execute(
        "SELECT * FROM pipeline_revisions WHERE pipeline_id = ? AND content_hash = ?",
        (pipeline_id, digest),
    ).fetchone()
    if existing is not None:
        if existing["schema_version"] != schema_version:
            raise ValueError(
                f"revision {existing['revision_id']} has identical content "
                f"under schema version {existing['schema_version']}"
            )
        revision_id = existing["revision_id"]
    else:
        revision_id = new_id()
        number = conn.execute(
            "SELECT COALESCE(MAX(revision_number), 0) + 1 FROM pipeline_revisions "
            "WHERE pipeline_id = ?",
            (pipeline_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO pipeline_revisions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (revision_id, pipeline_id, number, digest, schema_version, document_json, now),
        )
    conn.execute(
        "UPDATE pipelines SET current_revision_id = ?, updated_at = ? WHERE pipeline_id = ?",
        (revision_id, now, pipeline_id),
    )
    return revision_id
