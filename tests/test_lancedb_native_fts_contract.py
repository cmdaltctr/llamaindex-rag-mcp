"""Locked-version contract for LanceDB native full-text search (FTS).

Pre-implementation feasibility pins (task 0.1,
``implement-native-sparse-backend-strategy``): these tests exercise the
RAW ``lancedb`` 0.37.1 / ``pylance`` 10.0.0 API surface against real
temporary stores under ``tmp_path`` so a dependency bump that changes
the native-FTS behaviour this change builds on fails loudly here —
before any adapter code depends on it.

Pinned surface (observed on the locked versions):

- Index creation: ``table.create_index("text", config=FTS())`` is
  additive on populated tables, idempotent under the default
  ``replace=True``, and works on empty tables.
- Query: ``table.search(q, query_type="fts")`` with ``.where(sql)``
  and ``.limit(n)``; only the indexed ``text`` column is searched
  (``id``/``doc_id`` do not leak into matches).
- Result shape: plain row dicts carrying ``id``, ``doc_id``,
  ``vector``, ``text``, ``metadata`` and ``_score`` — no
  ``_distance``.
- Score semantics: ``_score`` is higher-is-better and BM25-like; a
  two-term match outranks a one-term match; matches score above zero.
- Freshness: query-time fresh-by-construction — rows added after
  index creation are found (unindexed-row scan) and deleted rows
  disappear (tombstones), while the query itself does not mutate
  index statistics.
- Refresh: ``table.optimize()`` folds unindexed rows into the index
  (``num_unindexed_rows`` drops to zero).
- Coverage: ``table.list_indices()`` exposes ``num_indexed_rows`` /
  ``num_unindexed_rows`` per FTS index — the mixed-coverage signal.
- Absence: FTS search without an index raises ``ValueError`` carrying
  "Cannot perform full text search" — the signal that routes the
  sparse backend to BM25 fallback.
- Durability: the index survives reconnection; a fresh connection
  serves FTS immediately.

The production row schema comes from the shared seam
(:func:`rag_mcp.core.vectordb.lance_rows.upsert_schema`) so the pins
hold for the schema the adapter actually writes, and metadata filters
flow through :func:`.lance_filter.translate_where` so the SQL the
adapter will build is the SQL pinned here.
"""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

from rag_mcp.core.vectordb.lance_filter import translate_where
from rag_mcp.core.vectordb.lance_rows import upsert_schema

_DIM = 4


