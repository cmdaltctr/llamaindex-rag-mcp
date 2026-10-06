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
