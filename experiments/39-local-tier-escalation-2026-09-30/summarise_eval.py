"""Experiment 39: summarise ``output/rules.json`` into ``output/summary.json``.

Computes O, the three gates per candidate, per-document escalation, the ``io06``
column and the exploratory C4 AUCs. Stops (no summary written) when the C0
values at the 0.8 cut do not reproduce Experiment 33.

    uv run python summarise_eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from score_rules import PLAN, RULES_OUT, write_atomic  # noqa: E402

SUMMARY_OUT = RULES_OUT.with_name("summary.json")

BAD_RECALL = 0.5  # a kept page with body recall below this indexes junk
G2_MAX = 0.05
G3_ALLOWANCE = 0.05
GOOD_RECALL = 0.8  # modern Latin print, the C4 negatives
NON_LATIN = ("io01", "io02", "io03", "io07")
CANDIDATES = ("C0", "C1", "C3")  # in tie-break order, simplest first
SWEEP = ("C0@0.5", "C0@0.6", "C0@0.7", "C0@0.8", "C0@0.9")
REPRODUCTION_TOLERANCE = 0.001


def share(part: int, whole: int) -> float:
    """Return part / whole, or 0.0 for an empty whole."""
    return part / whole if whole else 0.0


def is_bad(page: dict) -> bool:
    """A page is bad when its body recall is below 0.5."""
    return page["body_recall"] < BAD_RECALL


def kept_bad(pages: list[dict], rule: str) -> tuple[int, int]:
    """Return (kept pages, kept pages that are bad) for *rule*."""
    kept = [p for p in pages if not p["escalate"][rule]]
    return len(kept), sum(is_bad(p) for p in kept)


def auc(positives: list[float], negatives: list[float]) -> float:
    """Return the AUC of the signal: P(positive > negative), ties count half."""
    if not positives or not negatives:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def rule_metrics(gated: list[dict], rule: str, oracle: float) -> dict:
    """Return the gate values and diagnostics of one rule on the gated pages."""
    kept, bad = kept_bad(gated, rule)
    no_io06 = [p for p in gated if p["doc_id"] != "io06"]
    kept_n, bad_n = kept_bad(no_io06, rule)
    non_latin = [p for p in gated if p["doc_id"] in NON_LATIN]
    io06 = [p for p in gated if p["doc_id"] == "io06"]
    io06_bad = [p for p in io06 if is_bad(p)]
    escalated = share(sum(p["escalate"][rule] for p in gated), len(gated))
    non_latin_kept = sum(not p["escalate"][rule] for p in non_latin)
    g2_share = share(bad_n, kept_n)
    return {
        "escalated_share": escalated,
        "kept": kept,
        "kept_bad": bad,
        "kept_bad_share_with_io06": share(bad, kept),
        "kept_bad_share_without_io06": g2_share,
        "kept_without_io06": kept_n,
        "non_latin_kept": non_latin_kept,
        "io06": {
            "pages": len(io06),
            "bad_pages": len(io06_bad),
            "bad_escalated_share": share(sum(p["escalate"][rule] for p in io06_bad), len(io06_bad)),
            "escalated_share": share(sum(p["escalate"][rule] for p in io06), len(io06)),
        },
        "gates": {
            "G1": non_latin_kept == 0,
            "G2": g2_share <= G2_MAX,
            "G3": escalated <= oracle + G3_ALLOWANCE,
        },
        "per_document": per_document(gated, rule),
    }


def per_document(gated: list[dict], rule: str) -> dict:
    """Return the escalation count and share per document for *rule*."""
    docs: dict[str, list[dict]] = {}
    for page in gated:
        docs.setdefault(page["doc_id"], []).append(page)
    return {
        doc: {
            "pages": len(pages),
            "escalated": (n := sum(p["escalate"][rule] for p in pages)),
            "share": share(n, len(pages)),
        }
        for doc, pages in sorted(docs.items())
    }


def c4_aucs(pages: list[dict]) -> dict:
    """Return the exploratory AUCs of the two engine signals (decision DR1)."""
    gated_io06 = [p for p in pages if p["population"] == "gated" and p["doc_id"] == "io06"]
    positives = [p for p in gated_io06 if is_bad(p)]
    negatives = [
        p
        for p in pages
        if p["doc_id"] != "io06"
        and p["doc_id"] not in NON_LATIN
        and p["body_recall"] is not None
        and p["body_recall"] >= GOOD_RECALL
    ]
    # Direction fixed in DR1: more discarded regions and fewer chars mean positive.
    signals = {
        "discarded_regions": lambda p: p["signals"]["discarded_regions"],
        "chars_low_is_positive": lambda p: -p["signals"]["chars"],
    }
    out: dict = {"positives": len(positives), "negatives": len(negatives)}
    for name, fn in signals.items():
        one_sided = auc([fn(p) for p in positives], [fn(p) for p in negatives])
        out[name] = {
            "auc_one_sided": one_sided,
            "auc_two_sided": max(one_sided, 1 - one_sided),
            "follow_up": one_sided >= 0.8,
        }
    return out


def select(metrics: dict[str, dict]) -> str | None:
    """Return the passing candidate with the lowest escalated share, or ``None``."""
    passing = [c for c in CANDIDATES if all(metrics[c]["gates"].values())]
    if not passing:
        return None
    return min(passing, key=lambda c: (metrics[c]["escalated_share"], CANDIDATES.index(c)))


def main() -> None:
    """Summarise ``rules.json``, check reproduction, write ``summary.json``."""
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    pages = json.loads(RULES_OUT.read_text(encoding="utf-8"))["pages"]
    gated = [p for p in pages if p["population"] == "gated"]
    figure_only = [p for p in pages if p["population"] == "figure_only"]
    oracle = share(sum(is_bad(p) for p in gated), len(gated))
    if round(oracle, 4) != plan["oracle_O"]["value"]:
        sys.exit(f"O {oracle:.4f} differs from the plan {plan['oracle_O']['value']}")
    metrics = {r: rule_metrics(gated, r, oracle) for r in (*CANDIDATES, *SWEEP)}
    repro = plan["reproduction_check"]
    c0_08 = metrics["C0@0.8"]
    observed = {
        "C0_escalation": c0_08["escalated_share"],
        "C0_kept_below_0_5": c0_08["kept_bad_share_with_io06"],
    }
    drift = {k: abs(observed[k] - repro[k]) for k in observed}
    reproduced = all(d <= repro["tolerance"] for d in drift.values())
    if not reproduced or metrics["C0"]["escalated_share"] != c0_08["escalated_share"]:
        sys.exit(f"reproduction failed, stop: observed {observed}, drift {drift}")
    winner = select(metrics)
    write_atomic(
        SUMMARY_OUT,
        {
            "experiment_id": plan["experiment_id"],
            "gated_pages": len(gated),
            "O": oracle,
            "gate_bounds": {"G2_max": G2_MAX, "G3_max": oracle + G3_ALLOWANCE},
            "reproduction": {"observed": observed, "drift": drift, "ok": reproduced},
            "metrics": metrics,
            "figure_only_escalated_share": {
                r: share(sum(p["escalate"][r] for p in figure_only), len(figure_only))
                for r in (*CANDIDATES, *SWEEP)
            },
            "c4": c4_aucs(pages),
            "winner": winner,
        },
    )
    print(f"O={oracle:.4f} reproduction ok, winner={winner}", flush=True)
    for rule in (*CANDIDATES, *SWEEP):
        m = metrics[rule]
        print(
            f"{rule:7s} esc={m['escalated_share']:.3f} kept-bad(no io06)="
            f"{m['kept_bad_share_without_io06']:.3f} non-latin kept={m['non_latin_kept']} "
            f"gates={''.join(g[1] if ok else '-' for g, ok in m['gates'].items())}",
            flush=True,
        )


if __name__ == "__main__":
    main()