def _locked_version(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def _row(
    row_id: str,
    text: str,
    category: str,
    doc_id: str = "doc-1",
) -> dict:
    return {
        "id": row_id,
        "doc_id": doc_id,
        "vector": [0.1] * _DIM,
        "text": text,
        "metadata": {"category": category},
    }


@pytest.fixture()
def fts_table(tmp_path: Path):
    """A populated table with an FTS index on ``text``.

    Built through the production ``upsert_schema`` seam so the pinned
    behaviour applies to the column layout the adapter writes
    (``id``, ``doc_id``, ``vector``, ``text``, ``metadata`` struct).
    """
    import lancedb
    from lancedb.index import FTS

    connection = lancedb.connect(str(tmp_path / "contract"))
    table = connection.create_table(
        "contract_fts",
        schema=upsert_schema(_DIM, [{"category": "history"}]),
        mode="create",
    )
    table.add(
        [
            _row("history-1", "the colosseum of ancient rome", "history"),
            _row("science-1", "quantum computing qubits", "science"),
            _row("sport-1", "modern stadium concrete design", "sport"),
        ]
    )
    table.create_index("text", config=FTS())
    return connection, table


def _fts_index_stats(table) -> tuple[int, int] | None:
    """Return ``(num_indexed_rows, num_unindexed_rows)`` for the FTS index."""
    for index in table.list_indices():
        if index.index_type == "FTS" and "text" in index.columns:
            return index.num_indexed_rows, index.num_unindexed_rows
    return None


# ── Version lock ─────────────────────────────────────────────────────


def test_locked_lancedb_versions() -> None:
    """The pins below are only valid for the locked dependency pair."""
    assert _locked_version("lancedb") == "0.37.1"
    assert _locked_version("pylance") == "10.0.0"


# ── Index configuration ──────────────────────────────────────────────


def test_fts_index_creation_is_additive_on_existing_rows(fts_table) -> None:
    """Index creation covers rows written before the index existed."""
    _connection, table = fts_table
    stats = _fts_index_stats(table)
    assert stats is not None, "no FTS index reported by list_indices()"
    indexed, unindexed = stats
    assert indexed == 3
    assert unindexed == 0


def test_fts_index_recreation_is_idempotent(fts_table) -> None:
    """Default ``replace=True`` makes explicit re-creation safe."""
    from lancedb.index import FTS

    _connection, table = fts_table
    table.create_index("text", config=FTS())
    rows = table.search("colosseum", query_type="fts").to_list()
    assert [row["id"] for row in rows] == ["history-1"]


def test_fts_index_creation_on_empty_table_succeeds(tmp_path: Path) -> None:
    """First-use creation must not require existing rows."""
    import lancedb
    from lancedb.index import FTS

    connection = lancedb.connect(str(tmp_path / "empty"))
    table = connection.create_table(
        "empty_fts",
        schema=upsert_schema(_DIM, [{"category": "x"}]),
        mode="create",
    )
    table.create_index("text", config=FTS())
    assert table.search("anything", query_type="fts").to_list() == []


# ── Query surface ────────────────────────────────────────────────────


def test_fts_search_returns_matching_rows_only(fts_table) -> None:
    """``query_type="fts"`` ranks text matches; non-matches are absent."""
    _connection, table = fts_table
    rows = table.search("colosseum", query_type="fts").to_list()
    assert [row["id"] for row in rows] == ["history-1"]


def test_fts_result_row_shape(fts_table) -> None:
    """FTS rows carry content fields plus ``_score`` — never ``_distance``."""
    _connection, table = fts_table
    row = table.search("colosseum", query_type="fts").to_list()[0]
    assert set(row) == {"id", "doc_id", "vector", "text", "metadata", "_score"}
    # ``_score`` is injected by the query builder and appears in results;
    # dense-mode's ``_distance`` must not.
    assert row["_score"] > 0.0
    assert "_distance" not in row
    assert row["text"] == "the colosseum of ancient rome"
    assert row["metadata"] == {"category": "history"}


def test_fts_searches_only_the_indexed_text_column(fts_table) -> None:
    """``id``/``doc_id`` values must not leak text matches."""
    _connection, table = fts_table
    # "history-1" appears as an id value; only prose matches count.
    rows = table.search("history", query_type="fts").to_list()
    assert rows == []


def test_fts_limit_truncates_results(fts_table) -> None:
    """.limit() applies to the fused FTS ranking."""
    _connection, table = fts_table
    rows = table.search("rome stadium qubits", query_type="fts").limit(2).to_list()
    assert len(rows) == 2


def test_fts_empty_query_returns_no_rows(fts_table) -> None:
    """An empty query is a valid no-op, not an error."""
    _connection, table = fts_table
    assert table.search("", query_type="fts").to_list() == []


# ── Metadata filtering combined with FTS ─────────────────────────────


def test_fts_where_filter_restricts_matches(fts_table) -> None:
    """A translated Chroma-style filter composes with the FTS query."""
    _connection, table = fts_table
    # Both rows mention "stadium"-adjacent prose via the terms below;
    # only the sport row matches the filter.
    table.add([_row("science-2", "stadium sized quantum array", "science")])
    sql = translate_where(
        {"category": "sport"}, metadata_column="metadata", known_fields={"category"}
    )
    rows = table.search("stadium", query_type="fts").where(sql).to_list()
    assert [row["id"] for row in rows] == ["sport-1"]


def test_fts_where_filter_can_exclude_every_match(fts_table) -> None:
    """A filter that excludes all text matches yields an empty result."""
    _connection, table = fts_table
    sql = translate_where(
        {"category": "science"}, metadata_column="metadata", known_fields={"category"}
    )
    rows = table.search("colosseum", query_type="fts").where(sql).to_list()
    assert rows == []


# ── Score semantics ──────────────────────────────────────────────────


def test_fts_scores_are_higher_is_better(fts_table) -> None:
    """A two-term match outranks a one-term match (BM25-like)."""
    _connection, table = fts_table
    table.add(
        [
            _row("both-terms", "zephyr theta combined", "history"),
            _row("one-term", "zephyr alone here", "history"),
        ]
    )
    rows = table.search("zephyr theta", query_type="fts").to_list()
    assert [row["id"] for row in rows[:2]] == ["both-terms", "one-term"]
    assert rows[0]["_score"] > rows[1]["_score"] > 0.0


# ── Freshness / refresh ──────────────────────────────────────────────


def test_fts_fresh_after_write_covers_unindexed_rows(fts_table) -> None:
    """Rows added after index creation are found without an explicit refresh.

    This is the load-bearing freshness fact: the native query is
    fresh-by-construction (unindexed rows are scanned at query time),
    so a native result never silently misses post-index writes.
    """
    _connection, table = fts_table
    table.add([_row("late-1", "zephyr unique late token", "science")])
    # The index statistics still report the row as unindexed...
    assert _fts_index_stats(table) == (3, 1)
    # ...yet the query finds it.
    rows = table.search("zephyr", query_type="fts").to_list()
    assert [row["id"] for row in rows] == ["late-1"]


def test_fts_query_does_not_mutate_index_statistics(fts_table) -> None:
    """Searching is read-only for coverage statistics (no lazy fold-in)."""
    _connection, table = fts_table
    table.add([_row("late-2", "omega late row", "science")])
    assert _fts_index_stats(table) == (3, 1)
    table.search("omega", query_type="fts").to_list()
    assert _fts_index_stats(table) == (3, 1)


def test_fts_fresh_after_delete_drops_rows(fts_table) -> None:
    """Deleted rows disappear from FTS results immediately (tombstones)."""
    _connection, table = fts_table
    table.delete("id = 'history-1'")
    assert table.search("colosseum", query_type="fts").to_list() == []


def test_fts_optimize_folds_unindexed_rows_into_index(fts_table) -> None:
    """``optimize()`` is the refresh operation: coverage returns to full."""
    _connection, table = fts_table
    table.add([_row("late-3", "omega late row", "science")])
    assert _fts_index_stats(table) == (3, 1)
    table.optimize()
    assert _fts_index_stats(table) == (4, 0)
    assert [row["id"] for row in table.search("omega", query_type="fts").to_list()] == ["late-3"]


def test_fts_index_and_stats_survive_reconnect(fts_table) -> None:
    """The on-disk index is durable across connections (cross-process)."""
    connection, table = fts_table
    table.add([_row("late-4", "theta late row", "science")])
    reopened = lancedb_connect_existing(connection, "contract_fts")
    assert _fts_index_stats(reopened) == (3, 1)
    assert [row["id"] for row in reopened.search("theta", query_type="fts").to_list()] == ["late-4"]


def lancedb_connect_existing(connection, table_name: str):
    """Reopen *table_name* through a NEW connection on the same URI."""
    import lancedb

    uri = str(connection.uri)
    return lancedb.connect(uri).open_table(table_name)


# ── Coverage diagnostics ─────────────────────────────────────────────


def test_list_indices_reports_partial_coverage(fts_table) -> None:
    """Mixed coverage is observable: indexed vs unindexed row counts."""
    _connection, table = fts_table
    table.add(
        [
            _row("late-5", "kappa late row one", "science"),
            _row("late-6", "kappa late row two", "science"),
        ]
    )
    assert _fts_index_stats(table) == (3, 2)


# ── Absence / failure signal (the BM25-fallback trigger) ────────────


def test_fts_search_without_index_raises_value_error(tmp_path: Path) -> None:
    """No FTS index → the documented ValueError naming the requirement.

    This exception (message pinned by regex, not exact text) is the
    signal the adapter treats as "native unavailable on this
    collection" and routes to BM25 fallback.
    """
    import lancedb

    connection = lancedb.connect(str(tmp_path / "no_index"))
    table = connection.create_table(
        "no_index_fts",
        schema=upsert_schema(_DIM, [{"category": "x"}]),
        mode="create",
    )
    table.add([_row("only-1", "unindexed zephyr text", "history")])
    with pytest.raises(ValueError, match=re.escape("full text search")):
        table.search("zephyr", query_type="fts").to_list()


def test_fts_search_on_absent_column_name_fails(fts_table) -> None:
    """The pre-correction column name ``documents`` is not the FTS column."""
    from lancedb.index import FTS

    _connection, table = fts_table
    with pytest.raises(Exception, match="(?i)not found|does not exist|column"):
        table.create_index("documents", config=FTS())
