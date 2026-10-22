#!/usr/bin/env python3
"""Experiment 17: Reranker MPS vs ONNX CPU latency.

Coordinator spawns a fresh child process per cell x repetition to isolate
ONNX Runtime state (Experiment 16 finding) and MPS memory.

Cells:
  17A: production CrossEncoderReranker (ONNX CPU) -- baseline
  17B: torch CrossEncoder adapter, device="cpu"    -- torch control
  17C: torch CrossEncoder adapter, device="mps"    -- MPS candidate

See protocol.md for hypotheses, pass gates, and interpretation rules.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

MODEL_ID = "cross-encoder/ms-marco-MiniLM-L-6-v2"
BATCH_SIZE = 32
DEFAULT_REPETITIONS = 3
DEFAULT_ITERATIONS = 5


# ── Pure functions (tested by test_gates.py) ──────────────────────────


def repetition_key(cell_id: str, rep: int) -> str:
    """Checkpoint key for a cell repetition."""
    return f"{cell_id}_rep{rep}"


def rankings_match(r1: list[list[int]], r2: list[list[int]]) -> bool:
    """True if two ranking sets are identical (same queries, same order)."""
    if len(r1) != len(r2):
        return False
    return all(a == b for a, b in zip(r1, r2, strict=True))


def evaluate_gates(cell_a: dict, cell_b: dict, cell_c: dict) -> dict:
    """Evaluate H1 to H5 pass gates from aggregated cell data.

    Uses the design.md threshold definitions. All gates require H1 (MPS
    usable) to pass, since comparing MPS metrics is meaningless if MPS
    was not selected.
    """
    h1 = cell_c.get("loaded", False) and cell_c.get("selected_device") == "mps"

    c_p50 = cell_c.get("p50_query_ms")
    b_p50 = cell_b.get("p50_query_ms")
    h2 = h1 and c_p50 is not None and b_p50 is not None and c_p50 <= 0.8 * b_p50

    a_p50 = cell_a.get("p50_query_ms")
    c_p95 = cell_c.get("p95_query_ms")
    a_p95 = cell_a.get("p95_query_ms")
    h3 = (
        h1
        and c_p50 is not None
        and a_p50 is not None
        and c_p95 is not None
        and a_p95 is not None
        and c_p50 <= 0.8 * a_p50
        and c_p95 <= a_p95
    )

    a_cold = cell_a.get("cold_start_s", 0)
    a_rss = cell_a.get("peak_rss_mb", 0)
    c_cold = cell_c.get("cold_start_s", float("inf"))
    c_rss = cell_c.get("peak_rss_mb", float("inf"))
    h4 = h1 and c_cold <= 3 * a_cold and c_rss <= 2 * a_rss

    h5 = (
        h1
        and rankings_match(
            cell_b.get("rankings", []),
            cell_c.get("rankings", []),
        )
        and rankings_match(
            cell_a.get("rankings", []),
            cell_c.get("rankings", []),
        )
    )

    all_pass = all([h1, h2, h3, h4, h5])
    return {
        "H1": {"pass": h1, "criterion": "17C loads, selects MPS, no fallback"},
        "H2": {"pass": h2, "criterion": "17C P50 <= 0.8 * 17B P50"},
        "H3": {"pass": h3, "criterion": "17C P50 <= 0.8 * 17A P50 and 17C P95 <= 17A P95"},
        "H4": {"pass": h4, "criterion": "17C cold <= 3x 17A and RSS <= 2x 17A"},
        "H5": {"pass": h5, "criterion": "17B==17C rankings and 17A==17C rankings"},
        "overall": {
            "pass": all_pass,
            "verdict": "PASS" if all_pass else "FAIL",
        },
    }


def aggregate_repetitions(reps: list[dict]) -> dict:
    """Aggregate repetition results into a cell summary using medians."""
    if not reps:
        raise ValueError("No repetitions to aggregate")
    successful = [r for r in reps if r.get("loaded", False)]
    if not successful:
        successful = reps  # use all if none loaded (for error reporting)

    def _median(key: str) -> float | None:
        vals = [r[key] for r in successful if key in r and r[key] is not None]
        return round(statistics.median(vals), 2) if vals else None

    agg = {
        "cell_id": reps[0].get("cell_id"),
        "backend": reps[0].get("backend"),
        "num_repetitions": len(reps),
        "num_successful": len(successful),
        "loaded": any(r.get("loaded", False) for r in reps),
        "selected_device": successful[0].get("selected_device") if successful else None,
        "p50_query_ms": _median("p50_query_ms"),
        "p95_query_ms": _median("p95_query_ms"),
        "cold_start_s": _median("cold_start_s"),
        "peak_rss_mb": _median("peak_rss_mb"),
        "rankings": successful[0].get("rankings", []) if successful else [],
        "scores": successful[0].get("scores", []) if successful else [],
        "repetition_p50s": [r.get("p50_query_ms") for r in reps],
    }
    # Preserve fields from first successful rep
    for key in (
        "mps_current_allocated_mb",
        "mps_driver_allocated_mb",
        "onnx_variant",
        "versions",
        "hardware",
        "effective_max_length",
        "per_query_latencies_ms",
    ):
        if key in successful[0]:
            agg[key] = successful[0][key]
    return agg


def assert_device(result: dict, expected: str) -> None:
    """Assert that a cell result used the expected device."""
    actual = result["selected_device"]
    if actual != expected:
        raise AssertionError(
            f"Device assertion failed: expected {expected}, got {actual}",
        )


def get_completed_reps(checkpoint_dir: Path) -> set[str]:
    """Return set of completed repetition keys from checkpoint files."""
    if not checkpoint_dir.exists():
        return set()
    return {f.stem for f in checkpoint_dir.glob("*.json")}


def save_repetition_result(
    checkpoint_dir: Path,
    key: str,
    data: dict,
) -> None:
    """Save a repetition result atomically."""
    _save_atomic(checkpoint_dir / f"{key}.json", data)


# ── Internal helpers ──────────────────────────────────────────────────


def _save_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_val = math.exp(value)
    return exp_val / (1.0 + exp_val)


def _peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return rss / (1024 * 1024)
    return rss / 1024


def _build_docs(seed_texts: list[str], length_targets: list[dict]) -> list[str]:
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


def _hardware_info() -> dict[str, str]:
    info: dict[str, str] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
    }
    if sys.platform == "darwin":
        info["macos_version"] = platform.mac_ver()[0]
        try:
            info["chip"] = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                text=True,
            ).strip()
        except Exception:
            info["chip"] = "unknown"
        try:
            mem_bytes = int(
                subprocess.check_output(
                    ["sysctl", "-n", "hw.memsize"],
                    text=True,
                ).strip()
            )
            info["memory_gb"] = f"{mem_bytes / (1024**3):.0f}"
        except Exception:
            pass
    return info


def _record_versions(backend: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    try:
        if backend in ("onnx", "all"):
            import onnxruntime as ort

            versions["onnxruntime"] = ort.__version__
        if backend in ("torch", "all"):
            import torch

            versions["torch"] = torch.__version__
            import sentence_transformers

            versions["sentence_transformers"] = sentence_transformers.__version__
    except ImportError:
        pass
    try:
        import tokenizers

        versions["tokenizers"] = tokenizers.__version__
    except ImportError:
        pass
    return versions


# ── Cell implementations (heavy deps imported lazily) ─────────────────


def run_cell_17a(
    queries: list[str],
    docs: list[str],
    iterations: int,
) -> dict[str, Any]:
    """Cell 17A: production ONNX reranker on CPU."""
    from omrg.core.retrieval._model_config import read_max_position_embeddings
    from omrg.core.retrieval._reranker_cache import reset_model_cache
    from omrg.core.retrieval.reranker import (
        TOKENIZER_MAX_LENGTH,
        CrossEncoderReranker,
        _select_onnx_variant,
    )

    reset_model_cache()
    model_max = read_max_position_embeddings(MODEL_ID, TOKENIZER_MAX_LENGTH)
    effective_max_length = min(TOKENIZER_MAX_LENGTH, model_max)

    # Resolve ONNX variant
    onnx_variant = None
    for candidate in _select_onnx_variant(MODEL_ID):
        try:
            from huggingface_hub import hf_hub_download

            hf_hub_download(repo_id=MODEL_ID, filename=candidate)
            onnx_variant = candidate
            break
        except Exception:
            pass

    # Cold start: cached construction + first load
    t0 = time.perf_counter()
    reranker = CrossEncoderReranker(
        model_id=MODEL_ID,
        tokenizer_max_length=effective_max_length,
    )
    warmup_results = [{"text": docs[0], "score": 0.0, "_doc_idx": 0}]
    reranker.rerank(queries[0], warmup_results, top_k=1)
    cold_start = round(time.perf_counter() - t0, 3)

    # Warm-up (discarded)
    full = [{"text": d, "score": 0.0, "_doc_idx": i} for i, d in enumerate(docs)]
    reranker.rerank(queries[0], [r.copy() for r in full], top_k=len(docs))

    # Timed iterations
    per_query_latencies: list[float] = []
    iteration_totals: list[float] = []
    rankings: list[list[int]] = []
    scores: list[list[float]] = []

    for it in range(iterations):
        it_t0 = time.perf_counter()
        it_rankings: list[list[int]] = []
        it_scores: list[list[float]] = []
        for query in queries:
            q_t0 = time.perf_counter()
            results = [{"text": d, "score": 0.0, "_doc_idx": i} for i, d in enumerate(docs)]
            reranked = reranker.rerank(query, results, top_k=len(docs))
            per_query_latencies.append(round((time.perf_counter() - q_t0) * 1000, 2))
            it_rankings.append([r["_doc_idx"] for r in reranked])
            it_scores.append([round(r["score"], 6) for r in reranked])
        iteration_totals.append(round((time.perf_counter() - it_t0) * 1000, 2))
        if it == 0:
            rankings = it_rankings
            scores = it_scores

    return {
        "cell_id": "17A",
        "backend": "onnx",
        "requested_device": "cpu",
        "selected_device": "cpu",
        "loaded": True,
        "model_id": MODEL_ID,
        "onnx_variant": onnx_variant,
        "effective_max_length": effective_max_length,
        "cold_start_s": cold_start,
        "per_query_latencies_ms": per_query_latencies,
        "iteration_totals_ms": iteration_totals,
        "rankings": rankings,
        "scores": scores,
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "versions": _record_versions("onnx"),
        "hardware": _hardware_info(),
    }


def run_cell_torch(
    queries: list[str],
    docs: list[str],
    device: str,
    cell_id: str,
    iterations: int,
) -> dict[str, Any]:
    """Cell 17B/17C: torch CrossEncoder adapter with explicit device."""
    # Must be set before torch import — called from child process
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"

    import torch  # noqa: F811
    from sentence_transformers import CrossEncoder

    from omrg.core.retrieval._model_config import read_max_position_embeddings
    from omrg.core.retrieval.reranker import TOKENIZER_MAX_LENGTH

    model_max = read_max_position_embeddings(MODEL_ID, TOKENIZER_MAX_LENGTH)
    effective_max_length = min(TOKENIZER_MAX_LENGTH, model_max)

    # Verify MPS availability before constructing
    if device == "mps":
        if not torch.backends.mps.is_built():
            return _fail(cell_id, device, "torch.backends.mps.is_built() is False")
        if not torch.backends.mps.is_available():
            return _fail(cell_id, device, "torch.backends.mps.is_available() is False")

    # Cold start: cached construction + first predict
    t0 = time.perf_counter()
    cross_encoder = CrossEncoder(
        MODEL_ID,
        max_length=effective_max_length,
        device=device,
    )
    # Verify selected device (CrossEncoder.device replaces deprecated _target_device)
    selected = str(getattr(cross_encoder, "device", None) or cross_encoder._target_device)
    if device == "mps" and "mps" not in selected:
        return _fail(cell_id, device, f"Expected mps, CrossEncoder selected {selected}")
    # First predict triggers model loading and device transfer
    cross_encoder.predict(
        [(queries[0], docs[0])],
        activation_fn=torch.nn.Identity(),
        convert_to_numpy=True,
    )
    cold_start = round(time.perf_counter() - t0, 3)

    # Warm-up (discarded)
    cross_encoder.predict(
        [(queries[0], doc) for doc in docs[:5]],
        activation_fn=torch.nn.Identity(),
        convert_to_numpy=True,
    )

    # Timed iterations
    per_query_latencies: list[float] = []
    iteration_totals: list[float] = []
    rankings: list[list[int]] = []
    scores: list[list[float]] = []

    for it in range(iterations):
        it_t0 = time.perf_counter()
        it_rankings: list[list[int]] = []
        it_scores: list[list[float]] = []
        for query in queries:
            pairs = [(query, doc) for doc in docs]

            if device == "mps":
                torch.mps.synchronize()
            q_t0 = time.perf_counter()
            raw_logits = cross_encoder.predict(
                pairs,
                activation_fn=torch.nn.Identity(),
                convert_to_numpy=True,
            )
            if device == "mps":
                torch.mps.synchronize()
            per_query_latencies.append(round((time.perf_counter() - q_t0) * 1000, 2))

            cell_scores = [_sigmoid(float(v)) for v in raw_logits]
            ranked = sorted(range(len(cell_scores)), key=lambda i: cell_scores[i], reverse=True)
            it_rankings.append(ranked)
            it_scores.append([round(s, 6) for s in cell_scores])
        iteration_totals.append(round((time.perf_counter() - it_t0) * 1000, 2))
        if it == 0:
            rankings = it_rankings
            scores = it_scores

    result: dict[str, Any] = {
        "cell_id": cell_id,
        "backend": "torch",
        "requested_device": device,
        "selected_device": "mps" if "mps" in selected else selected,
        "loaded": True,
        "model_id": MODEL_ID,
        "effective_max_length": effective_max_length,
        "cold_start_s": cold_start,
        "per_query_latencies_ms": per_query_latencies,
        "iteration_totals_ms": iteration_totals,
        "rankings": rankings,
        "scores": scores,
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "versions": _record_versions("torch"),
        "hardware": _hardware_info(),
    }

    if device == "mps":
        try:
            result["mps_current_allocated_mb"] = round(
                torch.mps.current_allocated_memory() / (1024 * 1024),
                1,
            )
            result["mps_driver_allocated_mb"] = round(
                torch.mps.driver_allocated_memory() / (1024 * 1024),
                1,
            )
        except Exception:
            pass

    return result


def run_preflight(queries: list[str], docs: list[str]) -> dict[str, Any]:
    """Untimed preflight: verify which device SentenceTransformerReranker selects."""
    from omrg.core.retrieval._reranker_cache import reset_model_cache
    from omrg.core.retrieval.reranker_torch import SentenceTransformerReranker

    reset_model_cache()
    reranker = SentenceTransformerReranker(model_id=MODEL_ID)
    results = [{"text": docs[0], "score": 0.0}]
    reranker.rerank(queries[0], results, top_k=1)

    # Inspect the cached CrossEncoder's device
    from omrg.core.retrieval._reranker_cache import _MODEL_CACHE

    cached = _MODEL_CACHE.get(("torch", MODEL_ID))
    selected = "unknown"
    if cached:
        ce = cached[0]
        selected = str(getattr(ce, "device", None) or getattr(ce, "_target_device", "unknown"))

    return {
        "cell_id": "PREFLIGHT",
        "loaded": reranker._loaded,
        "selected_device": "mps" if "mps" in selected else selected,
        "versions": _record_versions("torch"),
    }


def _fail(cell_id: str, device: str, error: str) -> dict[str, Any]:
    return {
        "cell_id": cell_id,
        "backend": "torch",
        "requested_device": device,
        # "none" rather than the requested device: the device was never
        # actually selected, so reporting it would mislead manual inspection.
        "selected_device": "none",
        "loaded": False,
        "load_error": error,
        "model_id": MODEL_ID,
    }


# ── Coordinator / child dispatch ──────────────────────────────────────


def _compute_stats(latencies: list[float]) -> dict[str, float]:
    if not latencies:
        return {"p50": 0, "p95": 0, "mean": 0, "min": 0, "max": 0}
    return {
        "p50": round(statistics.median(latencies), 2),
        "p95": round(
            statistics.quantiles(latencies, n=100, method="inclusive")[94],
            2,
        )
        if len(latencies) >= 100
        else round(max(latencies), 2),
        "mean": round(statistics.mean(latencies), 2),
        "min": round(min(latencies), 2),
        "max": round(max(latencies), 2),
    }


def _finalize_result(raw: dict) -> dict:
    """Add computed stats to a raw repetition result."""
    if not raw.get("loaded"):
        return raw
    latencies = raw.get("per_query_latencies_ms", [])
    stats = _compute_stats(latencies)
    raw["p50_query_ms"] = stats["p50"]
    raw["p95_query_ms"] = stats["p95"]
    raw["mean_query_ms"] = stats["mean"]
    raw["min_query_ms"] = stats["min"]
    raw["max_query_ms"] = stats["max"]
    return raw


def _spawn_child(
    cell_id: str,
    rep: int,
    iterations: int,
    output_dir: Path,
) -> None:
    """Spawn a child process for one cell repetition."""
    cmd = [
        sys.executable,
        "-u",
        str(SCRIPT_DIR / "run_eval.py"),
        "--child",
        "--cell",
        cell_id,
        "--rep",
        str(rep),
        "--iterations",
        str(iterations),
    ]
    print(f"  Spawning {cell_id} rep {rep}...", flush=True)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        print(f"  CHILD TIMED OUT {cell_id} rep {rep} (600s)", flush=True)
        checkpoint_dir = output_dir / "checkpoint"
        save_repetition_result(
            checkpoint_dir,
            repetition_key(cell_id, rep),
            {
                "cell_id": cell_id,
                "repetition": rep,
                "loaded": False,
                "load_error": "Child process timed out after 600s",
            },
        )
        return
    if result.returncode != 0:
        print(f"  CHILD FAILED {cell_id} rep {rep}: {result.stderr[:300]}", flush=True)
        checkpoint_dir = output_dir / "checkpoint"
        save_repetition_result(
            checkpoint_dir,
            repetition_key(cell_id, rep),
            {
                "cell_id": cell_id,
                "repetition": rep,
                "loaded": False,
                "load_error": result.stderr[:500],
            },
        )


def _merge_and_evaluate(
    checkpoint_dir: Path,
    repetitions: int,
    iterations: int,
) -> None:
    """Load all checkpoint files, aggregate, evaluate gates, save merged."""
    all_results: dict[str, dict] = {}
    for f in sorted(checkpoint_dir.glob("*.json")):
        try:
            all_results[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  Warning: could not read {f.name}: {exc}", flush=True)

    # Preflight
    preflight = all_results.get("PREFLIGHT_rep0", {})

    # Aggregate cells
    cells_data: dict[str, dict] = {}
    for cell_id in ("17A", "17B", "17C"):
        reps = []
        for rep in range(1, repetitions + 1):
            key = repetition_key(cell_id, rep)
            if key in all_results:
                reps.append(_finalize_result(all_results[key]))
        if reps:
            cells_data[cell_id] = aggregate_repetitions(reps)

    cell_a = cells_data.get("17A", {})
    cell_b = cells_data.get("17B", {})
    cell_c = cells_data.get("17C", {})
    gates = evaluate_gates(cell_a, cell_b, cell_c)

    output = {
        "experiment": "17-reranker-mps-vs-onnx-cpu-2026-08-11",
        "model": MODEL_ID,
        "repetitions": repetitions,
        "iterations": iterations,
        "batch_size": BATCH_SIZE,
        "cells": cells_data,
        "gates": gates,
        "preflight": preflight,
    }
    output_path = SCRIPT_DIR / "output" / "eval_results.json"
    _save_atomic(output_path, output)
    summary_path = SCRIPT_DIR / "output" / "eval_results.summary.json"
    _save_atomic(summary_path, {"gates": gates, "preflight": preflight})
    print(f"\nResults saved to {output_path}", flush=True)
    print(f"Summary saved to {summary_path}", flush=True)
    print(f"\nVerdict: {gates['overall']['verdict']}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 17 runner")
    parser.add_argument("--child", action="store_true", help="Run as child process")
    parser.add_argument("--cell", help="Cell ID (child mode)")
    parser.add_argument("--rep", type=int, default=0, help="Repetition number (child mode)")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--cells", default="17A,17B,17C")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    workload = json.loads((SCRIPT_DIR / "workload.json").read_text(encoding="utf-8"))
    queries = workload["queries"]
    docs = _build_docs(workload["seed_texts"], workload["length_targets"])

    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = output_dir / "checkpoint"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # ── Child mode ─────────────────────────────────────────────────
    if args.child:
        print(f"Child: cell={args.cell} rep={args.rep}", flush=True)
        if args.cell == "17A":
            result = run_cell_17a(queries, docs, args.iterations)
        elif args.cell in ("17B", "17C"):
            device = "cpu" if args.cell == "17B" else "mps"
            result = run_cell_torch(queries, docs, device, args.cell, args.iterations)
        elif args.cell == "PREFLIGHT":
            result = run_preflight(queries, docs)
        else:
            raise ValueError(f"Unknown cell: {args.cell}")
        result["repetition"] = args.rep
        result = _finalize_result(result)
        key = repetition_key(args.cell, args.rep)
        save_repetition_result(checkpoint_dir, key, result)
        print(f"  Saved {key}", flush=True)
        return

    # ── Coordinator mode ───────────────────────────────────────────
    cells = [c.strip() for c in args.cells.split(",") if c.strip()]
    all_pairs = [(cell, rep) for cell in cells for rep in range(1, args.repetitions + 1)]

    if args.resume:
        completed = get_completed_reps(checkpoint_dir)
        to_run = [(c, r) for c, r in all_pairs if repetition_key(c, r) not in completed]
        print(f"Resume: {len(completed)} done, {len(to_run)} to run", flush=True)
    else:
        to_run = all_pairs

    # Preflight (untimed, always runs once)
    if repetition_key("PREFLIGHT", 0) not in get_completed_reps(checkpoint_dir):
        print("\nRunning untimed preflight...", flush=True)
        _spawn_child("PREFLIGHT", 0, 0, output_dir)

    # Run cell repetitions
    for cell_id, rep in to_run:
        _spawn_child(cell_id, rep, args.iterations, output_dir)

    # Merge and evaluate
    _merge_and_evaluate(checkpoint_dir, args.repetitions, args.iterations)


if __name__ == "__main__":
    main()
