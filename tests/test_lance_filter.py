"""Semantic tests for the ChromaDB-to-LanceDB where-clause translator.

The ``lancedb-vector-store`` spec requires ``translate_where`` to build
type-safe expressions through the ``lancedb.expr`` builder — never by
interpolating values into SQL strings.  These tests verify that
requirement semantically: each supported operator is applied to a real
LanceDB table of known rows through ``count_rows(filter=...)`` and must
select exactly the expected row count.  A repr-based test would pass
with a string-building implementation that the spec forbids.

The injection case plants a decoy row whose value only matches when a
user-supplied string is interpolated raw into SQL, so a vulnerable
translator cannot pass by accident.
"""

from __future__ import annotations

from pathlib import Path

import lancedb
import pytest

from omrg.core.vectordb.lance_filter import translate_where

# Four rows with known field values; the vector column exists only so
# the table is a valid LanceDB table (dimension 4, arbitrary values).
_ROWS = [
    {
        "id": "r1",
        "file_path": "a/b.py",
        "category": "AI",
        "score": 1,
        "vector": [0.1, 0.0, 0.0, 0.0],
    },
    {
        "id": "r2",
        "file_path": "c/d.py",
        "category": "Biology",
        "score": 5,
        "vector": [0.0, 0.1, 0.0, 0.0],
    },
    {
        "id": "r3",
        "file_path": "e/f.py",
        "category": "AI",
        "score": 10,
        "vector": [0.0, 0.0, 0.1, 0.0],
    },
    {
        "id": "r4",
        "file_path": "g/h.py",
        "category": "Chemistry",
        "score": 7,
        "vector": [0.0, 0.0, 0.0, 0.1],
    },
]


@pytest.fixture
def table(tmp_path: Path):
    """Return a tiny LanceDB table loaded with ``_ROWS``."""
    db = lancedb.connect(str(tmp_path / "lancedb"))
    return db.create_table("probe", _ROWS, mode="overwrite")


@pytest.mark.parametrize(
    ("where", "expected"),
    [
        ({"category": {"$eq": "AI"}}, 2),
        ({"category": {"$ne": "AI"}}, 2),
        ({"score": {"$gt": 5}}, 2),
        ({"score": {"$gte": 5}}, 3),
        ({"score": {"$lt": 5}}, 1),
        ({"score": {"$lte": 5}}, 2),
        ({"category": {"$in": ["AI", "Biology"]}}, 3),
        ({"category": {"$nin": ["AI", "Biology"]}}, 1),
    ],
    ids=["eq", "ne", "gt", "gte", "lt", "lte", "in", "nin"],
)
def test_operator_selects_expected_rows(table, where: dict, expected: int) -> None:
    """Each ChromaDB operator must filter the table to the expected rows.

    Covers the spec's equality, comparison, and set-membership scenarios
    in one parametrised sweep over a real table.
    """
    assert table.count_rows(filter=translate_where(where)) == expected


def test_bare_equality_shorthand_matches_nested_form(table) -> None:
    """``{"field": value}`` and ``{"field": {"$eq": value}}`` agree."""
    bare = table.count_rows(filter=translate_where({"file_path": "a/b.py"}))
    nested = table.count_rows(filter=translate_where({"file_path": {"$eq": "a/b.py"}}))
    assert bare == nested == 1


def test_and_composition(table) -> None:
    """``$and`` must select rows matching every clause."""
    where = {"$and": [{"category": "AI"}, {"score": {"$gt": 5}}]}
    assert table.count_rows(filter=translate_where(where)) == 1


def test_or_composition(table) -> None:
    """``$or`` must select rows matching any clause."""
    where = {"$or": [{"score": {"$lt": 2}}, {"category": "Chemistry"}]}
    assert table.count_rows(filter=translate_where(where)) == 2


