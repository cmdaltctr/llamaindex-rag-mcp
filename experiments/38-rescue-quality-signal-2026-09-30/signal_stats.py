"""Operating points and paired statistics for the frozen signal experiment."""

from __future__ import annotations

import math
from collections import Counter

import numpy as np


def equal_cost_threshold(rows: list[dict]) -> float:
    """Choose the highest strict threshold with healthy flag rate at most 0.02."""
    healthy = sorted(row["score"] for row in rows if row["class"] == "healthy")
    if not healthy:
        raise ValueError("equal-cost threshold requires healthy pages")
    allowance = math.floor(0.02 * len(healthy))
    # Strict '<' keeps the first disallowed healthy score, and all its ties,
    # outside the flagged set. Finite samples need not attain exactly 0.02.
    return float(healthy[allowance])


def metrics(rows: list[dict], threshold: float) -> dict:
    """Count junk recall and healthy false positives at a strict threshold."""
    junk = [row for row in rows if row["class"] == "junk"]
    healthy = [row for row in rows if row["class"] == "healthy"]
    caught = sum(row["score"] < threshold for row in junk)
    false = sum(row["score"] < threshold for row in healthy)
    return {
        "threshold": threshold,
        "junk_pages": len(junk),
        "junk_flagged": caught,
        "junk_recall": caught / len(junk) if junk else None,
        "healthy_pages": len(healthy),
        "healthy_false_positives": false,
        "healthy_false_positive_rate": false / len(healthy) if healthy else None,
    }


def bootstrap_interval(rows: list[dict], threshold: float, documents: list[str]) -> dict:
    """Resample whole documents 2,000 times with seed 38 for junk recall."""
    total = Counter(row["doc_id"] for row in rows if row["class"] == "junk")
    caught = Counter(
        row["doc_id"] for row in rows if row["class"] == "junk" and row["score"] < threshold
    )
    indices = np.random.default_rng(38).integers(0, len(documents), size=(2000, len(documents)))
    denominator = np.array([total[d] for d in documents])[indices].sum(axis=1)
    numerator = np.array([caught[d] for d in documents])[indices].sum(axis=1)
    values = numerator[denominator > 0] / denominator[denominator > 0]
    return {
        "lower": float(np.quantile(values, 0.025)) if len(values) else None,
        "upper": float(np.quantile(values, 0.975)) if len(values) else None,
        "resamples": 2000,
        "defined_resamples": len(values),
        "seed": 38,
    }


def mcnemar(a: list[dict], b: list[dict], threshold_a: float, threshold_b: float) -> dict:
    """Compute exact one-sided McNemar probability for B catching more junk."""
    flags_a = {
        (r["doc_id"], r["page"]): r["score"] < threshold_a for r in a if r["class"] == "junk"
    }
    flags_b = {
        (r["doc_id"], r["page"]): r["score"] < threshold_b for r in b if r["class"] == "junk"
    }
    if flags_a.keys() != flags_b.keys():
        raise ValueError("paired junk populations differ")
    a_only = sum(flags_a[key] and not flags_b[key] for key in flags_a)
    b_only = sum(flags_b[key] and not flags_a[key] for key in flags_a)
    discordant = a_only + b_only
    probability = (
        sum(math.comb(discordant, k) for k in range(b_only, discordant + 1)) / 2**discordant
    )
    return {
        "a_only": a_only,
        "b_only": b_only,
        "discordant": discordant,
        "p_one_sided": probability,
    }


def auc_badness(rows: list[dict]) -> float | None:
    """Measure ranking of body recall below 0.5; lower quality means worse text."""
    bad = np.array([r["score"] for r in rows if r["body_recall"] < 0.5])
    good = np.array([r["score"] for r in rows if r["body_recall"] >= 0.5])
    if not len(bad) or not len(good):
        return None
    return float(((bad[:, None] < good[None, :]) + 0.5 * (bad[:, None] == good[None, :])).mean())
