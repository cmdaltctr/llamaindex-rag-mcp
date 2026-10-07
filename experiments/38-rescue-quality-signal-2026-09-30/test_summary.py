"""Synthetic tests for unchanged operating points, gates and paired statistics."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def stats():
    return importlib.import_module("signal_stats")


@pytest.fixture
def summary():
    return importlib.import_module("summarise_eval")


def page(doc, number, label, score):
    return {"doc_id": doc, "page": number, "tier": "liteparse", "class": label, "score": score}


def test_equal_cost_threshold_preserves_ties_and_ceiling(stats):
    rows = [page("healthy", i, "healthy", 0.1 if i < 2 else 0.9) for i in range(50)]
    rows += [page("junk", 1, "junk", 0.09), page("junk", 2, "junk", 0.2)]
    threshold = stats.equal_cost_threshold(rows)
    result = stats.metrics(rows, threshold)
    assert threshold == 0.1
    assert result["healthy_false_positives"] == 0
    assert result["junk_recall"] == 0.5
    assert result["healthy_false_positive_rate"] <= 0.02


def test_as_designed_is_strictly_below_half(stats):
    rows = [page("test", 1, "junk", 0.5), page("test", 2, "healthy", 0.49)]
    result = stats.metrics(rows, 0.5)
    assert result["junk_recall"] == 0.0
    assert result["healthy_false_positive_rate"] == 1.0


def test_document_bootstrap_is_clustered_and_reproducible(stats):
    rows = [page("a", 1, "junk", 0.0), page("b", 1, "junk", 1.0)]
    first = stats.bootstrap_interval(rows, 0.5, ["a", "b"])
    assert first == stats.bootstrap_interval(rows, 0.5, ["a", "b"])
    assert first["lower"] == 0.0 and first["upper"] == 1.0
    assert first["resamples"] == 2000 and first["seed"] == 38


def test_mcnemar_is_exact_and_one_sided_towards_b(stats):
    a = [page("test", i, "junk", 1.0) for i in range(10)]
    b = [page("test", i, "junk", 0.0) for i in range(10)]
    result = stats.mcnemar(a, b, 0.5, 0.5)
    assert result["b_only"] == 10 and result["a_only"] == 0
    assert result["p_one_sided"] == pytest.approx(1 / 1024)
    assert stats.mcnemar(b, a, 0.5, 0.5)["p_one_sided"] == 1.0


@pytest.mark.parametrize(
    "a,b,delta,p,expected",
    [
        (True, True, 0.09, 0.001, "A"),
        (True, True, 0.10, 0.01, "B"),
        (False, False, 0.5, 0.001, None),
        (False, True, 0.09, 0.001, None),
        (True, True, 0.2, 0.05, "A"),
        (True, False, 0.2, 0.001, "A"),
    ],
)
def test_recommendation_follows_frozen_outcome_table(summary, a, b, delta, p, expected):
    assert summary.recommend(a, b, delta, p) == expected


def test_routing_uses_only_rescued_pages_and_original_tenth_fraction(summary):
    baseline = [
        {
            "doc_id": "rf06",
            "page_count": 10,
            "extraction_fallback_backend": "liteparse",
            "ocr_required": False,
        },
        {
            "doc_id": "rf07",
            "page_count": 10,
            "extraction_fallback_backend": "liteparse",
            "ocr_required": False,
        },
        {
            "doc_id": "healthy",
            "page_count": 10,
            "extraction_fallback_backend": "liteparse",
            "ocr_required": False,
        },
        {
            "doc_id": "native",
            "page_count": 10,
            "extraction_fallback_backend": None,
            "ocr_required": False,
        },
        {
            "doc_id": "prior",
            "page_count": 10,
            "extraction_fallback_backend": None,
            "ocr_required": True,
        },
    ]
    labels = {
        row["doc_id"]: {"label": "usable" if row["doc_id"] == "healthy" else "needs_ocr"}
        for row in baseline
    }
    rows = [
        page(row["doc_id"], 1, "healthy" if row["doc_id"] == "healthy" else "junk", 0.0)
        for row in baseline
    ]
    routing = summary.simulate_routing(rows, baseline, labels, 0.5)
    assert routing["rf06"]["routed"] and routing["rf07"]["routed"]
    assert routing["healthy"]["newly_routed_usable"]
    assert not routing["native"]["routed"] and routing["native"]["flagged_rescue_pages"] == 0
    assert routing["prior"]["routed"] and not routing["prior"]["newly_routed_usable"]


def test_auc_uses_lower_quality_as_badness_and_half_credit_for_ties(stats):
    rows = [{"body_recall": 0.1, "score": 0.0}, {"body_recall": 0.9, "score": 1.0}]
    assert stats.auc_badness(rows) == 1.0
    rows[1]["score"] = 0.0
    assert stats.auc_badness(rows) == 0.5
    rows[0]["score"] = 1.0
    assert stats.auc_badness(rows) == 0.0


def test_followup_attachment_refuses_a_retuned_threshold(summary):
    main = {"recommendation": "A", "candidates": {"A": {"equal_cost_threshold": 0.5}}}
    local = {"thresholds": {"A": 0.4}, "rows": []}
    with pytest.raises(ValueError, match="threshold"):
        summary.attach_followup(main, local, "digest")


def test_followup_attachment_reports_saved_ranking(summary):
    main = {
        "recommendation": "A",
        "candidates": {"A": {"equal_cost_threshold": 0.5}},
        "artefact_sha256": {},
    }
    local = {
        "thresholds": {"A": 0.5},
        "rows": [
            {
                "doc_id": "io06",
                "population": "gated",
                "body_recall": 0.1,
                "scores": {"A": {"score": 0.1}},
            },
            {
                "doc_id": "io06",
                "population": "gated",
                "body_recall": 0.9,
                "scores": {"A": {"score": 0.9}},
            },
        ],
    }
    summary.attach_followup(main, local, "digest")
    assert main["local_text_followup"]["signals"]["A"]["io06"]["auc"] == 1.0
    assert main["artefact_sha256"]["local_text_signal.json"] == "digest"
