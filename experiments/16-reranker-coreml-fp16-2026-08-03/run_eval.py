# NOTE (v2.0.0): this script targets the PRE-v2.0.0 import surface
# (rag_mcp.ingestion, rag_mcp.retrieval, rag_mcp.reranker, ...), which was
# removed by the architecture-v2 conformance change. It is an archived
# historical artefact, is not run in CI, and is intentionally NOT repaired:
# its results are already recorded in results.md, and rewriting it would
# change the code that produced them. See docs/adr/037.

#!/usr/bin/env python3
"""Benchmark: reranker CoreML EP + fp16 feasibility and latency (Experiment 16).

Tests three cells on Alibaba-NLP/gte-reranker-modernbert-base:
  16A: int8 (model_quantized.onnx) + CPU         — baseline (swap default plan)
  16B: fp16 (model_fp16.onnx) + CoreML EP         — candidate (the open question)
  16C: fp16 (model_fp16.onnx) + CPU               — control (isolates CoreML effect)

Mirrors the production rerank() inference loop (batch=32, padding=True,
truncation=True, sigmoid) but loads each model directly via onnxruntime with
explicit provider control, bypassing the singleton so each cell is clean.

See protocol.md for hypotheses, pass gates, and interpretation rules.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import resource
import statistics
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent

MODEL_ID = "Alibaba-NLP/gte-reranker-modernbert-base"
BATCH_SIZE = 32
MAX_LENGTH = 2048

# (cell_id, variant_path, providers, label)
CELLS: list[tuple[str, str, list[str], str]] = [
    ("16A", "onnx/model_quantized.onnx",
     ["CPUExecutionProvider"], "int8 + CPU (baseline)"),
    ("16B", "onnx/model_fp16.onnx",
     ["CoreMLExecutionProvider", "CPUExecutionProvider"], "fp16 + CoreML (candidate)"),
    ("16C", "onnx/model_fp16.onnx",
     ["CPUExecutionProvider"], "fp16 + CPU (control)"),
]


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_val = math.exp(value)
    return exp_val / (1.0 + exp_val)


def _peak_rss_mb() -> float:
    """Peak resident set size in MB. macOS reports bytes; Linux reports KB."""
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return rss / (1024 * 1024)
    return rss / 1024


def _build_docs(seed_texts: list[str], length_targets: list[dict[str, int]]) -> list[str]:
    """Generate candidate docs at approximate target token lengths.

    Repeats seed text to roughly hit each target (chars ~= 4 * tokens for
    English). Exact count is not critical — the variety (short/medium/long)
    is what stresses dynamic padding across a batch.
    """
    docs: list[str] = []
    pool = " ".join(seed_texts)
    for target in length_targets:
        char_target = target["tokens"] * 4
        for _ in range(target["count"]):
            if len(pool) >= char_target:
                docs.append(pool[:char_target])
            else:
                reps = math.ceil(char_target / len(pool))
                docs.append((pool * reps)[:char_target])
    return docs


def _load_cell(
    variant: str, providers: list[str],
) -> dict[str, Any]:
    """Download + load a model variant. Returns load info or error."""
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from transformers import AutoTokenizer

    info: dict[str, Any] = {
        "variant": variant,
        "requested_providers": providers,
        "loaded": False,
        "load_error": None,
    }

    try:
        t0 = time.perf_counter()
        onnx_path = hf_hub_download(repo_id=MODEL_ID, filename=variant)
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        session = ort.InferenceSession(onnx_path, providers=providers)
        cold_start = time.perf_counter() - t0
        info.update({
            "loaded": True,
            "cold_start_s": round(cold_start, 3),
            "actual_providers": session.get_providers(),
        })
        info["_session"] = session
        info["_tokenizer"] = tokenizer
    except Exception as exc:
        info["load_error"] = f"{type(exc).__name__}: {exc}"

    return info


def _rerank_once(
    session: Any, tokenizer: Any, query: str, docs: list[str],
) -> list[float]:
    """One rerank-equivalent call. Mirrors reranker.py lines 287–301."""
    import numpy as np

    pairs = [(query, doc) for doc in docs]
    all_logits: list[float] = []
    for i in range(0, len(pairs), BATCH_SIZE):
        batch = pairs[i:i + BATCH_SIZE]
        encoded = tokenizer(
            batch, padding=True, truncation=True,
            max_length=MAX_LENGTH, return_tensors="np",
        )
        outputs = session.run(None, dict(encoded.items()))
        batch_logits = np.asarray(outputs[0]).flatten()
        all_logits.extend(float(v) for v in batch_logits)
    return [_sigmoid(v) for v in all_logits]


def _measure_cell(
    cell_id: str, variant: str, providers: list[str], label: str,
    queries: list[str], docs: list[str], iterations: int,
) -> dict[str, Any]:
    """Load model, run N iterations, collect latency + footprint."""
    print(f"\n{'='*60}", flush=True)
    print(f"Cell {cell_id}: {label}", flush=True)
    print(f"  variant:   {variant}", flush=True)
    print(f"  providers: {providers}", flush=True)
    print(f"{'='*60}", flush=True)

    cell: dict[str, Any] = {
        "cell_id": cell_id, "label": label,
        "variant": variant, "requested_providers": providers,
        "loaded": False, "load_error": None,
    }

    # ── Load (H1) ──────────────────────────────────────────────────────
    print("  Loading model...", flush=True)
    load_info = _load_cell(variant, providers)
    cell["loaded"] = load_info["loaded"]
    cell["load_error"] = load_info["load_error"]

    if not load_info["loaded"]:
        print(f"  LOAD FAILED (H1 FAIL): {load_info['load_error']}", flush=True)
        cell["interpretation"] = "H1 FAIL — CoreML crash or load error"
        return cell

    cell["cold_start_s"] = load_info["cold_start_s"]
    cell["actual_providers"] = load_info["actual_providers"]
    print(f"  Loaded in {load_info['cold_start_s']}s", flush=True)
    print(f"  Actual providers: {load_info['actual_providers']}", flush=True)

    session = load_info["_session"]
    tokenizer = load_info["_tokenizer"]

    # ── Warmup (discard) ───────────────────────────────────────────────
    print("  Warmup iteration (discarded)...", flush=True)
    _rerank_once(session, tokenizer, queries[0], docs)

    # ── Measured iterations (H2) ───────────────────────────────────────
    rss_before = _peak_rss_mb()
    per_query_latencies: list[float] = []
    iteration_totals: list[float] = []

    for it in range(1, iterations + 1):
        it_t0 = time.perf_counter()
        for query in queries:
            q_t0 = time.perf_counter()
            _rerank_once(session, tokenizer, query, docs)
            per_query_latencies.append(
                round((time.perf_counter() - q_t0) * 1000, 2),
            )
        iteration_totals.append(
            round((time.perf_counter() - it_t0) * 1000, 2),
        )
        if it % 5 == 0 or it == 1:
            print(f"  iteration {it}/{iterations} — "
                  f"last total {iteration_totals[-1]}ms", flush=True)

    rss_after = _peak_rss_mb()

    # ── Aggregate ──────────────────────────────────────────────────────
    cell.update({
        "iterations": iterations,
        "queries_per_iteration": len(queries),
        "docs_per_query": len(docs),
        "per_query_latencies_ms": per_query_latencies,
        "iteration_totals_ms": iteration_totals,
        "p50_query_ms": round(statistics.median(per_query_latencies), 2),
        "p95_query_ms": round(
            statistics.quantiles(per_query_latencies, n=100, method="inclusive")[94], 2,
        ) if len(per_query_latencies) >= 100 else round(max(per_query_latencies), 2),
        "mean_query_ms": round(statistics.mean(per_query_latencies), 2),
        "min_query_ms": round(min(per_query_latencies), 2),
        "max_query_ms": round(max(per_query_latencies), 2),
        "p50_iteration_ms": round(statistics.median(iteration_totals), 2),
        "mean_iteration_ms": round(statistics.mean(iteration_totals), 2),
        "peak_rss_mb": round(max(rss_before, rss_after), 1),
    })

    print(f"  P50 query:  {cell['p50_query_ms']}ms", flush=True)
    print(f"  P95 query:  {cell['p95_query_ms']}ms", flush=True)
    print(f"  Mean query: {cell['mean_query_ms']}ms", flush=True)
    print(f"  Peak RSS:   {cell['peak_rss_mb']}MB", flush=True)

    return cell


def _save_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reranker CoreML/fp16 latency benchmark (Exp 15)",
    )
    parser.add_argument("--iterations", type=int, default=20,
                        help="Warm iterations per cell (default 20)")
    parser.add_argument("--cells", default="16A,16B,16C",
                        help="Comma-separated cell IDs to run (default all)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip cells already in checkpoint")
    args = parser.parse_args()

    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    workload = json.loads((SCRIPT_DIR / "workload.json").read_text(encoding="utf-8"))
    queries = workload["queries"]
    docs = _build_docs(workload["seed_texts"], workload["length_targets"])

    print(f"Workload: {len(queries)} queries × {len(docs)} docs "
          f"= {len(queries) * len(docs)} pairs/iteration", flush=True)
    print(f"Platform: {platform.platform()} | {platform.machine()}", flush=True)

    # Verify CoreML availability
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        print(f"ORT providers available: {available}", flush=True)
        if "CoreMLExecutionProvider" not in available:
            print("WARNING: CoreMLExecutionProvider not available — "
                  "16B will fall back to CPU.", flush=True)
    except ImportError:
        print("ERROR: onnxruntime not installed. Run `uv sync`.", flush=True)
        sys.exit(1)

    selected = {c.strip() for c in args.cells.split(",") if c.strip()}
    cells_to_run = [c for c in CELLS if c[0] in selected]

    checkpoint_path = output_dir / "eval_results_checkpoint.json"
    existing_cells: list[dict[str, Any]] = []
    if args.resume and checkpoint_path.exists():
        existing_cells = json.loads(
            checkpoint_path.read_text(encoding="utf-8"),
        ).get("cells", [])
        done = {c["cell_id"] for c in existing_cells}
        cells_to_run = [c for c in cells_to_run if c[0] not in done]
        print(f"Resume: {len(done)} cells already done, "
              f"{len(cells_to_run)} to run.", flush=True)

    all_cells = list(existing_cells)
    for cell_id, variant, providers, label in cells_to_run:
        cell = _measure_cell(
            cell_id, variant, providers, label,
            queries, docs, args.iterations,
        )
        all_cells.append(cell)
        # Strip non-serialisable session/tokenizer refs before saving.
        serialisable = {
            k: v for k, v in cell.items() if not k.startswith("_")
        }
        for i, c in enumerate(all_cells):
            all_cells[i] = {
                k: v for k, v in c.items() if not k.startswith("_")
            }
        payload = {
            "experiment": "16-reranker-coreml-fp16-2026-08-03",
            "model": MODEL_ID,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "iterations": args.iterations,
            "queries": len(queries),
            "docs_per_query": len(docs),
            "cells": all_cells,
        }
        _save_atomic(checkpoint_path, payload)
        print(f"  Checkpoint saved.", flush=True)

    final_path = output_dir / "eval_results.json"
    _save_atomic(final_path, payload)
    print(f"\nRaw results saved to {final_path}", flush=True)
    print(f"Checkpoint at {checkpoint_path}", flush=True)


if __name__ == "__main__":
    main()
