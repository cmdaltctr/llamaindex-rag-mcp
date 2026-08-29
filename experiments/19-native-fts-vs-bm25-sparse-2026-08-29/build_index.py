"""Build the Experiment 19 store: ingest the Exp 9 corpus into LanceDB.

Sets the experiment-local environment BEFORE importing anything
config-dependent (the working-directory guard: state-mutating setup
runs against an isolated LANCEDB_URI under output/, never a real
persist directory), then ingests every corpus pack with real Ollama
embeddings (qwen3-embedding:0.6b) and metadata extraction disabled
(irrelevant to the sparse comparison, keeps the run fast and
deterministic).

Atomic and idempotent enough for a one-shot build: a completed build
writes output/build_done.json; re-running with that marker present
skips ingestion unless --force is given.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
CORPUS = PROJECT_ROOT / "experiments/9-hybrid-retrieval-2026-05-27/corpus"
STORE_URI = EXP_DIR / "output/lancedb"
COLLECTION = "exp19"

os.environ.update(
    {
        "LANCEDB_URI": str(STORE_URI),
        "VECTOR_STORE": "lancedb",
        "EMBED_PROVIDER": "ollama",
        "EMBED_MODEL": "qwen3-embedding:0.6b",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "METADATA__EXTRACTION_MODE": "disabled",
        "PDF_READER": "pypdf",
        "COLLECTION_NAME": COLLECTION,
    }
)

sys.path.insert(0, str(PROJECT_ROOT / "src"))


def main() -> None:
    """Ingest every corpus pack into the isolated experiment store."""
    force = "--force" in sys.argv
    marker = EXP_DIR / "output/build_done.json"
    if marker.exists() and not force:
        print(f"[build] {marker} present; skipping (pass --force to rebuild)", flush=True)
        return

    from rag_mcp.compose import ensure_runtime_setup
    from rag_mcp.core.ingestion import ingest_path_async

    # Installs the embed model and the default EffectiveSettings the
    # ingestion entry point resolves at its boundary.
    ensure_runtime_setup()
    started = time.perf_counter()
    stats: dict[str, object] = {"packs": {}}
    for pack in sorted(CORPUS.iterdir()):
        if not pack.is_dir():
            continue
        print(f"[build] ingesting {pack.name}/ ...", flush=True)
        result = asyncio.run(ingest_path_async(str(pack), collection_name=COLLECTION))
        stats["packs"][pack.name] = result  # type: ignore[index]
        print(f"[build]   -> {result}", flush=True)

    from rag_mcp.core.vectordb.lancedb import LanceVectorStore

    store = LanceVectorStore(uri=str(STORE_URI))
    stats["chunk_count"] = store.count(COLLECTION)
    stats["elapsed_s"] = round(time.perf_counter() - started, 2)
    tmp = marker.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stats, indent=2, default=str))
    tmp.replace(marker)
    print(f"[build] done: {stats['chunk_count']} chunks in {stats['elapsed_s']}s", flush=True)


if __name__ == "__main__":
    main()
