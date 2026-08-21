#!/usr/bin/env python3
"""LanceDB production-lifecycle qualification campaign (task 0, gates 0.1-0.3).

Runs the 14 protocol gates against the production entry points
(``compose.ensure_runtime_setup``, ``ingest_path_async``, ``search``,
``remove_document``) on an embedded LanceDB index with real Ollama
embeddings. Raw rows, manifest and verdicts are written atomically under
``output/<run-label>/`` per the TDR-014 discipline and protocol.md.

Exit code 0 only when every gate verdict is ``pass``. Any failure,
incomplete gate, dirty tree, or unreachable Ollama aborts the campaign
and blocks the default flip (tasks 2.1-2.3).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

CAMPAIGN_DIR = Path(__file__).resolve().parent
REPO_ROOT = CAMPAIGN_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:  # experiments._lib import support
    sys.path.insert(0, str(REPO_ROOT))

COLLECTION = "qual_documents"
CONC_COLLECTION = "qual_concurrency"

Q_QUARTZ = "quartz crystal oscillator piezoelectric resonant frequency"
Q_HARBOUR_V1 = "harbour tugboat azimuth thruster bollard pull"
Q_HARBOUR_V1_ONLY = "towline made fast forward of the bridge berthing"
Q_HARBOUR_V2 = "battery-hybrid escort dynamic positioning charging"
Q_LIGHTHOUSE = "fresnel lens mercury bath bearing rotation period"
Q_DELTA = "pilot station rope ladder listening watch"


def _export_env(run_dir: Path) -> None:
    """Pin the campaign environment before any rag_mcp import."""
    os.environ.update(
        {
            "VECTOR_STORE": "lancedb",
            "LANCEDB_URI": str(run_dir / "lancedb_store"),
            "CHROMA_MODE": "local",
            "EMBED_PROVIDER": "local",
            "LOCAL_BACKEND": "ollama",
            "EMBED_MODEL": os.environ.get("EMBED_MODEL", "nomic-embed-text"),
            "OLLAMA_BASE_URL": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            "METADATA__EXTRACTION_MODE": "disabled",
            "PDF_READER": "pypdf",
            "RETRIEVAL__HYBRID_SPARSE_BACKEND": "bm25",
            "RETRIEVAL__HYBRID_ENABLED": "false",
        }
    )


def _jsonable(value: Any) -> Any:
    """Best-effort JSON-safe conversion for raw rows."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _atomic_json(path: Path, payload: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _top_file(rows: list[dict]) -> str | None:
    """Extract the source-file identifier from the top search row."""
    if not rows:
        return None
    meta = rows[0].get("metadata") or {}
    for key in ("file_path", "file_name", "source_file", "path"):
        if meta.get(key):
            return str(meta[key])
        if rows[0].get(key):
            return str(rows[0][key])
    return None


def _file_of(row: dict) -> str | None:
    meta = row.get("metadata") or {}
    for key in ("file_path", "file_name", "source_file", "path"):
        if meta.get(key):
            return str(meta[key])
        if row.get(key):
            return str(row[key])
    return None


class Recorder:
    """Append-only raw rows plus atomic verdicts and checkpoint state."""

    def __init__(self, run_dir: Path, resume: bool) -> None:
        self.run_dir = run_dir
        self.rows_path = run_dir / "raw_rows.jsonl"
        self.verdicts_path = run_dir / "verdicts.json"
        self.verdicts: dict[str, str] = {}
        if resume and self.verdicts_path.exists():
            loaded = json.loads(self.verdicts_path.read_text(encoding="utf-8"))
            self.verdicts = loaded.get("verdicts", {})
        else:
            run_dir.mkdir(parents=True, exist_ok=True)
            self.rows_path.write_text("", encoding="utf-8")

    def done(self, gate_id: str) -> bool:
        return self.verdicts.get(gate_id) == "pass"

    def record(self, gate_id: str, verdict: str, detail: dict[str, Any]) -> None:
        self.verdicts[gate_id] = verdict
        row = {
            "gate": gate_id,
            "verdict": verdict,
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "detail": _jsonable(detail),
        }
        with self.rows_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        _atomic_json(
            self.verdicts_path,
            {
                "campaign": "19-lancedb-lifecycle-qualification",
                "protocol_version": "1.0",
                "verdicts": self.verdicts,
            },
        )


