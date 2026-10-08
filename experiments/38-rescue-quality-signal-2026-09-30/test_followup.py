"""Test candidate selection and unchanged thresholds in the local-text follow-up."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def followup():
    return importlib.import_module("score_local_text")


@pytest.mark.parametrize("selected,expected", [(None, ["A", "B"]), ("A", ["A"]), ("B", ["B"])])
def test_followup_uses_selected_signal_or_both(followup, selected, expected):
    assert followup.selected_candidates({"recommendation": selected}) == expected


def test_followup_preserves_each_main_equal_cost_threshold(followup):
    main = {
        "recommendation": None,
        "candidates": {
            "A": {"equal_cost_threshold": 0.8834080717488789},
            "B": {"equal_cost_threshold": 0.0030147846405897236},
        },
    }
    assert followup.frozen_thresholds(main) == {"A": 0.8834080717488789, "B": 0.0030147846405897236}


def test_followup_metrics_use_gated_population_and_report_misses(followup):
    payload = {
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
            {
                "doc_id": "rf06",
                "population": "gated",
                "body_recall": 0.1,
                "scores": {"A": {"score": 0.9}},
            },
            {
                "doc_id": "rf07",
                "population": "gated",
                "body_recall": 0.1,
                "scores": {"A": {"score": 0.1}},
            },
            {
                "doc_id": "other",
                "population": "figure_only",
                "body_recall": 0.1,
                "scores": {"A": {"score": 1.0}},
            },
        ],
    }
    result = followup.followup_metrics(payload)["A"]
    assert result["gated"]["pages"] == 4
    assert result["io06"]["auc"] == 1.0
    assert result["documents"]["rf06"]["bad_flagged"] == 0
    assert result["documents"]["rf07"]["bad_flagged"] == 1
