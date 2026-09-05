"""Unit and integration tests for the retrieval-context-assembly capability.

Pins every scenario of
``openspec/changes/fix-retrieval-freshness-and-context-assembly-2/specs/
retrieval-context-assembly/spec.md`` (stage 5): the explicit assembly
stage, contiguity-driven lossless merging, opt-in bounded neighbour
expansion, and assembly observability.  Merging scenarios run directly
against :func:`assemble`; expansion composes with the lineage navigator
over a seeded store; the observability and ``top_k`` scenarios run
through ``search()`` against a stub store, mirroring the pattern of
``tests/test_retrieval_timing_diagnostics.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from omrg.core.retrieval.assembly import (
    ASSEMBLY_INTERNAL_FIELDS,
    MERGED_CHUNK_IDS_KEY,
    assemble,
    promote_assembly_diagnostics,
)

_SOURCE = "src_alpha"
_OTHER_SOURCE = "src_beta"
_VERSION = "ver_one"
_OTHER_VERSION = "ver_two"
_COUNT = 6

_DENSE = "dense_cosine"
_RRF = "rrf_utility_v1"


# ── Row builders ──────────────────────────────────────────────────────


def _meta(
    source_id: str = _SOURCE,
    version: str = _VERSION,
    index: int = 0,
    count: int = _COUNT,
) -> dict[str, Any]:
    """Return persisted-style lineage metadata for one chunk."""
    return {
        "file_path": f"/data/{source_id}.txt",
        "source_id": source_id,
        "source_version": version,
        "chunk_id": f"chk_{source_id}_{version}_{index}",
        "source_chunk_index": index,
        "source_chunk_count": count,
    }


def _row(
    text: str,
    index: int,
    *,
    score: float = 0.5,
    score_kind: str = _DENSE,
    source_id: str = _SOURCE,
    version: str = _VERSION,
    reranked: bool = False,
) -> dict[str, Any]:
    """Build one retrieval-shaped ranked result row."""
    meta = _meta(source_id, version, index)
    return {
        "id": f"row_{index}",
        "score": score,
        "score_kind": score_kind,
        "source": meta["file_path"],
        "page_label": None,
        "text": text,
        "metadata": meta,
        "reranked": reranked,
        "source_id": meta["source_id"],
        "source_version": meta["source_version"],
        "chunk_id": meta["chunk_id"],
        "source_chunk_index": meta["source_chunk_index"],
        "source_chunk_count": meta["source_chunk_count"],
    }


def _no_lineage_row(text: str, score: float = 0.4) -> dict[str, Any]:
    """Build an experiment-precomputed row without any lineage."""
    return {
        "id": "row_experiment",
        "score": score,
        "score_kind": _DENSE,
        "source": "/exp/row.bin",
        "page_label": None,
        "text": text,
        "metadata": {"file_path": "/exp/row.bin"},
        "reranked": False,
    }


class _FakeStore:
    """Minimal store serving the filtered row-read contract for expansion."""

    def __init__(self, rows: dict[tuple[str, str, int], str]) -> None:
        self._rows = rows

    def iter_filtered_documents(
        self, collection_name: str, where: dict, page_size: int | None = None
    ) -> Iterator[tuple[str, str, dict]]:
        for (source_id, version, index), text in sorted(self._rows.items()):
            meta = _meta(source_id, version, index)
            if all(meta.get(key) == value for key, value in where.items()):
                yield (f"row_{index}", text, meta)


def _seeded_store(**overrides: tuple[str, str, int]) -> _FakeStore:
    """Return a store seeded with chunks 0..5 of the default source."""
    rows: dict[tuple[str, str, int], str] = {
        **{
            (_SOURCE, _VERSION, index): f"chunk {index} unique text t{index}"
            for index in range(_COUNT)
        },
        **{key: value for key, value in overrides.items()},
    }
    return _FakeStore(rows)


def _assemble(
    rows: list[dict[str, Any]],
    *,
    chunk_overlap: int = 100,
    expand_window: int = 0,
    store: Any = None,
) -> list[dict[str, Any]]:
    """Run assemble with default stubs."""
    return assemble(
        rows,
        chunk_overlap=chunk_overlap,
        expand_window=expand_window,
        store=store or _FakeStore({}),
        collection="documents",
    )


# ── Requirement: explicit assembly stage ──────────────────────────────


class TestAssemblyStage:
    """Assembly runs after ranking and never removes evidence."""

    def test_assembly_runs_on_the_final_set_and_preserves_ranked_order(self) -> None:
        """Scenario: assembly runs after ranking.

        The relative order established by ranking is preserved: a merged
        row takes the position of its earliest-ranked constituent.
        """
        rows = [
            _row("bravo text charlie delta", 2, score=0.9),
            _row("charlie delta echo foxtrot", 3, score=0.8),
            _row("unrelated first chunk", 0, score=0.7),
        ]
        results = _assemble(rows)
        assert [row["chunk_id"] for row in results] == [
            f"chk_{_SOURCE}_{_VERSION}_2",
            f"chk_{_SOURCE}_{_VERSION}_0",
        ]
        # The merged row keeps the best (earliest-ranked here) position.
        assert results[0]["_assembly_chunk_count"] == 2
        assert results[1]["_assembly_chunk_count"] == 1

    def test_assembly_never_removes_evidence(self) -> None:
        """Scenario: assembly never removes evidence.

        Every distinct chunk before assembly is represented afterwards,
        and no chunk's unique text is lost.
        """
        rows = [
            _row("alpha overlap beta", 0, score=0.9),
            _row("alpha overlap beta gamma", 1, score=0.8),
            _row("alpha overlap beta gamma delta", 2, score=0.7),
            _row("standalone unique words zulu yankee", 4, score=0.6),
            _no_lineage_row("experiment unique words quebec"),
        ]
        results = _assemble(rows)
        represented: set[str] = set()
        for row in results:
            represented.update(row.get(MERGED_CHUNK_IDS_KEY, [row.get("chunk_id")]))
        expected = {f"chk_{_SOURCE}_{_VERSION}_{index}" for index in (0, 1, 2, 4)}
        expected.add(None)  # the lineage-free row carries no chunk id
        assert expected <= represented
        joined = "\n".join(row["text"] for row in results)
        for token in ("gamma", "delta", "zulu", "yankee", "quebec", "standalone", "experiment"):
            assert token in joined, f"unique token {token!r} was lost"

    def test_inert_rows_pass_through_unchanged_in_order(self) -> None:
        """Rows without lineage are never merged and keep their position."""
        rows = [
            _no_lineage_row("first experiment row", score=0.9),
            _row("adjacent one", 0, score=0.8),
            _row("adjacent two", 1, score=0.7),
            _no_lineage_row("second experiment row", score=0.6),
        ]
        results = _assemble(rows)
        assert len(results) == 3
        assert results[0]["text"] == "first experiment row"
        assert results[2]["text"] == "second experiment row"

    def test_bare_row_without_metadata_is_inert(self) -> None:
        """A row with neither top-level lineage nor metadata stands alone."""
        results = _assemble([{"text": "bare row", "score": 0.5, "score_kind": _DENSE}])
        assert len(results) == 1
        assert results[0]["text"] == "bare row"

    def test_repeated_index_keeps_the_higher_ranked_row(self) -> None:
        """A duplicate chunk index keeps its first, best-ranked candidate."""
        first = _row("duplicate chunk text", 2, score=0.9)
        duplicate = _row("duplicate chunk text", 2, score=0.4)
        results = _assemble([first, duplicate])
        assert len(results) == 1
        assert results[0]["score"] == 0.9

    def test_empty_input_returns_empty(self) -> None:
        """An empty ranked set assembles to nothing."""
        assert _assemble([]) == []


# ── Requirement: overlapping adjacent chunks are merged ───────────────


class TestOverlapMerging:
    """Contiguity-driven, lossless merging of adjacent chunks."""

    def test_adjacent_chunks_are_merged(self) -> None:
        """Scenario: adjacent chunks are merged.

        One merged row is emitted, each source sentence appears once, and
        the character length is less than the input sum because a
        non-empty exact boundary match was removed.
        """
        left = "alpha bravo charlie delta echo"
        right = "delta echo foxtrot golf hotel"
        results = _assemble([_row(left, 0, score=0.8), _row(right, 1, score=0.9, score_kind=_RRF)])
        assert len(results) == 1
        merged = results[0]
        assert merged["text"] == "alpha bravo charlie delta echo foxtrot golf hotel"
        assert len(merged["text"]) < len(left) + len(right)

    def test_no_exact_boundary_match_loses_no_text(self) -> None:
        """Scenario: whitespace differences defeat exact matching.

        Adjacent chunks with no exact suffix/prefix match within the
        budget are concatenated without deleting text; every unique
        character sequence from both inputs remains.
        """
        left = "the value is delta echo"
        right = "delta  echo means two spaces here"  # double space: no exact match
        results = _assemble([_row(left, 0), _row(right, 1)])
        assert len(results) == 1
        merged = results[0]["text"]
        assert "delta echo" in merged, "left-hand unique text was lost"
        assert "delta  echo" in merged, "right-hand unique text was lost"

    def test_heading_prepend_survives_the_merge(self) -> None:
        """A heading prepended inside the next chunk is never removed.

        Only the exact splitter overlap is removed; headings the splitter
        reattached are new text and must survive verbatim.
        """
        left = "body text delta echo"
        right = "delta echo\n# Next Section\nheading body follows"
        results = _assemble([_row(left, 0), _row(right, 1)])
        assert len(results) == 1
        merged = results[0]["text"]
        assert "# Next Section" in merged
        assert "heading body follows" in merged
        assert merged.count("delta echo") == 1, "the overlap must be removed exactly once"

    def test_repeated_text_is_deterministic(self) -> None:
        """Scenario: repeated text is deterministic.

        With repeated phrases at more than one possible boundary, the
        longest exact suffix/prefix match within the token budget is
        removed once and no non-boundary occurrence is removed.
        """
        phrase = "alpha beta"
        left = f"{phrase} head {phrase} {phrase}"
        right = f"{phrase} {phrase} tail"
        results = _assemble([_row(left, 0), _row(right, 1)], chunk_overlap=4)
        assert len(results) == 1
        merged = results[0]["text"]
        # 5 boundary-side occurrences in the inputs minus one removed pair.
        assert merged.count("alpha beta") == 3, merged
        assert merged == f"{phrase} head {phrase} {phrase} tail"
        # A tighter budget still removes exactly one (shorter) match.
        tighter = _assemble([_row(left, 0), _row(right, 1)], chunk_overlap=2)[0]["text"]
        assert tighter.count("alpha beta") == 4, tighter

    def test_non_adjacent_chunks_are_not_merged(self) -> None:
        """Scenario: chunks at indices i and i+3 stay two rows."""
        results = _assemble([_row("first part", 0), _row("second part", 3)])
        assert len(results) == 2
        assert [row["text"] for row in results] == ["first part", "second part"]

    def test_chunks_from_different_sources_are_not_merged(self) -> None:
        """Scenario: different source_id values never merge."""
        results = _assemble(
            [
                _row("alpha shared", 0, source_id=_SOURCE),
                _row("alpha shared", 1, source_id=_OTHER_SOURCE),
            ]
        )
        assert len(results) == 2

    def test_chunks_from_different_source_versions_are_not_merged(self) -> None:
        """Chunks of two versions of one source are never adjacent."""
        results = _assemble(
            [
                _row("alpha shared", 0, version=_VERSION),
                _row("alpha shared", 1, version=_OTHER_VERSION),
            ]
        )
        assert len(results) == 2

    def test_merged_row_reports_its_constituents(self) -> None:
        """Scenario: a merged row reports its constituents.

        Every constituent ``chunk_id`` is exposed, the index is the lowest
        constituent index, the score is the best constituent score, and
        ``score_kind`` is that best-scoring constituent's kind.
        """
        results = _assemble(
            [
                _row("alpha overlap beta", 0, score=0.8, score_kind=_DENSE),
                _row("alpha overlap beta gamma", 1, score=0.95, score_kind=_RRF, reranked=True),
                _row("gamma tail zulu", 2, score=0.7),
            ]
        )
        assert len(results) == 1
        merged = results[0]
        assert merged[MERGED_CHUNK_IDS_KEY] == [
            f"chk_{_SOURCE}_{_VERSION}_0",
            f"chk_{_SOURCE}_{_VERSION}_1",
            f"chk_{_SOURCE}_{_VERSION}_2",
        ]
        assert merged["source_chunk_index"] == 0
        assert merged["score"] == 0.95
        assert merged["score_kind"] == _RRF
        assert merged["reranked"] is True
        assert merged["chunk_id"] == f"chk_{_SOURCE}_{_VERSION}_0"

    def test_unmerged_rows_carry_no_merged_fields(self) -> None:
        """Singleton rows keep the plain shape: no ``chunk_ids`` key."""
        results = _assemble([_row("lone chunk", 0), _row("other", 3)])
        for row in results:
            assert MERGED_CHUNK_IDS_KEY not in row
            assert row["_assembly_merged"] is False
            assert row["_assembly_chunk_count"] == 1
            assert row["_assembly_expanded"] is False

    def test_zero_overlap_is_a_no_op(self) -> None:
        """Scenario: zero overlap still concatenates without removal."""
        left = "first chunk ends here."
        right = "Second chunk starts here."
        results = _assemble(
            [_row(left, 0), _row(right, 1)],
            chunk_overlap=0,
        )
        assert len(results) == 1
        merged = results[0]["text"]
        assert left in merged and right in merged
        assert len(merged) >= len(left) + len(right), "text was removed with a zero budget"

    def test_budget_too_small_for_the_match_concatenates_instead(self) -> None:
        """A genuine overlap larger than the budget is not removed."""
        left = "one two three four five"
        right = "one two three four five six"
        results = _assemble([_row(left, 0), _row(right, 1)], chunk_overlap=1)
        assert len(results) == 1
        merged = results[0]["text"]
        assert "one two three four five six" in merged
        assert merged.count("one two") == 2, "the oversized match must not be removed"

    def test_boundary_whitespace_joins_without_an_added_space(self) -> None:
        """A newline at the boundary joins directly, adding no space."""
        left = "paragraph one ends here\n"
        right = "\nparagraph two starts here"
        results = _assemble([_row(left, 0), _row(right, 1)], chunk_overlap=0)
        assert results[0]["text"] == left + right

    def test_empty_neighbour_text_is_tolerated(self) -> None:
        """Empty texts concatenate to the non-empty side without error."""
        results = _assemble([_row("kept text", 0), _row("", 1)], chunk_overlap=100)
        assert results[0]["text"] == "kept text"
        empty_leading = _assemble([_row("", 0), _row("kept text", 1)], chunk_overlap=100)
        assert empty_leading[0]["text"] == "kept text"

    def test_metadata_nested_lineage_rows_merge(self) -> None:
        """Rows carrying lineage only inside metadata still group by run."""
        first = _row("nested lineage one tail", 0)
        second = _row("nested lineage one tail two", 1)
        for row in (first, second):
            for key in (
                "source_id",
                "source_version",
                "chunk_id",
                "source_chunk_index",
                "source_chunk_count",
            ):
                row.pop(key)
        results = _assemble([first, second])
        assert len(results) == 1
        assert results[0][MERGED_CHUNK_IDS_KEY] == [
            f"chk_{_SOURCE}_{_VERSION}_0",
            f"chk_{_SOURCE}_{_VERSION}_1",
        ]

    def test_constituents_without_chunk_id_merge_without_the_ids_field(self) -> None:
        """A run whose rows lack chunk_id values gains no empty list."""
        first = _row("legacy tail", 0)
        second = _row("legacy tail two", 1)
        first.pop("chunk_id")
        second.pop("chunk_id")
        first["metadata"].pop("chunk_id")
        second["metadata"].pop("chunk_id")
        results = _assemble([first, second])
        assert len(results) == 1
        assert MERGED_CHUNK_IDS_KEY not in results[0]
        assert results[0]["_assembly_merged"] is True


# ── Requirement: neighbour expansion is opt-in and bounded ────────────


class TestNeighbourExpansion:
    """Opt-in, bounded neighbour expansion through the lineage navigator."""

    def test_expansion_is_off_by_default(self) -> None:
        """Scenario: without expansion no absent chunk is returned."""
        store = _seeded_store()
        rows = [_row("chunk 2 unique text t2", 2, score=0.9)]
        results = _assemble(rows, expand_window=0, store=store)
        assert len(results) == 1
        assert MERGED_CHUNK_IDS_KEY not in results[0]
        assert results[0]["chunk_id"] == f"chk_{_SOURCE}_{_VERSION}_2"

    def test_expansion_adds_neighbours_without_a_retrieval_score(self) -> None:
        """Scenario: expansion adds neighbours, marked and unscored.

        The standalone expanded row (retrieved chunk 0, neighbour 2 with
        chunk 1 absent from the store) carries no retrieval score and is
        marked as added by expansion.
        """
        store = _FakeStore(
            {
                (_SOURCE, _VERSION, 0): "chunk zero text",
                (_SOURCE, _VERSION, 2): "chunk two text",
                (_SOURCE, _VERSION, 3): "chunk three text",
            }
        )
        rows = [_row("chunk zero text", 0, score=0.9)]
        results = _assemble(rows, expand_window=2, store=store)
        assert [row["source_chunk_index"] for row in results] == [0, 2]
        expanded = results[1]
        assert expanded["_assembly_expanded"] is True
        assert "score" not in expanded
        assert "score_kind" not in expanded
        assert expanded["reranked"] is False
        assert results[0]["_assembly_expanded"] is False

    def test_expanded_rows_do_not_displace_retrieved_rows(self) -> None:
        """Scenario: every retrieved chunk survives expansion."""
        store = _seeded_store()
        rows = [
            _row("chunk 2 unique text t2", 2, score=0.9),
            _row("chunk 3 unique text t3", 3, score=0.8),
            _row("other source chunk", 0, source_id=_OTHER_SOURCE, score=0.7),
        ]
        results = _assemble(rows, expand_window=1, store=store)
        represented: set[str] = set()
        for row in results:
            represented.update(row.get(MERGED_CHUNK_IDS_KEY, [row.get("chunk_id")]))
        for index in (2, 3):
            assert f"chk_{_SOURCE}_{_VERSION}_{index}" in represented
        assert f"chk_{_OTHER_SOURCE}_{_VERSION}_0" in represented

    def test_expansion_composes_with_merging(self) -> None:
        """Scenario: an expanded neighbour merges into its retrieved chunk."""
        store = _seeded_store()
        rows = [_row("chunk 2 unique text t2", 2, score=0.9)]
        results = _assemble(rows, expand_window=1, store=store)
        assert len(results) == 1
        merged = results[0]
        assert merged[MERGED_CHUNK_IDS_KEY] == [
            f"chk_{_SOURCE}_{_VERSION}_1",
            f"chk_{_SOURCE}_{_VERSION}_2",
            f"chk_{_SOURCE}_{_VERSION}_3",
        ]
        assert merged["_assembly_merged"] is True
        assert merged["_assembly_chunk_count"] == 3
        # The merged row is retrieved-led, so it is not expansion-added.
        assert merged["_assembly_expanded"] is False
        assert merged["score"] == 0.9
        for text in ("chunk 1 unique text t1", "chunk 3 unique text t3"):
            assert text in merged["text"]

    def test_expansion_window_is_bounded(self) -> None:
        """A window of one adds exactly the immediate neighbours."""
        store = _seeded_store()
        rows = [_row("chunk 2 unique text t2", 2, score=0.9)]
        merged = _assemble(rows, expand_window=1, store=store)[0]
        assert merged[MERGED_CHUNK_IDS_KEY] == [
            f"chk_{_SOURCE}_{_VERSION}_1",
            f"chk_{_SOURCE}_{_VERSION}_2",
            f"chk_{_SOURCE}_{_VERSION}_3",
        ]

    def test_rows_without_lineage_expand_to_nothing(self) -> None:
        """Inert rows trigger no neighbour reads."""
        results = _assemble(
            [_no_lineage_row("experiment row")], expand_window=1, store=_seeded_store()
        )
        assert len(results) == 1
        assert results[0]["_assembly_expanded"] is False

    def test_expanded_only_run_merges_without_a_retrieval_score(self) -> None:
        """Two adjacent expansion-only chunks merge and stay unscored.

        The store is missing chunks 1 and 2, so neighbours 3 and 4 of the
        retrieved chunk 0 form a contiguous run that never touches a
        retrieved chunk: the merged row reports expansion and no score.
        """
        store = _FakeStore(
            {
                (_SOURCE, _VERSION, 0): "retrieved head text",
                (_SOURCE, _VERSION, 3): "island three text",
                (_SOURCE, _VERSION, 4): "island three text continues four",
            }
        )
        results = _assemble(
            [_row("retrieved head text", 0, score=0.9)], expand_window=4, store=store
        )
        assert len(results) == 2
        island = results[1]
        assert island[MERGED_CHUNK_IDS_KEY] == [
            f"chk_{_SOURCE}_{_VERSION}_3",
            f"chk_{_SOURCE}_{_VERSION}_4",
        ]
        assert island["_assembly_expanded"] is True
        assert island["_assembly_merged"] is True
        assert "score" not in island
        assert "score_kind" not in island
        assert island["text"] == "island three text continues four"


# ── Requirement: assembly behaviour is observable ─────────────────────


class TestAssemblyObservability:
    """Markers and timings report what assembly did."""

    def test_promote_renames_internal_markers(self) -> None:
        """promote_assembly_diagnostics renames the underscore fields."""
        rows = _assemble([_row("alpha overlap beta", 0), _row("alpha overlap beta gamma", 1)])
        promote_assembly_diagnostics(rows)
        merged = rows[0]
        assert merged["assembly_merged"] is True
        assert merged["assembly_chunk_count"] == 2
        assert merged["assembly_expanded"] is False
        for field in ASSEMBLY_INTERNAL_FIELDS:
            assert field not in merged

    def test_internal_fields_are_listed_for_stripping(self) -> None:
        """The strip helper removes every assembly-internal field."""
        from omrg.core.retrieval.pipeline import _strip_internal_result_fields

        row = _row("alpha", 0)
        row.update(dict.fromkeys(ASSEMBLY_INTERNAL_FIELDS, True))
        public = _strip_internal_result_fields(row)
        for field in ASSEMBLY_INTERNAL_FIELDS:
            assert field not in public
        # Public additive fields survive stripping.
        public[MERGED_CHUNK_IDS_KEY] = ["a", "b"]
        assert _strip_internal_result_fields(public)[MERGED_CHUNK_IDS_KEY] == ["a", "b"]


# ── search()-level integration ────────────────────────────────────────


class _StubSearchStore:
    """Store serving the dense query and filtered row-read seams."""

    def __init__(self, chunks: list[tuple[str, int, str, float]]) -> None:
        self._chunks = chunks

    def count(self, collection_name: str) -> int:
        return len(self._chunks)

    def query_dense(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int,
        where: dict | None = None,
    ) -> list[dict]:
        ranked = sorted(self._chunks, key=lambda chunk: chunk[3], reverse=True)[:n_results]
        return [
            {
                "id": f"row_{source}_{index}",
                "score": score,
                "score_kind": _DENSE,
                "document": text,
                "metadata": _meta(source_id=source, index=index),
            }
            for source, index, text, score in ranked
        ]

    def iter_filtered_documents(
        self, collection_name: str, where: dict, page_size: int | None = None
    ) -> Iterator[tuple[str, str, dict]]:
        for source, index, text, _ in self._chunks:
            meta = _meta(source_id=source, index=index)
            if all(meta.get(key) == value for key, value in where.items()):
                yield (f"row_{source}_{index}", text, meta)


_OVERLAP_TAIL = "shared overlap omega"
_STUB_CHUNKS = [
    (_SOURCE, 0, f"first unique words alpha {_OVERLAP_TAIL}", 0.7),
    (_SOURCE, 1, f"{_OVERLAP_TAIL} second unique words bravo", 0.9),
    (_OTHER_SOURCE, 0, "third standalone chunk sierra", 0.8),
]


def _run_search(
    *,
    expand_window: int = 0,
    diagnostics: bool = False,
    top_k: int = 5,
    chunks: list[tuple[str, int, str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Run search() over the stub store with mocked embeddings."""
    from omrg.core.retrieval import search
    from omrg.core.settings import EffectiveSettings

    return search(
        "unique words",
        top_k=top_k,
        rerank=False,
        hybrid=False,
        expand_window=expand_window,
        store=_StubSearchStore(chunks or _STUB_CHUNKS),
        effective_settings=EffectiveSettings(),
        include_diagnostics=diagnostics,
    )


