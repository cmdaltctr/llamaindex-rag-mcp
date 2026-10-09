"""Task 6.1: each gate, the margin, McNemar, the routing rule and the verdict."""

from __future__ import annotations

import pytest
from exp42_io import EXP38, load_module
from summarise_eval import STATS, gates, margin, primary_pass, verdict, wilson

SIMULATE = load_module(EXP38 / "summarise_eval.py", "exp38_summarise_eval").simulate_routing


def doc_routing(routed: bool, usable_new: bool = False) -> dict:
    return {"routed": routed, "newly_routed_usable": usable_new}


def test_g1_fails_when_a_junk_layer_document_does_not_route() -> None:
    routing = {"j1": doc_routing(True), "j2": doc_routing(False)}
    assert gates(routing, ["j1"], 0.0)["G1"]
    assert not gates(routing, ["j1", "j2"], 0.0)["G1"]


def test_g2_fails_when_a_usable_document_newly_routes() -> None:
    assert gates({"u": doc_routing(False)}, [], 0.0)["G2"]
    assert not gates({"u": doc_routing(True, usable_new=True)}, [], 0.0)["G2"]


@pytest.mark.parametrize(("rate", "passes"), [(0.02, True), (0.0201, False)])
def test_g3_ceiling(rate: float, passes: bool) -> None:
    assert gates({}, [], rate)["G3"] is passes


@pytest.mark.parametrize(
    ("clef", "p", "passes"), [(0.80, 0.04, True), (0.79, 0.04, False), (0.80, 0.05, False)]
)
def test_margin_needs_010_and_p_below_005(clef: float, p: float, passes: bool) -> None:
    result = margin({"junk_recall": clef}, {"junk_recall": 0.70}, {"p_one_sided": p})
    assert result["pass"] is passes


def test_mcnemar_exact_one_sided() -> None:
    a = [{"doc_id": "d", "page": i, "class": "junk", "score": 0.9} for i in range(5)]
    b = [{**r, "score": 0.1} for r in a]
    result = STATS.mcnemar(a, b, 0.5, 0.5)
    assert (result["b_only"], result["a_only"]) == (5, 0)
    assert result["p_one_sided"] == pytest.approx(1 / 32)


def test_routing_counts_only_rescued_tier_flags_at_ten_percent() -> None:
    baseline = [
        {
            "doc_id": "d",
            "page_count": 20,
            "extraction_fallback_backend": "liteparse",
            "ocr_required": False,
        }
    ]
    labels = {"d": {"label": "usable"}}

    def rows(lite: int, pypdf: int) -> list[dict]:
        out = [{"doc_id": "d", "tier": "liteparse", "score": 0.0} for _ in range(lite)]
        return out + [{"doc_id": "d", "tier": "pypdf", "score": 0.0} for _ in range(pypdf)]

    assert SIMULATE(rows(2, 0), baseline, labels, 0.5)["d"]["routed"]
    assert not SIMULATE(rows(1, 5), baseline, labels, 0.5)["d"]["routed"]
    assert SIMULATE(rows(2, 0), baseline, labels, 0.5)["d"]["newly_routed_usable"]
    prior = [{**baseline[0], "ocr_required": True}]
    assert not SIMULATE(rows(0, 0), prior, labels, 0.5)["d"]["newly_routed_usable"]
    assert SIMULATE(rows(0, 0), prior, labels, 0.5)["d"]["routed"]


def test_option_a_ignores_g3_and_option_b_needs_it() -> None:
    gate = {"G1": True, "G2": True, "G3": False}
    assert primary_pass(gate, "A", True)
    assert not primary_pass(gate, "B", True)
    assert not primary_pass(gate, "A", False)
    assert not primary_pass({**gate, "G2": False}, "A", True)


@pytest.mark.parametrize(
    ("clef", "a", "label"),
    [(True, False, "PASS"), (False, True, "FAIL for Clef-flash"), (False, False, "FAIL")],
)
def test_verdict_mapping(clef: bool, a: bool, label: str) -> None:
    assert verdict(clef, a) == label


def test_wilson_interval_matches_reference() -> None:
    interval = wilson(72, 100)
    assert interval["lower"] == pytest.approx(0.6252, abs=1e-4)
    assert interval["upper"] == pytest.approx(0.7987, abs=1e-4)
