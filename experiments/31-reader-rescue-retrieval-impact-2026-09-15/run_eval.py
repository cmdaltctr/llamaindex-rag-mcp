"""Experiment 31 measured evaluation run (task 5.1; 5.4 evidence capture).

Runs the frozen query set, in frozen order, against each cell's index and
records per query per cell:

- the top-10 retrieved chunk texts (private — ``output/eval_results.json``
  is gitignored);
- ``evidence_recovered``: the gold span matches the cell's FULL extraction
  (parser stage, measured before embedding, from
  ``output/.extractions/<cell>/<doc>.txt``);
- ``first_hit_rank``: rank (1-based) of the first retrieved chunk matching
  the gold span under the SAME frozen rule, else null;
- per-rank hit booleans, search latency, and any error.

Checkpoint: ``output/eval_results_checkpoint.json`` written atomically
after every query; ``--resume`` skips completed (cell, query) pairs.

Refuses to run when the freeze is violated or the preflight has failures.

Usage:
    uv run python run_eval.py [--cell A|B|C ...] [--resume]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(EXP_DIR))

import harness_readers  # noqa: E402
from build_indexes import PINNED_ENV  # noqa: E402
from matching import span_hit  # noqa: E402

harness_readers.register_mirrors()

TOP_K = 10


def _load_checkpoint(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"cells": {}}


def _atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _run_cell(cell: str, queries: list[dict], checkpoint: dict, resume: bool) -> None:
    collection = f"exp31_{cell}"
    cell_state = checkpoint["cells"].setdefault(cell, {})

    import omrg.config as config_module

    env = dict(PINNED_ENV)
    # The reader never runs at search time; the production name keeps
    # Settings valid and the engine construction identical to build time.
    env["PDF_READER"] = harness_readers.PRODUCTION_NAME
    env["COLLECTION_NAME"] = collection
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    engine = None
    try:
        config_module._settings = None
        from omrg.compose import build_engine

        engine = build_engine()
        for q in queries:
            qid = q["query_id"]
            if resume and qid in cell_state and "error" not in cell_state[qid]:
                continue
            row: dict = {"query_id": qid, "doc_id": q["doc_id"]}
            try:
                started = time.perf_counter()
                hits = engine.search(q["query"], top_k=TOP_K, collection_name=collection)
                row["search_seconds"] = round(time.perf_counter() - started, 3)
                texts = [h.get("text", "") or "" for h in hits]
                row["retrieved_texts"] = texts
                row["hit_ranks"] = [
                    rank if rank else None
                    for rank in (
                        (position + 1) if span_hit(q["evidence_span"], text) else None
                        for position, text in enumerate(texts)
                    )
                ]
                row["first_hit_rank"] = next((r for r in row["hit_ranks"] if r), None)
                extraction_path = EXP_DIR / "output" / ".extractions" / cell / f"{q['doc_id']}.txt"
                extraction = (
                    extraction_path.read_text(encoding="utf-8", errors="replace")
                    if extraction_path.is_file()
                    else ""
                )
                row["evidence_recovered"] = span_hit(q["evidence_span"], extraction)
                row["retrieved_count"] = len(hits)
            except Exception as exc:  # noqa: BLE001 - record, keep the run alive
                row["error"] = f"{type(exc).__name__}: {exc}"
            cell_state[qid] = row
            _atomic_write(EXP_DIR / "output" / "eval_results_checkpoint.json", checkpoint)
            status = row.get("error") or (
                f"recovered={row['evidence_recovered']} first_hit={row['first_hit_rank']}"
            )
            print(f"[{cell}] {qid}: {status}", flush=True)
    finally:
        if engine is not None:
            engine.close()
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config_module._settings = None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", choices=["A", "B", "C"], action="append")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    cells = args.cell or ["A", "B", "C"]

    # Gates: freeze + preflight.
    import freeze

    recorded = json.loads((EXP_DIR / "output" / "frozen.manifest.json").read_text())
    current = freeze._build()
    if any(
        current["files"].get(label, {}).get("sha256") != entry["sha256"]
        for label, entry in recorded["files"].items()
    ) or any(
        current["documents"].get(doc_id) != digest
        for doc_id, digest in recorded["documents"].items()
    ):
        print("FROZEN INPUTS CHANGED — refusing to run", file=sys.stderr)
        return 1
    preflight_path = EXP_DIR / "output" / "preflight.json"
    if not preflight_path.is_file():
        print("PREFLIGHT MISSING — run preflight.py first", file=sys.stderr)
        return 1
    failures = [r for r in json.loads(preflight_path.read_text()) if r["status"] == "FAIL"]
    if failures:
        print(f"PREFLIGHT HAS {len(failures)} FAILURES — refusing to run", file=sys.stderr)
        return 1

    qrels = json.loads((EXP_DIR / "queries" / "qrels.json").read_text(encoding="utf-8"))
    queries = qrels["queries"]  # frozen order

    checkpoint_path = EXP_DIR / "output" / "eval_results_checkpoint.json"
    checkpoint = _load_checkpoint(checkpoint_path)
    checkpoint.setdefault("meta", {})["operator_started_utc"] = datetime.now(UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    for cell in cells:
        _run_cell(cell, queries, checkpoint, resume=args.resume)

    checkpoint["meta"]["operator_finished_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    _atomic_write(EXP_DIR / "output" / "eval_results.json", checkpoint)
    print("wrote output/eval_results.json", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
