"""Tests for the answer stage reporter (add-answer-stage-progress, task 1.1)."""

from __future__ import annotations

import logging

import pytest

from omrs.core.answer.progress import (
    AnswerStage,
    StageReporter,
    report_stage,
    reporting,
)


def _recorder() -> tuple[list[AnswerStage], object]:
    seen: list[AnswerStage] = []
    return seen, seen.append


def test_stages_arrive_in_order() -> None:
    seen, record = _recorder()
    reporter = StageReporter(record)
    for stage in AnswerStage:
        reporter.enter(stage)
    assert seen == list(AnswerStage)
    assert [s.value for s in seen] == ["searching", "writing", "citing", "verifying"]


def test_repeat_is_dropped() -> None:
    seen, record = _recorder()
    reporter = StageReporter(record)
    reporter.enter(AnswerStage.SEARCHING)
    reporter.enter(AnswerStage.SEARCHING)
    reporter.enter(AnswerStage.WRITING)
    reporter.enter(AnswerStage.WRITING)
    assert seen == [AnswerStage.SEARCHING, AnswerStage.WRITING]


def test_backward_stage_is_dropped() -> None:
    seen, record = _recorder()
    reporter = StageReporter(record)
    reporter.enter(AnswerStage.CITING)
    reporter.enter(AnswerStage.SEARCHING)
    reporter.enter(AnswerStage.WRITING)
    reporter.enter(AnswerStage.VERIFYING)
    assert seen == [AnswerStage.CITING, AnswerStage.VERIFYING]


def test_raising_callback_is_logged_and_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    def broken(stage: AnswerStage) -> None:
        raise RuntimeError("consumer gone")

    reporter = StageReporter(broken)
    with caplog.at_level(logging.WARNING, logger="omrs.core.answer.progress"):
        reporter.enter(AnswerStage.SEARCHING)
        reporter.enter(AnswerStage.WRITING)
    assert "stage callback failed" in caplog.text


def test_reporting_none_installs_nothing() -> None:
    seen, record = _recorder()
    with reporting(record):
        with reporting(None):
            report_stage(AnswerStage.SEARCHING)
    # ``reporting(None)`` keeps the outer reporter; it does not mask it.
    assert seen == [AnswerStage.SEARCHING]


def test_report_stage_without_reporter_does_nothing() -> None:
    report_stage(AnswerStage.WRITING)


def test_nested_reporting_restores_outer_reporter() -> None:
    outer, record_outer = _recorder()
    inner, record_inner = _recorder()
    with reporting(record_outer):
        report_stage(AnswerStage.SEARCHING)
        with reporting(record_inner):
            report_stage(AnswerStage.WRITING)
        report_stage(AnswerStage.CITING)
    report_stage(AnswerStage.VERIFYING)
    assert outer == [AnswerStage.SEARCHING, AnswerStage.CITING]
    assert inner == [AnswerStage.WRITING]
