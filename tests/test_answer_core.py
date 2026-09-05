"""Red-first tests for the grounded answering operation (tasks 1.2-1.4).

Pins the contract of ``omrg.core.answer.answer``: the status taxonomy,
deterministic citations built from supplied lineage, the no-evidence
short-circuit, failure attribution, diagnostics, and merged constituent
reporting. Every test must FAIL today (the operation does not exist) and
pass once ``core/answer/`` lands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omrg.core.answer import answer
from omrg.core.ingestion import ingest_path_async
from omrg.core.retrieval import search

_COLLECTION = "answer_core_docs"

_EVIDENCE_KEYS = (
    "chunk_id",
    "chunk_ids",
    "source_id",
    "source_version",
    "source",
    "source_chunk_index",
    "score",
    "score_kind",
)

_CITATION_KEYS = _EVIDENCE_KEYS[:-1] + ("ordinal",)


class RecordingSeam:
    """Injected completion seam that records every prompt it receives."""

    def __init__(self, *replies: str) -> None:
        """Script one or more replies; the last one repeats when exhausted."""
        if not replies:
            raise ValueError("RecordingSeam needs at least one reply")
        self._replies = list(replies)
        self._last = replies[0]
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        """Record the prompt and return the next scripted reply."""
        self.prompts.append(prompt)
        if self._replies:
            self._last = self._replies.pop(0)
        return self._last


async def _ingest(tmp_path: Path, text: str, name: str = "doc.txt") -> Path:
    """Ingest one text document into the module's test collection."""
    source = tmp_path / name
    source.write_text(text, encoding="utf-8")
    result = await ingest_path_async(str(source), collection_name=_COLLECTION)
    assert result["status"] == "ok", result
    return source


def _answer_kwargs(**extra: Any) -> dict[str, Any]:
    """Permissive, deterministic answer arguments over the test collection."""
    kwargs: dict[str, Any] = {
        "collection_name": _COLLECTION,
        "top_k": 5,
        "similarity_threshold": 0.0,
        "hybrid": False,
        "rerank": False,
    }
    kwargs.update(extra)
    return kwargs


# ── Requirement: absent evidence never produces an invented answer ────────


async def test_empty_collection_returns_no_evidence_without_model_call(tmp_path: Path) -> None:
    """Scenario: empty collection short-circuits before any model call."""
    seam = RecordingSeam("unused reply [1].")

    result = await answer(
        "anything at all",
        complete=seam,
        **_answer_kwargs(collection_name="never_ingested_collection"),
    )

    assert result["status"] == "no_evidence"
    assert result["citations"] == []
    assert result["evidence"] == []
    assert result["answer"] is None
    assert seam.prompts == [], "the completion seam must never be awaited"


async def test_no_provider_with_empty_retrieval_still_reports_no_evidence() -> None:
    """The no-evidence short-circuit beats the missing-provider error."""
    result = await answer(
        "anything at all",
        complete=None,
        **_answer_kwargs(collection_name="never_ingested_collection"),
    )

    assert result["status"] == "no_evidence"
    assert result["answer"] is None
    assert result["evidence"] == []


# ── Requirement: answers are grounded in retrieved evidence ───────────────


async def test_ok_answer_cites_supplied_evidence(tmp_path: Path) -> None:
    """A cited answer is ``ok`` and the evidence rows carry full lineage."""
    await _ingest(
        tmp_path,
        "The lantern array at station one is calibrated every Tuesday. " * 20,
    )
    seam = RecordingSeam("The array is calibrated at station one [1].")

    result = await answer("lantern array calibration", complete=seam, **_answer_kwargs())

    assert result["status"] == "ok"
    assert result["answer"] is not None
    assert result["citations"], "a cited answer must carry at least one citation"
    assert result["citations"][0]["ordinal"] == 1
    assert result["evidence"], "every chunk supplied as context must be returned"
    for row in result["evidence"]:
        for key in _EVIDENCE_KEYS:
            assert key in row, f"evidence row is missing {key!r}"


