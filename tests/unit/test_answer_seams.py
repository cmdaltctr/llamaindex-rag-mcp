"""Answer stage seams: evidence, synthesis, citations and verification.

Task 3.6 of ``add-local-web-pipeline-workspace``. The seams in
``omrs.core.answer.stages`` and the result builders in
``omrs.core.answer.results`` are the single implementation that both the
standard ``answer()`` path and later graph adapters call. These tests
pin each seam on its own, then chain the seams by hand over every parity
fixture and require the exact result the standard path produced before
the extraction (``expected.json``).

Every completion and judge seam is a fake: no model or network call.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.pipeline_parity.answer.harness import (
    CASE_NAMES,
    EXPECTED,
    QUERY,
    SOURCE,
    ScriptedSeam,
    case_by_name,
    case_rows,
    case_settings,
    make_seam,
    observation,
)

from omrs.core.answer.results import (
    answer_status,
    answered_result,
    disabled_result,
    generation_diagnostics,
    no_evidence_result,
    no_provider_result,
    stage_failure_result,
    zero_generation_diagnostics,
)
from omrs.core.answer.stages import (
    FAILURE_STAGE_GENERATION,
    NO_VERIFICATION,
    error_detail_for,
    prepare_evidence,
    resolve_citations,
    synthesise_answer,
    verify_answer,
)
from omrs.core.answer.verify import VerificationFields
from omrs.core.settings import AnswerBlock

_ROW = {
    "chunk_id": "c1",
    "source_id": "doc-1",
    "source_version": 1,
    "source": "doc.txt",
    "source_chunk_index": 0,
    "score": 0.9,
    "score_kind": "dense",
    "text": "The tower is exactly 100 metres tall.",
}


def _redact(exc: BaseException) -> str:
    """Test redactor: proves the seam routes messages through it."""
    return str(exc).replace("sk-secret", "***")


# ── Evidence preparation ──────────────────────────────────────────────────


def test_prepare_evidence_empty_rows_is_empty_evidence() -> None:
    """Design D3: an empty result set is valid data, not an error."""
    assert prepare_evidence([]) == []


def test_prepare_evidence_numbers_rows_and_keeps_lineage() -> None:
    """Rows become 1-based evidence with lineage and merged constituents."""
    merged = {**_ROW, "chunk_id": "c2", "chunk_ids": ["c1", "c2"]}
    rows = [_ROW, merged]
    evidence = prepare_evidence(rows)

    assert [row["ordinal"] for row in evidence] == [1, 2]
    assert evidence[0]["chunk_ids"] == ["c1"]
    assert evidence[1]["chunk_ids"] == ["c1", "c2"]
    assert evidence[0]["source_id"] == "doc-1"
    assert rows[1]["chunk_ids"] == ["c1", "c2"], "input rows must not be mutated"


# ── Synthesis ─────────────────────────────────────────────────────────────


async def test_synthesise_answer_returns_text_and_call_count() -> None:
    """A successful synthesis reports text and the completion calls made."""
    seam = ScriptedSeam({"replies": ["Tall [1]."]})
    outcome = await synthesise_answer(
        "how tall?",
        prepare_evidence([_ROW]),
        complete=seam,
        answer_block=AnswerBlock(),
        error_detail=_redact,
    )

    assert outcome.text == "Tall [1]."
    assert outcome.completion_calls == 1
    assert outcome.error is None
    assert outcome.failure_stage is None
    assert len(seam.prompts) == 1
    assert "[1]" in seam.prompts[0], "evidence must carry its ordinal label"


async def test_synthesise_answer_failure_is_attributed_to_generation() -> None:
    """A raising seam is a generation failure with a redacted message."""
    seam = ScriptedSeam({"raise": "key sk-secret rejected"})
    outcome = await synthesise_answer(
        "how tall?",
        prepare_evidence([_ROW]),
        complete=seam,
        answer_block=AnswerBlock(),
        error_detail=_redact,
    )

    assert outcome.text is None
    assert outcome.failure_stage == FAILURE_STAGE_GENERATION == "generation"
    assert outcome.error == "Generation failed: ConnectionError: key *** rejected"
    assert outcome.completion_calls == 1, "attempts before the failure are reported"


async def test_synthesise_answer_uses_injected_runner() -> None:
    """The runner seam lets the standard path keep its patch target."""

    async def _runner(query: str, nodes: list, *, seam: Any, **kwargs: Any) -> tuple[str, int]:
        await seam("first")
        await seam("second")
        return "runner text [1].", 2

    seam = ScriptedSeam({"replies": ["ignored"]})
    outcome = await synthesise_answer(
        "q",
        prepare_evidence([_ROW]),
        complete=seam,
        answer_block=AnswerBlock(),
        error_detail=_redact,
        runner=_runner,
    )

    assert outcome.text == "runner text [1]."
    assert outcome.completion_calls == 2
    assert seam.prompts == ["first", "second"]


# ── Citation resolution ───────────────────────────────────────────────────


def test_resolve_citations_maps_ordinals_to_supplied_lineage() -> None:
    """Only valid supplied ordinals resolve; each carries full lineage."""
    evidence = prepare_evidence([_ROW, {**_ROW, "chunk_id": "c9", "source": "b.txt"}])
    outcome = resolve_citations("A [2, 2] B [7] C [1, x].", evidence, error_detail=_redact)

    assert outcome.error is None
    assert outcome.grounded is True
    assert [c["ordinal"] for c in outcome.citations] == [2]
    assert outcome.citations[0]["chunk_id"] == "c9"
    assert outcome.citations[0]["source"] == "b.txt"


def test_resolve_citations_uncited_text_is_not_grounded() -> None:
    """An answer with no valid citation is never grounded."""
    outcome = resolve_citations(
        "No citations here.", prepare_evidence([_ROW]), error_detail=_redact
    )

    assert outcome.citations == []
    assert outcome.grounded is False
    assert outcome.failure_stage is None


def test_resolve_citations_absurd_ordinal_is_a_generation_failure() -> None:
    """Citation assembly failure is attributed to generation, not raised."""
    outcome = resolve_citations(
        "Cites [12345678901].", prepare_evidence([_ROW]), error_detail=_redact
    )

    assert outcome.failure_stage == "generation"
    assert outcome.error is not None
    assert outcome.error.startswith(
        "Generation failed: citation assembly rejected the model output: ValueError:"
    )
    assert outcome.citations == []
    assert outcome.grounded is False


# ── Opt-in claim verification ─────────────────────────────────────────────


async def test_verify_answer_off_by_default_makes_no_judge_call() -> None:
    """Verification is opt-in: the default block never calls the judge."""
    judge = ScriptedSeam({"raise": "must not run"})
    fields = await verify_answer(
        "Tall [1].",
        prepare_evidence([_ROW]),
        grounded=True,
        answer_block=AnswerBlock(),
        verify_complete=judge,
        unavailable_reason=None,
        error_detail=_redact,
    )

    assert fields == NO_VERIFICATION == VerificationFields()
    assert judge.prompts == []


async def test_verify_answer_skips_ungrounded_answers() -> None:
    """A non-grounded answer skips the judge even when enabled."""
    judge = ScriptedSeam({"raise": "must not run"})
    fields = await verify_answer(
        "Tall.",
        prepare_evidence([_ROW]),
        grounded=False,
        answer_block=AnswerBlock(verify_claims=True),
        verify_complete=judge,
        unavailable_reason=None,
        error_detail=_redact,
    )

    assert fields == NO_VERIFICATION
    assert judge.prompts == []


@pytest.mark.parametrize(
    ("judge_spec", "reason", "expected_skip"),
    [
        (None, None, "verification provider unavailable (no judge configured)"),
        (None, "provider missing", "provider missing"),
        ({"raise": "sk-secret down"}, None, "verification failed: ConnectionError: *** down"),
        ({"replies": ["no idea"]}, None, "unparseable verdict rate 100.0%"),
    ],
)
async def test_verify_answer_degrades_with_its_actual_reason(
    judge_spec: dict | None, reason: str | None, expected_skip: str
) -> None:
    """Degraded verification keeps its label and its actual skipped reason."""
    fields = await verify_answer(
        "Tall [1].",
        prepare_evidence([_ROW]),
        grounded=True,
        answer_block=AnswerBlock(verify_claims=True),
        verify_complete=make_seam(judge_spec),
        unavailable_reason=reason,
        error_detail=_redact,
    )

    assert fields.verified is False
    assert fields.skipped_reason == expected_skip
    assert fields.failing == ()


def test_answer_status_mapping() -> None:
    """Status taxonomy: failing claims, then grounded, then unverified."""
    failing = VerificationFields(failing=({"claim": "x"},), ran=True)
    assert answer_status(True, failing) == "unverified_claims"
    assert answer_status(True, NO_VERIFICATION) == "ok"
    assert answer_status(False, NO_VERIFICATION) == "generation_unverified"


# ── Seam-chain parity with the standard path ──────────────────────────────


async def _chain_seams(
    settings: Any,
    rows: list[dict],
    *,
    complete: ScriptedSeam | None,
    judge: ScriptedSeam | None,
    unavailable_reason: str | None,
) -> dict[str, Any]:
    """Call each seam and result builder in the standard order."""
    block, detail = settings.answer, error_detail_for(settings)
    no_generation = zero_generation_diagnostics(0.0)
    if not block.enabled:
        return disabled_result(QUERY, SOURCE)
    evidence = prepare_evidence(rows)
    if not evidence:
        return no_evidence_result(QUERY, SOURCE, diagnostics=no_generation)
    if complete is None:
        return no_provider_result(QUERY, SOURCE, evidence, diagnostics=no_generation)
    synth = await synthesise_answer(
        QUERY, evidence, complete=complete, answer_block=block, error_detail=detail
    )
    diagnostics = generation_diagnostics(0.0, synth.ms, synth.completion_calls)
    if synth.text is None:
        return stage_failure_result(
            QUERY,
            SOURCE,
            failure_stage=synth.failure_stage,
            error=synth.error or "",
            evidence=evidence,
            diagnostics=diagnostics,
        )
    cites = resolve_citations(synth.text, evidence, error_detail=detail)
    if cites.error is not None:
        return stage_failure_result(
            QUERY,
            SOURCE,
            failure_stage=cites.failure_stage,
            error=cites.error,
            evidence=evidence,
            diagnostics=diagnostics,
        )
    verification = await verify_answer(
        synth.text,
        evidence,
        grounded=cites.grounded,
        answer_block=block,
        verify_complete=judge,
        unavailable_reason=unavailable_reason,
        error_detail=detail,
    )
    return answered_result(
        QUERY,
        SOURCE,
        text=synth.text,
        citations=cites.citations,
        grounded=cites.grounded,
        evidence=evidence,
        verification=verification,
        diagnostics=diagnostics,
    )


async def run_case_through_seams(case: dict[str, Any], base: Any) -> dict[str, Any]:
    """Chain the seams and builders the way a graph adapter will.

    Mirrors ``answer()`` for pre-retrieved rows (retrieval time is 0.0).
    """
    settings = case_settings(base, case)
    complete = make_seam(case.get("complete"))
    judge = make_seam(case.get("judge"))
    result = await _chain_seams(
        settings,
        case_rows(case),
        complete=complete,
        judge=judge,
        unavailable_reason=case.get("verify_unavailable_reason"),
    )
    return observation(result, complete, judge)


@pytest.mark.parametrize("name", CASE_NAMES)
async def test_seam_chain_reproduces_standard_path(name: str, effective_settings: Any) -> None:
    """Chained seams give the exact pre-extraction ``answer()`` outcome."""
    observed = await run_case_through_seams(case_by_name(name), effective_settings())
    assert observed == EXPECTED[name]


async def test_seams_never_read_process_default_settings(
    effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seams use only injected values; poisoned defaults are never read."""
    import omrs.core.settings as core_settings

    def _poisoned() -> Any:
        raise AssertionError("an answer seam read the process default settings")

    monkeypatch.setattr(core_settings, "get_default_effective_settings", _poisoned)
    case = case_by_name("verification_unsupported_claim")
    observed = await run_case_through_seams(case, effective_settings())
    assert observed == EXPECTED["verification_unsupported_claim"]


