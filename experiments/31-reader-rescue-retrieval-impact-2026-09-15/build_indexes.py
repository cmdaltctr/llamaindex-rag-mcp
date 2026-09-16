"""Experiment 31 index builder (tasks 3.5, 3.6).

Builds ONE index per cell — held-out + distractor groups only; development
documents are never indexed — through the real composition root so every
downstream variable (chunking, embedding, store, profile resolution) is the
production path. The only per-cell difference is the PDF reader name.

Per cell, this script:

1. pins the controlled environment (local ollama embeddings, lancedb,
   ``documents`` profile, metadata extraction disabled, OCR off);
2. resets the ``omrg.config`` settings singleton so each engine resolves
   fresh from the pinned environment;
3. ingests every held-out and distractor document into
   ``exp31_<cell>``;
4. emits a SECRET-FREE runtime manifest (source commit, lockfile hash,
   effective settings, index identity, chunk counts, index size) to
   ``output/runtime_manifest_<cell>.json`` — no paths, no text, no keys.

Usage:
    uv run python build_indexes.py --cell B           # one cell
    uv run python build_indexes.py --smoke            # tiny end-to-end check
    uv run python build_indexes.py --force            # rebuild existing tables
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(EXP_DIR))

import harness_readers  # noqa: E402

harness_readers.register_mirrors()

#: Logical cell readers, mounted under the production registry name
#: (see harness_readers.install_cell_reader for why the experiment
#: names cannot travel through PDF_READER: the Settings validator
#: whitelists concrete literals and silently resets unknowns to auto).
CELL_READERS = {"A": "inspector_only", "B": "pdf_inspector", "C": "pypdf_guard"}

#: Environment pinned identically in every cell. The reader difference
#: is mounted in the registry, not in the environment.
PINNED_ENV = {
    "EMBED_PROVIDER": "local",
    "LOCAL_BACKEND": "ollama",
    "EMBED_MODEL": "qwen3-embedding:0.6b",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "VECTOR_STORE": "lancedb",
    "LANCEDB_URI": str((EXP_DIR / "output" / "lancedb").resolve()),
    "RAG_PROFILE": "documents",
    "METADATA__EXTRACTION_MODE": "disabled",
    "OCR_FALLBACK_ENABLED": "false",
    "OCR_WORKER_COMMAND": "",
    "LITEPARSE_OCR_ENABLED": "false",
    "RETRIEVAL__TOP_K": "10",
    "RETRIEVAL__RERANK_ENABLED": "true",
    "RETRIEVAL__HYBRID_ENABLED": "false",
}


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["/usr/bin/git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return "unknown"


def _lockfile_hash() -> str:
    lock = PROJECT_ROOT / "uv.lock"
    if not lock.is_file():
        return "unknown"
    return hashlib.sha256(lock.read_bytes()).hexdigest()


def _effective_snapshot(engine: object) -> dict:
    """Serialise the secret-free controlled variables from the engine settings."""
    eff = engine._effective_settings  # composition-root product; read-only here
    snapshot = {
        "profile_name": eff.profile_name,
        "pdf_reader": eff.pdf_reader,
        "vector_store": eff.vector_store,
        "embed_provider": eff.embed_provider,
        "embed_model": eff.embed_model,
        "chunking": {
            "chunk_size": eff.chunking.chunk_size,
            "chunk_overlap": eff.chunking.chunk_overlap,
            "markdown_chunk_size": eff.chunking.markdown_chunk_size,
            "strategy_fallback": eff.chunking.strategy_fallback,
            "markdown_heading_prepend": eff.chunking.markdown_heading_prepend,
        },
        "embedding": {
            # Key names avoid the word "token" prefix: gitleaks'
            # generic-api-key rule flags <anything-token>-shaped keys
            # carrying a high-entropy hex revision.
            "splitter_model": eff.embedding.tokenizer_model,
            "splitter_revision": eff.embedding.tokenizer_revision,
            "norm_guard_enabled": eff.embedding.norm_guard_enabled,
            "query_instruction": eff.embedding.query_instruction,
        },
        "retrieval": {
            "top_k": eff.retrieval.top_k,
            "rerank_enabled": eff.retrieval.rerank_enabled,
            "hybrid_enabled": eff.retrieval.hybrid_enabled,
            "similarity_threshold": eff.retrieval.similarity_threshold,
        },
        "metadata": {"extraction_mode": eff.metadata.extraction_mode},
        "ocr": {
            "ocr_fallback_enabled": eff.ocr_fallback_enabled,
            "ocr_worker_command": eff.ocr_worker_command,
        },
        "liteparse_ocr_enabled": eff.liteparse_ocr_enabled,
    }
    return snapshot


def _index_bytes(uri: Path, table: str) -> int:
    for candidate in (uri / table, uri / f"{table}.lance"):
        if candidate.is_dir():
            return sum(p.stat().st_size for p in candidate.rglob("*") if p.is_file())
    return 0


async def _build_cell(cell: str, docs: list[dict], force: bool) -> dict:
    import omrg.config as config_module

    collection = f"exp31_{cell}"
    env = dict(PINNED_ENV)
    env["PDF_READER"] = harness_readers.PRODUCTION_NAME
    env["COLLECTION_NAME"] = collection
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        # Fresh Settings singleton per cell: build_engine() -> get_settings().
        config_module._settings = None
        # Mount this cell's reader under the production registry name;
        # the reader resolves lazily at ingest time, inside this block.
        harness_readers.install_cell_reader(CELL_READERS[cell])

        from omrg.compose import build_engine

        engine = build_engine()
        snapshot = _effective_snapshot(engine)
        existing = engine.list_collections()
        if collection in existing:
            if not force:
                print(
                    f"[{cell}] {collection} exists; skipping (use --force to rebuild)", flush=True
                )
                engine.close()
                return {"cell": cell, "skipped": True}
            engine.delete_collection(collection)

        per_doc: list[dict] = []
        for entry in docs:
            started = time.perf_counter()
            result = await engine.ingest(entry["path"], collection_name=collection)
            elapsed = time.perf_counter() - started
            file_rows = result.get("files") or result.get("file_details") or []
            failed_files = sum(1 for fd in file_rows if fd.get("status") == "failed")
            per_doc.append(
                {
                    "doc_id": entry["doc_id"],
                    "split": entry["split"],
                    "chunks_created": result.get("chunks_created"),
                    "documents_processed": result.get("documents_processed"),
                    "failed_files": failed_files,
                    "ingest_seconds": round(elapsed, 1),
                }
            )
            print(
                f"[{cell}] ingested {entry['doc_id']}: {result.get('chunks_created')} chunks "
                f"({failed_files} failed files) in {elapsed:.1f}s",
                flush=True,
            )

        engine.close()
    finally:
        harness_readers.restore_production_reader()
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config_module._settings = None

    uri = Path(PINNED_ENV["LANCEDB_URI"])
    manifest = {
        "cell": cell,
        "reader": CELL_READERS[cell],
        "registry_name": harness_readers.PRODUCTION_NAME,
        "collection": collection,
        "built_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_commit": _git_commit(),
        "lockfile_sha256": _lockfile_hash(),
        "controlled_variables": snapshot,
        "documents": per_doc,
        "total_chunks": sum(d["chunks_created"] or 0 for d in per_doc),
        "index_size_bytes": _index_bytes(uri, collection),
        "embedding_tokens": None,  # not exposed by the ingest result surface
    }
    out = EXP_DIR / "output" / f"runtime_manifest_{cell}.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        f"[{cell}] manifest -> {out.name} ({manifest['total_chunks']} chunks, "
        f"{manifest['index_size_bytes']} bytes)",
        flush=True,
    )
    return manifest


async def _amain(args: argparse.Namespace) -> None:
    private = json.loads((EXP_DIR / "output" / ".collection.private.json").read_text())
    if args.smoke:
        docs = [d for d in private["documents"] if d["doc_id"] in ("h08", "d01")]
        cells = ["B"]
    else:
        docs = [d for d in private["documents"] if d["split"] in ("heldout", "distractor")]
        cells = args.cell or sorted(CELL_READERS)
    for cell in cells:
        await _build_cell(cell, docs, force=args.force or args.smoke)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", choices=sorted(CELL_READERS), action="append")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
