"""ChromaDB ``where`` clause translation for LanceDB filters.

Translates the ChromaDB-style ``where`` dict (the shape the MCP
``search_documents`` and ``answer_documents`` tools advertise) into a
LanceDB SQL filter string.

Construction safety (design decision DD2 of the archived
``add-lancedb-vectordb-backend`` change, ADR-046): every VALUE is
serialised by the ``lancedb.expr`` literal builder —
``lit(value).to_sql()`` — whose unparser performs the engine's own
quoting.  Field names are validated against a conservative identifier
grammar and then backtick-quoted, and the operator vocabulary is a
fixed internal set, so neither half of any comparison is built by
interpolating client input.  A full expression tree per leaf is not
possible in the locked version: ``lancedb.expr`` (0.37.1) has no struct
field access (``col("metadata.tag")`` is one quoted identifier naming a
column, verified live), the adapter stores user metadata inside an
Arrow ``metadata`` struct whose ``metadata.<field>`` paths ``col()``
cannot express, and LanceDB offers no bind-parameter API — ``where()``
takes a SQL string or an ``Expr`` that is itself serialised to SQL.

Fail-closed verification (security finding F1): the engine's unparser
is treated as untrusted.  Every serialised fragment is checked against
a closed form per value type, and string fragments are re-decoded with
the standard SQL literal grammar and compared to the original value.
This is not theoretical: on lancedb 0.37.1, ``lit("''").to_sql()`` is
``''''`` — the engine parses it as ONE apostrophe, so an unverified
filter on a double-apostrophe value silently matches the WRONG row —
and a backslash directly before an apostrophe emits ``\'`` undoubled,
which is unfaithful under every decode convention.  Values the engine
cannot serialise faithfully are refused with an actionable
``ValueError`` rather than emitted.

Structural bounds (findings F1/F2): client filters are untrusted
input, so nesting depth (10), comparison-clause count (50),
``$in``/``$nin`` list length (100), and serialised length (8192
characters) are each capped with a ``ValueError`` naming the limit.

Null semantics (ChromaDB parity): Arrow struct fields are nullable, and
ChromaDB treats a missing metadata key on a row as "not equal" — so
``$ne``/``$nin`` must match rows where the field is NULL (explicit
``OR ... IS NULL``), while ``$eq``/``$in``/comparisons naturally exclude
them (SQL unknown).  A field absent from the table's schema entirely
would fail DataFusion planning ("Field ... not found in struct"), so
callers that know the schema pass ``known_fields`` and such predicates
fold to constants with the same ChromaDB semantics: ``false`` for
equality/membership/comparison operators, ``true`` for ``$ne``/``$nin``.

Supported operators: ``$eq $ne $gt $gte $lt $lte $in $nin $and $or``,
plus the bare-equality shorthand ``{"field": value}`` and the nested
form ``{"field": {"$gt": value}}``.  Any other operator raises a
``ValueError`` naming it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal

from lancedb.expr import lit

__all__ = ["translate_where"]

# Comparison operators → SQL infix.  Boolean composition ($and/$or) and
# set membership ($in/$nin) are handled structurally below.
_COMPARISON_OPS: dict[str, str] = {
    "$eq": "=",
    "$ne": "!=",
    "$gt": ">",
    "$gte": ">=",
    "$lt": "<",
    "$lte": "<=",
}

_ALL_OPS = frozenset(_COMPARISON_OPS) | {"$in", "$nin", "$and", "$or"}

# ChromaDB semantics for a field absent from the row (or from the whole
# schema): inequality operators match, everything else does not.
_ABSENT_MATCHES_OPS = frozenset({"$ne", "$nin"})

# Metadata field names arrive from MCP clients, so they are validated
# against a conservative grammar before being embedded in a filter.
# Dots are excluded deliberately: the dot is the struct path separator.
_FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

# Structural complexity bounds (security findings F1/F2): client filters
# are untrusted input, so depth, clause count, membership-list length,
# and serialised size are each capped with an actionable ValueError.
# The serialised cap also bounds every value length by construction.
_MAX_FILTER_DEPTH = 10
_MAX_CLAUSE_COUNT = 50
_MAX_IN_LIST_LENGTH = 100
_MAX_FILTER_SQL_LENGTH = 8192


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
_CAST_FORM = re.compile(r"CAST\('([^']*)' AS (?:DATE|TIMESTAMP)\)")


def _is_faithful_literal(value: object, sql: str) -> bool:
    """Check the engine's serialisation against a closed form per type.

    Args:
        value: The original comparison value handed to ``lit``.
        sql: The fragment the engine's unparser produced.

    Returns:
        True only when *sql* is a well-formed, faithful serialisation
        of *value* for its type.  ``bool`` is checked before ``int``
        because ``bool`` subclasses ``int``.
    """
    if isinstance(value, bool):
        return sql in _BOOL_FORMS
    if isinstance(value, int):
        return _INT_FORM.fullmatch(sql) is not None
    if isinstance(value, float):
        return sql in _FLOAT_SPECIAL_FORMS or _NUMERIC_FORM.fullmatch(sql) is not None
    if isinstance(value, Decimal):
        return _NUMERIC_FORM.fullmatch(sql) is not None
    if isinstance(value, str):
        decoded = _decode_single_quoted_literal(sql)
        return decoded is not None and decoded == value
    if isinstance(value, bytes):
        match = _BYTES_FORM.fullmatch(sql)
        return match is not None and bytes.fromhex(match.group(1)) == value
    if isinstance(value, (date, datetime)):
        return _CAST_FORM.fullmatch(sql) is not None
    return False


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


def _quote_identifier(identifier: str) -> str:
    """Backtick-quote one validated identifier segment.

    The grammar check in :func:`_field_sql` has already rejected
    backticks inside the name, so the quoting cannot be escaped.
    Quoting keeps hyphen-bearing names (valid under the grammar and
    storable in metadata) parseable by the SQL planner.
    """
    return f"`{identifier}`"


def _field_sql(field: str, metadata_column: str | None) -> str:
    """Return the validated, quoted SQL reference for one metadata field.

    Args:
        field: The ChromaDB metadata field name.
        metadata_column: The struct column holding user metadata
            (``"metadata"`` for adapter-written tables), or ``None``
            when the table stores fields as top-level columns.

    Returns:
        ```` `metadata`.`field` ```` or ```` `field` ````.

    Raises:
        ValueError: When the field name contains characters outside
            the identifier grammar.
    """
    if not _FIELD_NAME_RE.match(field):
        raise ValueError(
            f"Metadata field name {field!r} contains characters that cannot be "
            "used in a filter. Field names must match "
            "[A-Za-z_][A-Za-z0-9_-]*."
        )
    if metadata_column is None:
        return _quote_identifier(field)
    return f"{_quote_identifier(metadata_column)}.{_quote_identifier(field)}"


class _ClauseCounter:
    """Running comparison-clause count across a whole filter tree.

    Charging past :data:`_MAX_CLAUSE_COUNT` raises immediately, so a
    client cannot buy unbounded predicate work with a wide filter.
    """

    __slots__ = ("count",)

    def __init__(self) -> None:
        self.count = 0

    def charge(self) -> None:
        """Count one comparison leaf, refusing the tree past the cap."""
        self.count += 1
        if self.count > _MAX_CLAUSE_COUNT:
            raise ValueError(
                f"metadata_filter has more than {_MAX_CLAUSE_COUNT} comparison "
                "clauses. Split the filter into separate queries."
            )


def _leaf(
    field: str,
    op: str,
    value: object,
    metadata_column: str | None,
    known_fields: frozenset[str] | None,
    counter: _ClauseCounter,
) -> str:
    """Build one field/operator/value comparison as SQL.

    Args:
        field: Metadata field name.
        op: One of the supported operators (already validated).
        value: The comparison value, or a list for ``$in``/``$nin``.
        metadata_column: Struct column prefix, or ``None``.
        known_fields: Field names present in the table's schema, when
            the caller knows them.  Predicates on any other field fold
            to the ChromaDB absent-field constant.
        counter: The tree-wide clause counter (charged once per leaf).

    Returns:
        The SQL predicate string.

    Raises:
        ValueError: When ``$in``/``$nin`` receives a non-list value or a
            list longer than :data:`_MAX_IN_LIST_LENGTH`.
    """
    counter.charge()
    if known_fields is not None and field not in known_fields:
        # ChromaDB parity: the planner would reject the reference
        # ("Field ... not found in struct"), so fold it to the
        # semantics ChromaDB gives a key no row carries.
        return "true" if op in _ABSENT_MATCHES_OPS else "false"
    ref = _field_sql(field, metadata_column)
    if op in _COMPARISON_OPS:
        literal = _literal_sql(value)
        if op == "$ne":
            # A row lacking the field is "not equal" in ChromaDB; SQL
            # unknown would silently drop it.
            return f"({ref} != {literal} OR {ref} IS NULL)"
        return f"{ref} {_COMPARISON_OPS[op]} {literal}"
    if op in ("$in", "$nin"):
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"{op} requires a list of values, got {type(value).__name__}.")
        if len(value) > _MAX_IN_LIST_LENGTH:
            raise ValueError(
                f"{op} list exceeds the maximum of {_MAX_IN_LIST_LENGTH} entries "
                f"(got {len(value)})."
            )
        elements = ", ".join(_literal_sql(item) for item in value)
        if not elements:
            # An empty $in matches nothing; an empty $nin matches everything.
            return "false" if op == "$in" else "true"
        keyword = "IN" if op == "$in" else "NOT IN"
        if op == "$nin":
            return f"({ref} {keyword} ({elements}) OR {ref} IS NULL)"
        return f"{ref} {keyword} ({elements})"
    raise ValueError(f"Unsupported filter operator {op!r}. Supported: {sorted(_ALL_OPS)}")


def _field_predicate(
    field: str,
    value: object,
    metadata_column: str | None,
    known_fields: frozenset[str] | None,
    counter: _ClauseCounter,
) -> str:
    """Build the predicate for one ``field: value`` entry.

    A bare scalar becomes an equality test; a dict of operators applies
    each operator to the field and ANDs the results.

    Raises:
        ValueError: When the dict mixes in an unknown operator or uses
            a non-operator nested dict.
    """
    if isinstance(value, dict):
        if not value:
            raise ValueError(f"Filter for field {field!r} is an empty operator dict.")
        parts: list[str] = []
        for op, operand in value.items():
            if op not in _ALL_OPS:
                raise ValueError(
                    f"Unsupported filter operator {op!r}. Supported: {sorted(_ALL_OPS)}"
                )
            if op in ("$and", "$or"):
                raise ValueError(
                    f"Boolean operator {op!r} is only valid at the top level of "
                    "a where clause, not inside a field's operator dict."
                )
            parts.append(_leaf(field, op, operand, metadata_column, known_fields, counter))
        return f"({' AND '.join(parts)})"
    return _leaf(field, "$eq", value, metadata_column, known_fields, counter)


def translate_where(
    where: dict | None,
    *,
    metadata_column: str | None = None,
    known_fields: frozenset[str] | set[str] | None = None,
) -> str | None:
    """Translate a ChromaDB ``where`` dict into a LanceDB SQL filter.

    Enforces the structural bounds — nesting depth, clause count,
    membership-list length, and serialised length — with actionable
    ``ValueError`` messages naming the limit that was crossed.

    Args:
        where: The ChromaDB-style filter dict, or ``None``.
        metadata_column: Name of the struct column holding user metadata
            (adapter-written tables use ``"metadata"``); ``None``
            references fields as top-level columns.
        known_fields: Field names present in the table's schema.  When
            supplied, predicates on fields outside it fold to the
            ChromaDB absent-field constants instead of reaching the
            planner (which rejects unknown struct fields).  ``None``
            assumes every referenced field exists.

    Returns:
        The SQL filter string, or ``None`` when *where* is ``None`` or
        empty (no filtering).

    Raises:
        ValueError: On an unsupported operator, an unsafe field name, a
            malformed clause, a crossed structural bound, or a value
            the engine's literal builder cannot serialise faithfully.
        TypeError: When a value's type is rejected by the literal
            builder (lists, dicts, ``None`` as a bare value).
    """
    if not where:
        return None
    fields = frozenset(known_fields) if known_fields is not None else None
    counter = _ClauseCounter()
    result = _translate(
        where, metadata_column=metadata_column, fields=fields, depth=1, counter=counter
    )
    if result is not None and len(result) > _MAX_FILTER_SQL_LENGTH:
        raise ValueError(
            f"metadata_filter serialises to {len(result)} characters, above the "
            f"maximum of {_MAX_FILTER_SQL_LENGTH}. Reduce the filter's size or "
            "its list lengths."
        )
    return result


def _translate(
    where: dict,
    *,
    metadata_column: str | None,
    fields: frozenset[str] | None,
    depth: int,
    counter: _ClauseCounter,
) -> str:
    """Recursive translation core carrying depth and clause budget.

    Raises:
        ValueError: When the nesting depth exceeds
            :data:`_MAX_FILTER_DEPTH`.
    """
    if depth > _MAX_FILTER_DEPTH:
        raise ValueError(
            f"metadata_filter nesting exceeds the maximum depth of {_MAX_FILTER_DEPTH}."
        )
    parts: list[str] = []
    for key, value in where.items():
        if key in ("$and", "$or"):
            joiner = " AND " if key == "$and" else " OR "
            clauses = joiner.join(
                _translate(
                    clause,
                    metadata_column=metadata_column,
                    fields=fields,
                    depth=depth + 1,
                    counter=counter,
                )
                for clause in _require_clause_list(key, value)
            )
            parts.append(f"({clauses})" if clauses else "true")
        else:
            parts.append(_field_predicate(key, value, metadata_column, fields, counter))
    return f"({' AND '.join(parts)})" if len(parts) > 1 else parts[0]


def _require_clause_list(key: str, value: object) -> Iterable:
    """Validate that a boolean operator received a list of sub-clauses.

    Args:
        key: The boolean operator (``$and`` or ``$or``).
        value: The operator's operand.

    Returns:
        The list of sub-clause dicts.

    Raises:
        ValueError: When the operand is not a non-empty list of
            non-empty where dicts.  An empty sub-clause would translate
            to ``None`` inside the recursive join and surface as a
            confusing ``TypeError`` — or worse, as "no filter".
    """
    if not isinstance(value, list) or not value:
        raise ValueError(f"{key} requires a non-empty list of where clauses.")
    for clause in value:
        if not isinstance(clause, dict) or not clause:
            raise ValueError(f"Every {key} sub-clause must be a non-empty where dict.")
    return value
