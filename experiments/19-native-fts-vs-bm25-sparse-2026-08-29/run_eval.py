"""Experiment 19 cell runner: one sparse backend per subprocess.

Usage:
    python run_eval.py --cell bm25
    python run_eval.py --cell native

Per cell (isolated process → isolated BM25 class cache, FTS index
state, and peak-RSS measurement):

1. Load ground truth (Exp 9, 20 queries).
2. Open the experiment store built by ``build_index.py``.
3. Sparse-only passes: three passes of the 20 queries through the
   cell's registered sparse retriever — pass 1 is COLD (includes
   BM25 cache build or FTS index creation/refresh), passes 2 and 3
   are WARM (steady state). Pass 2 vs pass 3 doc-id sequences are
   the determinism check. Every query is individually timed.
4. Hybrid passes: ``pipeline.search(hybrid=True, rerank=False)`` with
   the cell's backend baked into injected EffectiveSettings, one
   warm pass (the sparse-only passes already paid the cold cost).
5. Memory: ``tracemalloc`` peak around the COLD first query, and the
   process-wide peak RSS at exit (``ru_maxrss``).

Output: ``output/cells/<cell>.json`` (atomic .tmp → rename).
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
import tracemalloc
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
GT_PATH = PROJECT_ROOT / "experiments/9-hybrid-retrieval-2026-05-27/ground-truth.json"
STORE_URI = EXP_DIR / "output/lancedb"
COLLECTION = "exp19"
TOP_K = 10

os.environ.update(
    {
        "LANCEDB_URI": str(STORE_URI),
        "VECTOR_STORE": "lancedb",
        "EMBED_PROVIDER": "ollama",
        "EMBED_MODEL": "qwen3-embedding:0.6b",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "METADATA__EXTRACTION_MODE": "disabled",
        "PDF_READER": "pypdf",
    }
)

sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _source_of(metadata: dict) -> str:
    """Match ground-truth ``expected_source`` against chunk lineage."""
    name = metadata.get("file_path") or metadata.get("file_name") or ""
    return str(name)


def _is_hit(source: str, expected: str) -> bool:
    """A chunk hits when it comes from the expected source file."""
    return Path(source).name == expected or expected in Path(source).name


def sparse_pass(retriever_cls, store) -> tuple[list[dict], list[float]]:
    """One pass over the query set through the sparse retriever only."""
    queries = json.loads(GT_PATH.read_text())["queries"]
    rows: list[dict] = []
    timings: list[float] = []
    for entry in queries:
        started = time.perf_counter()
        ranked = retriever_cls(COLLECTION, store=store).query(entry["query"], TOP_K)
        timings.append(time.perf_counter() - started)
        rows.append(
            {
                "query": entry["query"],
                "category": entry["category"],
                "expected_source": entry["expected_source"],
                "doc_ids": [doc_id for _rank, doc_id, _text, _meta in ranked],
                "sources": [_source_of(meta) for _r, _d, _t, meta in ranked],
            }
        )
    return rows, timings


def hybrid_pass(store, backend: str, embed_ready) -> list[dict]:
    """One warm hybrid pass through the real pipeline."""
    from omrg.core.retrieval import pipeline
    from omrg.core.settings import EffectiveSettings, RetrievalBlock

    queries = json.loads(GT_PATH.read_text())["queries"]
    settings = EffectiveSettings(
        retrieval=RetrievalBlock(
            hybrid_enabled=True,
            hybrid_sparse_backend=backend,
            rerank_enabled=False,
            similarity_threshold=0.0,
        )
    )
    rows: list[dict] = []
    for entry in queries:
        results = pipeline.search(
            entry["query"],
            top_k=TOP_K,
            rerank=False,
            hybrid=True,
            collection_name=COLLECTION,
            store=store,
            effective_settings=settings,
        )
        rows.append(
            {
                "query": entry["query"],
                "category": entry["category"],
                "expected_source": entry["expected_source"],
                "sources": [row.get("source") or "" for row in results],
            }
        )
    return rows


def run_cell(cell: str) -> None:
    """Run one backend cell and write its JSON atomically."""
    from omrg.compose import ensure_runtime_setup
    from omrg.core.retrieval.native_sparse import NativeSparseRetriever
    from omrg.core.retrieval.sparse import BM25SparseRetriever
    from omrg.core.vectordb.lancedb import LanceVectorStore

    ensure_runtime_setup()
    store = LanceVectorStore(uri=str(STORE_URI))
    chunk_count = store.count(COLLECTION)
    if chunk_count == 0:
        raise SystemExit(f"store at {STORE_URI} is empty; run build_index.py first")

    retriever_cls = {
        "bm25": BM25SparseRetriever,
        "native": NativeSparseRetriever,
    }[cell]
    print(f"[{cell}] store ready ({chunk_count} chunks); cold sparse pass...", flush=True)

    tracemalloc.start()
    cold_rows, cold_timings = sparse_pass(retriever_cls, store)
    tracemalloc_peak_mb = tracemalloc.get_traced_memory()[1] / (1024 * 1024)
    tracemalloc.stop()

    warm_rows, warm_timings = sparse_pass(retriever_cls, store)
    determinism_rows, _ = sparse_pass(retriever_cls, store)
    determinism_mismatches = sum(
        1
        for warm, again in zip(warm_rows, determinism_rows, strict=True)
        if warm["doc_ids"] != again["doc_ids"]
    )

    print(f"[{cell}] hybrid pass...", flush=True)
    hybrid_rows = hybrid_pass(store, cell, embed_ready=None)

    peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
        1024 * 1024 if sys.platform == "darwin" else 1024
    )
    payload = {
        "cell": cell,
        "chunk_count": chunk_count,
        "top_k": TOP_K,
        "sparse": {
            "cold": {"rows": cold_rows, "timings_s": cold_timings},
            "warm": {"rows": warm_rows, "timings_s": warm_timings},
            "determinism_mismatches": determinism_mismatches,
        },
        "hybrid": {"rows": hybrid_rows},
        "memory": {
            "tracemalloc_cold_peak_mb": round(tracemalloc_peak_mb, 2),
            "peak_rss_mb": round(peak_rss_mb, 2),
        },
    }
    out = EXP_DIR / "output/cells" / f"{cell}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(out)
    print(
        f"[{cell}] wrote {out} (rss {peak_rss_mb:.0f} MB, mismatches {determinism_mismatches})",
        flush=True,
    )


def main() -> None:
    """Parse --cell and run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--cell", choices=["bm25", "native"], required=True)
    args = parser.parse_args()
    run_cell(args.cell)


if __name__ == "__main__":
    main()
