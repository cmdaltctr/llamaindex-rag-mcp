"""Build the Experiment 22 store: ingest the freshstack corpus into LanceDB.

Adapts the Experiment 19 pattern (production ``ingest_path_async`` against
an isolated experiment-local store) with the cloud embedding provider this
baseline targets: OpenRouter ``qwen/qwen3-embedding-4b``. The API key is
never set here — it loads from the project ``.env``. Everything else is
pinned explicitly so the build is hermetic against later .env drift.

Idempotent: a completed build writes ``output/build_done.json``; re-running
with that marker skips unless ``--force``. Per-file embedding failures do
not stop the batch (per-file error boundary); re-run the script to retry
only the files that failed.
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
CORPUS = EXP_DIR / "corpus"
STORE_URI = EXP_DIR / "output/lancedb"
COLLECTION = "exp22"

# Project .env supplies OPENROUTER_API_KEY (and, as a fallback, the cloud
# provider block). Isolation and identity overrides come after it loads.
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


def main() -> None:
    """Ingest both corpus packs into the isolated experiment store."""
    force = "--force" in sys.argv
    marker = EXP_DIR / "output/build_done.json"
    if marker.exists() and not force:
        print(f"[build] {marker} present; skipping (pass --force to rebuild)", flush=True)
        return

    from omrg.compose import ensure_runtime_setup
    from omrg.core.ingestion import ingest_path_async

    ensure_runtime_setup()
    started = time.perf_counter()
    stats: dict[str, object] = {"packs": {}}
    for pack in ("langchain", "continuity"):
        pack_path = CORPUS / pack
        if not pack_path.is_dir():
            print(f"[build] missing pack {pack_path}; skipping", flush=True)
            continue
        print(f"[build] ingesting corpus/{pack}/ ...", flush=True)
        result = asyncio.run(ingest_path_async(str(pack_path), collection_name=COLLECTION))
        stats["packs"][pack] = result  # type: ignore[index]
        print(f"[build]   -> {result}", flush=True)

    from omrg.core.vectordb.lancedb import LanceVectorStore

    store = LanceVectorStore(uri=str(STORE_URI))
    stats["chunk_count"] = store.count(COLLECTION)
    stats["elapsed_s"] = round(time.perf_counter() - started, 2)
    tmp = marker.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stats, indent=2, default=str))
    tmp.replace(marker)
    print(f"[build] done: {stats['chunk_count']} chunks in {stats['elapsed_s']}s", flush=True)


if __name__ == "__main__":
    main()
