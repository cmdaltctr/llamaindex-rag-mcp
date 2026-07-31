"""Record raw logit distributions for MiniLM vs gte-reranker.

Scores a sample of query-document pairs through each model's ONNX session
and records raw logits (before sigmoid normalisation) to assess whether
the ÷30 threshold scaling factor (ADR-021) needs recalibration.

Usage:
    uv run python experiments/15-gte-reranker-swap-2026-07-31/record_logits.py
"""

from __future__ import annotations

import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

MINILM_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
GTE_MODEL = "Alibaba-NLP/gte-reranker-modernbert-base"

# Number of query-document pairs to score per model.
SAMPLE_SIZE = 200


def _load_sample_pairs(gt_path: Path, n: int) -> list[tuple[str, str]]:
    """Load query-document pairs from the ground truth.

    Uses the query text and the first relevant document's ID to build
    pairs.  Falls back to query-only pairs if document text is unavailable.
    """
    data = json.loads(gt_path.read_text(encoding="utf-8"))
    pairs: list[tuple[str, str]] = []
    for query in data.get("queries", []):
        q_text = query.get("query", "")[:4000]
        # Use nugget text as the "document" side if available.
        for nugget in query.get("nuggets", []):
            doc_text = nugget.get("text") or nugget.get("answer") or q_text
            if doc_text:
                pairs.append((q_text, str(doc_text)[:4000]))
                if len(pairs) >= n:
                    return pairs
        # If no nuggets, use the query itself as a self-pair (low relevance).
        if not query.get("nuggets"):
            pairs.append((q_text, q_text))
            if len(pairs) >= n:
                return pairs
    return pairs[:n]


def _load_onnx_session(model_id: str) -> tuple[Any, Any, str]:
    """Load the ONNX session and tokenizer for a model.

    Returns (session, tokenizer, variant_filename).
    """
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from transformers import AutoTokenizer

    from rag_mcp.reranker import _select_onnx_variant

    candidates = _select_onnx_variant(model_id)
    onnx_path = None
    onnx_filename = None
    for candidate in candidates:
        try:
            onnx_path = hf_hub_download(repo_id=model_id, filename=candidate)
            onnx_filename = candidate
            break
        except Exception:
            continue

    if onnx_path is None:
        raise RuntimeError(f"No ONNX variant available for {model_id}")

    tokenizer = AutoTokenizer.from_pretrained(model_id)

    available = ort.get_available_providers()
    providers = []
    if "CoreMLExecutionProvider" in available:
        providers.append("CoreMLExecutionProvider")
    providers.append("CPUExecutionProvider")
    session = ort.InferenceSession(onnx_path, providers=providers)

    return session, tokenizer, onnx_filename or "unknown"


def _score_pairs(
    session: Any, tokenizer: Any, pairs: list[tuple[str, str]]
) -> list[float]:
    """Score query-document pairs and return raw logits."""
    import numpy as np

    BATCH_SIZE = 32
    all_logits: list[float] = []
    for i in range(0, len(pairs), BATCH_SIZE):
        batch = pairs[i : i + BATCH_SIZE]
        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=512,  # Use 512 for fair comparison (MiniLM max)
            return_tensors="np",
        )
        outputs = session.run(None, dict(encoded.items()))
        batch_logits = np.asarray(outputs[0]).flatten()
        all_logits.extend(float(v) for v in batch_logits)
    return all_logits


def _logit_stats(logits: list[float]) -> dict[str, float]:
    """Compute distribution statistics for raw logits."""
    if not logits:
        return {}
    sorted_logits = sorted(logits)
    n = len(sorted_logits)
    return {
        "n": n,
        "mean": round(statistics.mean(logits), 6),
        "stdev": round(statistics.stdev(logits), 6) if n > 1 else 0.0,
        "min": round(min(logits), 6),
        "max": round(max(logits), 6),
        "p5": round(sorted_logits[int(n * 0.05)], 6),
        "p25": round(sorted_logits[int(n * 0.25)], 6),
        "p50": round(statistics.median(logits), 6),
        "p75": round(sorted_logits[int(n * 0.75)], 6),
        "p95": round(sorted_logits[int(n * 0.95)], 6),
    }


def main() -> None:
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    gt_path = SCRIPT_DIR / "ground-truth.json"

    pairs = _load_sample_pairs(gt_path, SAMPLE_SIZE)
    print(f"Loaded {len(pairs)} query-document pairs", flush=True)

    results: dict[str, Any] = {
        "experiment": "15-gte-reranker-swap-2026-07-31",
        "sample_size": len(pairs),
        "max_length": 512,
        "hardware": {"platform": platform.platform()},
        "models": {},
    }

    for model_id in (MINILM_MODEL, GTE_MODEL):
        print(f"\nLoading model: {model_id}", flush=True)
        started = time.perf_counter()
        try:
            session, tokenizer, variant = _load_onnx_session(model_id)
            load_time = time.perf_counter() - started
            print(f"  Loaded (variant: {variant}, {load_time:.1f}s)", flush=True)

            print(f"  Scoring {len(pairs)} pairs...", flush=True)
            logits = _score_pairs(session, tokenizer, pairs)
            stats = _logit_stats(logits)
            stats["load_time_s"] = round(load_time, 2)
            stats["variant"] = variant
            results["models"][model_id] = stats

            print(f"  Mean={stats['mean']:.4f}, StdDev={stats['stdev']:.4f}", flush=True)
            print(
                f"  Range=[{stats['min']:.4f}, {stats['max']:.4f}], "
                f"P50={stats['p50']:.4f}",
                flush=True,
            )

        except Exception as exc:
            print(f"  ERROR: {exc}", flush=True)
            results["models"][model_id] = {"error": str(exc)}

    # Compute std dev ratio for threshold scaling assessment.
    minilm_stats = results["models"].get(MINILM_MODEL, {})
    gte_stats = results["models"].get(GTE_MODEL, {})
    minilm_std = minilm_stats.get("stdev", 0)
    gte_std = gte_stats.get("stdev", 0)
    if minilm_std > 0 and gte_std > 0:
        ratio = max(minilm_std, gte_std) / min(minilm_std, gte_std)
        results["std_dev_ratio"] = round(ratio, 4)
        results["recalibration_needed"] = ratio > 2.0
        print(
            f"\nStd dev ratio: {ratio:.4f} "
            f"({'RECALIBRATION NEEDED' if ratio > 2.0 else 'OK — within 2× tolerance'})",
            flush=True,
        )

    output_path = output_dir / "logit_distributions.json"
    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nLogit distributions saved to {output_path}", flush=True)


if __name__ == "__main__":
    main()
