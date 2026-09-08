"""Experiment 25 evaluation runner: candidate model-token chunking cell.

Usage:
    uv run --no-sync python run_eval.py

Adapted from Experiment 22's runner with the metric-relevant behaviour
kept identical (same 223 queries, raw query text, hybrid retrieval,
top_k 50, rerank disabled, latency measured around ``pipeline.search``
with ``time.perf_counter``, no warm-up pass). Only the store differs:
this runner points at the Experiment 25 candidate index
(``exp25_model_token``), built by ``build_index.py``.

The baseline arm is NOT re-run: Experiment 22's ``hybrid__raw``
checkpoint is reused by ``summarise_eval.py`` (loaded, not executed).

Transient-provider handling: OpenRouter's free-tier embedding endpoint
returns HTTP 429 "engine_overloaded" for minutes at a time. Each query's
``pipeline.search`` is retried inside the process with exponential
backoff (429/rate-limit text only, bounded attempts) so one busy period
does not waste the ~1-minute BM25 warm-up a fresh process re-pays.
Latency is measured around the successful attempt only, exactly as
Experiment 22 measured its (never-failing) searches.

Checkpoint/resume is automatic: per-query results are appended to
``output/cells/model_token_markdown.json`` with tmp-then-rename atomic
writes, so an interrupted run resumes at the first missing query.
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
# Ground truth is frozen in Experiment 22's output (read-only reuse).
GT_PATH = EXP_DIR.parent / "22-raw-query-qwen4b-baseline-2026-09-07/output/ground-truth.json"
MANIFEST_PATH = EXP_DIR / "corpus/langchain_manifest.jsonl"
STORE_URI = EXP_DIR / "output/lancedb"
COLLECTION = "exp25_model_token"
CELL = "model_token_markdown"
TOP_K = 50
TRANSIENT_MARKERS = ("429", "ratelimit", "rate limit", "engine_overloaded", "model busy")
MAX_TRANSIENT_ATTEMPTS = 15

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


def _load_parent_id_map() -> dict[str, str]:
    """filename → freshstack_id from the corpus manifest."""
    mapping: dict[str, str] = {}
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            mapping[Path(row["metadata"]["file_path"]).name] = row["freshstack_id"]
    return mapping


def _checkpoint_path() -> Path:
    return EXP_DIR / "output/cells" / f"{CELL}.json"


def _load_checkpoint() -> dict:
    path = _checkpoint_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"done": [], "rows": []}


def _save_checkpoint(payload: dict) -> None:
    path = _checkpoint_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _is_transient(exc: BaseException) -> bool:
    """True when the error text indicates provider congestion (429 family)."""
    text = str(exc).lower()
    return any(marker in text for marker in TRANSIENT_MARKERS)


def _search_with_transient_retry(entry: dict, settings, store) -> tuple[list[dict], float]:
    """Run one query, retrying 429-family failures with backoff.

    Returns the results and the wall time of the successful attempt
    only (same measurement point as Experiment 22's runner).
    """
    from omrg.core.retrieval import pipeline

    last_exc: BaseException | None = None
    for attempt in range(1, MAX_TRANSIENT_ATTEMPTS + 1):
        import time as _time

        started = _time.perf_counter()
        try:
            results = pipeline.search(
                entry["query"],
                top_k=TOP_K,
                rerank=False,
                hybrid=True,
                collection_name=COLLECTION,
                store=store,
                effective_settings=settings,
            )
            return results, _time.perf_counter() - started
        except Exception as exc:  # noqa: BLE001 - classified below
            if not _is_transient(exc):
                raise
            last_exc = exc
            delay = min(30 * 2 ** (attempt - 1), 600)
            print(
                f"[{CELL}] transient 429 on {entry['query_id']} (attempt "
                f"{attempt}/{MAX_TRANSIENT_ATTEMPTS}); backing off {delay}s",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(
        f"transient retries exhausted for query {entry['query_id']}"
    ) from last_exc


def run_cell() -> None:
    """Run the candidate retrieval arm over all queries, checkpointing per query."""
    from omrg.compose import ensure_runtime_setup
    from omrg.core.settings import EffectiveSettings, RetrievalBlock
    from omrg.core.vectordb.lancedb import LanceVectorStore

    ensure_runtime_setup()
    store = LanceVectorStore(uri=str(STORE_URI))
    chunk_count = store.count(COLLECTION)
    if chunk_count == 0:
        raise SystemExit("store is empty; run build_index.py first")

    id_map = _load_parent_id_map()
    queries = json.loads(GT_PATH.read_text(encoding="utf-8"))["queries"]
    settings = EffectiveSettings(
        retrieval=RetrievalBlock(
            hybrid_enabled=True,
            rerank_enabled=False,
            similarity_threshold=0.0,
        )
    )

    state = _load_checkpoint()
    done = set(state["done"])
    print(
        f"[{CELL}] store={chunk_count} chunks, queries={len(queries)}, "
        f"resume skips {len(done)}",
        flush=True,
    )

    for entry in queries:
        if entry["query_id"] in done:
            continue
        results, latency = _search_with_transient_retry(entry, settings, store)
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
        _save_checkpoint(state)
        print(
            f"[{CELL}] {entry['query_id']} rank1={parent_ids[0] if parent_ids else '-'} "
            f"({latency:.2f}s)",
            flush=True,
        )

    print(f"[{CELL}] complete: {len(state['rows'])} queries", flush=True)


def main() -> None:
    """Parse optional flags and run."""
    parser = argparse.ArgumentParser()
    # --resume accepted for protocol.md compatibility; resume is automatic.
    parser.add_argument("--resume", action="store_true", help="no-op; resume is automatic")
    args = parser.parse_args()
    del args
    run_cell()


if __name__ == "__main__":
    main()