# ── Citations resolve to stored chunks (store-backed) ─────────────────────


async def test_seam_citations_resolve_to_stored_chunks(tmp_path: Path) -> None:
    """Every citation chunk id from the seams refetches one stored chunk."""
    from omrs.core.answer import answer
    from omrs.core.ingestion import ingest_path_async
    from omrs.core.retrieval import search

    collection = "answer_seams_store"
    source = tmp_path / "seams-doc.txt"
    source.write_text("Lantern seam sentinel paragraph about calibration. " * 120, "utf-8")
    ingested = await ingest_path_async(str(source), collection_name=collection)
    assert ingested["status"] == "ok", ingested

    knobs = {"top_k": 5, "similarity_threshold": 0.0, "hybrid": False, "rerank": False}
    rows = search("lantern calibration", collection_name=collection, **knobs)
    assert rows, "the fixture document must be retrievable"
    evidence = prepare_evidence(rows)
    reply = f"Calibration is described [1] and again [{len(evidence)}]."
    synth = await synthesise_answer(
        "lantern calibration",
        evidence,
        complete=ScriptedSeam({"replies": [reply]}),
        answer_block=AnswerBlock(),
        error_detail=_redact,
    )
    cites = resolve_citations(synth.text, evidence, error_detail=_redact)

    assert cites.grounded and cites.citations
    for citation in cites.citations:
        for chunk_id in citation["chunk_ids"]:
            single = search(
                "lantern calibration",
                collection_name=collection,
                metadata_filter={"chunk_id": chunk_id},
                **knobs,
            )
            assert [row["chunk_id"] for row in single] == [chunk_id]

    standard = await answer(
        "lantern calibration",
        complete=ScriptedSeam({"replies": [reply]}),
        rows=rows,
        collection_name=collection,
        **knobs,
    )
    assert standard["citations"] == cites.citations
    assert standard["evidence"] == evidence


