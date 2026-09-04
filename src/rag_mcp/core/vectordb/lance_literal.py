"""Engine literal serialisation and fail-closed verification.

The LanceDB filter adapter (``lance_filter.py``) serialises every VALUE
through the engine's own literal builder — ``lit(value).to_sql()`` —
whose unparser performs the engine's quoting.  The engine's unparser is
treated as untrusted: every fragment is checked against a closed form
per value type, and string fragments are re-decoded with the standard
SQL literal grammar and compared to the original value.

This is not theoretical: on lancedb 0.37.1, ``lit("''").to_sql()`` is
``''''`` — the engine parses it as ONE apostrophe, so an unverified
filter on a double-apostrophe value silently matches the WRONG row —
and a backslash directly before an apostrophe emits ``\'`` undoubled,
which is unfaithful under every decode convention.  Values the engine
cannot serialise faithfully are refused with an actionable
``ValueError`` rather than emitted.

This module is the sole sanctioned exception to the parameterised-query
invariant (ADR-058), scoped to the LanceDB filter adapter.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal

from lancedb.expr import lit

__all__ = ["_is_faithful_literal", "_literal_sql"]


def _decode_single_quoted_literal(fragment: str) -> str | None:
    """Decode *fragment* as exactly one standard-grammar SQL literal.

    A literal opens with ``'``, closes with a ``'`` that is not doubled,
    and an interior ``''`` decodes to one ``'``.  Returns ``None`` when
    the fragment is not exactly one well-formed literal — including a
    literal that closes early or ends on a doubled pair.

    Args:
        fragment: The candidate SQL fragment.

    Returns:
        The decoded literal value, or ``None`` when the fragment is not
        exactly one well-formed quoted literal.
    """
    if len(fragment) < 2 or fragment[0] != "'" or fragment[-1] != "'":
        return None
    chars: list[str] = []
    i = 1
    last = len(fragment) - 1
    while i < last:
        if fragment[i] == "'":
            if fragment[i + 1] == "'":
                chars.append("'")
                i += 2
                continue
            return None  # closes early or is a stray quote
        chars.append(fragment[i])
        i += 1
    return "".join(chars) if i == last else None


# Closed serialisation forms per value type.  Anything the engine's
# unparser emits outside these forms is refused (fail closed).
_BOOL_FORMS = frozenset({"true", "false"})
_INT_FORM = re.compile(r"-?\d+")
_NUMERIC_FORM = re.compile(r"-?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")
_FLOAT_SPECIAL_FORMS = frozenset({"inf", "-inf", "NaN"})
_BYTES_FORM = re.compile(r"X'([0-9a-fA-F]*)'")
# The CAST target type is CAPTURED (not discarded): a date value in a
# TIMESTAMP cast — or a datetime in a DATE cast — is a different SQL
# value class even when the inner string round-trips, so the target
# type must be validated against the value type, not assumed.
_CAST_FORM = re.compile(r"CAST\('([^']*)' AS (DATE|TIMESTAMP)\)")


def _is_faithful_literal(value: object, sql: str) -> bool:
    """Check the engine's serialisation against a closed form per type.

    The engine's unparser is treated as untrusted: each fragment must
    not only match a valid SQL shape but also *represent* the original
    value.  For every supported scalar type the fragment is parsed or
    decoded and compared with the original using exact or canonical
    type semantics, so a regression that emits a different valid-looking
    value is refused.

    Args:
        value: The original comparison value handed to ``lit``.
        sql: The fragment the engine's unparser produced.

    Returns:
        True only when *sql* is a well-formed, faithful serialisation
        of *value* for its type.  ``bool`` is checked before ``int``
        because ``bool`` subclasses ``int``.
    """
    if isinstance(value, bool):
        # bool: exact match against the two SQL boolean literals.
        return sql == ("true" if value else "false")
    if isinstance(value, int):
        # int: the fragment must parse to the same integer.
        match = _INT_FORM.fullmatch(sql)
        return match is not None and int(sql) == value
    if isinstance(value, float):
        # float: special values (inf, -inf, NaN) matched by name;
        # ordinary floats compared by numeric equality so that
        # equivalent representations (1e10 vs 10000000000.0) pass.
        if value != value:  # NaN
            return sql == "NaN"
        if value == float("inf"):
            return sql == "inf"
        if value == float("-inf"):
            return sql == "-inf"
        match = _NUMERIC_FORM.fullmatch(sql)
        return match is not None and float(sql) == value
    if isinstance(value, Decimal):
        # Decimal: the fragment must parse to the same Decimal using
        # exact arithmetic (not float coercion, which loses precision).
        match = _NUMERIC_FORM.fullmatch(sql)
        return match is not None and Decimal(sql) == value
    if isinstance(value, str):
        decoded = _decode_single_quoted_literal(sql)
        return decoded is not None and decoded == value
    if isinstance(value, bytes):
        match = _BYTES_FORM.fullmatch(sql)
        return match is not None and bytes.fromhex(match.group(1)) == value
    if isinstance(value, (date, datetime)):
        # date/datetime: the engine emits CAST('...' AS DATE|TIMESTAMP).
        # The target type must agree with the value type (a swapped cast
        # is a different SQL value class even when the inner string
        # round-trips), the fragment must match the CAST form at all,
        # and the inner string must parse to the same calendar date or
        # instant.  For naive datetimes the engine converts local time
        # to UTC, so the comparison round-trips through the same
        # conversion.
        match = _CAST_FORM.fullmatch(sql)
        if match is None:
            return False
        inner, target = match.group(1), match.group(2)
        if isinstance(value, datetime):
            return target == "TIMESTAMP" and _datetime_matches(value, inner)
        return target == "DATE" and _date_matches(value, inner)
    return False


def _date_matches(value: date, inner: str) -> bool:
    """Check whether a CAST(... AS DATE) inner string matches *value*.

    Args:
        value: The original ``date`` value.
        inner: The date string inside the CAST, e.g. ``2026-09-02``.

    Returns:
        True when *inner* parses to the same calendar date.
    """
    try:
        parsed = date.fromisoformat(inner)
    except ValueError:
        return False
    return parsed == value


def _datetime_matches(value: datetime, inner: str) -> bool:
    """Check whether a CAST(... AS TIMESTAMP) inner string matches *value*.

    The engine converts naive datetimes from local time to UTC before
    serialising.  This function replicates that conversion for the
    comparison so a faithful serialisation is recognised.

    Args:
        value: The original ``datetime`` value (naive or aware).
        inner: The timestamp string inside the CAST, e.g.
            ``2026-09-02 14:30:45``.

    Returns:
        True when *inner* represents the same instant as *value* after
        accounting for the engine's local-to-UTC conversion.
    """
    try:
        parsed = datetime.fromisoformat(inner)
    except ValueError:
        return False
    if value.tzinfo is not None:
        # Aware datetime: the engine serialises the UTC equivalent.
        expected_utc = value.astimezone(UTC).replace(tzinfo=None)
    else:
        # Naive datetime: the engine converts from local time to UTC.
        local = value.replace(tzinfo=None)
        expected_utc = local.astimezone().astimezone(UTC).replace(tzinfo=None)
    return parsed == expected_utc


def _literal_sql(value: object) -> str:
    """Serialise one value through the type-safe literal builder.

    The engine's unparser output is verified against a closed form per
    value type (and, for strings, decoded back and compared to the
    original value) before it is allowed into a filter.  The engine has
    demonstrated mis-serialisation classes — apostrophe runs collapse,
    and a backslash before an apostrophe emits ``\'`` undoubled — so an
    unverified fragment is a wrong-row or broken-SQL hazard, and this
    boundary refuses it.

    Args:
        value: A scalar supported by ``lit`` (bool/int/float/str/bytes/
            date/datetime/Decimal).

    Returns:
        The verified, engine-quoted SQL literal.

    Raises:
        TypeError: When ``lit`` rejects the value's type — the trust
            boundary that keeps structured values from reaching SQL.
        ValueError: When the engine's serialisation fails the closed-
            form or round-trip check.  The filter is refused rather
            than emitted with an unfaithful literal.
    """
    sql = lit(value).to_sql()
    if not _is_faithful_literal(value, sql):
        raise ValueError(
            "metadata_filter value cannot be serialised safely: the engine's "
            f"literal builder returned an unfaithful fragment for a "
            f"{type(value).__name__} value (sample {str(value)[:60]!r}). "
            "Refusing to build the filter; values containing runs of "
            "apostrophes, or a backslash directly before an apostrophe, are "
            "known to be affected."
        )
    return sql
