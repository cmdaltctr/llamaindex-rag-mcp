"""Tests for Experiment 39 scoring rules, on fixed strings and synthetic rows.

Run: uv run pytest experiments/39-local-tier-escalation-2026-09-30/test_score_rules.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from score_rules import (  # noqa: E402
    c0,
    c1,
    c3,
    cjk_share,
    decisions,
    discarded_regions,
    script_group,
)

SPANISH = "Los reyes de la casa de Austria gobernaron la monarquía durante dos siglos."
# The style the saved io07 (Bengali) pages take: CJK mixed with Latin fragments.
IO07_STYLE = "向\n\n## 国可可印\n\n### 要可可更可不币\n\nC辆1\n\n不可51\n\n23开，扬あ该1"


def _row(confidence: float | None = 0.95, *, hosted: bool = False) -> dict:
    return {"confidence": confidence, "hosted_recommended": hosted}


@pytest.mark.parametrize(
    ("char", "group"),
    [
        ("a", "LATIN"),
        ("é", "LATIN"),
        ("क", "DEVANAGARI"),
        ("ب", "ARABIC"),
        ("ক", "BENGALI"),
        ("漢", "CJK"),
        ("あ", "CJK"),
        ("ア", "CJK"),
        ("한", "CJK"),
        ("1", None),
        (" ", None),
        ("，", None),
    ],
)
def test_script_group(char: str, group: str | None) -> None:
    assert script_group(char) == group


def test_clean_spanish_line_has_no_cjk() -> None:
    assert cjk_share(SPANISH) == 0.0
    assert not c1(SPANISH)


def test_cjk_and_latin_fragments_exceed_threshold() -> None:
    assert cjk_share(IO07_STYLE) >= 0.05
    assert c1(IO07_STYLE)


def test_cjk_threshold_boundary_is_inclusive() -> None:
    assert cjk_share("漢" + "a" * 19) == pytest.approx(0.05)
    assert c1("漢" + "a" * 19)
    assert not c1("漢" + "a" * 20)


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_empty_output_escalates_in_every_rule(text: str) -> None:
    assert c1(text)
    assert c0(_row(), text)
    assert c3(_row(), text)


def test_text_without_letters_is_not_a_script_mismatch() -> None:
    assert cjk_share("1234 56") == 0.0
    assert not c1("1234 56")


def test_c0_confidence_cut_is_exclusive_and_none_escalates() -> None:
    assert c0(_row(0.79), SPANISH)
    assert not c0(_row(0.8), SPANISH)
    assert c0(_row(None), SPANISH)


def test_c0_hosted_recommended_escalates() -> None:
    assert c0(_row(0.99, hosted=True), SPANISH)


def test_c0_accepts_a_sweep_cut() -> None:
    assert not c0(_row(0.85), SPANISH, 0.8)
    assert c0(_row(0.85), SPANISH, 0.9)


def test_c3_is_c0_or_c1() -> None:
    confident_junk = _row(0.97)
    assert not c0(confident_junk, IO07_STYLE)
    assert c1(IO07_STYLE)
    assert c3(confident_junk, IO07_STYLE)
    assert c3(_row(0.5), SPANISH)
    assert not c3(_row(0.95), SPANISH)


def test_decisions_hold_one_entry_per_rule() -> None:
    out = decisions(_row(0.85), SPANISH)
    assert set(out) == {"C0", "C1", "C3", "C0@0.5", "C0@0.6", "C0@0.7", "C0@0.8", "C0@0.9"}
    assert out["C0@0.8"] == out["C0"]
    assert out["C0@0.9"] and not out["C0@0.8"]


def test_discarded_regions_sums_the_warnings() -> None:
    assert discarded_regions([]) == 0
    assert discarded_regions(["discarded 3 regions without usable recognition output"]) == 3
    assert discarded_regions(["discarded 2 regions x", "other", "discarded 5 regions y"]) == 7


# ── summarise_eval: AUC, gates and selection ──────────────────────────

from summarise_eval import auc, kept_bad, rule_metrics, select  # noqa: E402


def _page(doc: str, recall: float, escalate: bool) -> dict:
    return {"doc_id": doc, "body_recall": recall, "escalate": {"R": escalate}}


def test_auc_separates_ties_and_inverts() -> None:
    assert auc([3, 4], [1, 2]) == 1.0
    assert auc([1, 2], [3, 4]) == 0.0
    assert auc([2], [2]) == 0.5
    assert auc([], [1]) != auc([], [1])  # NaN when a side is empty


def test_kept_bad_counts_only_kept_pages_below_half_recall() -> None:
    pages = [_page("a", 0.2, False), _page("a", 0.9, False), _page("a", 0.1, True)]
    assert kept_bad(pages, "R") == (2, 1)


def test_g1_fails_when_one_non_latin_page_is_kept() -> None:
    pages = [_page("io02", 0.0, True)] * 3 + [_page("io02", 0.0, False)]
    pages += [_page("bd02", 0.95, False)] * 4
    assert not rule_metrics(pages, "R", 0.5)["gates"]["G1"]
    pages[3] = _page("io02", 0.0, True)
    assert rule_metrics(pages, "R", 0.5)["gates"]["G1"]


def test_g2_ignores_io06_and_bounds_the_kept_bad_share() -> None:
    clean = [_page("bd02", 0.95, False)] * 19
    bad = [_page("bd02", 0.1, False)]
    io06_bad = [_page("io06", 0.1, False)] * 10
    # 1 bad of 20 kept, io06 left out: share 0.05 passes (bound is inclusive).
    assert rule_metrics(clean + bad + io06_bad, "R", 0.5)["gates"]["G2"]
    assert not rule_metrics(clean[:-1] + bad * 2 + io06_bad, "R", 0.5)["gates"]["G2"]


def test_g3_bound_is_oracle_plus_allowance() -> None:
    # Oracle 0.5. Bound 0.55: 11 of 20 escalated passes, 12 of 20 fails.
    def pages(escalated: int) -> list[dict]:
        return [_page("bd02", 0.1 if i < 10 else 0.9, i < escalated) for i in range(20)]

    assert rule_metrics(pages(11), "R", 0.5)["gates"]["G3"]
    assert not rule_metrics(pages(12), "R", 0.5)["gates"]["G3"]


def _gates(passed: bool, escalated: float) -> dict:
    return {"gates": {"G1": passed, "G2": True, "G3": True}, "escalated_share": escalated}


def test_select_takes_lowest_escalation_and_breaks_ties_simply() -> None:
    assert (
        select({"C0": _gates(True, 0.5), "C1": _gates(True, 0.4), "C3": _gates(True, 0.6)}) == "C1"
    )
    assert (
        select({"C0": _gates(True, 0.5), "C1": _gates(True, 0.5), "C3": _gates(True, 0.5)}) == "C0"
    )
    assert (
        select({"C0": _gates(False, 0.5), "C1": _gates(False, 0.4), "C3": _gates(False, 0.6)})
        is None
    )
