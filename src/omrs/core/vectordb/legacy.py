"""Fail-closed legacy Chroma data decision (task 4, design D6).

A recognised legacy Chroma layout on disk means the operator may hold
data written by a previous ``VECTOR_STORE=chroma`` deployment. When the
backend was not explicitly selected, startup fails closed so the data
cannot be silently abandoned by a default flip to LanceDB. The software
never deletes, moves, or writes the legacy directory as part of this
decision.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

#: Directory classification outcomes.
_ABSENT = "absent"
_EMPTY = "empty"
_RECOGNISED = "recognised"
_UNRECOGNISED_NONEMPTY = "unrecognised_nonempty"

# A persisted Chroma vector segment is a UUID-named subdirectory containing
# HNSW files. ``header.bin`` plus ``data_level0.bin`` are sufficiently
# distinctive to recognise a segment even when the directory is incomplete;
# healthy layouts normally also contain ``length.bin``, ``link_lists.bin`` and
# ``index_metadata.pickle``. A generic file named ``segment*`` is not a Chroma
# persistence marker.
_HNSW_SEGMENT_MARKERS = frozenset({"header.bin", "data_level0.bin"})


class LegacyChromaDataError(RuntimeError):
    """Raised when recognised legacy Chroma data needs an explicit choice."""


def classify_legacy_directory(directory: str | Path) -> str:
    """Classify *directory* against the recognised Chroma markers.

    A directory is ``recognised`` when it carries ``chroma.sqlite3`` or
    the documented HNSW vector-segment layout (a nested directory holding
    both ``header.bin`` and ``data_level0.bin``). A missing path is
    ``absent``, an empty directory is ``empty``, and anything else
    non-empty is ``unrecognised_nonempty``.

    Args:
        directory: The persisted Chroma data directory.

    Returns:
        One of ``absent``, ``empty``, ``recognised``, or
        ``unrecognised_nonempty``.
    """
    path = Path(directory)
    if not path.exists():
        return _ABSENT
    if not path.is_dir():
        # A file at the configured path is not a Chroma layout.
        return _UNRECOGNISED_NONEMPTY
    try:
        entries = list(path.iterdir())
    except OSError:
        return _UNRECOGNISED_NONEMPTY
    if not entries:
        return _EMPTY
    if (path / "chroma.sqlite3").exists():
        return _RECOGNISED
    for child in entries:
        if not child.is_dir():
            continue
        try:
            filenames = {item.name for item in child.iterdir() if item.is_file()}
        except OSError:
            continue
        if _HNSW_SEGMENT_MARKERS.issubset(filenames):
            return _RECOGNISED
    return _UNRECOGNISED_NONEMPTY


def _error_message(directory: Path) -> str:
    """Build the operator-facing fail-closed diagnostic."""
    return (
        f"Recognised legacy Chroma data was found in {directory} and no "
        f"explicit VECTOR_STORE was selected. The directory is left "
        f"untouched — no automatic migration is performed and Chroma data "
        f"is never deleted automatically. Choose one of:\n"
        f"  - keep using it: set VECTOR_STORE=chroma and install the chroma "
        f"extra (uv sync --extra chroma);\n"
        f"  - switch to LanceDB: set VECTOR_STORE=lancedb to acknowledge "
        f"that re-ingestion into LanceDB is required.\n"
        f"See ADR-049 for the migration and rollback steps."
    )


def evaluate_legacy_chroma_data(
    directory: str | Path,
    backend: str,
    provenance: str,
) -> None:
    """Apply the fail-closed legacy-data decision.

    Args:
        directory: The persisted Chroma data directory.
        backend: The resolved vector-store backend (``chroma`` or
            ``lancedb``).
        provenance: ``explicit`` when the operator selected the backend
            (constructor, environment, or ``.env``), ``default`` when it
            came from shipped defaults.

    Raises:
        LegacyChromaDataError: Recognised legacy data with a
            default-derived backend and no explicit choice.

    The explicit-LanceDB case acknowledges re-ingestion with a warning;
    explicit Chroma with matching data passes silently; an unrecognised
    non-empty directory warns instead of failing.
    """
    status = classify_legacy_directory(directory)
    path = Path(directory)

    if status == _RECOGNISED:
        if provenance == "default":
            raise LegacyChromaDataError(_error_message(path))
        if backend == "lancedb":
            logger.warning(
                "Recognised legacy Chroma data in %s will be left untouched. "
                "VECTOR_STORE=lancedb acknowledges that re-ingestion into "
                "LanceDB is required.",
                path,
            )
        # Explicit chroma with matching data: no warning, access preserved.
        return

    if status == _UNRECOGNISED_NONEMPTY:
        logger.warning(
            "Directory %s is non-empty but does not carry a recognised "
            "Chroma layout (no chroma.sqlite3 or HNSW segment layout). It is "
            "left untouched.",
            path,
        )