async def test_citation_schema_carries_lineage(tmp_path: Path) -> None:
    """Every citation entry exposes the full lineage field set."""
    await _ingest(
        tmp_path,
        "The lantern array at station one is calibrated every Tuesday. " * 20,
    )
    seam = RecordingSeam("The array is calibrated at station one [1].")

    result = await answer("lantern array calibration", complete=seam, **_answer_kwargs())

    assert result["status"] == "ok"
    for citation in result["citations"]:
        for key in _CITATION_KEYS:
            assert key in citation, f"citation is missing {key!r}"
        assert isinstance(citation["chunk_ids"], list)
        assert citation["chunk_id"] in citation["chunk_ids"]


# ── Requirement: citations are deterministic and verifiable ───────────────


async def test_every_citation_chunk_id_refetches_exactly_one_chunk(tmp_path: Path) -> None:
    """Scenario: a citation resolves to exactly one stored chunk."""
    await _ingest(
        tmp_path,
        "grounded citation sentinel paragraph about quantum lanterns " * 80,
        name="refetch-doc.txt",
    )
    seam = RecordingSeam("The sentinel answer [1].")
    query = "quantum lanterns"

    result = await answer(query, complete=seam, **_answer_kwargs(top_k=10))

    assert result["status"] == "ok"
    assert result["citations"]
    for citation in result["citations"]:
        single = search(
            query,
            collection_name=_COLLECTION,
            metadata_filter={"chunk_id": citation["chunk_id"]},
            similarity_threshold=0.0,
            top_k=10,
            hybrid=False,
            rerank=False,
        )
        assert len(single) == 1, f"chunk_id {citation['chunk_id']} must re-fetch exactly one chunk"
        assert single[0]["chunk_id"] == citation["chunk_id"]


async def test_merged_constituents_reported_and_verifiable(tmp_path: Path) -> None:
    """Scenario: merged context reports every constituent chunk id."""
    await _ingest(
        tmp_path,
        "grounded citation sentinel paragraph about quantum lanterns " * 240,
        name="merged-doc.txt",
    )
    query = "quantum lanterns"
    kwargs = _answer_kwargs(top_k=10, expand_window=1)

    probe = RecordingSeam("placeholder [1].")
    probe_result = await answer(query, complete=probe, **kwargs)
    merged_ordinals = [
        ordinal
        for ordinal, row in enumerate(probe_result["evidence"], start=1)
        if len(row["chunk_ids"]) > 1
    ]
    assert merged_ordinals, "context assembly must merge adjacent chunks here"

    target = merged_ordinals[0]
    seam = RecordingSeam(f"The merged evidence [ {target} ] supports the finding.")
    result = await answer(query, complete=seam, **kwargs)

    assert result["status"] == "ok"
    citation = next(c for c in result["citations"] if c["ordinal"] == target)
    assert len(citation["chunk_ids"]) > 1
    for chunk_id in citation["chunk_ids"]:
        single = search(
            query,
            collection_name=_COLLECTION,
            metadata_filter={"chunk_id": chunk_id},
            similarity_threshold=0.0,
            top_k=10,
            hybrid=False,
            rerank=False,
        )
        assert len(single) == 1, f"constituent {chunk_id} must resolve to one chunk"


# ── Malformed, duplicate and out-of-range citations ───────────────────────


async def test_out_of_range_ordinal_is_not_grounded(tmp_path: Path) -> None:
    """Scenario: model-invented identifiers are not trusted."""
    await _ingest(
        tmp_path,
        "The lantern array at station one is calibrated every Tuesday. " * 20,
    )
    seam = RecordingSeam("A detailed substantive answer [9].")

    result = await answer("lantern array calibration", complete=seam, **_answer_kwargs())

    assert result["citations"] == []
    assert result["status"] == "generation_unverified"
    assert result["answer"], "the answer text must still be returned"
    assert result["evidence"], "the supplied evidence must still be returned"


