"""Tests for leave-one-document-out thresholds and the held-out verdict."""

from __future__ import annotations

import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))

from lodo import held_out, lodo_thresholds  # noqa: E402
from signal_stats import metrics  # noqa: E402
from summarise_lodo import adoption  # noqa: E402


def page(doc_id, score, cls="healthy", tier="liteparse", n=0):
    return {"doc_id": doc_id, "page": n, "tier": tier, "class": cls, "score": score}


def corpus():
    # 100 healthy pages in "good" (scores 0.50 to 0.99) and 10 low healthy pages in "odd".
    rows = [page("good", 0.5 + i / 200, n=i) for i in range(100)]
    rows += [page("odd", 0.01 * i, n=i) for i in range(10)]
    return rows


def test_document_threshold_ignores_its_own_pages():
    thresholds = lodo_thresholds(corpus())
    # Without "odd", 2% of 100 healthy pages allows 2, so the threshold is the 3rd score.
    assert thresholds["odd"] == 0.51
    # With "odd" out of the pool for "good", only odd's 10 pages and none of good's set it.
    assert thresholds["good"] == 0.0


def test_pypdf_rows_use_the_liteparse_threshold_of_their_document():
    rows = corpus() + [page("good", 0.9, tier="pypdf")]
    assert set(lodo_thresholds(rows)) == {"good", "odd"}
    assert lodo_thresholds(rows) == lodo_thresholds(corpus())


def test_shift_keeps_strict_flags_exactly():
    rows = [page("d", s, cls="junk", n=i) for i, s in enumerate((0.2, 0.3, 0.30000000000000004))]
    flags = [r["score"] < 0.3 for r in rows]
    shifted = held_out(rows, {"d": 0.3})
    assert [r["score"] < 0 for r in shifted] == flags
    assert metrics(shifted, 0.0)["junk_flagged"] == 1


def test_adoption_needs_margin_significance_and_gates():
    def result(caught, gate=True):
        return {
            "populations": {"liteparse": {"junk_pages": 100, "junk_flagged": caught}},
            "gates": {"G1": gate, "G2": True, "G3": True},
        }

    junk = [page("d", 0, cls="junk", n=i) for i in range(100)]
    flagged = lambda k: [{**r, "score": -1 if r["page"] < k else 1} for r in junk]  # noqa: E731
    results = {"A": result(40), "B": result(45), "C": result(70)}
    shifted = {"A": flagged(40), "B": flagged(45), "C": flagged(70)}
    verdict = adoption(results, shifted)
    assert verdict["C"]["adopt"] and not verdict["B"]["adopt"]
    assert verdict["recommendation"] == ["C"]
    results["C"] = result(70, gate=False)
    assert adoption(results, shifted)["recommendation"] == ["A"]


def test_nested_selection_never_sees_the_held_out_document():
    from lodo import nested_select

    def doc(doc_id, junk, healthy):
        return [page(doc_id, s, cls="junk", n=i) for i, s in enumerate(junk)] + [
            page(doc_id, s, n=100 + i) for i, s in enumerate(healthy)
        ]

    # x separates junk only in d1; y separates junk only in d2.
    high = [0.9 + i / 1000 for i in range(60)]
    variants = {
        "x": doc("d1", [0.1] * 5, high) + doc("d2", [0.95] * 5, high),
        "y": doc("d1", [0.99] * 5, high) + doc("d2", [0.1] * 5, high),
    }
    _, chosen = nested_select(variants)
    # Each document's wording is chosen on the other document only.
    assert chosen == {"d1": "y", "d2": "x"}


def test_cascade_only_flags_pages_both_signals_suspect():
    from lodo import cascade_select

    # Two documents; each has 50 healthy pages and 5 junk pages.
    def rows(scores_a, scores_c):
        out_a, out_c = [], []
        for doc_id in ("d1", "d2"):
            for i in range(55):
                cls = "junk" if i < 5 else "healthy"
                base = {"doc_id": doc_id, "page": i, "tier": "liteparse", "class": cls}
                out_a.append({**base, "score": scores_a(cls, i)})
                out_c.append({**base, "score": scores_c(cls, i)})
        return out_a, out_c

    # A suspects junk and the lowest healthy pages; Jev clears every healthy page.
    a, c = rows(
        lambda cls, i: 0.1 if cls == "junk" else i / 100,
        lambda cls, i: 0.05 if cls == "junk" else 0.9,
    )
    shifted, sent = cascade_select(a, c, screen_rate=0.20)
    flagged = {(r["doc_id"], r["page"]) for r in shifted if r["score"] < 0}
    assert flagged == {(d, i) for d in ("d1", "d2") for i in range(5)}
    assert 0 < sent < 0.5
    # If Jev cannot confirm, the cascade flags nothing even where A suspects junk.
    a, c = rows(lambda cls, i: 0.1 if cls == "junk" else i / 100, lambda cls, i: 0.9)
    shifted, _ = cascade_select(a, c, screen_rate=0.20)
    assert not any(r["score"] < 0 and r["class"] == "junk" for r in shifted)
