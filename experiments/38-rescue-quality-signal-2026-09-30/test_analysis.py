"""Run saved-result analysis with synthetic JSON and no experiment services."""

from __future__ import annotations

import json
import runpy
import shutil
from pathlib import Path


def test_analysis_loads_saved_results_without_running_models(tmp_path, monkeypatch):
    monkeypatch.setenv("MPLBACKEND", "Agg")
    target = tmp_path / "analysis.py"
    shutil.copyfile(Path(__file__).with_name("analysis.py"), target)
    output = tmp_path / "output"
    output.mkdir()
    measure = {
        "threshold": 0.5,
        "junk_recall": 0.5,
        "healthy_false_positive_rate": 0.01,
        "junk_flagged": 1,
        "junk_pages": 2,
        "healthy_false_positives": 1,
        "healthy_pages": 100,
        "per_document": {"test": {"junk_pages": 2, "junk_recall": 0.5}},
    }
    point = {"populations": {"liteparse": measure, "pypdf": measure}}
    candidates = {
        name: {"operating_points": {"as_designed": point, "equal_cost": point}}
        for name in ("A", "B")
    }
    followup = {name: {"gated": {"auc": 0.9}, "io06": {"auc": 0.8}} for name in ("A", "B")}
    data = {
        "recommendation": None,
        "candidates": candidates,
        "local_text_followup": {"signals": followup},
    }
    (output / "summary.json").write_text(json.dumps(data))
    namespace = runpy.run_path(str(target))
    assert len(namespace["main_table"]) == 8
    assert len(namespace["followup_table"]) == 4
    assert namespace["main_table"]["junk_recall"].tolist() == [0.5] * 8
