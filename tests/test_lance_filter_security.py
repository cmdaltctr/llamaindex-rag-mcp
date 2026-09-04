"""Adversarial security tests for the LanceDB where-clause translator.

Evidence file for security finding F1 (``add-grounded-answer-synthesis-3``):
client-controlled ``metadata_filter`` values must never escape the
engine's single-quoted-literal boundary, field names must never escape
the identifier grammar, and filter complexity must be structurally
bounded (finding F2's filter part).

Three proof layers:

1. **Payload corpus + seeded fuzz** — classic injection payloads and
   random quote-heavy strings must each either be rejected with
   ``ValueError``/``TypeError`` or land inside exactly ONE quoted
   literal in the serialised SQL, and must not survive in the SQL after
   every literal is stripped out.
2. **Engine round-trip** — a real table row whose value IS the payload
   is matched by an equality filter on that payload, and only by it.
3. **Structural bounds** — nesting depth, clause count, ``$in``/``$nin``
   list length, and serialised length are each capped with an
   actionable ``ValueError`` naming the limit.

The literal scanner below is written from the SQL string-literal
grammar independently of any production code, so a quoting bug in the
translator cannot hide behind a shared implementation.
"""

from __future__ import annotations

import random
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import lancedb
import pytest

from rag_mcp.core.vectordb.lance_filter import (
    _MAX_CLAUSE_COUNT,
    _MAX_FILTER_DEPTH,
    _MAX_FILTER_SQL_LENGTH,
    _MAX_IN_LIST_LENGTH,
    translate_where,
)

# ── Independent SQL string-literal scanner ────────────────────────────


def _extract_string_literals(sql: str) -> list[str]:
    """Return the decoded value of every single-quoted literal in *sql*.

    Implements the SQL grammar directly: a literal opens with ``'``,
    closes with a ``'`` that is not doubled, and an interior ``''``
    decodes to one ``'``.  Raises on an unterminated literal — a
    serialisation that cannot be scanned is itself a failure.
    """
    literals: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        if sql[i] != "'":
            i += 1
            continue
        j = i + 1
        chars: list[str] = []
        closed = False
        while j < n:
            if sql[j] == "'":
                if j + 1 < n and sql[j + 1] == "'":
                    chars.append("'")
                    j += 2
                    continue
                closed = True
                break
            chars.append(sql[j])
            j += 1
        if not closed:
            raise AssertionError(f"Unterminated literal in serialised filter: {sql!r}")
        literals.append("".join(chars))
        i = j + 1
    return literals


def _strip_string_literals(sql: str) -> str:
    """Remove every quoted literal (content included) from *sql*."""
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        if sql[i] != "'":
            out.append(sql[i])
            i += 1
            continue
        j = i + 1
        while j < n:
            if sql[j] == "'":
                if j + 1 < n and sql[j + 1] == "'":
                    j += 2
                    continue
                break
            j += 1
        i = j + 1
    return "".join(out)


def _assert_payload_contained(field: str, payload: str) -> None:
    """The payload is rejected, or serialises to one faithful literal.

    Rejection (``ValueError``) is an acceptable outcome: the engine's
    literal builder mis-serialises some value classes (runs of
    apostrophes collapse; backslash-before-quote emits non-standard
    SQL), and the translator must refuse those rather than emit a
    filter that matches the WRONG rows.  What is never acceptable is
    an unfaithful or multi-literal serialisation.
    """
    try:
        sql = translate_where({field: payload})
    except ValueError:
        return  # refused before serialisation — fail-closed, acceptable
    assert sql is not None
    literals = _extract_string_literals(sql)
    assert payload in literals, (
        f"Payload {payload!r} did not serialise as one complete quoted "
        f"literal; literals found: {literals!r}; SQL: {sql!r}"
    )
    residue = _strip_string_literals(sql)
    # The residue check is heuristic for tiny payloads: a one- or two-
    # character payload made of SQL punctuation ("=", "-", " ") collides
    # with the predicate's own syntax while still being safely quoted.
    # Apply it only to payloads long enough to be unambiguous, with at
    # least one alphanumeric character, and non-numeric.
    if len(payload) >= 4 and any(ch.isalnum() for ch in payload) and not payload.isdigit():
        assert payload not in residue, (
            f"Payload {payload!r} appears in SQL outside a quoted literal: {sql!r}"
        )


