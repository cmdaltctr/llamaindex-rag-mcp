# Eval Runner Pattern

Use this as the canonical structure for `experiments/<id>/run_eval.py`.

## Core requirements

- Import project source with `sys.path.insert(0, str(PROJECT_ROOT / "src"))`
- Load `.env` from repo root
- Read ground truth before running; validate corpus size/evidence density
- Evaluate a cell matrix, not ad-hoc runs
- Save raw per-query rows with metrics, latency, parent IDs, and diagnostics
- Save `eval_results_checkpoint.json` atomically after each completed cell
- Support `--resume` and skip completed cells
- Clear caches between cells

## Skeleton

```python
from __future__ import annotations

import argparse
import inspect
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _load_ground_truth(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    # Validate before running to avoid invalid conclusions.
    if not data.get("queries"):
        raise SystemExit(f"No queries in {path}")
    return data
```

## Environment setup per cell

Patch both environment variables and already-imported module globals.

```python
def _setup_environment(mode: str, chroma_dir: Path) -> None:
    if mode == "dense-only":
        os.environ["HYBRID_ENABLED"] = "false"
    elif mode == "hybrid_bm25":
        os.environ["HYBRID_ENABLED"] = "true"
        os.environ["HYBRID_SPARSE_BACKEND"] = "bm25"
    else:
        raise ValueError(f"unknown mode: {mode}")

    os.environ["CHROMA_PERSIST_DIR"] = str(chroma_dir)

    for mod_name in ("rag_mcp.config", "rag_mcp.retrieval", "rag_mcp.ingestion"):
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        if hasattr(mod, "CHROMA_PERSIST_DIR"):
            mod.CHROMA_PERSIST_DIR = str(chroma_dir)
        if hasattr(mod, "HYBRID_ENABLED"):
            mod.HYBRID_ENABLED = mode != "dense-only"

    try:
        from rag_mcp.retrieval import _cached_query_embedding
        _cached_query_embedding.cache_clear()
    except Exception:
        pass
```

## Cell evaluation

```python
def _evaluate_cell(
    *,
    mode: str,
    rerank: bool,
    chroma_dir: Path,
    queries: list[dict[str, Any]],
    top_k: int,
) -> dict[str, Any]:
    import rag_mcp.retrieval as retrieval

    _setup_environment(mode, chroma_dir)
    per_query: list[dict[str, Any]] = []

    for index, query in enumerate(queries, start=1):
        started = time.perf_counter()
        results = retrieval.search(
            query=query["query"],
            top_k=top_k,
            similarity_threshold=0.0,
            rerank=rerank,
            hybrid=mode != "dense-only",
            include_diagnostics=True,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        parent_ids = [_parent_id(result) for result in results]
        per_query.append({
            "query_index": index,
            "query_id": query.get("query_id", str(index)),
            "category": query.get("category"),
            "latency_ms": round(latency_ms, 2),
            "metrics": _metrics_for_query(parent_ids, query),
            "top_results": _top_results(results, top_k),
        })
```

```python
        if index % 25 == 0 or index == len(queries):
            print(f"    {mode}/rerank={rerank}: {index}/{len(queries)} queries", flush=True)

    latencies = [row["latency_ms"] for row in per_query]
    p95 = statistics.quantiles(latencies, n=100, method="inclusive")[94] if latencies else 0.0
    return {
        "mode": mode,
        "rerank": rerank,
        "chroma_dir": str(chroma_dir),
        "mean_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p50_latency_ms": round(statistics.median(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(p95, 2),
        "queries": per_query,
    }
```

## Checkpoint / resume

```python
def _cell_key(mode: str, rerank: bool) -> str:
    return f"{mode}__rerank_{str(rerank).lower()}"


def _load_checkpoint(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cells = data.get("cells", [])
        return cells if isinstance(cells, list) else []
    except Exception as exc:
        print(f"Ignoring unreadable checkpoint {path}: {exc}", flush=True)
        return []
```

```python
def _save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)
```

Call `_save_checkpoint()` after every cell, not just at the end.

## Main loop

```python
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, default=SCRIPT_DIR)
    parser.add_argument("--modes", default="dense-only,hybrid_bm25")
    parser.add_argument("--rerank-cross", action="store_true")
    parser.add_argument("--k-values", nargs="+", type=int, default=[5, 10, 20, 50])
    parser.add_argument("--limit-queries", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    exp_dir = args.experiment_dir.resolve()
    output_dir = exp_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    gt_path = output_dir / "ground-truth.json"
    if not gt_path.exists():
        gt_path = exp_dir / "ground-truth.json"
    ground_truth = _load_ground_truth(gt_path)
    queries = ground_truth["queries"][: args.limit_queries]
```

```python
    top_k = max(args.k_values)
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    rerank_settings = [False, True] if args.rerank_cross else [True]

    import rag_mcp.retrieval as retrieval
    if "hybrid" not in inspect.signature(retrieval.search).parameters:
        raise RuntimeError("retrieval.search does not expose the hybrid parameter")

    checkpoint_path = output_dir / "eval_results_checkpoint.json"
    output_path = output_dir / "eval_results.json"
    cells = _load_checkpoint(checkpoint_path) if args.resume and not args.no_resume else []
    completed = {_cell_key(c["mode"], c["rerank"]) for c in cells}

    for mode in modes:
        chroma_dir = output_dir / f"chroma_{mode.replace('-', '_')}"
        if not chroma_dir.exists():
            raise SystemExit(f"Missing Chroma index for {mode}: {chroma_dir}")
        for rerank in rerank_settings:
            key = _cell_key(mode, rerank)
            if key in completed:
                print(f"Skipping completed cell from checkpoint: {key}", flush=True)
                continue
            print(f"Evaluating mode={mode}, rerank={rerank}, top_k={top_k}", flush=True)
            cells.append(_evaluate_cell(mode=mode, rerank=rerank, chroma_dir=chroma_dir, queries=queries, top_k=top_k))
            completed.add(key)
            payload = _result_payload(ground_truth=ground_truth, modes=modes, rerank_settings=rerank_settings, k_values=args.k_values, top_k=top_k, cells=cells)
            _save_checkpoint(checkpoint_path, payload)
            print(f"Checkpoint saved to {checkpoint_path}", flush=True)

    result = _result_payload(ground_truth=ground_truth, modes=modes, rerank_settings=rerank_settings, k_values=args.k_values, top_k=top_k, cells=cells)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Raw eval results saved to {output_path}")
```
