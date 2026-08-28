"""Build the D17 LanceDB index from the frozen FreshStack corpus.

Replaces the former symlink to the 9a Chroma builder (superseded
2026-08-22 when the D17 campaign re-based its immutable inputs on the
qualified LanceDB default per ADR-049 D11 — the user-ratified
alternative to the chroma manipulated-factor declaration recorded in
``plan.json``'s previous vector_store_policy).

Reads the corpus manifest frozen by
``IDENTITY-FREEZE-2026-08-22.md`` (by default the 9a export),
embeds with the local Ollama batch client, and upserts through the
production ``VectorStore`` ABC via the shared experiment storage
helper.  The builder resumes from the durable row count after
interruption: upserts commit per batch, so ``store.count()`` is a safe
checkpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_MANIFEST = (
    SCRIPT_DIR.parent
    / "9a-hybrid-retrieval-freshstack-langchain-2026-05-30"
    / "corpus"
    / "langchain_manifest.jsonl"
)
EXPERIMENT_ID = "exp10b"
CORPUS_ID = "freshstack-langchain-seed-20260530"


class OllamaEmbedder:
    """Batch embedding client for the local Ollama server."""

    def __init__(self, model: str, base_url: str, timeout: float) -> None:
        self.model = model
        self.base_url = base_url
        self.client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self.client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": texts},
            )
            response.raise_for_status()
            payload = response.json()
            embeddings = payload.get("embeddings")
            if embeddings is not None:
                return embeddings
            if "embedding" in payload:
                return [payload["embedding"]]
        except Exception:
            if len(texts) != 1:
                pass  # Fall through to the legacy one-prompt endpoint below.
            else:
                raise

        embeddings: list[list[float]] = []
        for text in texts:
            response = self.client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            response.raise_for_status()
            embeddings.append(response.json()["embedding"])
        return embeddings


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _clean_metadata(meta: dict[str, Any]) -> dict[str, str | int | float | bool]:
    clean: dict[str, str | int | float | bool] = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
        else:
            clean[key] = json.dumps(value, ensure_ascii=False)
    return clean


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dense-dir", type=Path, default=None)
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("EMBED_BATCH_SIZE", "100")))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--progress-every", type=int, default=1)
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    dense_dir = args.dense_dir or (output_dir / "lancedb_dense")

    rows = _read_manifest(args.manifest)
    if len(rows) < 10_000:
        raise SystemExit(f"Refusing to build invalid corpus: {len(rows)} < 10000 docs")

    model = os.getenv("EMBED_MODEL")
    if not model:
        raise SystemExit("EMBED_MODEL is required; set it in .env or the environment")

    from experiments._lib.storage import experiment_storage_config

    storage = experiment_storage_config(
        experiment_id=EXPERIMENT_ID,
        corpus=CORPUS_ID,
        provider="ollama",
        model=model,
        persist_dir=str(dense_dir),
        backend="lancedb",
    )
    collection_name = storage.collection_name

    if args.force:
        shutil.rmtree(dense_dir, ignore_errors=True)
    dense_dir.mkdir(parents=True, exist_ok=True)

    store = storage.build_store()
    if not store.collection_exists(collection_name) or args.force:
        store.create_collection(collection_name)
    existing = store.count(collection_name)
    if existing == len(rows) and not args.force:
        print(
            json.dumps(
                {"status": "reused", "chunks": existing, "store_dir": str(dense_dir)}, indent=2
            )
        )
        return
    if existing and args.force:
        store.delete_collection(collection_name)
        store.create_collection(collection_name)
        existing = 0

    print(
        f"Building LanceDB index {collection_name} in {dense_dir} "
        f"({len(rows)} docs, {existing} already present)",
        flush=True,
    )
    rows_to_add = list(enumerate(rows[existing:], start=existing))

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    timeout = float(os.getenv("EXP10B_OLLAMA_TIMEOUT", "120"))
    embedder = OllamaEmbedder(model=model, base_url=base_url, timeout=timeout)

    started = time.perf_counter()
    try:
        for batch_no, offset in enumerate(range(0, len(rows_to_add), args.batch_size), start=1):
            indexed_batch = rows_to_add[offset : offset + args.batch_size]
            batch = [row for _idx, row in indexed_batch]
            ids = [f"{row['freshstack_id']}::row{idx}" for idx, row in indexed_batch]
            docs = [row["text"] for row in batch]
            metas = [
                _clean_metadata(row["metadata"] | {"freshstack_id": row["freshstack_id"]})
                for row in batch
            ]
            if args.progress_every > 0 and (batch_no == 1 or batch_no % args.progress_every == 0):
                start_row = existing + offset + 1
                end_row = existing + offset + len(batch)
                print(
                    f"  embedding batch {batch_no}: rows {start_row}-{end_row}/{len(rows)}",
                    flush=True,
                )
            embeddings = embedder.embed_batch(docs)
            store.upsert_precomputed(
                collection_name,
                ids=ids,
                documents=docs,
                metadatas=metas,
                embeddings=embeddings,
                embedding_identity=storage.embedding_identity,
            )
            done = existing + min(offset + len(batch), len(rows_to_add))
            if done == len(rows) or done % max(args.batch_size * 10, 500) == 0:
                elapsed = time.perf_counter() - started
                new_done = min(offset + len(batch), len(rows_to_add))
                rate = new_done / elapsed if elapsed else 0.0
                print(f"  embedded {done}/{len(rows)} docs ({rate:.1f} docs/s)", flush=True)
    finally:
        embedder.close()

    summary = {
        "manifest": str(args.manifest),
        "backend": "lancedb",
        "collection_name": collection_name,
        "parent_docs": len(rows),
        "dense": {
            "status": "built",
            "chunks": store.count(collection_name),
            "store_dir": str(dense_dir),
            "embedding_model": model,
            "elapsed_seconds": round(time.perf_counter() - started, 2),
        },
        "hybrid_bm25": {
            "status": "shared-collection-at-query-time",
            "note": "BM25 is built in-process at query time; no second index required.",
        },
    }
    (output_dir / "index_build.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