class TestSearchIntegration:
    """search() runs assembly once, after truncation, before diagnostics."""

    def test_search_merges_adjacent_chunks(self) -> None:
        """The pipeline output no longer repeats the overlap text."""
        results = _run_search()
        assert len(results) == 2
        merged = results[0]
        assert merged["source_chunk_index"] == 0
        assert merged[MERGED_CHUNK_IDS_KEY] == [
            f"chk_{_SOURCE}_{_VERSION}_0",
            f"chk_{_SOURCE}_{_VERSION}_1",
        ]
        assert merged["text"].count(_OVERLAP_TAIL) == 1
        assert merged["score"] == 0.9
        assert results[1]["chunk_id"] == f"chk_{_OTHER_SOURCE}_{_VERSION}_0"

    def test_search_expansion_off_by_default(self) -> None:
        """Scenario: without expansion nothing absent from ranking returns."""
        results = _run_search()
        for row in results:
            assert row.get("_assembly_expanded", False) is False
            assert "score" in row

    def test_search_expansion_adds_and_merges_neighbours(self) -> None:
        """Expansion through search() merges neighbours into the row."""
        chunks = [
            (_SOURCE, 0, f"first unique words alpha {_OVERLAP_TAIL}", 0.7),
            (_SOURCE, 1, f"{_OVERLAP_TAIL} second unique words bravo", 0.9),
            (_SOURCE, 2, "third alpha chunk sierra", 0.6),  # below the top_k cut
            (_OTHER_SOURCE, 0, "standalone beta chunk tango", 0.8),
        ]
        results = _run_search(top_k=3, expand_window=1, chunks=chunks)
        assert len(results) == 2
        merged = next(row for row in results if row["source_id"] == _SOURCE)
        assert merged[MERGED_CHUNK_IDS_KEY] == [
            f"chk_{_SOURCE}_{_VERSION}_0",
            f"chk_{_SOURCE}_{_VERSION}_1",
            f"chk_{_SOURCE}_{_VERSION}_2",
        ]
        assert "third alpha chunk sierra" in merged["text"]
        assert merged["score"] == 0.9
        standalone = next(row for row in results if row["source_id"] == _OTHER_SOURCE)
        assert MERGED_CHUNK_IDS_KEY not in standalone

    def test_search_expansion_never_drops_retrieved_rows_for_top_k(self) -> None:
        """Scenario: top_k truncation happens before expansion."""
        results = _run_search(top_k=1, expand_window=1)
        represented: set[str] = set()
        for row in results:
            represented.update(row.get(MERGED_CHUNK_IDS_KEY, [row.get("chunk_id")]))
        assert f"chk_{_SOURCE}_{_VERSION}_1" in represented, "the retrieved chunk was dropped"

    def test_search_diagnostics_report_assembly(self) -> None:
        """Scenario: diagnostics report assembly markers and duration."""
        results = _run_search(diagnostics=True)
        assert results
        for row in results:
            assert "assembly_merged" in row
            assert "assembly_chunk_count" in row
            assert "assembly_expanded" in row
            assert row["timings"]["assembly_seconds"] >= 0
            assert "_assembly_merged" not in row

    def test_search_public_results_stay_stable(self) -> None:
        """Scenario: without diagnostics the public shape is unchanged."""
        results = _run_search(diagnostics=False)
        assert results
        expected_keys = {
            "score",
            "score_kind",
            "source",
            "page_label",
            "text",
            "reranked",
            "metadata",
            "source_id",
            "source_version",
            "chunk_id",
            "source_chunk_index",
            "source_chunk_count",
        }
        for row in results:
            for field in ASSEMBLY_INTERNAL_FIELDS:
                assert field not in row
            if MERGED_CHUNK_IDS_KEY in row:
                assert set(row.keys()) == expected_keys | {MERGED_CHUNK_IDS_KEY}
            else:
                assert set(row.keys()) == expected_keys

    def test_search_expanded_only_row_has_no_score(self) -> None:
        """A standalone expanded row carries no retrieval score."""
        chunks = [
            (_SOURCE, 0, "retrieved chunk text alpha", 0.9),
            (_SOURCE, 2, "expanded island text tango", 0.0),
        ]
        results = _run_search(top_k=1, expand_window=2, chunks=chunks)
        island = [row for row in results if row.get("source_chunk_index") == 2]
        assert island, "expected the non-adjacent neighbour to be returned"
        assert "score" not in island[0]


