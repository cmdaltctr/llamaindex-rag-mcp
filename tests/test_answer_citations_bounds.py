"""Citation ordinal validation bounds (security finding F12).

``parse_citation_ordinals`` converts matched digit groups with
``int()``.  An absurd ordinal string (thousands of digits) hits
CPython's integer-string conversion limit and raises an opaque
``ValueError`` from deep inside the parser; a superscript digit group
(``[²]``) passes ``str.isdigit()`` but is rejected by ``int()``.  Both
must be handled by explicit validation before conversion.
"""

from __future__ import annotations

import pytest

from omrg.core.answer.citations import parse_citation_ordinals


def test_five_thousand_digit_ordinal_rejected_actionably() -> None:
    """A 5000-digit group raises a ValueError naming the digit bound."""
    with pytest.raises(ValueError, match="9 digits"):
        parse_citation_ordinals(f"[{'7' * 5_000}]", 3)


def test_ten_digit_ordinal_rejected() -> None:
    """One digit over the bound is already rejected."""
    with pytest.raises(ValueError, match="9 digits"):
        parse_citation_ordinals("[1234567890]", 3)


def test_mixed_group_with_absurd_ordinal_rejected() -> None:
    """The bound applies inside a comma-separated group too."""
    with pytest.raises(ValueError, match="9 digits"):
        parse_citation_ordinals("[1, 9999999999]", 3)


def test_nine_digit_boundary_parses_and_is_discarded() -> None:
    """A 9-digit ordinal parses; out-of-range discards it silently."""
    assert parse_citation_ordinals("[999999999]", 3) == []


def test_normal_ordinals_unaffected() -> None:
    """Ordinary bracket groups keep their exact behaviour."""
    assert parse_citation_ordinals("see [1] and [2, 3]", 5) == [1, 2, 3]
    assert parse_citation_ordinals("[ 3 ]", 5) == [3]
    assert parse_citation_ordinals("[0]", 5) == []
    assert parse_citation_ordinals("[6]", 5) == []
    assert parse_citation_ordinals("no citations here", 5) == []
    assert parse_citation_ordinals("", 5) == []


def test_superscript_digit_group_dropped_not_crashed() -> None:
    """``²`` passes ``isdigit()`` but ``int()`` rejects it.

    The group must be dropped as non-numeric, never raise from inside
    the integer parser.
    """
    assert parse_citation_ordinals("[²]", 5) == []
    assert parse_citation_ordinals("claim [1] and [²]", 5) == [1]
