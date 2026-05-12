"""Semantic search over the ChromaDB-backed vector index."""

from __future__ import annotations

import os

import chromadb
from dotenv import load_dotenv
from llama_index.core import Settings, VectorStoreIndex
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

from .reranker import CrossEncoderReranker

load_dotenv()

# ── Embedding model (local via Ollama) ──────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "nomic-embed-text")

Settings.embed_model = OllamaEmbedding(
    model_name=EMBED_MODEL_NAME,
    base_url=OLLAMA_BASE_URL,
    embed_batch_size=10,
)
# ────────────────────────────────────────────────────────────────────────

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "documents")
TOP_K = int(os.getenv("TOP_K", "5"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").lower() == "true"
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.0"))


def search(
    query: str,
    top_k: int = TOP_K,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    rerank: bool = RERANK_ENABLED,
) -> list[dict]:
    """Run a semantic similarity search over every indexed document.

    Args:
        query: Free-text search query.
        top_k: Maximum number of chunks to return (default from env or 5).
        similarity_threshold: Minimum score to include a result
            (0.0 = no filtering, default from env).
        rerank: If True, re-score results with the cross-encoder
            reranker for better precision (default from env).

    Returns:
        A list of dicts sorted by descending relevance score, each with:
            score      – float (0–1, vector similarity or reranker score)
            source     – source file path
            page_label – page number (or None)
            text       – the chunk text
            reranked   – bool (True if cross-encoder re-scored the result)
    """
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    try:
        collection = db.get_collection(COLLECTION_NAME)
    except Exception:
        return []

    if collection.count() == 0:
        return []

    vector_store = ChromaVectorStore(chroma_collection=collection)
    index = VectorStoreIndex.from_vector_store(vector_store)

    # Fetch more candidates when reranking so the cross-encoder
    # has a meaningful pool to re-score.
    fetch_k = top_k * 2 if rerank else top_k
    retriever = index.as_retriever(similarity_top_k=fetch_k)
    nodes = retriever.retrieve(query)

    results: list[dict] = []
    for item in nodes:
        node = item.node
        meta = node.metadata
        results.append(
            {
                "score": float(item.score) if item.score is not None else 0.0,
                "source": (
                    meta.get("file_path")
                    or meta.get("file_name")
                    or "unknown"
                ),
                "page_label": meta.get("page_label"),
                "text": node.text,
                "reranked": False,
            }
        )

    # Optional: re-score with cross-encoder reranker.
    if rerank and results:
        reranker = CrossEncoderReranker()
        results = reranker.rerank(query, results, top_k=top_k)
        # Propagate the reranked flag from the internal _reranked key.
        for r in results:
            r["reranked"] = r.pop("_reranked", False)

    # Filter by similarity threshold (applies after reranking).
    if similarity_threshold > 0.0:
        results = [r for r in results if r["score"] >= similarity_threshold]

    results.sort(key=lambda r: r["score"], reverse=True)
    return results
