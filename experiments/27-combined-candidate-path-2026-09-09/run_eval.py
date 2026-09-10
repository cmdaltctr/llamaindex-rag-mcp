"""Experiment 27 evaluation runner: combined candidate path (task 5.4).

Usage:
    uv run python run_eval.py --run-dir <name>   # measured run (own dir)
    uv run python run_eval.py --limit 2          # smoke, isolated dir

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
arm) are loaded by the summariser and never re-run. Whether the whole
run shares ONE execution period is recorded rather than asserted: see
the session state written next to the checkpoints.

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

Checkpoint safety (repair tasks 4.4/4.5): every run writes to its own
destination — smoke runs to `output/smoke/limit-<N>/`, measured runs to
`output/runs/<name>/`. Checkpoints carry a timestamp-free run identity
binding plan, ground truth, corpus manifest, runtime treatment and code
hashes; resume recomputes the identity and refuses any mismatch. The
legacy `output/cells/` checkpoints are complete historical evidence:
they are never resumed into, appended to, or overwritten. A session file
records session id, execution periods and interruptions so reports can
disclose mixed execution periods instead of asserting one uninterrupted
network period.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
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


def _legacy_cells_dir() -> Path:
    """Directory of the complete historical 2026-09-09 run (read-only)."""
    return EXP_DIR / "output/cells"


def resolve_checkpoint_base(limit: int | None = None, run_name: str | None = None) -> Path:
    """Destination for this invocation's checkpoints (repair task 4.4).

    Smoke runs land under ``output/smoke/limit-<N>/`` and never reuse an
    existing directory. Measured runs land under ``output/runs/<name>/``.
    Without a destination the runner refuses: the legacy ``output/cells``
    checkpoints are historical evidence, not a resume target.
    """
    if limit is not None and limit <= 0:
        raise SystemExit("--limit must be a positive integer; 0 or negative would run every query")
    if limit is not None:
        base = EXP_DIR / f"output/smoke/limit-{limit}"
        if base.exists():
            raise SystemExit(
                f"smoke destination {base} already exists; remove it explicitly "
                "before starting another smoke run"
            )
        return base
    if run_name is None:
        legacy = _legacy_cells_dir()
        if any((legacy / f"{cell}.json").exists() for cell in CELLS):
            raise SystemExit(
                f"{legacy} contains historical evidence that is not resumable "
                "into new runs; measured runs require --run-dir <name>"
            )
        raise SystemExit("measured runs require --run-dir <name>; smoke runs use --limit <N>")
    if run_name in {"", ".", ".."} or Path(run_name).name != run_name:
        raise SystemExit(
            f"--run-dir must be a single path component under output/runs/, got {run_name!r}"
        )
    return EXP_DIR / "output/runs" / run_name


def _checkpoint_path(base: Path, cell: str) -> Path:
    return base / "cells" / f"{cell}.json"


def _load_checkpoint(path: Path) -> dict | None:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _save_checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def new_session_state(identity: dict) -> dict:
    """Fresh session: one execution period, zero interruptions (task 4.5)."""
    return {
        "session_id": uuid.uuid4().hex,
        "run_identity": identity,
        "periods": [{"started_utc": _utc_now(), "ended_utc": None}],
        "interruptions": 0,
    }


def resume_session_state(previous: dict) -> dict:
    """Record a resume: new execution period, interruption count +1."""
    state = dict(previous)
    state["periods"] = list(previous.get("periods", [])) + [
        {"started_utc": _utc_now(), "ended_utc": None}
    ]
    state["interruptions"] = int(previous.get("interruptions", 0)) + 1
    return state


def execution_periods_text(session: dict | None) -> str:
    """Honest wording about execution periods for reports (task 4.5).

    Historical checkpoints recorded no session; a resumed run reports
    mixed execution periods and claims no common network epoch.
    """
    if session is None:
        return (
            "Execution periods were not recorded for this run "
            "(historical checkpoint; provenance limit)."
        )
    periods = session.get("periods", [])
    if len(periods) == 1:
        return (
            f"Session {session.get('session_id', '?')}: measurements were taken "
            "in a single period; one network epoch is claimed only for that period."
        )
    return (
        f"Session {session.get('session_id', '?')}: measurements span "
        f"{len(periods)} mixed execution periods with "
        f"{session.get('interruptions', 0)} recorded interruption(s); "
        "no common network epoch is claimed across periods."
    )


def _run_identity(manifest: dict) -> dict:
    """Identity binding plan, corpus, treatment and code (task 4.3/4.4)."""
    from _lib.checkpoint_validity import run_identity

    code_paths = [Path(__file__).resolve()]
    lib_dir = EXP_DIR.parent / "_lib"
    for helper in ("preflight.py", "checkpoint_validity.py"):
        code_paths.append(lib_dir / helper)
    lock = PROJECT_ROOT / "uv.lock"
    if lock.exists():
        code_paths.append(lock)
    return run_identity(PLAN_PATH, GT_PATH, MANIFEST_PATH, manifest, code_paths)


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


def run(limit: int | None, run_name: str | None = None) -> None:
    """Run both arms interleaved over the queries, checkpointing per query."""
    manifest = _preflight()
    from _lib.checkpoint_validity import evaluate_resume

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
    if limit is not None:
        queries = queries[:limit]

    base = resolve_checkpoint_base(limit=limit, run_name=run_name)
    identity = _run_identity(manifest)
    state = {cell: _load_checkpoint(_checkpoint_path(base, cell)) for cell in CELLS}
    decision = evaluate_resume(state, identity)
    if decision["action"] != "resume":
        raise SystemExit("; ".join(str(r) for r in decision["reasons"]))
    for cell, cell_state in state.items():
        if cell_state is None:
            state[cell] = {
                "done": [],
                "rows": [],
                "run_identity": identity,
                "session_id": None,
            }

    session_path = base / "session.json"
    if session_path.exists():
        session = resume_session_state(json.loads(session_path.read_text(encoding="utf-8")))
    else:
        session = new_session_state(identity)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(json.dumps(session, indent=2, allow_nan=False), encoding="utf-8")
    for cell in CELLS:
        if state[cell].get("session_id") != session["session_id"]:
            state[cell]["session_id"] = session["session_id"]
            if state[cell]["rows"]:
                _save_checkpoint(_checkpoint_path(base, cell), state[cell])

    done = {cell: set(state[cell]["done"]) for cell in CELLS}
    resumed = len(set.intersection(*done.values())) if done else 0
    print(
        f"[run] index={chunk_count} chunks, queries={len(queries)}, resume skips {resumed}, "
        f"session={session['session_id'][:8]} periods={len(session['periods'])}",
        flush=True,
    )
    (base / "runtime_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    for index, entry in enumerate(queries):
        query_id = entry["query_id"]
        # Alternate arm order so first-call/second-call bias cannot
        # settle on one arm; both arms stay in the same execution period.
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
            _save_checkpoint(_checkpoint_path(base, cell), state[cell])
            summary.append(f"{cell}: rank1={parent_ids[0] if parent_ids else '-'} ({latency:.2f}s)")
        if summary:
            print(f"[run] {query_id} | " + " | ".join(summary), flush=True)

    session["periods"][-1]["ended_utc"] = _utc_now()
    session_path.write_text(json.dumps(session, indent=2, allow_nan=False), encoding="utf-8")
    for cell in CELLS:
        print(f"[run] {cell} complete: {len(state[cell]['rows'])} queries", flush=True)
    print(f"[run] checkpoints: {base}", flush=True)


def main() -> None:
    """Parse optional flags and run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="no-op; resume is identity-bound")
    parser.add_argument(
        "--run-dir",
        dest="run_name",
        default=None,
        help="name under output/runs/ for a measured run",
    )
    parser.add_argument("--limit", type=int, default=None, help="smoke: first N queries only")
    args = parser.parse_args()
    if args.resume and not args.run_name:
        raise SystemExit("--resume is implicit; measured runs require --run-dir <name>")
    run(args.limit, args.run_name)


if __name__ == "__main__":
    main()
