"""Build the Experiment 25 candidate store: model-token Markdown chunking.

Same production-ingestion pattern as the Experiment 22 builder, plus the
pinned Qwen tokenizer identity so the merged model-token-aware Markdown
chunker engages (both model AND revision are required — an empty value
silently falls back to the legacy splitter).

Preflight cost gate (frozen plan.json, task 1.6): refuses to spend API
money if output/token_accounting_{baseline,candidate}.json are missing
or the candidate/baseline embedded-token ratio exceeds the frozen cap.
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
COLLECTION = "exp25_model_token"
TOKENIZER_MODEL = "Qwen/Qwen3-Embedding-4B"
TOKENIZER_REVISION = "5cf2132abc99cad020ac570b19d031efec650f2b"

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
        "EMBEDDING__TOKENIZER_MODEL": TOKENIZER_MODEL,
        "EMBEDDING__TOKENIZER_REVISION": TOKENIZER_REVISION,
    }
)

sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _preflight_cost_gate() -> dict:
    """Refuse paid builds until a corrected pre-spend estimator exists.

    The original preflight read token_accounting_*.json from the deprecated
    standalone counter, which an external review proved defective (manifest
    contamination, body-only counting, non-cancelling ratio — TDR-022).
    That approval path is DISABLED: the defective counter must never
    authorise embedding spend again. Cost verdicts for completed builds
    come from verify_accounting.py (retrospective, deserialises real
    stored nodes). A future pre-spend estimator must reuse production
    preparation with an in-memory store and a network-blocked request
    recorder before this refusal is lifted.
    """
    print(
        "[gate] pre-spend accounting is unavailable in a corrected form;\n"
        "       refusing to start a paid build (TDR-022). Cost verdicts for\n"
        "       completed builds: uv run python verify_accounting.py --side <side>",
        flush=True,
    )
    sys.exit(1)


def main() -> None:
    """Ingest both corpus packs under the candidate chunker."""
    force = "--force" in sys.argv
    marker = EXP_DIR / "output/build_done.json"
    if marker.exists() and not force:
        print(f"[build] {marker} present; skipping (pass --force to rebuild)", flush=True)
        return

    gate = _preflight_cost_gate()

    from omrg.compose import ensure_runtime_setup
    from omrg.core.ingestion import ingest_path_async

    ensure_runtime_setup()
    started = time.perf_counter()
    stats: dict[str, object] = {
        "packs": {},
        "tokenizer": {"model": TOKENIZER_MODEL, "revision": TOKENIZER_REVISION},
        "cost_gate": gate,
    }
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