def test_single_quote_value_is_a_literal_not_sql(tmp_path: Path) -> None:
    """Values containing SQL metacharacters must stay literal.

    The decoy row's ``file_path`` is the classic ``x' OR '1'='1``
    payload: if a translator interpolated user values raw into SQL,
    filtering for the decoy value would produce
    ``file_path = 'x' OR '1'='1'`` and match every row.  Both filters
    must therefore count exactly one row — the literal match.
    """
    rows = [
        {"id": "literal", "file_path": "a'b\"c.py", "score": 1, "vector": [0.1, 0.0, 0.0, 0.0]},
        {"id": "decoy", "file_path": "x' OR '1'='1", "score": 2, "vector": [0.0, 0.1, 0.0, 0.0]},
        {"id": "plain1", "file_path": "plain1.py", "score": 3, "vector": [0.0, 0.0, 0.1, 0.0]},
        {"id": "plain2", "file_path": "plain2.py", "score": 4, "vector": [0.0, 0.0, 0.0, 0.1]},
    ]
    db = lancedb.connect(str(tmp_path / "lancedb"))
    table = db.create_table("injection", rows, mode="overwrite")

    assert table.count_rows(filter=translate_where({"file_path": "a'b\"c.py"})) == 1
    assert table.count_rows(filter=translate_where({"file_path": "x' OR '1'='1"})) == 1


def test_unknown_operator_raises_naming_the_operator(table) -> None:
    """An unsupported operator must raise a ValueError naming it."""
    with pytest.raises(ValueError, match=r"\$like"):
        translate_where({"file_path": {"$like": "%a"}})


def test_none_and_empty_where_translate_to_no_filter() -> None:
    """``None`` and ``{}`` must both translate to no filter at all."""
    assert translate_where(None) is None
    assert translate_where({}) is None


# ── Malformed-input rejection ─────────────────────────────────────────


def test_empty_operator_dict_rejected(table) -> None:
    """A field mapped to an empty dict has no operator to apply."""
    with pytest.raises(ValueError, match="empty operator dict"):
        translate_where({"file_path": {}})


@pytest.mark.parametrize("field", ["a.b", "file path", "file-path'", ""])
def test_unsafe_field_name_rejected(table, field: str) -> None:
    """Field names outside the identifier grammar must be rejected."""
    with pytest.raises(ValueError, match="cannot be"):
        translate_where({field: 1})


def test_in_requires_a_list(table) -> None:
    """``$in`` with a scalar operand is a malformed clause."""
    with pytest.raises(ValueError, match="requires a list"):
        translate_where({"file_path": {"$in": "a/b.py"}})


def test_boolean_operator_inside_field_dict_rejected(table) -> None:
    """``$and``/``$or`` are only valid at the top level."""
    with pytest.raises(ValueError, match="top level"):
        translate_where({"file_path": {"$and": [{"score": 1}]}})


@pytest.mark.parametrize(
    ("operand", "message"),
    [
        ("not-a-list", "non-empty list"),
        ([], "non-empty list"),
        (["not-a-dict"], "where dict"),
    ],
)
def test_boolean_operator_requires_clause_list(table, operand: object, message: str) -> None:
    """``$and``/``$or`` must receive a non-empty list of where dicts."""
    with pytest.raises(ValueError, match=message):
        translate_where({"$and": operand})


def test_empty_in_matches_nothing_and_empty_nin_matches_all(table) -> None:
    """Empty membership lists degrade to false/true, not broken SQL."""
    assert table.count_rows(filter=translate_where({"category": {"$in": []}})) == 0
    assert table.count_rows(filter=translate_where({"category": {"$nin": []}})) == len(_ROWS)


# ── ChromaDB missing-field semantics ──────────────────────────────────

_SCHEMA_FIELDS = frozenset({"id", "file_path", "category", "score", "vector"})


