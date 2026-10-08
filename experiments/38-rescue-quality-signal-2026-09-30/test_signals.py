"""Tests for candidate scoring coverage and keeping page text out of outputs."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))


@pytest.fixture
def runner():
    return importlib.import_module("score_signals")


@pytest.fixture
def rule():
    from experiment_io import load_token_rule

    return load_token_rule(EXP.parent / "33-ocr-routing-natural-positive-2026-09-17")


def test_rescue_population_excludes_grey_and_excluded(runner):
    rows = [{"class": value} for value in ("junk", "healthy", "grey", "excluded")]
    assert runner.eligible_rows(rows) == rows[:2]


def test_signal_scores_keep_keys_labels_and_hashes_without_text(runner, rule):
    from experiment_io import text_sha256

    text = "El estudiante lee un libro en la biblioteca."
    row = {
        "doc_id": "test",
        "page": 1,
        "tier": "liteparse",
        "class": "healthy",
        "body_recall": 0.99,
        "text_sha256": text_sha256(text),
    }
    result = runner.score_document([row], {"liteparse": [text]}, rule, "A")
    assert len(result) == 1
    assert result[0]["score"] >= 0.8
    assert result[0]["class"] == "healthy" and result[0]["page"] == 1
    assert result[0]["text_sha256"] == row["text_sha256"]
    assert text not in str(result) and "text" not in result[0]


def test_signal_scoring_refuses_changed_text(runner, rule):
    row = {
        "doc_id": "test",
        "page": 1,
        "tier": "liteparse",
        "class": "junk",
        "body_recall": 0.1,
        "text_sha256": "0" * 64,
    }
    with pytest.raises(ValueError, match="text hash"):
        runner.score_document([row], {"liteparse": ["changed"]}, rule, "A")


def test_coverage_rejects_missing_or_duplicate_scores(runner):
    rows = [{"doc_id": "test", "page": 1, "tier": "liteparse", "class": "healthy"}]
    runner.verify_coverage(rows, rows)
    for scores in ([], rows + rows):
        with pytest.raises(ValueError, match="coverage"):
            runner.verify_coverage(rows, scores)


def test_hosted_candidate_is_excluded_before_source_access(runner, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "score_signals.py",
            "--candidate",
            "hosted",
            "--source-exp",
            str(tmp_path),
        ],
    )
    with pytest.raises(SystemExit) as failure:
        runner.main()
    assert failure.value.code == 2
    assert "invalid choice: 'hosted'" in capsys.readouterr().err
