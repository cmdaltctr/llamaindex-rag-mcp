"""Build a mixed corpus for Experiment 10.1.

Ingests code files from `src/rag_mcp/` and documentation from `docs/` into a
ChromaDB collection in the experiment output directory. The corpus must contain
≥ 50 documents with pairwise similarity above 0.70 to produce a non-trivial
document graph.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import chromadb
import httpx
from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class OllamaEmbedder:
    def __init__(self, model: str, base_url: str, timeout: float) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        all_embeddings: list[list[float]] = []
        for text in texts:
            truncated = text[:8000]
            response = self.client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": truncated},
            )
            response.raise_for_status()
            payload = response.json()
            batch_embs = payload.get("embeddings")
            if batch_embs is not None:
                all_embeddings.extend(batch_embs)
            else:
                all_embeddings.append(payload["embedding"])
        return all_embeddings


def _collect_files(project_root: Path) -> list[dict[str, Any]]:
    """Collect code and doc files from the repo."""
    files: list[dict[str, Any]] = []

    # Code files from src/rag_mcp/
    code_dir = project_root / "src" / "rag_mcp"
    for py_file in sorted(code_dir.rglob("*.py")):
        text = py_file.read_text(encoding="utf-8", errors="replace")
        files.append({
            "id": f"code::{py_file.relative_to(project_root)}",
            "text": text,
            "metadata": {
                "content_type": "document",
                "category": "code",
                "file_path": str(py_file.relative_to(project_root)),
                "source": str(py_file),
            },
        })

    # Doc files from docs/
    doc_dir = project_root / "docs"
    for md_file in sorted(doc_dir.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8", errors="replace")
        files.append({
            "id": f"doc::{md_file.relative_to(project_root)}",
            "text": text,
            "metadata": {
                "content_type": "document",
                "category": "documentation",
                "file_path": str(md_file.relative_to(project_root)),
                "source": str(md_file),
            },
        })

    # Also include README.md and AGENTS.md
    for root_file in ["README.md", "AGENTS.md", "CONTRIBUTING.md", "CHANGELOG.md"]:
        path = project_root / root_file
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            files.append({
                "id": f"doc::{root_file}",
                "text": text,
                "metadata": {
                    "content_type": "document",
                    "category": "documentation",
                    "file_path": root_file,
                    "source": str(path),
                },
            })

    return files


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, default=SCRIPT_DIR)
    parser.add_argument("--collection-name", default="documents")
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("EMBED_BATCH_SIZE", "50")))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    exp_dir = args.experiment_dir.resolve()
    output_dir = exp_dir / "output"
    chroma_dir = output_dir / "chroma_mixed"
    output_dir.mkdir(parents=True, exist_ok=True)

    files = _collect_files(PROJECT_ROOT)
    code_count = sum(1 for f in files if f["metadata"]["category"] == "code")
    doc_count = sum(1 for f in files if f["metadata"]["category"] == "documentation")
    print(f"Collected {len(files)} files: {code_count} code, {doc_count} docs", flush=True)

    if code_count < 30:
        print(f"WARNING: Only {code_count} code files (expected ≥ 30)", flush=True)
    if doc_count < 20:
        print(f"WARNING: Only {doc_count} doc files (expected ≥ 20)", flush=True)

    if args.force:
        import shutil
        shutil.rmtree(chroma_dir, ignore_errors=True)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(args.collection_name)

    if collection.count() == len(files) and not args.force:
        print(f"Collection already has {collection.count()} docs, skipping", flush=True)
        return

    if args.force and collection.count() > 0:
        client.delete_collection(args.collection_name)
        collection = client.get_or_create_collection(args.collection_name)

    model = os.getenv("EMBED_MODEL")
    if not model:
        raise SystemExit("EMBED_MODEL is required; set it in .env or the environment")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    timeout = float(os.getenv("EXP101_OLLAMA_TIMEOUT", "120"))
    embedder = OllamaEmbedder(model=model, base_url=base_url, timeout=timeout)

    started = time.perf_counter()
    try:
        for offset in range(0, len(files), args.batch_size):
            batch = files[offset: offset + args.batch_size]
            ids = [f["id"] for f in batch]
            docs = [f["text"] for f in batch]
            metas = [_clean_metadata(f["metadata"]) for f in batch]
            print(f"  embedding batch {offset // args.batch_size + 1}: {offset + 1}-{offset + len(batch)}/{len(files)}", flush=True)
            embeddings = embedder.embed_batch(docs)
            collection.add(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)
    finally:
        embedder.close()

    elapsed = time.perf_counter() - started
    summary = {
        "total_files": len(files),
        "code_files": code_count,
        "doc_files": doc_count,
        "collection_count": collection.count(),
        "chroma_dir": str(chroma_dir),
        "embedding_model": model,
        "elapsed_seconds": round(elapsed, 2),
    }
    (output_dir / "corpus_build.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
