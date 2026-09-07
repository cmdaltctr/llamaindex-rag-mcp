"""Gate-freeze noise analysis for task 1.6 (frozen 2026-09-08).

Derives the noise tolerances used by the Stage 5 validity gates from the
committed Experiment 22 per-query checkpoints. No candidate data exists
or is used.

Writes output/gate_noise.json. Bootstrap: N=10,000, seed 20260908.
"""

from __future__ import annotations

import json
import random
import statistics
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
GT_PATH = EXP_DIR / "output/ground-truth.json"
CELLS = ("dense_only__raw", "hybrid__raw")
N_BOOT = 10_000
SEED = 20260908
METRICS = ("recall_at_5", "recall_at_10", "recall_at_50", "hit_at_10")


def _per_query(row: dict, query: dict) -> dict:
    """Per-query metrics with the summariser's rank semantics."""
    parent_ids = row["parent_ids"]
    ranks: dict[str, int] = {}
    for rank, pid in enumerate(parent_ids, start=1):
        ranks.setdefault(pid, rank)
    relevant = set(query.get("relevant_parent_ids") or [])
    hit_ranks = [ranks[d] for d in relevant if d in ranks]
    first = min(hit_ranks) if hit_ranks else None
    out: dict = {"latency_ms": row["latency_s"] * 1000}
    for k in (1, 5, 10, 50):
        top = set(parent_ids[:k])
        out[f"recall_at_{k}"] = len(relevant & top) / len(relevant) if relevant else 0.0
    out["hit_at_10"] = first is not None and first <= 10
    return {m: float(v) for m, v in out.items()}


def _p95(vals: list[float]) -> float:
    s = sorted(vals)
    return s[max(0, int(0.95 * len(s)) - 1)]


def main() -> None:
    queries = {q["query_id"]: q for q in json.loads(GT_PATH.read_text(encoding="utf-8"))["queries"]}
    per_cell: dict[str, dict[str, dict]] = {}
    for cell in CELLS:
        rows = json.loads((EXP_DIR / "output/cells" / f"{cell}.json").read_text(encoding="utf-8"))[
            "rows"
        ]
        per_cell[cell] = {r["query_id"]: _per_query(r, queries[r["query_id"]]) for r in rows}

    # Seeded PRNG is intentional: reproducible bootstrap, not security.
    rng = random.Random(SEED)  # noqa: S311
    report: dict = {
        "seed": SEED,
        "n_boot": N_BOOT,
        "categories": {},
        "paired_reference": {},
        "latency": {},
    }

    for cat in ("all", "identifier-heavy", "continuity"):
        ids = [
            q
            for q, m in per_cell["hybrid__raw"].items()
            if cat == "all" or m is not None and queries[q]["category"] == cat
        ]
        entry: dict = {"n": len(ids)}
        for metric in METRICS:
            vals = [per_cell["hybrid__raw"][q][metric] for q in ids]
            means = sorted(statistics.fmean(rng.choices(vals, k=len(vals))) for _ in range(N_BOOT))
            half = (means[int(0.975 * N_BOOT)] - means[int(0.025 * N_BOOT)]) / 2
            entry[metric] = {
                "mean": round(statistics.fmean(vals), 6),
                "boot95_halfwidth": round(half, 6),
            }
        report["categories"][cat] = entry

    for metric in METRICS:
        diffs = [
            per_cell["hybrid__raw"][q][metric] - per_cell["dense_only__raw"][q][metric]
            for q in per_cell["hybrid__raw"]
        ]
        se = statistics.pstdev(diffs) / (len(diffs) ** 0.5)
        report["paired_reference"][metric] = {
            "sd_diff": round(statistics.pstdev(diffs), 6),
            "se_of_mean_diff": round(se, 6),
            "ci95_halfwidth": round(1.96 * se, 6),
        }

    lats = [m["latency_ms"] for m in per_cell["hybrid__raw"].values()]
    p95_boots = sorted(_p95(rng.choices(lats, k=len(lats))) for _ in range(N_BOOT))
    report["latency"] = {
        "p95_ms": round(_p95(lats), 1),
        "boot95_ci_of_p95": [
            round(p95_boots[int(0.025 * N_BOOT)], 1),
            round(p95_boots[int(0.975 * N_BOOT)], 1),
        ],
    }

    out = EXP_DIR / "output/gate_noise.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    tmp.replace(out)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