# ── Layer 1: payload corpus ───────────────────────────────────────────

_CLASSIC_PAYLOADS = [
    "x' OR '1'='1",
    "'; DROP TABLE probe; --",
    "a' UNION SELECT id FROM probe --",
    "x' AND '1'='2",
    "a`b",
    "`file_path`",
    "`metadata`.`file_path` = 'x",
    'a" OR 1=1 --',
    "\\' OR '1'='1",
    "é' OR '1'='1",
    "\x00' OR '1'='1",
    "a\nb' OR '1'='1",
    "a--b",
    "a;b",
    "' || '1'='1",
    "x'y'z",
    "1' ORDER BY id--",
    "a' /* comment",
    "*/ OR '1'='1",
    ") OR (1=1",
    "${jndi:ldap://x}",
    "{{7*7}}",
    "a' LIMIT 1--",
    "'",
    "''",
    "'''",
    "\x00\x01\x02",
]


@pytest.mark.parametrize("payload", _CLASSIC_PAYLOADS)
def test_injection_payload_stays_one_literal(payload: str) -> None:
    """Every classic payload is rejected or contained in ONE literal."""
    _assert_payload_contained("tag", payload)


@pytest.mark.parametrize("payload", _CLASSIC_PAYLOADS)
def test_injection_payload_in_list_stays_one_literal(payload: str) -> None:
    """The same guarantee holds through ``$in`` membership lists."""
    try:
        sql = translate_where({"tag": {"$in": [payload, "safe"]}})
    except ValueError:
        return  # refused before serialisation — fail-closed, acceptable
    assert sql is not None
    literals = _extract_string_literals(sql)
    assert payload in literals


def test_oversized_value_rejected_by_serialised_length_bound() -> None:
    """A 10k-character value exceeds the serialised-filter bound."""
    with pytest.raises(ValueError, match=str(_MAX_FILTER_SQL_LENGTH)):
        translate_where({"tag": "a" * 10_000})


# ── Layer 1b: seeded property fuzz ────────────────────────────────────

_FUZZ_ALPHABET = ["a", "b", "'", '"', "`", "\\", ";", "-", "=", " ", "é", "中", "\x00", "\n", "$"]


def test_fuzzed_values_stay_one_literal() -> None:
    """300 seeded random quote-heavy strings all stay inside one literal."""
    # Seeded PRNG on purpose: a fuzz failure must be reproducible
    # exactly for triage; cryptographic randomness would hide the case.
    rng = random.Random(20260902)  # noqa: S311
    for _ in range(300):
        length = rng.randint(0, 40)
        payload = "".join(rng.choice(_FUZZ_ALPHABET) for _ in range(length))
        _assert_payload_contained("tag", payload)


_UNSAFE_FIELD_NAMES: list[tuple[str, str | None]] = [
    ("", "cannot be"),
    ("a.b", "cannot be"),
    ("a b", "cannot be"),
    ("a`b", "cannot be"),
    ("a'b", "cannot be"),
    ('a"b', "cannot be"),
    # "$and" as a field key is intercepted as a boolean operator with an
    # invalid operand — rejected with the boolean-operator message.
    ("$and", "non-empty list"),
    ("a;b", "cannot be"),
    ("a\nb", "cannot be"),
    ("a[0]", "cannot be"),
    ("é", "cannot be"),
    ("a\\b", "cannot be"),
    ("a'b OR '1'='1", "cannot be"),
]