# ── Retrieval failure attribution and lazy resources ──────────────────────


class _ExplodingStore:
    """A store whose every method raises."""

    def __getattr__(self, name: str) -> Any:
        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError(f"store exploded in {name}")

        return _boom


async def test_retrieval_failure_is_attributed_before_any_model_call() -> None:
    """The standard path attributes a store failure to retrieval."""
    from omrs.core.answer import answer

    seam = ScriptedSeam({"replies": ["never [1]."]})
    result = await answer(
        "anything",
        complete=seam,
        store=_ExplodingStore(),
        collection_name="answer_seams_explode",
        similarity_threshold=0.0,
        hybrid=False,
        rerank=False,
    )

    assert result["status"] == "error"
    assert result["failure_stage"] == "retrieval"
    assert result["evidence"] == []
    assert seam.prompts == []


def test_answer_seam_modules_stay_lazy_and_graph_free() -> None:
    """Design D6: importing the seams builds no model and no graph runtime."""
    code = (
        "import sys\n"
        "import omrs.core.answer.stages, omrs.core.answer.results\n"
        "bad = [m for m in sys.modules if m.startswith(("
        "'omrs.compose_answer', 'omrs.core.pipelines', 'omrs.transports', "
        "'omrs.integrations'))]\n"
        "print(json.dumps(bad))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", "import json\n" + code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []
