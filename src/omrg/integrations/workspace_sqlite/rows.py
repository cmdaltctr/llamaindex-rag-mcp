"""JSON helpers and row-to-record conversion for the SQLite workspace adapter."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

Record = dict[str, Any]


def dumps(value: Any) -> str:
    """Serialise to canonical JSON, rejecting values without a JSON form.

    Args:
        value: A JSON-compatible value.

    Returns:
        JSON text with sorted keys and no whitespace.

    Raises:
        ValueError: If the value is not JSON-compatible.
    """
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except TypeError as exc:
        raise ValueError(f"value is not JSON-compatible: {exc}") from exc


def loads(text: str | None) -> Any:
    """Parse stored JSON text; ``None`` stays ``None``."""
    return None if text is None else json.loads(text)


def pipeline_record(row: sqlite3.Row) -> Record:
    """Convert a ``pipeline`` row to a plain record."""
    return {
        "pipeline_id": row["pipeline_id"],
        "title": row["title"],
        "current_revision_id": row["current_revision_id"],
        "layout": loads(row["layout_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def revision_record(row: sqlite3.Row) -> Record:
    """Convert a ``revision`` row to a plain record."""
    return {
        "revision_id": row["revision_id"],
        "pipeline_id": row["pipeline_id"],
        "revision_number": row["revision_number"],
        "content_hash": row["content_hash"],
        "schema_version": row["schema_version"],
        "document": loads(row["document_json"]),
        "created_at": row["created_at"],
    }


def run_record(row: sqlite3.Row) -> Record:
    """Convert a ``run`` row to a plain record."""
    return {
        "run_id": row["run_id"],
        "pipeline_id": row["pipeline_id"],
        "revision_id": row["revision_id"],
        "graph_hash": row["graph_hash"],
        "status": row["status"],
        "origin": row["origin"],
        "source_run_id": row["source_run_id"],
        "settings": loads(row["settings_json"]),
        "resources": loads(row["resources_json"]),
        "inputs": loads(row["inputs_json"]),
        "failure": loads(row["failure_json"]),
        "result_ref": row["result_ref"],
        "last_sequence": row["last_sequence"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def event_record(row: sqlite3.Row) -> Record:
    """Convert a ``event`` row to a plain record."""
    return {
        "run_id": row["run_id"],
        "sequence": row["sequence"],
        "kind": row["kind"],
        "node_id": row["node_id"],
        "unit_id": row["unit_id"],
        "summary": loads(row["summary_json"]),
        "created_at": row["created_at"],
    }


def plugin_record(row: sqlite3.Row) -> Record:
    """Convert a ``plugin`` row to a plain record."""
    return {
        "name": row["name"],
        "manifest_ref": row["manifest_ref"],
        "executable_ref": row["executable_ref"],
        "manifest_hash": row["manifest_hash"],
        "compatibility_status": row["compatibility_status"],
        "detail": loads(row["detail_json"]),
        "registered_at": row["registered_at"],
        "checked_at": row["checked_at"],
    }