@pytest.mark.parametrize(("field", "fragment"), _UNSAFE_FIELD_NAMES)
def test_unsafe_field_names_rejected(field: str, fragment: str | None) -> None:
    """No field name outside the grammar reaches the serialisation."""
    with pytest.raises(ValueError, match=fragment):
        translate_where({field: 1})


_FIELD_GRAMMAR = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


def test_fuzzed_field_names_never_bypass_grammar() -> None:
    """Random names either raise or match the grammar exactly."""
    # Seeded PRNG on purpose: reproducible fuzz failures for triage.
    rng = random.Random(20260903)  # noqa: S311
    for _ in range(200):
        length = rng.randint(0, 12)
        name = "".join(rng.choice(_FUZZ_ALPHABET) for _ in range(length))
        try:
            sql = translate_where({name: 1})
        except ValueError:
            continue
        assert sql is not None
        assert _FIELD_GRAMMAR.fullmatch(name), f"Unvalidated name {name!r} produced {sql!r}"


# ── Layer 2: engine round-trip ────────────────────────────────────────


def _payload_table(tmp_path: Path, payload: str):
    """Table of three rows whose middle row's value IS the payload."""
    db = lancedb.connect(str(tmp_path / "lancedb"))
    return db.create_table(
        "payload_probe",
        [
            {"id": "plain1", "tag": "unrelated", "vector": [0.1, 0.0]},
            {"id": "payload", "tag": payload, "vector": [0.0, 0.1]},
            {"id": "plain2", "tag": "other", "vector": [0.0, 0.0]},
        ],
        mode="overwrite",
    )


@pytest.mark.parametrize(
    "payload",
    [
        "x' OR '1'='1",
        "'; DROP TABLE payload_probe; --",
        "a' UNION SELECT id FROM payload_probe --",
        "a`b",
        "\x00' OR '1'='1",
    ],
)
def test_engine_treats_payload_as_a_literal(tmp_path: Path, payload: str) -> None:
    """An equality filter on the payload matches exactly its own row.

    If the payload were interpolated raw, the filter would evaluate as
    SQL and match more than one row (or all of them).
    """
    table = _payload_table(tmp_path, payload)
    sql = translate_where({"tag": payload})
    assert sql is not None
    assert table.count_rows(filter=sql) == 1


def test_engine_treats_payload_in_in_list_as_literal(tmp_path: Path) -> None:
    """``$in`` membership on a payload matches only the payload row."""
    payload = "x' OR '1'='1"
    table = _payload_table(tmp_path, payload)
    sql = translate_where({"tag": {"$in": [payload, "unrelated"]}})
    assert table.count_rows(filter=sql) == 2  # the payload row and the unrelated row


# ── Layer 3: structural bounds (finding F2 filter part) ───────────────


def _nested(depth: int) -> dict:
    """A where clause nested *depth* boolean levels deep."""
    where: dict = {"tag": "x"}
    for _ in range(depth - 1):
        where = {"$and": [where]}
    return where


def test_depth_beyond_bound_rejected() -> None:
    """Nesting eleven boolean levels deep is rejected."""
    with pytest.raises(ValueError, match="depth"):
        translate_where(_nested(_MAX_FILTER_DEPTH + 1))


def test_depth_at_bound_accepted() -> None:
    """Nesting at exactly the bound still translates."""
    assert translate_where(_nested(_MAX_FILTER_DEPTH)) is not None


def test_clause_count_beyond_bound_rejected() -> None:
    """Fifty-one comparison clauses exceed the clause-count bound."""
    where = {f"tag{i}": i for i in range(_MAX_CLAUSE_COUNT + 1)}
    with pytest.raises(ValueError, match="50"):
        translate_where(where)


def test_clause_count_at_bound_accepted() -> None:
    """Fifty clauses (spread across branches) still translate."""
    where = {"$or": [{f"tag{i}": i for i in range(25)}, {f"other{i}": i for i in range(25)}]}
    assert translate_where(where) is not None


