"""Build indexes for Experiment 14: LiteParse vs pypdf on Qasper.

Builds separate ChromaDB indexes for each PDF reader type.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class OllamaEmbedder:
    def __init__(self, model: str, base_url: str) -> None:
        import requests

        self.model = model
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()

    def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            resp = self._session.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": text},
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings:
                results.append(embeddings[0])
            else:
                results.append([])
        return results


def _load_corpus(corpus_dir: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for md_file in sorted(corpus_dir.glob("*.md")):
        docs.append({
            "id": md_file.stem,
            "text": md_file.read_text(encoding="utf-8"),
        })
    return docs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reader", choices=["pypdf", "liteparse"], required=True)
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    import chromadb

    embed_model = os.getenv("EMBED_MODEL", "qwen3-embedding:0.6b")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    chroma_dir = str(SCRIPT_DIR / "output" / f"chroma_{args.reader}")

    corpus_dir = SCRIPT_DIR / "qasper_pdfs"
    if not corpus_dir.exists():
        raise SystemExit(f"Corpus directory not found: {corpus_dir}. Run prepare_qasper_pdfs.py first.")

    docs = _load_corpus(corpus_dir)
    print(f"Loaded {len(docs)} documents from {corpus_dir}", flush=True)

    # Set PDF_READER env for this build
    os.environ["PDF_READER"] = args.reader

    # Embed
    print(f"Embedding with {embed_model} (reader={args.reader})...", flush=True)
    embedder = OllamaEmbedder(embed_model, ollama_url)

    batch_size = int(os.getenv("EMBED_BATCH_SIZE", "50"))
    all_embeddings: list[list[float]] = []
    ingestion_start = time.perf_counter()
    for i in range(0, len(docs), batch_size):
        batch_texts = [d["text"] for d in docs[i:i + batch_size]]
        embs = embedder.embed(batch_texts)
        all_embeddings.extend(embs)
        print(f"  Embedded {i + len(batch_texts)}/{len(docs)}", flush=True)
    ingestion_time = time.perf_counter() - ingestion_start

    # Store in ChromaDB
    print(f"Storing in ChromaDB at {chroma_dir}...", flush=True)
    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_or_create_collection("documents")

    try:
        collection.delete(ids=collection.get()["ids"])
    except Exception:
        pass

    collection.add(
        ids=[d["id"] for d in docs],
        documents=[d["text"] for d in docs],
        embeddings=all_embeddings,
        metadatas=[{"id": d["id"], "reader": args.reader} for d in docs],
    )

    print(f"Stored {len(docs)} documents. Ingestion time: {ingestion_time:.1f}s", flush=True)

    build_info = {
        "built_at_unix": time.time(),
        "reader": args.reader,
        "embed_model": embed_model,
        "total_docs": len(docs),
        "ingestion_time_s": round(ingestion_time, 2),
        "chroma_dir": chroma_dir,
    }
    (SCRIPT_DIR / "output" / f"index_build_{args.reader}.json").write_text(
        json.dumps(build_info, indent=2), encoding="utf-8",
    )
    print("Index build metadata written", flush=True)


if __name__ == "__main__":
    main()
