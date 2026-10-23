"""Path-component safety for LanceDB table names.

LanceDB maps a table name to a filesystem path component under the
store URI (``{lancedb_uri}/{name}.lance``), so a collection name
containing separators, ``.``/``..``, or an absolute prefix can
address directories outside the store.  OpenSpec change
``add-per-collection-persist-dirs`` requires every collection name to
be validated as a non-empty single path component before the name can
resolve to a filesystem path.  The rejection set is deliberately
narrow (empty, separators, ``.``, ``..``, control characters) so
existing documented collection names remain valid.  Chroma
collection names are logical identifiers inside one shared persist
directory and stay outside this module until the deferred
per-directory Chroma scope.
"""

from __future__ import annotations

_SEPARATORS = ("/", "\\")


def validate_table_name(name: str) -> str:
    """Validate a collection name as a single safe path component.

    Args:
        name: Candidate LanceDB table (collection) name.

    Returns:
        The name unchanged, so call sites can validate inline.

    Raises:
        ValueError: When *name* is empty, equals ``.`` or ``..``, contains
            a ``/`` or ``\\`` separator (which also covers every
            absolute-path form on POSIX and Windows), or contains a C0
            control character (NUL and friends cannot form a real
            on-disk name and would otherwise surface as an internal
            LanceDB Rust panic rather than a clear error).
    """
    if (
        not name
        or name in (".", "..")
        or any(sep in name for sep in _SEPARATORS)
        or any(ord(char) < 0x20 for char in name)
    ):
        raise ValueError(
            "Invalid LanceDB collection name: must be a non-empty single "
            "path component with no separators, control characters, '.', "
            f"'..', or absolute paths (got: {name})."
        )
    return name
