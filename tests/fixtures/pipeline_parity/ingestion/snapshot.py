"""Deterministic ingestion parity snapshots.

A later canonical-graph test ingests ``sources/`` through the graph runner
and compares its stored rows with ``ingest_path_async``. This module gives
both sides one projection:

* :func:`collect_rows` returns every stored row of one collection with the
  full lineage (``chunk_id`` included). Use it to compare two live runs
  over the same copied tree; ``chunk_id`` and ``source_id`` depend on the
  absolute source path, so they only match within one test run.
* :func:`portable_rows` drops the path- and run-dependent fields so the
  result can be compared with the committed ``expected_chunks.json``.

The expected file was produced with the conftest offline settings
(``extraction_mode="disabled"``, ``pdf_reader="pypdf"``, OCR fallback off,
empty tokenizer identity), the unit-norm mock embedding, and content
detection pinned by :func:`pin_detection` so the result does not depend on
the Magika binary being on ``PATH``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent
SOURCES_DIR = FIXTURE_DIR / "sources"
EXPECTED_PATH = FIXTURE_DIR / "expected_chunks.json"

#: Metadata that differs between attempts or between machines.
VOLATILE_KEYS = frozenset(
    {
        "source_attempt",
        "file_path",
        "file_name",
        "file_size",
        "creation_date",
        "last_modified_date",
        "last_accessed_date",
    }
)

#: Lineage that depends on the absolute path of the copied tree.
PATH_BOUND_KEYS = frozenset({"source_id", "chunk_id", "source_version"})

#: Content types Magika 1.0.3 reports for the fixture tree.
FIXTURE_CONTENT_TYPES = {
    "guide.md": ("document", "markdown"),
    "nested/appendix.md": ("document", "markdown"),
    "notes.txt": ("document", "text"),
}


def pin_detection(monkeypatch: Any) -> None:
    """Replace Magika detection with the recorded fixture content types."""
    from omrg.core.codebase import codebase_map

    def _detect(path: str, *, settings: Any) -> SimpleNamespace:
        entries = [
            SimpleNamespace(path=str(Path(rel)), group=group, label=label)
            for rel, (group, label) in FIXTURE_CONTENT_TYPES.items()
        ]
        return SimpleNamespace(entries=entries)

    monkeypatch.setattr(codebase_map, "detect_file_types", _detect)


def copy_sources(destination: Path) -> Path:
    """Copy the synthetic source tree under *destination* and return its root."""
    root = destination / "sources"
    shutil.copytree(SOURCES_DIR, root)
    return root


def collect_rows(store: Any, collection_name: str, root: Path) -> list[dict[str, Any]]:
    """Return stored rows ordered by relative path and chunk index.

    Args:
        store: Vector store that holds the ingested rows.
        collection_name: Collection to read.
        root: Root of the copied source tree, used for relative paths.

    Returns:
        One dictionary per row with ``rel_path``, ``text`` and the
        non-volatile metadata (full lineage included).
    """
    rows = []
    resolved_root = root.resolve()
    for _row_id, text, metadata in store.iter_documents(collection_name):
        rel_path = Path(metadata["file_path"]).resolve().relative_to(resolved_root).as_posix()
        kept = {key: value for key, value in metadata.items() if key not in VOLATILE_KEYS}
        rows.append({"rel_path": rel_path, "text": text, "metadata": kept})
    rows.sort(key=lambda row: (row["rel_path"], row["metadata"]["source_chunk_index"]))
    return rows


def portable_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop path-bound lineage and add a text hash for golden comparison."""
    portable = []
    for row in rows:
        metadata = {k: v for k, v in row["metadata"].items() if k not in PATH_BOUND_KEYS}
        metadata.pop("source_index_identity", None)
        portable.append(
            {
                "rel_path": row["rel_path"],
                "text_sha256": hashlib.sha256(row["text"].encode("utf-8")).hexdigest(),
                "text": row["text"],
                "metadata": metadata,
            }
        )
    return portable


def load_expected() -> list[dict[str, Any]]:
    """Return the committed portable snapshot."""
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
