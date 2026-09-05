"""Path-component validation for LanceDB collection names (task 1.1).

``validate_table_name`` is the adapter-side filesystem boundary guard
(design D2): a valid name passes through unchanged, and anything that
could escape the ``{lancedb_uri}/{collection_name}.lance`` layout
raises ``ValueError``.  Dots inside a name are legal; only the exact
``.`` and ``..`` components are rejected.
"""

from __future__ import annotations

import pytest

from omrg.core.vectordb.lance_table_name import validate_table_name

_BAD_NAMES = [
    "",
    ".",
    "..",
    "a/b",
    "a\\b",
    "/abs",
    "//abs",
    "C:\\win\\path",
    "trailing/",
    "/leading",
    # Control characters cannot form a real on-disk name; without
    # rejection they surface as an internal LanceDB Rust panic
    # instead of a clear ValueError (security-audit finding).
    "bad\x00name",
    "nl\nname",
]

_GOOD_NAMES = [
    "documents",
    "codebase",
    "my.collection",
    "doc_1",
    "2026-data",
    "a..b",
]


@pytest.mark.parametrize("name", _BAD_NAMES)
def test_rejects_unsafe_names(name: str) -> None:
    """A name that is not one safe path component raises ValueError."""
    with pytest.raises(ValueError):
        validate_table_name(name)


@pytest.mark.parametrize("name", _GOOD_NAMES)
def test_accepts_safe_names_unchanged(name: str) -> None:
    """A valid name is returned unchanged."""
    assert validate_table_name(name) == name


@pytest.mark.parametrize("name", _BAD_NAMES)
def test_rejection_message_names_the_offender(name: str) -> None:
    """The ValueError message mentions the offending name."""
    with pytest.raises(ValueError) as excinfo:
        validate_table_name(name)
    assert str(name) in str(excinfo.value)
