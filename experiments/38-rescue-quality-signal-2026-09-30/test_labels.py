"""Test the registered body-reference classes and strict pypdf agreement guard."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))


@pytest.fixture
def scoring():
    return importlib.import_module("score_candidates")


@pytest.fixture
def rule():
    from experiment_io import load_token_rule

    return load_token_rule(EXP.parent / "33-ocr-routing-natural-positive-2026-09-17")


@pytest.mark.parametrize(
    ("matches", "label"), [(0, "junk"), (4, "junk"), (5, "grey"), (7, "grey"), (8, "healthy")]
)
def test_classes_follow_frozen_body_recall(scoring, rule, matches, label):
    text = " ".join(["palabra"] * matches + ["otro"])
    result = scoring.classify_page(text, ["palabra"] * 10, "usable", rule)
    assert result["class"] == label
    assert result["body_recall"] == matches / 10


@pytest.mark.parametrize("label", ["unrecoverable", "ambiguous"])
def test_frozen_excluded_labels_override_healthy_text(scoring, rule, label):
    result = scoring.classify_page("palabra " * 10, ["palabra"] * 10, label, rule)
    assert result["class"] == "excluded"


def test_short_body_reference_is_excluded(scoring, rule):
    assert scoring.classify_page("palabra", ["palabra"] * 9, "usable", rule)["class"] == "excluded"


@pytest.mark.parametrize("text", ["", "  \n", "a !"])
def test_rescue_without_frozen_tokens_is_excluded(scoring, rule, text):
    assert scoring.classify_page(text, ["palabra"] * 10, "usable", rule)["class"] == "excluded"


def test_recall_agreement_accepts_frozen_rounding(scoring):
    scoring.verify_pypdf_recall(0.123456, 0.1235, "test", 1)
    scoring.verify_pypdf_recall(0.1236, 0.1235, "test", 1)


def test_recall_agreement_stops_on_mismatch(scoring):
    with pytest.raises(ValueError, match="pypdf recall mismatch"):
        scoring.verify_pypdf_recall(0.123601, 0.1235, "test", 1)


def test_body_reference_prefers_split_even_when_empty(scoring, rule, tmp_path):
    for folder, record in (
        (".transcripts", {"transcription": "full transcription"}),
        (".transcripts_split", {"body_text": ""}),
    ):
        target = tmp_path / "output" / folder / "test" / "p001.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(record))
    assert scoring.body_reference(tmp_path, "test", 1, rule) == []


def test_body_reference_falls_back_only_if_split_absent(scoring, rule, tmp_path):
    target = tmp_path / "output" / ".transcripts" / "test" / "p001.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"transcription": "Full transcription"}))
    assert scoring.body_reference(tmp_path, "test", 1, rule) == ["full", "transcription"]
