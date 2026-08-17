"""ChromaDB ``where`` clause translation for LanceDB filters.

Translates the ChromaDB-style ``where`` dict (the shape the MCP
``search_documents`` tool advertises) into a LanceDB SQL filter string.

Construction safety (design decision DD2): every VALUE is serialised by
the ``lancedb.expr`` literal builder — ``lit(value).to_sql()`` — whose
unparser performs the engine's own quoting (verified: a single quote
becomes ``'a''b"c.py'``).  Field names are validated against a
conservative identifier grammar and then backtick-quoted, and the
operator vocabulary is a fixed internal set, so neither half of any
comparison is built by interpolating client input.  A full expression
tree per leaf is not possible: ``lancedb.expr`` (0.37.1) has no struct
field access, and the adapter stores user metadata inside an Arrow
``metadata`` struct, so filters must reference ``metadata.<field>``
paths that ``col()`` would quote as a single identifier.  Values still
flow exclusively through the type-safe literal builder.

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


def _literal_sql(value: object) -> str:
    """Serialise one value through the type-safe literal builder.

    Args:
        value: A scalar supported by ``lit`` (bool/int/float/str/bytes/
            date/datetime/Decimal).

    Returns:
        The engine-quoted SQL literal.

    Raises:
        TypeError: When ``lit`` rejects the value's type — the trust
            boundary that keeps structured values from reaching SQL.
    """
    return lit(value).to_sql()


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


def _leaf(
    field: str,
    op: str,
    value: object,
    metadata_column: str | None,
    known_fields: frozenset[str] | None,
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

    Returns:
        The SQL predicate string.

    Raises:
        ValueError: When ``$in``/``$nin`` receives a non-list value.
    """
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
            parts.append(_leaf(field, op, operand, metadata_column, known_fields))
        return f"({' AND '.join(parts)})"
    return _leaf(field, "$eq", value, metadata_column, known_fields)


def translate_where(
    where: dict | None,
    *,
    metadata_column: str | None = None,
    known_fields: frozenset[str] | set[str] | None = None,
) -> str | None:
    """Translate a ChromaDB ``where`` dict into a LanceDB SQL filter.

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
        ValueError: On an unsupported operator, an unsafe field name,
            or a malformed clause.
        TypeError: When a value's type is rejected by the literal
            builder (lists, dicts, ``None`` as a bare value).
    """
    if not where:
        return None
    fields = frozenset(known_fields) if known_fields is not None else None
    parts: list[str] = []
    for key, value in where.items():
        if key == "$and":
            clauses = " AND ".join(
                translate_where(clause, metadata_column=metadata_column, known_fields=fields)
                for clause in _require_clause_list(key, value)
            )
            parts.append(f"({clauses})" if clauses else "true")
        elif key == "$or":
            clauses = " OR ".join(
                translate_where(clause, metadata_column=metadata_column, known_fields=fields)
                for clause in _require_clause_list(key, value)
            )
            parts.append(f"({clauses})" if clauses else "true")
        else:
            parts.append(_field_predicate(key, value, metadata_column, fields))
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
