"""Build indexes for Experiment 13: HARD_TECHNICAL_THRESHOLD calibration.

Builds a combined ChromaDB index from FreshStack LangChain corpus and
Qasper semantic corpus.
"""

from __future__ import annotations

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
    """Minimal Ollama embedder for experiment scripts."""

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


def _load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.exists():
        return []
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _load_qasper_corpus(qasper_gt: Path) -> tuple[list[str], list[dict[str, Any]]]:
    """Load Qasper documents from corpus directory."""
    corpus_dir = SCRIPT_DIR / "corpus"
    if not corpus_dir.exists():
        return [], []
    gt = json.loads(qasper_gt.read_text(encoding="utf-8"))
    qrels = gt.get("qrels", {})

    doc_ids: set[str] = set()
    for qid, rels in qrels.items():
        for doc_id in rels:
            doc_ids.add(doc_id)

    docs: list[str] = []
    metas: list[dict[str, Any]] = []
    for doc_id in sorted(doc_ids):
        doc_path = corpus_dir / f"{doc_id}.md"
        if doc_path.exists():
            docs.append(doc_path.read_text(encoding="utf-8"))
            metas.append({"id": doc_id, "source": "qasper"})

    return docs, metas


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    import chromadb

    embed_model = os.getenv("EMBED_MODEL", "qwen3-embedding:0.6b")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    chroma_dir = str(SCRIPT_DIR / "output" / "chroma_combined")

    # Load FreshStack manifest
    fs_manifest_path = SCRIPT_DIR / "freshstack-manifest.jsonl"
    if not fs_manifest_path.exists():
        # Try Exp 9a's manifest
        fs_manifest_path = (
            SCRIPT_DIR.parent
            / "9a-hybrid-retrieval-freshstack-langchain-2026-05-30"
            / "freshstack-manifest.jsonl"
        )

    fs_docs: list[dict[str, Any]] = _load_manifest(fs_manifest_path) if fs_manifest_path.exists() else []
    print(f"FreshStack docs: {len(fs_docs)}", flush=True)

    # Load Qasper corpus
    qasper_gt = SCRIPT_DIR / "output" / "qasper_qrels.json"
    qasper_texts, qasper_metas = _load_qasper_corpus(qasper_gt) if qasper_gt.exists() else ([], [])
    print(f"Qasper docs: {len(qasper_texts)}", flush=True)

    # Combine
    all_texts: list[str] = []
    all_ids: list[str] = []
    all_metas: list[dict[str, Any]] = []

    for doc in fs_docs:
        all_texts.append(doc.get("text", ""))
        all_ids.append(doc.get("id", f"fs_{len(all_ids)}"))
        all_metas.append({"id": doc.get("id", ""), "source": "freshstack"})

    for text, meta in zip(qasper_texts, qasper_metas):
        all_texts.append(text)
        all_ids.append(meta["id"])
        all_metas.append(meta)

    print(f"Total documents: {len(all_texts)}", flush=True)

    # Embed
    print(f"Embedding with {embed_model}...", flush=True)
    embedder = OllamaEmbedder(embed_model, ollama_url)

    batch_size = int(os.getenv("EMBED_BATCH_SIZE", "50"))
    all_embeddings: list[list[float]] = []
    for i in range(0, len(all_texts), batch_size):
        batch = all_texts[i:i + batch_size]
        embs = embedder.embed(batch)
        all_embeddings.extend(embs)
        print(f"  Embedded {i + len(batch)}/{len(all_texts)}", flush=True)

    # Store in ChromaDB
    print("Storing in ChromaDB...", flush=True)
    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_or_create_collection("documents")

    # Clear existing
    try:
        collection.delete(ids=collection.get()["ids"])
    except Exception:
        pass

    collection.add(
        ids=all_ids,
        documents=all_texts,
        embeddings=all_embeddings,
        metadatas=all_metas,
    )

    print(f"Stored {len(all_ids)} documents in ChromaDB at {chroma_dir}", flush=True)

    # Write index build metadata
    build_info = {
        "built_at_unix": time.time(),
        "embed_model": embed_model,
        "total_docs": len(all_ids),
        "freshstack_docs": len(fs_docs),
        "qasper_docs": len(qasper_texts),
        "chroma_dir": chroma_dir,
    }
    (SCRIPT_DIR / "output" / "index_build.json").write_text(
        json.dumps(build_info, indent=2), encoding="utf-8",
    )
    print("Index build metadata written", flush=True)


if __name__ == "__main__":
    main()
