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


@pytest.fixture
def synthetic_run(scoring, tmp_path, monkeypatch):
    import subprocess
    from types import SimpleNamespace

    import experiment_io as io
    import extract_rescue_text as extraction

    source = tmp_path / "source"
    output = tmp_path / "run" / "output"
    source.mkdir()
    original_rule = EXP.parent / "33-ocr-routing-natural-positive-2026-09-17" / "build_labels.py"
    (source / "build_labels.py").write_text(original_rule.read_text())
    text = "palabra " * 10
    files = {
        "sources.json": {},
        "labels.json": {},
        "output/frozen.manifest.json": {},
        "output/.transcripts/test/p001.json": {"transcription": text + "figura " * 10},
        "output/.transcripts_split/test/p001.json": {"body_text": text},
        "output/page_evidence.json": {
            "pages": [
                {
                    "doc_id": "test",
                    "page": 1,
                    "label": "usable",
                    "r_pypdf": 0.5,
                    "reference_tokens": 20,
                }
            ]
        },
    }
    for relative, data in files.items():
        io.atomic_json(source / relative, data)
    io.atomic_json(
        tmp_path / "run" / "plan.json",
        {
            "source_data": {"documents": 1, "pages": 1},
            "decision_register": [{"status": "APPROVED", "date": "2026-10-07"}] * 2,
            "amendments": [{"id": "A2", "status": "APPROVED by operator"}],
        },
    )
    monkeypatch.setattr(io, "EXP_DIR", tmp_path / "run")
    monkeypatch.setattr(scoring, "OUTPUT", output)
    monkeypatch.setattr(extraction, "OUTPUT", output)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="freeze verified", stderr=""),
    )
    for tier in ("liteparse", "pypdf"):
        io.atomic_json(output / ".rescue_text" / "test" / f"{tier}.json", [text])
    payload = {
        "identity": extraction.extraction_identity(source),
        "completed_documents": ["test"],
        "rows": [
            {"doc_id": "test", "page": 1, "tier": tier, "text_sha256": io.text_sha256(text)}
            for tier in ("liteparse", "pypdf")
        ],
    }
    io.atomic_json(output / "rescue_text.json", payload)
    return source, output


def test_a2_sanity_uses_all_text_while_quality_uses_body(scoring, synthetic_run):
    source, output = synthetic_run
    scoring.label_rescue(source, False)
    result = json.loads((output / "rescue_text.json").read_text())
    assert all(row["body_recall"] == 1.0 and row["class"] == "healthy" for row in result["rows"])
    checks = json.loads((output / "recall_check.json").read_text())
    assert checks["passed"][0]["all_text_recall"] == 0.5
    assert checks["failed"] is None


def test_a2_still_stops_on_all_text_drift(scoring, synthetic_run):
    source, output = synthetic_run
    target = source / "output" / "page_evidence.json"
    evidence = json.loads(target.read_text())
    evidence["pages"][0]["r_pypdf"] = 0.4
    target.write_text(json.dumps(evidence))
    import extract_rescue_text as extraction

    target = output / "rescue_text.json"
    payload = json.loads(target.read_text())
    payload["identity"] = extraction.extraction_identity(source)
    target.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="pypdf recall mismatch"):
        scoring.label_rescue(source, False)