class TestMissingFieldSemantics:
    """Null-aware operators and absent-field folding must match ChromaDB.

    ChromaDB treats a metadata key a row does not carry as "not equal":
    ``$ne``/``$nin`` match such rows, every other operator does not.
    LanceDB SQL drops NULL comparisons silently, and the planner
    rejects struct fields that do not exist at all — both divergence
    points are covered here.
    """

    @pytest.fixture
    def nullable(self, tmp_path: Path):
        """Table whose ``category`` is NULL on one row, absent nowhere."""
        rows = [
            {"id": "n1", "category": None, "score": 1, "vector": [0.1, 0.0]},
            {"id": "n2", "category": "AI", "score": 2, "vector": [0.0, 0.1]},
        ]
        db = lancedb.connect(str(tmp_path / "lancedb"))
        return db.create_table("nullable", rows, mode="overwrite")

    def test_ne_matches_null_rows(self, nullable) -> None:
        """``$ne`` must include rows where the field is NULL."""
        count = nullable.count_rows(filter=translate_where({"category": {"$ne": "Biology"}}))
        assert count == 2  # the NULL row and the differing row

    def test_nin_matches_null_rows(self, nullable) -> None:
        """``$nin`` must include rows where the field is NULL."""
        count = nullable.count_rows(filter=translate_where({"category": {"$nin": ["Biology"]}}))
        assert count == 2

    def test_eq_and_comparisons_exclude_null_rows(self, nullable) -> None:
        """``$eq``/``$gt`` must not match NULL rows (SQL unknown already does)."""
        assert nullable.count_rows(filter=translate_where({"category": "AI"})) == 1
        assert nullable.count_rows(filter=translate_where({"score": {"$gt": 0}})) == 2

    def test_absent_from_schema_folds_to_chroma_constants(self, table) -> None:
        """A field no row carries folds instead of failing planning."""
        assert (
            table.count_rows(filter=translate_where({"nope": "x"}, known_fields=_SCHEMA_FIELDS))
            == 0
        )
        assert table.count_rows(
            filter=translate_where({"nope": {"$ne": "x"}}, known_fields=_SCHEMA_FIELDS)
        ) == len(_ROWS)
        assert (
            table.count_rows(
                filter=translate_where({"nope": {"$in": ["x"]}}, known_fields=_SCHEMA_FIELDS)
            )
            == 0
        )
        assert table.count_rows(
            filter=translate_where({"nope": {"$nin": ["x"]}}, known_fields=_SCHEMA_FIELDS)
        ) == len(_ROWS)

    def test_absent_field_folds_inside_boolean_composition(self, table) -> None:
        """Folded constants must compose with present-field predicates."""
        where = {
            "$or": [
                {"nope": {"$ne": "anything"}},
                {"category": "Chemistry"},
            ]
        }
        assert table.count_rows(filter=translate_where(where, known_fields=_SCHEMA_FIELDS)) == len(
            _ROWS
        )

    def test_unknown_field_without_schema_still_reaches_the_planner(self, table) -> None:
        """Without ``known_fields`` an absent field is the engine's error.

        The match is loosened to the field name only: the full planner
        message ("field named nope") is DataFusion's wording and can
        change across upgrades without any behaviour change here.
        """
        with pytest.raises(ValueError, match="nope"):
            table.count_rows(filter=translate_where({"nope": "x"}))

    @pytest.mark.parametrize("boolean_op", ["$and", "$or"])
    def test_empty_boolean_sub_clause_rejected(self, boolean_op: str) -> None:
        """An empty sub-clause dict must fail before the recursive join.

        Unrejected, ``translate_where({})`` inside ``$and``/``$or``
        returns ``None`` and the join raises an unrelated
        ``TypeError`` — or worse, folds to "no filter".
        """
        with pytest.raises(ValueError, match="non-empty where dict"):
            translate_where({boolean_op: [{"tag": "x"}, {}]})

    def test_boolean_op_with_only_empty_clauses_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty where dict"):
            translate_where({"$or": [{}]})


# ── Identifier quoting ────────────────────────────────────────────────


def test_hyphenated_field_name_is_quoted_and_matches(tmp_path: Path) -> None:
    """Grammar-legal hyphenated names must filter correctly.

    Unquoted, ``metadata.file-path`` parses as ``file`` minus ``path``;
    backticks keep it one identifier.
    """
    rows = [
        {"id": "h1", "file-path": "a.py", "vector": [0.1, 0.0]},
        {"id": "h2", "file-path": "b.py", "vector": [0.0, 0.1]},
    ]
    db = lancedb.connect(str(tmp_path / "lancedb"))
    table = db.create_table("hyphen", rows, mode="overwrite")
    assert table.count_rows(filter=translate_where({"file-path": "a.py"})) == 1


def test_field_references_are_backtick_quoted() -> None:
    """Every emitted field reference is quoted (hyphens stay one identifier)."""
    expr = translate_where({"file-path": "a.py"}, metadata_column="metadata")
    assert expr == "`metadata`.`file-path` = 'a.py'"