async def test_duplicate_ordinals_are_deduplicated(tmp_path: Path) -> None:
    """``[1, 1]`` yields exactly one citation for ordinal 1."""
    await _ingest(
        tmp_path,
        "The lantern array at station one is calibrated every Tuesday. " * 20,
    )
    seam = RecordingSeam("The array answer [1, 1].")

    result = await answer("lantern array calibration", complete=seam, **_answer_kwargs())

    assert result["status"] == "ok"
    ordinals = [citation["ordinal"] for citation in result["citations"]]
    assert ordinals == [1]


async def test_malformed_bracket_groups_are_dropped(tmp_path: Path) -> None:
    """Non-numeric bracket groups are dropped, never fabricated into citations."""
    await _ingest(
        tmp_path,
        "The lantern array at station one is calibrated every Tuesday. " * 20,
    )
    seam = RecordingSeam("An answer mentioning [abc] and also [1, x] here.")

    result = await answer("lantern array calibration", complete=seam, **_answer_kwargs())

    assert result["citations"] == []
    assert result["status"] == "generation_unverified"


async def test_substantive_uncited_answer_is_never_ok(tmp_path: Path) -> None:
    """Scenario: a substantive answer needs a valid citation."""
    await _ingest(
        tmp_path,
        "The lantern array at station one is calibrated every Tuesday. " * 20,
    )
    seam = RecordingSeam("A thorough explanation grounded in careful reasoning without markers.")

    result = await answer("lantern array calibration", complete=seam, **_answer_kwargs())

    assert result["status"] != "ok"
    assert result["status"] == "generation_unverified"
    assert result["answer"], "the answer text must still be returned"
    assert result["evidence"], "the supplied evidence must still be returned"


# ── Requirement: the answer model is injected ─────────────────────────────


async def test_missing_provider_is_actionable_error_with_evidence(tmp_path: Path) -> None:
    """Scenario: no provider configured names the setting, keeps the evidence."""
    await _ingest(
        tmp_path,
        "The lantern array at station one is calibrated every Tuesday. " * 20,
    )

    result = await answer("lantern array calibration", complete=None, **_answer_kwargs())

    assert result["status"] == "error"
    assert result["failure_stage"] is None
    assert "ANSWER__PROVIDER" in (result["error"] or "")
    assert "sampling" in (result["error"] or "").lower()
    assert result["evidence"], "the retrieved evidence must still be returned"
    assert result["answer"] is None


# ── Requirement: retrieval failure is distinguishable ─────────────────────


class _ExplodingStore:
    """A store whose every method raises when called."""

    def __getattr__(self, name: str):
        def _boom(*args, **kwargs):
            raise RuntimeError(f"store exploded in {name}")

        return _boom


async def test_retrieval_failure_attributed_and_seam_untouched(tmp_path: Path) -> None:
    """Scenario: retrieval fails before generation."""
    seam = RecordingSeam("never reached [1].")

    result = await answer(
        "lantern array calibration",
        complete=seam,
        store=_ExplodingStore(),  # type: ignore[arg-type]
        **_answer_kwargs(),
    )

    assert result["status"] == "error"
    assert result["failure_stage"] == "retrieval"
    assert result["error"]
    assert result["evidence"] == []
    assert seam.prompts == [], "the completion seam must never be awaited"


# ── Requirement: the cost of answering is disclosed ───────────────────────


async def test_diagnostics_report_timings_and_call_count(tmp_path: Path) -> None:
    """Diagnostics time both stages and count completion calls."""
    await _ingest(
        tmp_path,
        "The lantern array at station one is calibrated every Tuesday. " * 20,
    )
    seam = RecordingSeam("The array is calibrated at station one [1].")

    result = await answer(
        "lantern array calibration",
        complete=seam,
        include_diagnostics=True,
        **_answer_kwargs(),
    )

    assert "diagnostics" in result
    diagnostics = result["diagnostics"]
    assert isinstance(diagnostics["retrieval_ms"], float)
    assert isinstance(diagnostics["generation_ms"], float)
    assert diagnostics["retrieval_ms"] >= 0.0
    assert diagnostics["generation_ms"] >= 0.0
    assert diagnostics["completion_calls"] == len(seam.prompts)


