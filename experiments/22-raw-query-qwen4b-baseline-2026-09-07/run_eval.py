"""Experiment 22 cell runner: raw-query baseline, one cell per subprocess.

Usage:
    uv run python run_eval.py --cell dense_only__raw
    uv run python run_eval.py --cell hybrid__raw

Per cell (isolated process → isolated query-embedding cache and BM25
index state):

1. Load the deterministic filename→freshstack_id map from the corpus
   manifest (front matter is NOT preserved by omrg ingestion, so chunk
   file_name metadata is the only join key).
2. Load ground truth (223 queries, nugget qrels, categories).
3. For each query: ``pipeline.search(top_k=50, rerank=False,
   hybrid=<cell>)`` with injected EffectiveSettings; time each query;
   map retrieved rows to freshstack parent ids; checkpoint atomically
   after every query (``--resume`` skips completed query ids).

Ranked parent ids are recorded raw (duplicates included); metric code
deduplicates by first rank exactly as 9a's ``_rank_map`` did.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
GT_PATH = EXP_DIR / "output/ground-truth.json"
MANIFEST_PATH = EXP_DIR / "corpus/langchain_manifest.jsonl"
STORE_URI = EXP_DIR / "output/lancedb"
COLLECTION = "exp22"
TOP_K = 50

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

os.environ.update(
    {
        "LANCEDB_URI": str(STORE_URI),
        "VECTOR_STORE": "lancedb",
        "COLLECTION_NAME": COLLECTION,
        "EMBED_PROVIDER": "cloud",
        "CLOUD_BACKEND": "openrouter",
        "OPENROUTER_EMBED_MODEL": "qwen/qwen3-embedding-4b",
        "METADATA__EXTRACTION_MODE": "disabled",
        "PDF_READER": "pypdf",
    }
)

sys.path.insert(0, str(PROJECT_ROOT / "src"))

CELLS = {
    "dense_only__raw": {"hybrid": False},
    "hybrid__raw": {"hybrid": True},
}


def _load_parent_id_map() -> dict[str, str]:
    """filename → freshstack_id from the corpus manifest."""
    mapping: dict[str, str] = {}
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            mapping[Path(row["metadata"]["file_path"]).name] = row["freshstack_id"]
    return mapping


def _checkpoint_path(cell: str) -> Path:
    return EXP_DIR / "output/cells" / f"{cell}.json"


def _load_checkpoint(cell: str) -> dict:
    path = _checkpoint_path(cell)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"done": [], "rows": []}


def _save_checkpoint(cell: str, payload: dict) -> None:
    path = _checkpoint_path(cell)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def run_cell(cell: str) -> None:
    """Run one retrieval arm over all queries, checkpointing per query."""
    from omrg.compose import ensure_runtime_setup
    from omrg.core.retrieval import pipeline
    from omrg.core.settings import EffectiveSettings, RetrievalBlock
    from omrg.core.vectordb.lancedb import LanceVectorStore

    ensure_runtime_setup()
    store = LanceVectorStore(uri=str(STORE_URI))
    chunk_count = store.count(COLLECTION)
    if chunk_count == 0:
        raise SystemExit("store is empty; run build_index.py first")

    id_map = _load_parent_id_map()
    queries = json.loads(GT_PATH.read_text(encoding="utf-8"))["queries"]
    hybrid = CELLS[cell]["hybrid"]
    settings = EffectiveSettings(
        retrieval=RetrievalBlock(
            hybrid_enabled=hybrid,
            rerank_enabled=False,
            similarity_threshold=0.0,
        )
    )

    state = _load_checkpoint(cell)
    done = set(state["done"])
    print(
        f"[{cell}] store={chunk_count} chunks, queries={len(queries)}, resume skips {len(done)}",
        flush=True,
    )

    for entry in queries:
        if entry["query_id"] in done:
            continue
        started = time.perf_counter()
        results = pipeline.search(
            entry["query"],
            top_k=TOP_K,
            rerank=False,
            hybrid=hybrid,
            collection_name=COLLECTION,
            store=store,
            effective_settings=settings,
        )
        latency = time.perf_counter() - started
        parent_ids: list[str] = []
        for row in results:
            meta = row.get("metadata") or {}
            name = str(meta.get("file_name") or Path(str(row.get("source") or "")).name)
            freshstack_id = id_map.get(name)
            if freshstack_id:
                parent_ids.append(freshstack_id)
        state["rows"].append(
            {
                "query_id": entry["query_id"],
                "category": entry["category"],
                "parent_ids": parent_ids,
                "latency_s": round(latency, 4),
            }
        )
        state["done"].append(entry["query_id"])
        _save_checkpoint(cell, state)
        print(
            f"[{cell}] {entry['query_id']} rank1={parent_ids[0] if parent_ids else '-'} "
            f"({latency:.2f}s)",
            flush=True,
        )

    print(f"[{cell}] complete: {len(state['rows'])} queries", flush=True)


def main() -> None:
    """Parse --cell and run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--cell", choices=sorted(CELLS), required=True)
    args = parser.parse_args()
    run_cell(args.cell)


if __name__ == "__main__":
    main()