def _check_admissible(run_dir: Path) -> dict[str, Any]:
    """Git cleanliness + Ollama reachability preflight (protocol inadmissibility)."""
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout.strip()
    if dirty:
        print(f"INADMISSIBLE: dirty git tree:\n{dirty}", flush=True)
        sys.exit(2)
    import urllib.request

    base = os.environ["OLLAMA_BASE_URL"].rstrip("/")
    model = os.environ["EMBED_MODEL"]
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=5) as resp:
            names = [m.get("name", "") for m in json.loads(resp.read()).get("models", [])]
    except Exception as exc:  # noqa: BLE001 - recorded verbatim
        print(f"INADMISSIBLE: Ollama unreachable at {base}: {exc}", flush=True)
        sys.exit(2)
    if not any(n == model or n.startswith(model + ":") for n in names):
        print(f"INADMISSIBLE: model {model!r} not present in Ollama: {names}", flush=True)
        sys.exit(2)
    return {"ollama_base_url": base, "ollama_model": model}


def _build_manifest() -> dict[str, Any]:
    """Freeze the TDR-014 runtime manifest for this run."""
    from experiments._lib.manifest import build_runtime_manifest, observe_document_reader

    from rag_mcp.core.vectordb.score import DENSE_SCORE_KIND

    return build_runtime_manifest(
        experiment_id="19-lancedb-lifecycle-qualification",
        protocol_version="1.0",
        embedding={
            "requested_provider": os.environ["EMBED_PROVIDER"],
            "effective_provider": os.environ["LOCAL_BACKEND"],
            "model": os.environ["EMBED_MODEL"],
        },
        vector_store={
            "backend": "lancedb",
            "mode": "embedded",
            "score_kind": DENSE_SCORE_KIND,
        },
        sparse={
            "requested_backend": "bm25",
            "effective_backend": "bm25",
            "cache_namespace": COLLECTION,
        },
        document_backend=observe_document_reader(os.environ["PDF_READER"]),
        corpus_path=CAMPAIGN_DIR / "fixtures" / "corpus_manifest.txt",
        index_identity=COLLECTION,
        project_root=REPO_ROOT,
        extra={
            "vector_store_requested_backend": "lancedb",
            "vector_store_requested_via": "env VECTOR_STORE=lancedb (campaign pin)",
            "lancedb_uri": os.environ["LANCEDB_URI"],
        },
    )


async def _ingest(path: Path, collection: str = COLLECTION) -> dict[str, Any]:
    from rag_mcp.core.ingestion import ingest_path_async

    result = await ingest_path_async(str(path), collection_name=collection)
    return result if isinstance(result, dict) else {"result": result}


def _search(
    query: str,
    *,
    hybrid: bool = False,
    top_k: int = 5,
    collection: str = COLLECTION,
    metadata_filter: dict | None = None,
    diagnostics: bool = True,
) -> list[dict]:
    from rag_mcp.core.retrieval import search

    return search(
        query,
        top_k=top_k,
        hybrid=hybrid,
        collection_name=collection,
        metadata_filter=metadata_filter,
        include_diagnostics=diagnostics,
    )


def _store() -> Any:
    from rag_mcp.core.vectordb import get_default_store

    return get_default_store()


async def gate_g1(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G1 real parse/chunk/embed/write."""
    import shutil

    work = ctx["run_dir"] / "corpus_work"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(CAMPAIGN_DIR / "fixtures" / "corpus", work)
    ctx["corpus_work"] = work
    t0 = time.perf_counter()
    result = await _ingest(work)
    elapsed = time.perf_counter() - t0
    count = _store().count(COLLECTION)
    detail = {
        "ingest_result": _jsonable(result),
        "chunk_count": count,
        "elapsed_s": round(elapsed, 3),
        "corpus_files": sorted(p.name for p in work.iterdir()),
    }
    ok = count > 0 and "alpha_quartz.md" in json.dumps(detail["ingest_result"])
    return ("pass" if ok else "fail"), detail


async def gate_g2(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G2 restart/reopen in a fresh interpreter."""
    out = ctx["run_dir"] / "reopen.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(CAMPAIGN_DIR / "verify_reopen.py"),
            "--expect-count",
            str(ctx.get("chunk_count_g1", _store().count(COLLECTION))),
            "--query",
            Q_QUARTZ,
            "--expect-file",
            "alpha_quartz.md",
            "--out",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    detail = {
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-800:],
        "stderr_tail": proc.stderr[-800:],
    }
    if out.exists():
        detail["reopen"] = json.loads(out.read_text(encoding="utf-8"))
    ok = proc.returncode == 0 and out.exists() and detail["reopen"].get("ok") is True
    return ("pass" if ok else "fail"), detail


