"""Fast tests for the Stage 0 machine-readable experiment-plan contract."""

from __future__ import annotations

import pytest
from experiments._lib.plan import ExperimentPlan


def _payload() -> dict:
    return {
        "experiment_id": "example-factorial",
        "protocol_version": "1",
        "experimental_unit": "one fixed labelled query",
        "primary_metric": "coverage_at_20",
        "manipulated_factors": [
            {"name": "retrieval", "levels": ["dense", "hybrid"]},
            {"name": "rerank", "levels": [False, True]},
        ],
        "controlled_variables": {
            "corpus_sha256": "frozen",
            "embedding_identity": "frozen",
        },
        "cells": [
            {"id": "dense_off", "factors": {"retrieval": "dense", "rerank": False}},
            {"id": "dense_on", "factors": {"retrieval": "dense", "rerank": True}},
            {"id": "hybrid_off", "factors": {"retrieval": "hybrid", "rerank": False}},
            {"id": "hybrid_on", "factors": {"retrieval": "hybrid", "rerank": True}},
        ],
        "preflight_assertions": [
            {
                "manifest_field": "embedding.identity",
                "operator": "eq",
                "expected": "frozen",
            }
        ],
    }


def test_plan_accepts_same_cells_in_counterbalanced_order() -> None:
    plan = ExperimentPlan.from_dict(_payload())
    counterbalanced = list(reversed(_payload()["cells"]))

    plan.assert_runner_cells(counterbalanced)


def test_plan_rejects_missing_runner_cell() -> None:
    plan = ExperimentPlan.from_dict(_payload())

    with pytest.raises(AssertionError, match="missing=.*hybrid_on"):
        plan.assert_runner_cells(_payload()["cells"][:-1])


def test_plan_rejects_changed_factor_level() -> None:
    plan = ExperimentPlan.from_dict(_payload())
    cells = _payload()["cells"]
    cells[0] = {"id": "dense_off", "factors": {"retrieval": "hybrid", "rerank": False}}

    with pytest.raises(AssertionError, match="changed=.*dense_off"):
        plan.assert_runner_cells(cells)


def test_plan_rejects_undeclared_factor_level_before_execution() -> None:
    payload = _payload()
    payload["cells"][0] = {
        "id": "dense_off",
        "factors": {"retrieval": "sparse-only", "rerank": False},
    }

    with pytest.raises(ValueError, match="undeclared level"):
        ExperimentPlan.from_dict(payload)


def test_plan_requires_explicit_controls_mapping() -> None:
    payload = _payload()
    payload["controlled_variables"] = ["corpus"]

    with pytest.raises(ValueError, match="controlled_variables"):
        ExperimentPlan.from_dict(payload)
