"""Stage reports from the direct answer path (add-answer-stage-progress, 1.3 and 1.5).

Runs ``core.answer.pipeline.answer`` inside ``reporting(recorder)`` with
pre-retrieved rows and fake seams, and pins which stages each outcome
reports.  No test reaches a real model or network.
"""

from __future__ import annotations

from typing import Any

import pytest

from omrs.core.answer import answer
from omrs.core.answer.progress import AnswerStage, reporting
from omrs.core.answer.synthesis import CompletionSeam
from omrs.core.answer.verify import VERDICT_SUPPORTED
from omrs.core.settings import AnswerBlock, EffectiveSettings

_EVIDENCE_TEXT = "The tower is exactly 100 metres tall."
_GROUNDED_ANSWER = "The tower is 100 metres tall [1]."
_QUESTION = "how tall is the tower?"

S, W, C, V = (
    AnswerStage.SEARCHING,
    AnswerStage.WRITING,
    AnswerStage.CITING,
    AnswerStage.VERIFYING,
)


class _Seam:
    """Fake async completion seam that replies with fixed text."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    async def __call__(self, prompt: str) -> str:
        self.calls += 1
        return self.reply


class _FailingSeam:
    """Fake seam whose model call always fails."""

    async def __call__(self, prompt: str) -> str:
        raise ConnectionError("model down")


def _row() -> dict[str, Any]:
    return {
        "chunk_id": "c1",
        "source_id": "c1-doc",
        "source_version": 1,
        "source": "c1.txt",
        "source_chunk_index": 0,
        "score": 0.9,
        "score_kind": "dense",
        "text": _EVIDENCE_TEXT,
    }


def _settings(base: EffectiveSettings, **block: Any) -> EffectiveSettings:
    return base.model_copy(update={"answer": AnswerBlock(**block)})


async def _run(
    settings: EffectiveSettings,
    *,
    query: str = _QUESTION,
    rows: list[dict] | None = None,
    complete: CompletionSeam | None = None,
    verify_complete: CompletionSeam | None = None,
    on_stage: Any = None,
) -> tuple[dict[str, Any], list[AnswerStage]]:
    seen: list[AnswerStage] = []
    callback = on_stage if on_stage is not None else seen.append
    with reporting(callback):
        result = await answer(
            query,
            complete=complete,
            verify_complete=verify_complete,
            rows=[_row()] if rows is None else rows,
            effective_settings=settings,
        )
    return result, seen


async def test_full_answer_with_judge_reports_four_stages(effective_settings: Any) -> None:
    result, seen = await _run(
        _settings(effective_settings(), verify_claims=True),
        complete=_Seam(_GROUNDED_ANSWER),
        verify_complete=_Seam(VERDICT_SUPPORTED),
    )
    assert result["status"] == "ok", result
    assert result.get("verified") is True
    assert seen == [S, W, C, V]


async def test_verification_off_reports_three_stages(effective_settings: Any) -> None:
    judge = _Seam(VERDICT_SUPPORTED)
    result, seen = await _run(
        _settings(effective_settings(), verify_claims=False),
        complete=_Seam(_GROUNDED_ANSWER),
        verify_complete=judge,
    )
    assert result["status"] == "ok", result
    assert seen == [S, W, C]
    assert judge.calls == 0


async def test_verification_on_without_judge_reports_three_stages(
    effective_settings: Any,
) -> None:
    result, seen = await _run(
        _settings(effective_settings(), verify_claims=True),
        complete=_Seam(_GROUNDED_ANSWER),
        verify_complete=None,
    )
    assert "verification_skipped" in result, result
    assert seen == [S, W, C]


async def test_no_evidence_reports_searching_only(effective_settings: Any) -> None:
    model = _Seam(_GROUNDED_ANSWER)
    result, seen = await _run(effective_settings(), rows=[], complete=model)
    assert result["status"] == "no_evidence", result
    assert seen == [S]
    assert model.calls == 0


async def test_no_provider_reports_searching_only(effective_settings: Any) -> None:
    result, seen = await _run(effective_settings(), complete=None)
    assert result["status"] == "error", result
    assert seen == [S]


async def test_master_switch_off_reports_nothing(effective_settings: Any) -> None:
    result, seen = await _run(
        _settings(effective_settings(), enabled=False), complete=_Seam(_GROUNDED_ANSWER)
    )
    assert result["status"] == "error", result
    assert seen == []


async def test_request_over_limit_reports_nothing(effective_settings: Any) -> None:
    result, seen = await _run(
        effective_settings(), query="x" * 4097, complete=_Seam(_GROUNDED_ANSWER)
    )
    assert result["status"] == "error", result
    assert seen == []


async def test_generation_failure_reports_searching_and_writing(
    effective_settings: Any,
) -> None:
    result, seen = await _run(
        _settings(effective_settings(), verify_claims=True),
        complete=_FailingSeam(),
        verify_complete=_Seam(VERDICT_SUPPORTED),
    )
    assert result["failure_stage"] == "generation", result
    assert seen == [S, W]


async def test_raising_callback_never_fails_the_answer(effective_settings: Any) -> None:
    settings = _settings(effective_settings(), verify_claims=True)

    def broken(stage: AnswerStage) -> None:
        raise RuntimeError("consumer gone")

    result, _ = await _run(
        settings,
        complete=_Seam(_GROUNDED_ANSWER),
        verify_complete=_Seam(VERDICT_SUPPORTED),
        on_stage=broken,
    )
    plain = await answer(
        _QUESTION,
        complete=_Seam(_GROUNDED_ANSWER),
        verify_complete=_Seam(VERDICT_SUPPORTED),
        rows=[_row()],
        effective_settings=settings,
    )
    assert result == plain


async def test_result_equals_a_run_without_reporter(effective_settings: Any) -> None:
    settings = _settings(effective_settings(), verify_claims=True)
    reported, seen = await _run(
        settings,
        complete=_Seam(_GROUNDED_ANSWER),
        verify_complete=_Seam(VERDICT_SUPPORTED),
    )
    plain = await answer(
        _QUESTION,
        complete=_Seam(_GROUNDED_ANSWER),
        verify_complete=_Seam(VERDICT_SUPPORTED),
        rows=[_row()],
        effective_settings=settings,
    )
    assert seen == [S, W, C, V]
    assert reported == plain


# ── Task 1.5: the callback sees stage names only; the seam stays whole-reply ──


async def test_callback_receives_stage_values_only(effective_settings: Any) -> None:
    marker = "MARKER-QUESTION-7f3a"
    received: list[Any] = []
    with reporting(received.append):
        await answer(
            f"{marker} how tall?",
            complete=_Seam(_GROUNDED_ANSWER),
            verify_complete=_Seam(VERDICT_SUPPORTED),
            rows=[_row()],
            effective_settings=_settings(effective_settings(), verify_claims=True),
        )
    assert received
    assert all(type(item) is AnswerStage for item in received)
    assert not any(marker in str(item) for item in received)
    assert not any(_EVIDENCE_TEXT in str(item) for item in received)


def test_seam_still_refuses_streaming() -> None:
    from omrs.core.answer.synthesis import SeamLLM

    with pytest.raises(NotImplementedError):
        SeamLLM(seam=_Seam(_GROUNDED_ANSWER)).stream_complete("prompt")