async def test_diagnostics_absent_by_default(tmp_path: Path) -> None:
    """Without the flag the diagnostics key is absent from the result."""
    await _ingest(
        tmp_path,
        "The lantern array at station one is calibrated every Tuesday. " * 20,
    )
    seam = RecordingSeam("The array is calibrated at station one [1].")

    result = await answer("lantern array calibration", complete=seam, **_answer_kwargs())

    assert "diagnostics" not in result


async def test_completion_source_label_is_echoed(tmp_path: Path) -> None:
    """The completion_source label is echoed verbatim into the result."""
    await _ingest(
        tmp_path,
        "The lantern array at station one is calibrated every Tuesday. " * 20,
    )
    seam = RecordingSeam("The array is calibrated at station one [1].")

    result = await answer(
        "lantern array calibration",
        complete=seam,
        completion_source="unit-test-label",
        **_answer_kwargs(),
    )

    assert result["completion_source"] == "unit-test-label"


# ── Master switch gates every completion path (review F4) ────────────────


async def test_disabled_returns_actionable_error_without_retrieval() -> None:
    """``enabled=False``: actionable error before retrieval or any model."""
    from omrg.core.settings import (
        AnswerBlock,
        get_default_effective_settings,
        set_default_effective_settings,
    )

    current = get_default_effective_settings()
    set_default_effective_settings(
        current.model_copy(update={"answer": AnswerBlock(enabled=False)})
    )
    seam = RecordingSeam("must never run [1].")
    try:
        result = await answer("lantern array calibration", complete=seam, **_answer_kwargs())
    finally:
        set_default_effective_settings(current)

    assert result["status"] == "error"
    assert result["failure_stage"] is None
    assert "ANSWER__ENABLED" in (result["error"] or "")
    assert result["evidence"] == []
    assert seam.prompts == [], "the completion seam must never be awaited"


# ── Settings bounds (review F5) ──────────────────────────────────────────


def test_max_rounds_is_bounded_in_both_settings_models() -> None:
    """``max_rounds`` accepts 1..8 and rejects values beyond the bound."""
    import pytest as _pytest

    from omrg.core.answer.settings import AnswerSettings
    from omrg.core.settings import AnswerBlock

    for model in (AnswerSettings, AnswerBlock):
        assert model(max_rounds=1).max_rounds == 1
        assert model(max_rounds=8).max_rounds == 8
        for bad in (0, -1, 9, 20):
            with _pytest.raises(Exception):
                model(max_rounds=bad)


# ── Hard input limits at the core entry (review F7) ─────────────────────


async def test_query_length_boundary_passes_and_one_over_fails() -> None:
    """A 4096-character query passes; 4097 is a structured error."""
    seam = RecordingSeam("unused [1].")
    kwargs = _answer_kwargs(collection_name="never_ingested_collection")

    ok = await answer("q" * 4096, complete=seam, **kwargs)
    assert ok["status"] == "no_evidence"

    too_long = await answer("q" * 4097, complete=seam, **kwargs)
    assert too_long["status"] == "error"
    assert "4096" in (too_long["error"] or "")
    assert seam.prompts == []


async def test_top_k_boundary_passes_and_one_over_fails() -> None:
    """``top_k`` 1..100 passes; 101 (and 0, -1) are structured errors."""
    seam = RecordingSeam("unused [1].")
    kwargs = _answer_kwargs(collection_name="never_ingested_collection")
    kwargs.pop("top_k")  # the explicit argument below replaces the default

    ok = await answer("q", complete=seam, top_k=100, **kwargs)
    assert ok["status"] == "no_evidence"

    for bad in (101, 0, -1):
        bad_result = await answer("q", complete=seam, top_k=bad, **kwargs)
        assert bad_result["status"] == "error", bad_result
        assert "100" in (bad_result["error"] or "")


async def test_expand_window_boundary_passes_and_one_over_fails() -> None:
    """``expand_window`` 0..10 passes; 11 (and -1) is a structured error."""
    seam = RecordingSeam("unused [1].")
    kwargs = _answer_kwargs(collection_name="never_ingested_collection")

    ok = await answer("q", complete=seam, expand_window=10, **kwargs)
    assert ok["status"] == "no_evidence"

    for bad in (11, -1):
        bad_result = await answer("q", complete=seam, expand_window=bad, **kwargs)
        assert bad_result["status"] == "error", bad_result
        assert "10" in (bad_result["error"] or "")


async def test_similarity_threshold_bounds_and_finiteness() -> None:
    """``similarity_threshold`` must be finite and within 0.0..1.0.

    Python's JSON decoder accepts ``NaN``/``Infinity`` literals, so the
    core entry rejects non-finite floats explicitly (security F2).
    """
    seam = RecordingSeam("unused [1].")
    kwargs = _answer_kwargs(collection_name="never_ingested_collection")
    kwargs.pop("similarity_threshold", None)

    ok = await answer("q", complete=seam, similarity_threshold=1.0, **kwargs)
    assert ok["status"] == "no_evidence"

    for bad in (1.5, -0.01, float("nan"), float("inf")):
        bad_result = await answer("q", complete=seam, similarity_threshold=bad, **kwargs)
        assert bad_result["status"] == "error", bad_result
        assert "similarity_threshold" in (bad_result["error"] or "")


# ── Retrieval must not block the event loop (review F10) ────────────────


class _SlowRetriever:
    """Stand-in retriever whose synchronous retrieve sleeps."""

    def __init__(self, **kwargs: Any) -> None:
        self.rows: list[dict] = []

    def retrieve(self, query: str) -> list[Any]:
        """Sleep in the caller's thread, then serve one evidence row."""
        import time as _time

        _time.sleep(0.2)
        self.rows = [
            {
                "chunk_id": "slow-1",
                "source_id": "slow-doc",
                "source_version": 1,
                "source": "slow.txt",
                "source_chunk_index": 0,
                "score": 0.9,
                "score_kind": "dense",
                "text": "slow evidence body",
            }
        ]
        return []


async def test_concurrent_answers_are_not_serialised_by_retrieval(
    monkeypatch: Any,
) -> None:
    """Two answers over a 0.2 s retrieval complete in under 0.35 s."""
    import asyncio as _asyncio
    import time as _time

    from omrg.core.answer import pipeline as answer_pipeline

    monkeypatch.setattr(answer_pipeline, "SearchRetriever", _SlowRetriever)
    seam = RecordingSeam("The slow evidence body [1].")
    start = _time.perf_counter()
    results = await _asyncio.gather(
        answer("first question", complete=seam, **_answer_kwargs()),
        answer("second question", complete=seam, **_answer_kwargs()),
    )
    elapsed = _time.perf_counter() - start

    assert all(result["status"] == "ok" for result in results), results
    assert elapsed < 0.35, f"synchronous retrieval serialised concurrent answers ({elapsed:.3f} s)"


# ── Honest diagnostics through the transport interface (review F11) ─────


def _plain_row(chunk_id: str, text: str) -> dict[str, Any]:
    """Build one minimal search() row for transport-interface tests."""
    return {
        "chunk_id": chunk_id,
        "source_id": f"{chunk_id}-doc",
        "source_version": 1,
        "source": f"{chunk_id}.txt",
        "source_chunk_index": 0,
        "score": 0.9,
        "score_kind": "dense",
        "text": text,
    }