# ── Scenario: citations remain verifiable after merging ───────────────


class TestCitationsRemainVerifiable:
    """Every reported constituent chunk_id resolves to exactly one stored row."""

    def test_merged_chunk_ids_resolve_to_exactly_one_stored_chunk(self) -> None:
        """Scenario: constituent chunk_id values are usable metadata filters."""
        from omrg.core.vectordb import get_default_store
        from omrg.core.vectordb.identity import EmbeddingIdentity

        store = get_default_store()
        collection = "assembly_citations"
        texts = [
            "citation alpha omega tail",
            "citation alpha omega tail continues bravo",
            "continues bravo gamma ending",
        ]
        metas = [_meta(index=index) for index in range(3)]
        store.upsert_precomputed(
            collection,
            ids=[f"row_{index}" for index in range(3)],
            documents=texts,
            metadatas=metas,
            embeddings=[[1.0, 0.0] for _ in texts],
            embedding_identity=EmbeddingIdentity(provider="test", model="mock"),
        )
        rows = [
            _row(texts[0], 0, score=0.8),
            _row(texts[1], 1, score=0.9),
            _row(texts[2], 2, score=0.7),
        ]
        merged = _assemble(rows)[0]
        assert len(merged[MERGED_CHUNK_IDS_KEY]) == 3
        for chunk_id in merged[MERGED_CHUNK_IDS_KEY]:
            matches = list(store.iter_filtered_documents(collection, {"chunk_id": chunk_id}))
            assert len(matches) == 1, f"chunk_id {chunk_id} must cite exactly one stored chunk"
            assert matches[0][2]["chunk_id"] == chunk_id