def test_in_list_beyond_bound_rejected() -> None:
    """A 101-entry ``$in`` list is rejected."""
    with pytest.raises(ValueError, match="100"):
        translate_where({"tag": {"$in": [f"v{i}" for i in range(_MAX_IN_LIST_LENGTH + 1)]}})


def test_in_list_at_bound_accepted() -> None:
    """A 100-entry ``$in`` list still translates."""
    sql = translate_where({"tag": {"$in": [f"v{i}" for i in range(_MAX_IN_LIST_LENGTH)]}})
    assert sql is not None


def test_serialised_length_bound_named_in_error() -> None:
    """The length error names the limit so a caller can act on it."""
    with pytest.raises(ValueError, match=str(_MAX_FILTER_SQL_LENGTH)):
        translate_where({"tag": "x" * 9_000})


# ── Layer 4: fail-closed literal-form verification ────────────────────
#
# The locked engine's literal builder mis-serialises at least two value
# classes (verified on lancedb 0.37.1):
#
# * Runs of apostrophes collapse — ``lit("''").to_sql()`` is ``''''``,
#   which the engine parses as ONE apostrophe, so an equality filter on
#   a double-apostrophe value silently matches the single-apostrophe
#   row instead (wrong-row corruption, not injection).
# * A backslash directly before an apostrophe emits ``\'`` undoubled —
#   non-standard SQL that is unfaithful under every decode convention.
#
# The translator must verify the engine's output against the standard
# literal grammar and REFUSE unfaithful serialisations.


def test_apostrophe_run_values_refused() -> None:
    """Values with apostrophe runs cannot be filtered faithfully."""
    with pytest.raises(ValueError, match="literal"):
        translate_where({"tag": "''"})
    with pytest.raises(ValueError, match="literal"):
        translate_where({"tag": "a''b"})


def test_backslash_quote_values_refused() -> None:
    """Backslash-before-apostrophe values cannot be filtered faithfully."""
    with pytest.raises(ValueError, match="literal"):
        translate_where({"tag": "\\' OR '1'='1"})


def test_single_apostrophes_still_filter_faithfully() -> None:
    """Ordinary single-apostrophe values keep working end to end."""
    sql = translate_where({"tag": "x' OR '1'='1"})
    assert sql is not None
    assert _extract_string_literals(sql) == ["x' OR '1'='1"]


