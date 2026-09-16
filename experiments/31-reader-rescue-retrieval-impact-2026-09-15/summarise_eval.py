"""Experiment 31 summariser (tasks 5.2-5.4).

Aggregates ``output/eval_results.json`` (plus the extraction and runtime
manifests) into ``output/eval_results.summary.json``:

- per cell: evidence recoverability, Evidence Recall@1/@3/@5/@10, MRR@10,
  no-hit rate, error count;
- secondary per cell: extraction latency (classify + full reader median),
  characters, chunk counts, index size, embedding tokens (null when the
  ingest surface does not expose them);
- paired candidate-vs-reference (B vs C) per-query results and, with >= 20
  measured queries, a 10,000-resample paired bootstrap percentile CI on
  the per-query hit@10 and reciprocal-rank differences;
- recommendation strings only — production changes require a separate
  OpenSpec proposal (task 6.2).

Usage:
    uv run python summarise_eval.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
K_VALUES = (1, 3, 5, 10)
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 31
MIN_QUERIES_FOR_BOOTSTRAP = 20


def _cell_metrics(rows: list[dict]) -> dict:
    scored = [r for r in rows if "error" not in r]
    errors = len(rows) - len(scored)
    n = len(scored)

    def recall(k: int) -> float | None:
        if not n:
            return None
        hits = sum(
            1 for r in scored if r.get("first_hit_rank") is not None and r["first_hit_rank"] <= k
        )
        return round(hits / n, 4)

    first_hits = [r.get("first_hit_rank") for r in scored]
    return {
        "queries": n,
        "errors": errors,
        "evidence_recoverability": (
            round(sum(1 for r in scored if r.get("evidence_recovered")) / n, 4) if n else None
        ),
        **{f"evidence_recall@{k}": recall(k) for k in K_VALUES},
        "mrr@10": (
            round(sum((1.0 / r) for r in first_hits if r is not None and r <= 10) / n, 4)
            if n
            else None
        ),
        "no_hit_rate": (round(sum(1 for r in first_hits if r is None) / n, 4) if n else None),
    }


def _paired(rows_b: list[dict], rows_c: list[dict]) -> dict:
    by_id_b = {r["query_id"]: r for r in rows_b}
    by_id_c = {r["query_id"]: r for r in rows_c}
    shared = [
        qid
        for qid in by_id_b
        if qid in by_id_c and "error" not in by_id_b[qid] and "error" not in by_id_c[qid]
    ]
    paired_rows = []
    for qid in shared:
        rb, rc = by_id_b[qid], by_id_c[qid]

        def rr(row: dict) -> float:
            rank = row.get("first_hit_rank")
            return 1.0 / rank if rank is not None and rank <= 10 else 0.0

        paired_rows.append(
            {
                "query_id": qid,
                "doc_id": rb["doc_id"],
                "b_recovered": rb.get("evidence_recovered"),
                "c_recovered": rc.get("evidence_recovered"),
                "b_hit": rb.get("first_hit_rank") is not None,
                "c_hit": rc.get("first_hit_rank") is not None,
                "b_rr": rr(rb),
                "c_rr": rr(rc),
            }
        )

    out: dict = {"paired_queries": len(paired_rows), "per_query": paired_rows}
    if not paired_rows:
        return out

    def _mean(values: list[float]) -> float:
        return sum(values) / len(values)

    hit_delta = [float(p["b_hit"]) - float(p["c_hit"]) for p in paired_rows]
    rr_delta = [p["b_rr"] - p["c_rr"] for p in paired_rows]
    out["mean_hit@10_delta_B_minus_C"] = round(_mean(hit_delta), 4)
    out["mean_rrr_delta_B_minus_C"] = round(_mean(rr_delta), 4)
    out["disagreements"] = [p["query_id"] for p in paired_rows if p["b_hit"] != p["c_hit"]]

    if len(paired_rows) >= MIN_QUERIES_FOR_BOOTSTRAP:
        # Bootstrap resampling, not cryptography — deterministic seed.
        rng = random.Random(BOOTSTRAP_SEED)  # noqa: S311

        def _bootstrap(deltas: list[float]) -> dict:
            means = []
            for _ in range(BOOTSTRAP_RESAMPLES):
                sample = [deltas[rng.randrange(len(deltas))] for _ in range(len(deltas))]
                means.append(_mean(sample))
            means.sort()
            lo = means[int(0.025 * len(means))]
            hi = means[int(0.975 * len(means)) - 1]
            return {"ci95_low": round(lo, 4), "ci95_high": round(hi, 4)}

        out["bootstrap"] = {
            "resamples": BOOTSTRAP_RESAMPLES,
            "seed": BOOTSTRAP_SEED,
            "hit@10_delta": _bootstrap(hit_delta),
            "rr_delta": _bootstrap(rr_delta),
        }
    else:
        out["bootstrap"] = None  # small sample stays a small-sample claim
    return out


def _secondary(cell: str, extraction: list[dict], runtime: dict | None) -> dict:
    rows = [r for r in extraction if r["cell"] == cell and r["split"] in ("heldout", "distractor")]
    heldout = [r for r in rows if r["split"] == "heldout"]
    return {
        "extraction": {
            "heldout_classify_seconds_median": _median([r["classify_seconds"] for r in heldout]),
            "heldout_reader_seconds_median": _median(
                [r["reader_seconds_median3"] for r in heldout]
            ),
            "heldout_characters_total": sum(r["characters"] for r in heldout),
            "distractor_characters_total": sum(
                r["characters"] for r in rows if r["split"] == "distractor"
            ),
            "rescued_documents": sum(1 for r in heldout if r["fallback_tier"]),
        },
        "index": {
            "total_chunks": runtime.get("total_chunks") if runtime else None,
            "index_size_bytes": runtime.get("index_size_bytes") if runtime else None,
            "embedding_tokens": runtime.get("embedding_tokens") if runtime else None,
            "source_commit": runtime.get("source_commit") if runtime else None,
            "lockfile_sha256": runtime.get("lockfile_sha256") if runtime else None,
        },
    }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return round((ordered[mid - 1] + ordered[mid]) / 2, 3)


def main() -> int:
    results = json.loads((EXP_DIR / "output" / "eval_results.json").read_text(encoding="utf-8"))
    extraction = json.loads(
        (EXP_DIR / "output" / "extraction_manifest.json").read_text(encoding="utf-8")
    )

    cells: dict = {}
    runtimes: dict = {}
    for cell in ("A", "B", "C"):
        # Checkpoint cells are dicts keyed by query_id; metrics want rows.
        rows = list(results["cells"].get(cell, {}).values())
        runtime_path = EXP_DIR / "output" / f"runtime_manifest_{cell}.json"
        runtime = json.loads(runtime_path.read_text()) if runtime_path.is_file() else None
        runtimes[cell] = runtime
        cells[cell] = {
            "role": {"A": "sanity_check", "B": "candidate", "C": "reference"}[cell],
            **_cell_metrics(rows),
            "secondary": _secondary(cell, extraction, runtime),
        }

    paired = _paired(
        list(results["cells"].get("B", {}).values()),
        list(results["cells"].get("C", {}).values()),
    )

    b, c, a = cells["B"], cells["C"], cells["A"]
    # Completeness prerequisite (CodeRabbit exp-31 review): a cell whose
    # queries all errored would score None metrics, and `or 0` would let the
    # zero-by-construction and rescue gates pass vacuously. Every measured
    # cell must have the full 24 poppler-labelled queries with zero errors.
    expected_queries = 24
    gates = {
        "cells_complete": all(
            cells[cell]["queries"] == expected_queries and cells[cell]["errors"] == 0
            for cell in ("A", "B", "C")
        ),
        "cell_A_zero_by_construction": (a.get("evidence_recall@10") or 0) == 0
        and (a.get("evidence_recoverability") or 0) == 0,
        "candidate_rescues_evidence": b["evidence_recoverability"] is not None
        and b["evidence_recoverability"] > 0,
        "reference_rescues_evidence": c["evidence_recoverability"] is not None
        and c["evidence_recoverability"] > 0,
        "candidate_not_materially_worse": not (
            (b["evidence_recall@10"] or 0) < (c["evidence_recall@10"] or 0)
            and paired.get("bootstrap")
            and paired["bootstrap"]["hit@10_delta"]["ci95_high"] < 0
        ),
    }

    summary = {
        "experiment": "31-reader-rescue-retrieval-impact-2026-09-15",
        "cells": cells,
        "paired_B_vs_C": {k: v for k, v in paired.items() if k != "per_query"},
        "per_query_paired_B_vs_C": paired["per_query"],
        "gates": gates,
        "all_gates_pass": all(gates.values()),
    }
    out = EXP_DIR / "output" / "eval_results.summary.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    public = dict(summary)
    public.pop("per_query_paired_B_vs_C")
    print(json.dumps(public, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