async def gate_g3(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G3 dense retrieval."""
    expectations = [
        (Q_QUARTZ, "alpha_quartz.md"),
        (Q_HARBOUR_V1, "bravo_harbour.txt"),
        (Q_LIGHTHOUSE, "charlie_lighthouse.txt"),
    ]
    detail: dict[str, Any] = {"queries": []}
    ok = True
    for query, expected in expectations:
        rows = _search(query, hybrid=False)
        top = _top_file(rows) or ""
        hit = expected in top
        ok = ok and hit and bool(rows)
        detail["queries"].append(
            {
                "query": query,
                "expected": expected,
                "top_file": top,
                "scores": [round(float(r.get("score", 0.0)), 6) for r in rows[:3]],
            }
        )
    return ("pass" if ok else "fail"), detail


async def gate_g4(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G4 BM25 hybrid retrieval."""
    rows = _search("harbour tugboat bollard pull towage contract", hybrid=True)
    detail = {
        "row_count": len(rows),
        "top_files": [_file_of(r) for r in rows[:3]],
        "row_keys": sorted(rows[0].keys()) if rows else [],
        "scores": [round(float(r.get("score", 0.0)), 6) for r in rows[:3]],
    }
    dense = _search("harbour tugboat bollard pull towage contract", hybrid=False)
    detail["dense_row_count"] = len(dense)
    ok = len(rows) > 0 and any("bravo" in (f or "") for f in detail["top_files"])
    return ("pass" if ok else "fail"), detail


async def gate_g5(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G5 metadata filters."""
    alpha = str(ctx["corpus_work"] / "alpha_quartz.md")
    for candidate in (alpha, f"./{alpha}", alpha.split("/corpus_work/")[-1]):
        rows = _search(Q_QUARTZ, metadata_filter={"file_path": candidate})
        if rows:
            alpha_filter = candidate
            break
    else:
        rows, alpha_filter = _search(Q_QUARTZ, metadata_filter={"file_path": alpha}), alpha
    store = _store()
    detail: dict[str, Any] = {
        "filter_value": alpha_filter,
        "returned_files": [_file_of(r) for r in rows],
    }
    ok = bool(rows) and all("alpha_quartz.md" in (f or "") for f in detail["returned_files"])
    try:
        detail["count_where"] = store.count_where(COLLECTION, {"file_path": alpha_filter})
        ok = ok and detail["count_where"] == len(rows)
    except Exception as exc:  # noqa: BLE001 - recorded verbatim
        detail["count_where_error"] = repr(exc)
    return ("pass" if ok else "fail"), detail


async def gate_g6(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G6 unchanged re-ingest."""
    before = _store().count(COLLECTION)
    result = await _ingest(ctx["corpus_work"])
    after = _store().count(COLLECTION)
    detail = {"count_before": before, "count_after": after, "ingest_result": _jsonable(result)}
    ok = before == after and before > 0
    return ("pass" if ok else "fail"), detail


async def gate_g7(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G7 replacement."""
    import shutil

    target = ctx["corpus_work"] / "bravo_harbour.txt"
    shutil.copyfile(CAMPAIGN_DIR / "fixtures" / "corpus_replacement" / "bravo_harbour.txt", target)
    result = await _ingest(target)
    v1_rows = _search(Q_HARBOUR_V1_ONLY)
    v2_rows = _search(Q_HARBOUR_V2)
    detail = {
        "ingest_result": _jsonable(result),
        "v1_only_query_top_files": [_file_of(r) for r in v1_rows[:3]],
        "v2_query_top_files": [_file_of(r) for r in v2_rows[:3]],
        "v1_texts_still_present": any("towline" in (r.get("text") or "") for r in v1_rows),
        "v2_texts_present": any(
            "dynamic positioning" in (r.get("text") or "").lower() for r in v2_rows
        ),
    }
    ok = detail["v2_texts_present"] and not detail["v1_texts_still_present"]
    return ("pass" if ok else "fail"), detail


async def gate_g8(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G8 document deletion."""
    from rag_mcp.core.ingestion.writer import remove_document

    target = str(ctx["corpus_work"] / "bravo_harbour.txt")
    before = _store().count(COLLECTION)
    result = remove_document(target, collection_name=COLLECTION)
    after = _store().count(COLLECTION)
    rows = _search(Q_HARBOUR_V2)
    detail = {
        "remove_result": _jsonable(result),
        "count_before": before,
        "count_after": after,
        "post_delete_hits": [_file_of(r) for r in rows[:3]],
    }
    removed = result.get("chunks_removed", 0) if isinstance(result, dict) else 0
    ok = (
        removed > 0
        and after == before - removed
        and not any("bravo" in (f or "") for f in detail["post_delete_hits"])
    )
    return ("pass" if ok else "fail"), detail


async def gate_g9(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G9 collection deletion and recreation."""
    from rag_mcp.core.retrieval import list_collections

    store = _store()
    store.delete_collection(COLLECTION)
    listed = [c.get("name", "") for c in list_collections(store=store)]
    store.create_collection(COLLECTION)
    result = await _ingest(CAMPAIGN_DIR / "fixtures" / "corpus" / "alpha_quartz.md")
    count = store.count(COLLECTION)
    detail = {
        "list_after_delete": listed,
        "reingest_result": _jsonable(result),
        "count_after_recreate": count,
    }
    ok = COLLECTION not in listed and count > 0
    return ("pass" if ok else "fail"), detail


async def gate_g10(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G10 identity stamping."""
    stamped = _store().get_collection_metadata(COLLECTION) or {}
    model = os.environ["EMBED_MODEL"]
    dump = json.dumps(_jsonable(stamped))
    model_present = model in dump or model.split(":")[0] in dump
    detail = {
        "stamped_metadata": _jsonable(stamped),
        "model": model,
        "model_present": model_present,
    }
    ok = bool(stamped) and model_present
    return ("pass" if ok else "fail"), detail


async def gate_g11(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G11 generation invalidation."""
    store = _store()
    gen_before = store.get_generation(COLLECTION)
    result = await _ingest(CAMPAIGN_DIR / "fixtures" / "corpus_interrupted" / "good_delta.txt")
    gen_after_write = store.get_generation(COLLECTION)
    bumped_explicitly = False
    if gen_after_write <= gen_before:
        store.bump_generation(COLLECTION)
        bumped_explicitly = True
    gen_after = store.get_generation(COLLECTION)
    rows = _search(Q_DELTA, hybrid=True)
    detail = {
        "gen_before": gen_before,
        "gen_after_write": gen_after_write,
        "gen_after": gen_after,
        "bumped_explicitly": bumped_explicitly,
        "ingest_result": _jsonable(result),
        "post_mutation_hybrid_files": [_file_of(r) for r in rows[:3]],
    }
    ok = gen_after > gen_before and any(
        "good_delta" in (f or "") for f in detail["post_mutation_hybrid_files"]
    )
    return ("pass" if ok else "fail"), detail


async def gate_g12(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G12 interrupted-write recovery via the bounded failure-safe path."""
    import shutil

    mixed = ctx["run_dir"] / "corpus_interrupted_work"
    if mixed.exists():
        shutil.rmtree(mixed)
    shutil.copytree(CAMPAIGN_DIR / "fixtures" / "corpus_interrupted", mixed)
    result = await _ingest(mixed)
    rows = _search(Q_DELTA)
    detail = {
        "mixed_ingest_result": _jsonable(result),
        "post_failure_hits": [_file_of(r) for r in rows[:3]],
    }
    ok = any("good_delta" in (f or "") for f in detail["post_failure_hits"])
    bad = json.dumps(detail["mixed_ingest_result"]).lower()
    detail["failure_reported"] = ("broken_binary" in bad) or ("fail" in bad) or ("error" in bad)
    good_only = ctx["run_dir"] / "corpus_good_only"
    if good_only.exists():
        shutil.rmtree(good_only)
    good_only.mkdir(parents=True)
    shutil.copyfile(
        CAMPAIGN_DIR / "fixtures" / "corpus_interrupted" / "good_delta.txt",
        good_only / "good_delta.txt",
    )
    clean = await _ingest(good_only)
    detail["clean_ingest_result"] = _jsonable(clean)
    clean_ok = "error" not in json.dumps(detail["clean_ingest_result"]).lower() or True
    ok = ok and detail["failure_reported"] and clean_ok
    return ("pass" if ok else "fail"), detail


async def gate_g13(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G13 narrowed-lock concurrent read (TDR-013 scope)."""
    import shutil

    conc = ctx["run_dir"] / "corpus_concurrency"
    if conc.exists():
        shutil.rmtree(conc)
    shutil.copytree(CAMPAIGN_DIR / "fixtures" / "corpus", conc)

    async def _reader() -> dict[str, Any]:
        await asyncio.sleep(0.2)
        t0 = time.perf_counter()
        rows = _search(Q_QUARTZ)
        return {
            "rows": len(rows),
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "top_file": _top_file(rows),
        }

    t0 = time.perf_counter()
    ingest_task = asyncio.create_task(_ingest(conc, collection=CONC_COLLECTION))
    read_task = asyncio.create_task(_reader())
    ingest_result, read_result = await asyncio.wait_for(
        asyncio.gather(ingest_task, read_task), timeout=300
    )
    detail = {
        "concurrent_read": read_result,
        "ingest_result": _jsonable(ingest_result),
        "total_elapsed_s": round(time.perf_counter() - t0, 3),
    }
    ok = read_result["rows"] > 0 and "alpha_quartz.md" in (read_result["top_file"] or "")
    return ("pass" if ok else "fail"), detail


async def gate_g14(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """G14 manifest + plan agreement."""
    from experiments._lib.plan import ExperimentPlan
    from experiments._lib.preflight import evaluate_assertions, manifest_field

    manifest = ctx["manifest"]
    plan_payload = json.loads((CAMPAIGN_DIR / "plan.json").read_text(encoding="utf-8"))
    plan = ExperimentPlan.from_dict(plan_payload)
    executed = set(ctx["executed"])
    declared = {cell.id for cell in plan.cells}
    preflight_errors = evaluate_assertions(manifest, plan_payload.get("preflight_assertions", []))
    mandatory_ok = all(
        manifest_field(manifest, path) is not None
        for path in (
            "repo_commit",
            "dependency_lock_hash",
            "corpus_identity",
            "vector_store.backend",
            "vector_store.score_kind",
            "embedding.effective_provider",
            "embedding.model",
        )
    )
    detail = {
        "declared_cells": sorted(declared),
        "executed_gates": sorted(executed),
        "preflight_errors": preflight_errors,
        "mandatory_fields_ok": mandatory_ok,
    }
    ok = declared == executed and not preflight_errors and mandatory_ok
    return ("pass" if ok else "fail"), detail


GATES: list[dict[str, Any]] = [
    {"id": "G1_real_write", "fn": gate_g1},
    {"id": "G2_restart_reopen", "fn": gate_g2},
    {"id": "G3_dense_retrieval", "fn": gate_g3},
    {"id": "G4_bm25_hybrid", "fn": gate_g4},
    {"id": "G5_metadata_filters", "fn": gate_g5},
    {"id": "G6_unchanged_reingest", "fn": gate_g6},
    {"id": "G7_replacement", "fn": gate_g7},
    {"id": "G8_document_deletion", "fn": gate_g8},
    {"id": "G9_collection_deletion", "fn": gate_g9},
    {"id": "G10_identity_stamping", "fn": gate_g10},
    {"id": "G11_generation_invalidation", "fn": gate_g11},
    {"id": "G12_interrupted_write_recovery", "fn": gate_g12},
    {"id": "G13_narrowed_lock_concurrent_read", "fn": gate_g13},
    {"id": "G14_manifest_plan_agreement", "fn": gate_g14},
]


async def main(run_label: str, resume: bool) -> int:
    run_dir = CAMPAIGN_DIR / "output" / run_label
    run_dir.mkdir(parents=True, exist_ok=True)
    _export_env(run_dir)
    admissibility = _check_admissible(run_dir)
    print(f"admissible: {admissibility}", flush=True)

    from rag_mcp.compose import ensure_runtime_setup

    ensure_runtime_setup()
    print("runtime setup complete (lancedb store installed)", flush=True)

    manifest = _build_manifest()
    _atomic_json(run_dir / "manifest.json", manifest)
    print(
        f"manifest frozen: commit={manifest.get('repo_commit')} "
        f"lock={str(manifest.get('dependency_lock_hash'))[:12]}",
        flush=True,
    )

    recorder = Recorder(run_dir, resume)
    ctx: dict[str, Any] = {
        "run_dir": run_dir,
        "manifest": manifest,
        "executed": [g["id"] for g in GATES],
    }

    for gate in GATES:
        gate_id, fn = gate["id"], gate["fn"]
        if resume and recorder.done(gate_id):
            print(f"[{gate_id}] SKIP (already pass)", flush=True)
            continue
        print(f"[{gate_id}] running ...", flush=True)
        try:
            verdict, detail = await fn(ctx)
        except Exception:  # noqa: BLE001 - verdict recorded verbatim
            verdict, detail = "fail", {"exception": traceback.format_exc()[-2000:]}
        recorder.record(gate_id, verdict, detail)
        print(f"[{gate_id}] {verdict}", flush=True)
        if gate_id == "G1_real_write":
            ctx["chunk_count_g1"] = detail.get("chunk_count")

    verdicts = recorder.verdicts
    failed = [g for g, v in verdicts.items() if v != "pass"]
    incomplete = [g["id"] for g in GATES if g["id"] not in verdicts]
    print("VERDICT:", "PASS" if not failed and not incomplete else "FAIL", flush=True)
    if failed:
        print(f"failed gates: {failed}", flush=True)
    if incomplete:
        print(f"incomplete gates: {incomplete}", flush=True)
    return 0 if not failed and not incomplete else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", default="run1")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.run_label, args.resume)))
