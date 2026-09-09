"""Experiment 27 evaluation runner: combined candidate path (task 5.4).

Usage:
    uv run python run_eval.py --resume
    uv run python run_eval.py --limit 2        # smoke, 2 queries per arm

Both arms run in ONE process, interleaved per query, against the
preserved Experiment 25 model-token index (read-only). Nothing is
ingested and no index is written: the query instruction deliberately
stays out of `build_index_identity` (task 4.8), so the same index serves
both arms.

The two cells measured here are the model-token half of the 2x2 the
protocol describes. `chunking_only_raw` re-measures the arm Experiment
25 published: it is re-run rather than loaded so it pairs query by query
with the combined arm and shares its network epoch. The other two cells
(Experiment 22's production baseline, Experiment 26's instruction-only
arm) are loaded by the summariser and never re-run.

OCR routing is not exercised: the FreshStack corpus contains no PDFs.

Metric-relevant behaviour is kept identical to Experiment 22's runner
(same 223 queries, hybrid retrieval, top_k 50, rerank disabled, latency
measured around `pipeline.search` with `time.perf_counter`, no warm-up
pass). The single manipulated factor is `EmbeddingBlock.query_instruction`.

Interleaving: the plan's latency gate is cloud-inclusive, so the arms
must not sit in different network epochs. Each query runs both arms
back to back, and the arm order alternates with the query index so a
systematic first-call/second-call bias cannot land on one arm.

Cache isolation comes for free from task 4.5: the query-embedding cache
is keyed by `(prepared_query, embedding_model_name)`, so the raw and
instructed forms of one query cannot collide inside the shared process.

Transient-provider handling follows Experiments 25 and 26: OpenRouter's free-tier
embedding endpoint returns HTTP 429 "engine_overloaded" for minutes at a
time, so each search is retried with exponential backoff (429 family
only, bounded attempts) and latency is measured around the successful
attempt only.

Checkpoint/resume is automatic: per-query rows are appended to
`output/cells/<cell>.json` with tmp-then-rename atomic writes, so an
interrupted run resumes at the first query missing from either arm.
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
EXP22_DIR = EXP_DIR.parent / "22-raw-query-qwen4b-baseline-2026-09-07"
GT_PATH = EXP22_DIR / "output/ground-truth.json"
MANIFEST_PATH = EXP22_DIR / "corpus/langchain_manifest.jsonl"
PLAN_PATH = EXP_DIR / "plan.json"
# Preserved Experiment 25 model-token index. Read-only here.
STORE_URI = Path.home() / "Development/DATA/omrg/experiments/exp25-lancedb"
COLLECTION = "exp25_model_token"
TOP_K = 50

# Task 4.7 candidate, byte-identical to Experiment 26's text.
CANDIDATE_INSTRUCTION = (
    "Given a user query, retrieve passages that provide relevant and "
    "accurate evidence for answering the query."
)
CELLS = {"chunking_only_raw": "", "combined_candidate": CANDIDATE_INSTRUCTION}

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
sys.path.insert(0, str(EXP_DIR.parent))


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


def _runtime_manifest() -> dict:
    """Manifest checked against the frozen plan's preflight assertions."""
    return {
        "embedding": {
            "model": "qwen/qwen3-embedding-4b",
            "provider": "openrouter (cloud)",
            "query_instruction_applied_to": "queries_only",
            "candidate_instruction": CANDIDATE_INSTRUCTION,
        },
        "retrieval": {"hybrid": True, "rerank_enabled": False, "top_k": TOP_K},
        "index": {"uri": str(STORE_URI), "collection": COLLECTION, "written": False},
        "chunking": {
            "splitter": "model_token_markdown",
            "tokenizer_model": "Qwen/Qwen3-Embedding-4B",
            "source": "experiment 25 candidate index, unchanged",
        },
        "ocr_routing": {"exercised": False, "reason": "corpus contains no PDFs"},
    }


def _preflight() -> dict:
    """Abort before any measured work if the plan's assertions do not hold."""
    from _lib.preflight import PreflightError, evaluate_assertions

    manifest = _runtime_manifest()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    failures = evaluate_assertions(manifest, plan.get("preflight_assertions", []))
    if failures:
        raise PreflightError("; ".join(failures))
    print(f"[preflight] {len(plan['preflight_assertions'])} assertions passed", flush=True)
    return manifest


def _is_transient(exc: BaseException) -> bool:
    """True when the error text indicates provider congestion (429 family)."""
    text = str(exc).lower()
    return any(marker in text for marker in TRANSIENT_MARKERS)