def test_regressed_unparser_output_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A literal builder that emits unquoted SQL text is refused.

    Simulates a lancedb regression: ``to_sql()`` returning attacker
    text without quoting must never reach ``.where()``.
    """

    class _BrokenLit:
        def __init__(self, value: object) -> None:
            self._value = value

        def to_sql(self) -> str:
            # No quoting at all — the exact regression class the
            # fail-closed check exists to stop.
            return str(self._value)

    monkeypatch.setattr("rag_mcp.core.vectordb.lance_literal.lit", _BrokenLit, raising=True)
    with pytest.raises(ValueError, match="literal"):
        translate_where({"tag": "x' OR '1'='1"})


@pytest.mark.parametrize(
    ("value", "pattern"),
    [
        ("plain", r"^'plain'$"),
        ("a'b", r"^'a''b'$"),
        (True, r"^true$"),
        (False, r"^false$"),
        (42, r"^-?\d+$"),
        (3.5, r"^-?\d+\.\d+$"),
    ],
)
def test_literal_forms_are_closed(value: object, pattern: str) -> None:
    """Engine literal serialisations match a closed form per type."""
    from rag_mcp.core.vectordb.lance_literal import _literal_sql

    assert re.fullmatch(pattern, _literal_sql(value))


# ── Layer 5: absent-field validation must not bypass input controls ────
#
# A field absent from the table's schema folds to a ChromaDB constant
# (false for equality/membership/comparison, true for $ne/$nin).  That
# fold must happen AFTER field-name validation, membership-operand
# validation, and the membership-list-length check — otherwise a client
# can probe schema layout or bypass complexity bounds by targeting
# absent fields with invalid input.


_KNOWN_FIELDS = frozenset({"id", "tag", "score"})


class TestAbsentFieldValidationBypass:
    """Schema-absent fields must not bypass field-name or membership checks."""

    def test_invalid_field_name_on_absent_field_rejected(self) -> None:
        """An invalid field name is rejected before the absent-field fold."""
        with pytest.raises(ValueError, match="cannot be"):
            translate_where({"bad.field": "x"}, known_fields=_KNOWN_FIELDS)

    def test_invalid_field_name_with_dollar_on_absent_field_rejected(self) -> None:
        """A field name with a dot is rejected even when the field is absent."""
        with pytest.raises(ValueError, match="cannot be"):
            translate_where({"a b": "x"}, known_fields=_KNOWN_FIELDS)

    def test_non_list_in_on_absent_field_rejected(self) -> None:
        """$in with a non-list operand is rejected even on an absent field."""
        with pytest.raises(ValueError, match="requires a list"):
            translate_where({"nope": {"$in": "x"}}, known_fields=_KNOWN_FIELDS)

    def test_non_list_nin_on_absent_field_rejected(self) -> None:
        """$nin with a non-list operand is rejected even on an absent field."""
        with pytest.raises(ValueError, match="requires a list"):
            translate_where({"nope": {"$nin": 42}}, known_fields=_KNOWN_FIELDS)

    def test_oversized_in_list_on_absent_field_rejected(self) -> None:
        """An oversized $in list is rejected even on an absent field."""
        with pytest.raises(ValueError, match="100"):
            translate_where(
                {"nope": {"$in": [f"v{i}" for i in range(_MAX_IN_LIST_LENGTH + 1)]}},
                known_fields=_KNOWN_FIELDS,
            )

    def test_oversized_nin_list_on_absent_field_rejected(self) -> None:
        """An oversized $nin list is rejected even on an absent field."""
        with pytest.raises(ValueError, match="100"):
            translate_where(
                {"nope": {"$nin": [f"v{i}" for i in range(_MAX_IN_LIST_LENGTH + 1)]}},
                known_fields=_KNOWN_FIELDS,
            )

    def test_valid_absent_field_still_folds(self) -> None:
        """A valid field name on an absent field still folds (sanity check)."""
        sql = translate_where({"nope": "x"}, known_fields=_KNOWN_FIELDS)
        assert sql == "false"

    def test_valid_absent_field_ne_still_folds(self) -> None:
        """A valid absent field with $ne still folds to true."""
        sql = translate_where({"nope": {"$ne": "x"}}, known_fields=_KNOWN_FIELDS)
        assert sql == "(true)"


# ── Layer 6: scalar value-faithfulness verification ───────────────────
#
# The engine's unparser is treated as untrusted.  Every serialised
# literal must not only match a valid SQL shape but also represent the
# original value.  These tests monkeypatch ``lit`` to emit a different
# valid-looking fragment for each scalar type and prove the translator
# refuses it.


class _MismatchedLit:
    """A broken ``lit`` that emits a valid-looking but WRONG fragment.

    Each branch produces SQL that passes the closed-form shape check but
    represents a different value than the one handed to ``lit``.
    """

    def __init__(self, value: object) -> None:
        self._value = value

    def to_sql(self) -> str:
        v = self._value
        # bool: swap true/false
        if isinstance(v, bool):
            return "false" if v else "true"
        # int: emit value + 1
        if isinstance(v, int):
            return str(v + 1)
        # float: emit a different but valid float
        if isinstance(v, float):
            if v != v:  # NaN
                return "0.0"
            if v == float("inf"):
                return "0.0"
            if v == float("-inf"):
                return "0.0"
            return repr(v + 1.0)
        # Decimal: emit a different but valid decimal
        if isinstance(v, Decimal):
            return str(v + Decimal("1"))
        # date: emit the next day
        if isinstance(v, date) and not isinstance(v, datetime):
            from datetime import timedelta

            return f"CAST('{(v + timedelta(days=1)).isoformat()}' AS DATE)"
        # datetime: emit a different but valid timestamp.
        # Shift by one day (not one hour) so a timezone-offset change
        # between seasons cannot accidentally cancel the mismatch.
        if isinstance(v, datetime):
            from datetime import timedelta

            shifted = v + timedelta(days=1)
            # Mimic the engine's UTC conversion for naive datetimes.
            # Use the timezone offset that applies at the shifted date,
            # not the current date, so the conversion matches the
            # engine's behaviour for that calendar date.
            if v.tzinfo is None:
                local_aware = shifted.astimezone()
                utc = local_aware.astimezone(UTC)
            else:
                utc = shifted.astimezone(UTC)
            ts = utc.replace(tzinfo=None).isoformat(sep=" ")
            return f"CAST('{ts}' AS TIMESTAMP)"
        # str: emit a different but valid quoted string
        if isinstance(v, str):
            return "'mismatched'"
        # bytes: emit different but valid hex
        if isinstance(v, bytes):
            return "X'00'"
        return str(v)


@pytest.mark.parametrize(
    ("value", "label"),
    [
        (True, "bool True"),
        (False, "bool False"),
        (0, "int zero"),
        (42, "int positive"),
        (-7, "int negative"),
        (3.14, "float positive"),
        (-0.5, "float negative"),
        (0.0, "float zero"),
        (float("inf"), "float inf"),
        (float("-inf"), "float -inf"),
        (float("nan"), "float nan"),
        (Decimal("0"), "Decimal zero"),
        (Decimal("3.14"), "Decimal positive"),
        (Decimal("-7.5"), "Decimal negative"),
        (date(2026, 9, 2), "date"),
        (date(1970, 1, 1), "date epoch"),
        (datetime(2026, 9, 2, 15, 30, 45), "datetime naive"),
        (datetime(2026, 1, 15, 12, 0, 0), "datetime winter"),
        (datetime(2026, 9, 2, 15, 30, 45, 123456), "datetime microsecond"),
    ],
)
def test_mismatched_scalar_refused(
    monkeypatch: pytest.MonkeyPatch, value: object, label: str
) -> None:
    """A valid-looking but wrong scalar fragment is refused.

    Monkeypatches ``lit`` to emit a fragment that passes the closed-form
    shape check but represents a different value.  The translator must
    refuse the filter rather than emit a literal that matches the wrong
    rows.
    """
    monkeypatch.setattr("rag_mcp.core.vectordb.lance_literal.lit", _MismatchedLit, raising=True)
    with pytest.raises(ValueError, match="literal"):
        translate_where({"tag": value})


def test_faithful_scalar_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Genuinely faithful scalar serialisations are accepted (no false refusal).

    Uses the real ``lit`` (no monkeypatch) to verify that ordinary values
    of every supported scalar type pass the faithfulness check without
    false refusal.
    """
    from rag_mcp.core.vectordb.lance_literal import _literal_sql

    values: list[object] = [
        True,
        False,
        0,
        42,
        -7,
        3.14,
        -0.5,
        0.0,
        float("inf"),
        float("-inf"),
        Decimal("0"),
        Decimal("3.14"),
        Decimal("-7.5"),
        date(2026, 9, 2),
        date(1970, 1, 1),
        datetime(2026, 9, 2, 15, 30, 45),
        datetime(2026, 1, 15, 12, 0, 0),
        datetime(2026, 9, 2, 15, 30, 45, 123456),
    ]
    for v in values:
        # Must not raise — the real engine serialises faithfully
        sql = _literal_sql(v)
        assert sql, f"Faithful serialisation of {v!r} was refused"
