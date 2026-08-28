"""Build Chroma indexes for Experiment 9a using metadata-preserving ingestion.

Storage goes through the shared experiment helper
(``experiments/_lib/storage.py``) and the production vector-store
factory, so the same script serves ``CHROMA_MODE=local`` (one persist
directory per index) and ``CHROMA_MODE=cloud`` (named collections in a
shared database).  Embeddings are computed by the local Ollama batch
client below and upserted with precomputed vectors.
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
sys.path.insert(0, str(PROJECT_ROOT / "src"))


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


class OllamaEmbedder:
    def __init__(self, model: str, base_url: str, timeout: float) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
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
                # Fall through to the legacy one-prompt endpoint below.
                pass
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


def _build_chroma(
    rows: list[dict[str, Any]],
    persist_dir: Path,
    *,
    collection_name: str | None,
    batch_size: int,
    force: bool,
    progress_every: int = 1,
) -> dict[str, Any]:
    from experiments._lib.storage import experiment_storage_config

    model = os.getenv("EMBED_MODEL")
    if not model:
        raise SystemExit("EMBED_MODEL is required; set it in .env or the environment")

    storage = experiment_storage_config(
        experiment_id="exp9a",
        corpus="freshstack",
        provider="ollama",
        model=model,
        persist_dir=str(persist_dir),
    )
    # The deterministic immutable-index name is the default; an explicit
    # --collection-name override remains for legacy local indexes.
    collection_name = collection_name or storage.collection_name

    # Reset local storage BEFORE constructing the store: the local
    # factory opens the on-disk Chroma client, and deleting the
    # directory under an open client leaves writes the next process
    # cannot see.
    if force and storage.mode == "local":
        shutil.rmtree(persist_dir, ignore_errors=True)
    persist_dir.mkdir(parents=True, exist_ok=True)

    store = storage.build_store()

    if force and storage.mode == "cloud" and store.collection_exists(collection_name):
        store.delete_collection(collection_name)

    store.create_collection(collection_name)
    existing = store.count(collection_name)
    if existing == len(rows) and not force:
        return {
            "status": "reused",
            "chunks": existing,
            "persist_dir": str(persist_dir),
            "collection_name": collection_name,
            "mode": storage.mode,
        }
    if existing and force:
        store.delete_collection(collection_name)
        store.create_collection(collection_name)
        existing = 0

    if existing and not force:
        print(f"  resuming existing collection with {existing} docs", flush=True)

    # The builder writes manifest rows in order.  On tool timeout the durable
    # Chroma count is therefore a safe checkpoint and avoids an expensive full
    # collection scan just to discover existing IDs.
    rows_to_add = list(enumerate(rows[existing:], start=existing))
    if not rows_to_add:
        return {
            "status": "reused",
            "chunks": store.count(collection_name),
            "persist_dir": str(persist_dir),
            "collection_name": collection_name,
            "mode": storage.mode,
        }

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    timeout = float(os.getenv("EXP9A_OLLAMA_TIMEOUT", "120"))
    embedder = OllamaEmbedder(model=model, base_url=base_url, timeout=timeout)

    started = time.perf_counter()
    try:
        for batch_no, offset in enumerate(range(0, len(rows_to_add), batch_size), start=1):
            indexed_batch = rows_to_add[offset : offset + batch_size]
            batch = [row for _idx, row in indexed_batch]
            ids = [f"{row['freshstack_id']}::row{idx}" for idx, row in indexed_batch]
            docs = [row["text"] for row in batch]
            metas = [
                _clean_metadata(row["metadata"] | {"freshstack_id": row["freshstack_id"]})
                for row in batch
            ]
            if progress_every > 0 and (batch_no == 1 or batch_no % progress_every == 0):
                start_row = existing + offset + 1
                end_row = existing + offset + len(batch)
                print(
                    f"  embedding batch {batch_no}: rows {start_row}-{end_row}/{len(rows)}",
                    flush=True,
                )
            embeddings = embedder.embed_batch(docs)
            if progress_every > 0 and (batch_no == 1 or batch_no % progress_every == 0):
                print(f"  writing batch {batch_no} to Chroma", flush=True)
            store.upsert_precomputed(
                collection_name,
                ids=ids,
                documents=docs,
                metadatas=metas,
                embeddings=embeddings,
                embedding_identity=storage.embedding_identity,
            )
            done = existing + min(offset + len(batch), len(rows_to_add))
            if done == len(rows) or done % max(batch_size * 10, 500) == 0:
                elapsed = time.perf_counter() - started
                new_done = min(offset + len(batch), len(rows_to_add))
                rate = new_done / elapsed if elapsed else 0.0
                print(f"  embedded {done}/{len(rows)} docs ({rate:.1f} docs/s)", flush=True)
    finally:
        embedder.close()

    return {
        "status": "built",
        "chunks": store.count(collection_name),
        "persist_dir": str(persist_dir),
        "collection_name": collection_name,
        "mode": storage.mode,
        "embedding_model": model,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, default=SCRIPT_DIR)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--dense-dir", type=Path, default=None)
    parser.add_argument("--hybrid-dir", type=Path, default=None)
    parser.add_argument("--collection-name", default=None)
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("EMBED_BATCH_SIZE", "100")))
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--progress-every", type=int, default=1, help="Print every N embedding batches"
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    exp_dir = args.experiment_dir.resolve()
    manifest = args.manifest or (exp_dir / "corpus" / "langchain_manifest.jsonl")
    output_dir = exp_dir / "output"
    dense_dir = args.dense_dir or (output_dir / "chroma_dense")
    hybrid_dir = args.hybrid_dir or (output_dir / "chroma_hybrid_bm25")
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_manifest(manifest)
    if len(rows) < 10_000:
        raise SystemExit(f"Refusing to build invalid corpus: {len(rows)} < 10000 docs")

    print(f"Building dense Chroma index from {manifest} ({len(rows)} docs)")
    dense_result = _build_chroma(
        rows,
        dense_dir,
        collection_name=args.collection_name,
        batch_size=args.batch_size,
        force=args.force,
        progress_every=args.progress_every,
    )

    if dense_result.get("mode") == "cloud":
        # Cloud mode: the deterministic collection name does not depend
        # on the persist directory, so the dense and hybrid cells share
        # one collection — the directory copy is a local-only concern.
        hybrid_result = {
            "status": "shared-collection",
            "persist_dir": str(hybrid_dir),
            "chunks": dense_result["chunks"],
            "collection_name": dense_result["collection_name"],
        }
    elif args.force or not hybrid_dir.exists():
        shutil.rmtree(hybrid_dir, ignore_errors=True)
        print(f"Copying dense Chroma index to hybrid path: {hybrid_dir}")
        shutil.copytree(dense_dir, hybrid_dir)
        hybrid_result = {
            "status": "copied-from-dense",
            "persist_dir": str(hybrid_dir),
            "chunks": len(rows),
        }
    else:
        from experiments._lib.storage import experiment_storage_config

        model = os.getenv("EMBED_MODEL")
        if not model:
            raise SystemExit("EMBED_MODEL is required; set it in .env or the environment")
        hybrid_storage = experiment_storage_config(
            experiment_id="exp9a",
            corpus="freshstack",
            provider="ollama",
            model=model,
            persist_dir=str(hybrid_dir),
        )
        hybrid_store = hybrid_storage.build_store()
        hybrid_name = args.collection_name or hybrid_storage.collection_name
        count = hybrid_store.count(hybrid_name)
        hybrid_result = {"status": "reused", "persist_dir": str(hybrid_dir), "chunks": count}

    summary = {
        "manifest": str(manifest),
        "collection_name": dense_result.get("collection_name", args.collection_name),
        "parent_docs": len(rows),
        "dense": dense_result,
        "hybrid_bm25": hybrid_result,
        "note": "Hybrid BM25 uses the same Chroma documents; sparse BM25 index is built at query time.",
    }
    (output_dir / "index_build.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