def _search_with_transient_retry(query: str, settings, store, label: str) -> tuple[list, float]:
    """Run one query, retrying 429-family failures with backoff.

    Returns the results and the wall time of the successful attempt only
    (same measurement point as Experiments 22 and 25).
    """
    from omrg.core.retrieval import pipeline

    last_exc: BaseException | None = None
    for attempt in range(1, MAX_TRANSIENT_ATTEMPTS + 1):
        started = time.perf_counter()
        try:
            results = pipeline.search(
                query,
                top_k=TOP_K,
                rerank=False,
                hybrid=True,
                collection_name=COLLECTION,
                store=store,
                effective_settings=settings,
            )
            return results, time.perf_counter() - started
        except Exception as exc:  # noqa: BLE001 - classified below
            if not _is_transient(exc):
                raise
            last_exc = exc
            delay = min(30 * 2 ** (attempt - 1), 600)
            print(
                f"[{label}] transient 429 (attempt {attempt}/{MAX_TRANSIENT_ATTEMPTS}); "
                f"backing off {delay}s",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(f"transient retries exhausted for {label}") from last_exc


def _parent_ids(results: list, id_map: dict[str, str]) -> list[str]:
    """Map retrieved chunk rows to FreshStack parent ids, rank order kept."""
    out: list[str] = []
    for row in results:
        meta = row.get("metadata") or {}
        name = str(meta.get("file_name") or Path(str(row.get("source") or "")).name)
        freshstack_id = id_map.get(name)
        if freshstack_id:
            out.append(freshstack_id)
    return out


def run(limit: int | None) -> None:
    """Run both arms interleaved over the queries, checkpointing per query."""
    manifest = _preflight()

    from omrg.compose import ensure_runtime_setup
    from omrg.core.settings import EffectiveSettings, EmbeddingBlock, RetrievalBlock
    from omrg.core.vectordb.lancedb import LanceVectorStore

    ensure_runtime_setup()
    store = LanceVectorStore(uri=str(STORE_URI))
    chunk_count = store.count(COLLECTION)
    if chunk_count == 0:
        raise SystemExit(f"preserved index at {STORE_URI} is empty or unreadable")

    settings_by_cell = {
        cell: EffectiveSettings(
            retrieval=RetrievalBlock(
                hybrid_enabled=True,
                rerank_enabled=False,
                similarity_threshold=0.0,
            ),
            embedding=EmbeddingBlock(query_instruction=instruction),
        )
        for cell, instruction in CELLS.items()
    }

    id_map = _load_parent_id_map()
    queries = json.loads(GT_PATH.read_text(encoding="utf-8"))["queries"]
    if limit:
        queries = queries[:limit]

    state = {cell: _load_checkpoint(cell) for cell in CELLS}
    done = {cell: set(state[cell]["done"]) for cell in CELLS}
    resumed = len(set.intersection(*done.values())) if done else 0
    print(
        f"[run] index={chunk_count} chunks, queries={len(queries)}, resume skips {resumed}",
        flush=True,
    )
    (EXP_DIR / "output/runtime_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    for index, entry in enumerate(queries):
        query_id = entry["query_id"]
        # Alternate arm order so first-call/second-call bias cannot
        # settle on one arm; both arms stay in the same network epoch.
        order = list(CELLS) if index % 2 == 0 else list(reversed(list(CELLS)))
        summary: list[str] = []
        for cell in order:
            if query_id in done[cell]:
                continue
            results, latency = _search_with_transient_retry(
                entry["query"], settings_by_cell[cell], store, f"{cell}/{query_id}"
            )
            parent_ids = _parent_ids(results, id_map)
            state[cell]["rows"].append(
                {
                    "query_id": query_id,
                    "category": entry["category"],
                    "parent_ids": parent_ids,
                    "latency_s": round(latency, 4),
                    "arm_position": order.index(cell) + 1,
                }
            )
            state[cell]["done"].append(query_id)
            _save_checkpoint(cell, state[cell])
            summary.append(f"{cell}: rank1={parent_ids[0] if parent_ids else '-'} ({latency:.2f}s)")
        if summary:
            print(f"[run] {query_id} | " + " | ".join(summary), flush=True)

    for cell in CELLS:
        print(f"[run] {cell} complete: {len(state[cell]['rows'])} queries", flush=True)


def main() -> None:
    """Parse optional flags and run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="no-op; resume is automatic")
    parser.add_argument("--limit", type=int, default=None, help="smoke: first N queries only")
    args = parser.parse_args()
    run(args.limit)


if __name__ == "__main__":
    main()
