"""Task 2.1/2.2 checks: the frozen thresholds reproduce from the committed inputs."""

from __future__ import annotations

import copy

import pytest
from exp42_io import EXP_DIR, read_json
from fit_thresholds import INPUTS, fit

PLAN = read_json(EXP_DIR / "plan.json")


@pytest.mark.parametrize("key", sorted(INPUTS))
def test_threshold_reproduces_from_committed_input(key: str) -> None:
    rows = read_json(INPUTS[key])["rows"]
    assert fit(rows) == PLAN["thresholds"][key]["value"]


def test_changing_one_healthy_score_changes_the_fit() -> None:
    rows = read_json(INPUTS["clef_flash_q8_0_w1"])["rows"]
    frozen = PLAN["thresholds"]["clef_flash_q8_0_w1"]["value"]
    changed = copy.deepcopy(rows)
    # The healthy LiteParse page that sits exactly at the threshold.
    target = next(
        r
        for r in changed
        if r["tier"] == "liteparse" and r["class"] == "healthy" and r["score"] == frozen
    )
    target["score"] = 0.5
    assert fit(changed) != frozen