async def test_resolved_retrieval_carries_honest_timings_and_counts() -> None:
    """``ResolvedRetrieval`` threads preflight timings into diagnostics."""
    from omrg.core.answer.pipeline import ResolvedRetrieval

    preflight = ResolvedRetrieval(
        rows=[_plain_row("pre-1", "pre-retrieved evidence body")],
        retrieval_ms=123.4,
        sampling_ms=50.0,
        sampling_calls=2,
    )
    seam = RecordingSeam("The pre-retrieved evidence body [1].")

    result = await answer(
        "preflight question",
        complete=seam,
        rows=preflight,
        completion_source="client_mrtr",
        include_diagnostics=True,
        **_answer_kwargs(),
    )

    assert result["status"] == "ok", result
    diagnostics = result["diagnostics"]
    assert diagnostics["retrieval_ms"] == 123.4
    assert diagnostics["generation_ms"] >= 50.0
    assert diagnostics["completion_calls"] == 2, (
        "the client path must count real client rounds, not seam replays"
    )


async def test_plain_rows_remain_backwards_compatible() -> None:
    """A plain ``rows`` list still skips retrieval and reports zero ms."""
    seam = RecordingSeam("The plain evidence body [1].")

    result = await answer(
        "plain question",
        complete=seam,
        rows=[_plain_row("plain-1", "plain evidence body")],
        include_diagnostics=True,
        **_answer_kwargs(),
    )

    assert result["status"] == "ok", result
    assert result["diagnostics"]["retrieval_ms"] == 0.0


# ── Citation parsing stays inside the generation guard (review F12) ──────


async def test_huge_ordinal_is_a_generation_error_with_evidence(
    tmp_path: Path,
) -> None:
    """A 5,000-digit ordinal never escapes core as a raw ValueError."""
    await _ingest(
        tmp_path,
        "The lantern array at station one is calibrated every Tuesday. " * 20,
    )
    huge_ordinal = "9" * 5000
    seam = RecordingSeam(f"A substantive answer citing [{huge_ordinal}] deeply.")

    result = await answer("lantern array calibration", complete=seam, **_answer_kwargs())

    assert result["status"] == "error", result
    assert result["failure_stage"] == "generation"
    assert result["evidence"], "the supplied evidence must still be returned"


# ── ExceptionGroup during generation maps to a generation failure (F3) ───


async def test_exception_group_during_generation_is_structured_error(
    tmp_path: Path,
) -> None:
    """asyncio-style ExceptionGroup wrapping maps to a generation failure."""
    await _ingest(
        tmp_path,
        "The lantern array at station one is calibrated every Tuesday. " * 20,
    )

    class _ExplodingSeam:
        prompts: list[str] = []

        async def __call__(self, prompt: str) -> str:
            self.prompts.append(prompt)
            raise ExceptionGroup("sampling failed", [RuntimeError("client dropped")])

    result = await answer(
        "lantern array calibration",
        complete=_ExplodingSeam(),  # type: ignore[arg-type]
        **_answer_kwargs(),
    )

    assert result["status"] == "error"
    assert result["failure_stage"] == "generation"
    assert result["evidence"], "the retrieved evidence must still be returned"


# ── Review fix: SearchRetriever forwards the engine embedder/cache ─────


def test_search_retriever_forwards_embedder_and_cache() -> None:
    """The retriever passes embed_model and query_cache into search()."""
    from omrg.core.answer.retriever import SearchRetriever

    captured: dict = {}

    def spy_search(query: str, **kwargs: object) -> list[dict]:
        captured.update(kwargs)
        return []

    embed = object()
    cache = {}
    retriever = SearchRetriever(
        search_fn=spy_search,
        collection_name="docs",
        embed_model=embed,
        query_cache=cache,
    )
    retriever.retrieve("query text")

    assert captured["embed_model"] is embed
    assert captured["query_cache"] is cache
