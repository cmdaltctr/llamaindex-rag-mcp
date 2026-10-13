"""Deletion of finished runs for previewed workspace cleanup.

Only run rows and their events are removed. Pipelines, revisions (which
triggers keep immutable) and plugin registrations stay.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Collection


def delete_finished_runs(
    conn: sqlite3.Connection, run_ids: Collection[str], terminal: Collection[str]
) -> dict[str, int]:
    """Delete finished runs and their events inside the caller's transaction.

    The checks and the deletions use the same transaction, so a run cannot
    become active, or gain a retry, between the check and the delete.
    ``secure_delete`` overwrites the removed content in the database file.

    Args:
        conn: A connection inside an open write transaction.
        run_ids: The runs to delete.
        terminal: The finished run statuses.

    Returns:
        ``{"runs": n, "events": m}``.

    Raises:
        KeyError: If a run does not exist.
        ValueError: If a run is active, or a run outside ``run_ids``
            names one of them as its retry source.
    """
    ids = sorted(set(run_ids))
    if not ids:
        return {"runs": 0, "events": 0}
    conn.execute("PRAGMA secure_delete = ON")
    conn.execute("CREATE TEMP TABLE cleanup_run_ids (run_id TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO temp.cleanup_run_ids VALUES (?)", [(i,) for i in ids])
    found = dict(
        conn.execute(
            "SELECT run_id, status FROM runs "
            "WHERE run_id IN (SELECT run_id FROM temp.cleanup_run_ids)"
        ).fetchall()
    )
    missing = [run_id for run_id in ids if run_id not in found]
    if missing:
        raise KeyError(f"unknown run: {missing[0]}")
    active = sorted(run_id for run_id, status in found.items() if status not in terminal)
    if active:
        raise ValueError(f"cleanup cannot delete active runs: {', '.join(active)}")
    referrers = conn.execute(
        "SELECT run_id, source_run_id FROM runs "
        "WHERE source_run_id IN (SELECT run_id FROM temp.cleanup_run_ids) "
        "AND run_id NOT IN (SELECT run_id FROM temp.cleanup_run_ids) ORDER BY run_id"
    ).fetchall()
    if referrers:
        pairs = ", ".join(f"{row[1]} (retried by {row[0]})" for row in referrers)
        raise ValueError(f"cleanup cannot delete runs that a kept run refers to: {pairs}")
    events = conn.execute(
        "DELETE FROM run_events WHERE run_id IN (SELECT run_id FROM temp.cleanup_run_ids)"
    ).rowcount
    runs = conn.execute(
        "DELETE FROM runs WHERE run_id IN (SELECT run_id FROM temp.cleanup_run_ids)"
    ).rowcount
    return {"runs": runs, "events": events}
