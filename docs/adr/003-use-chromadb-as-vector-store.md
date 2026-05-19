# ADR-003: Use ChromaDB as Vector Store

**Date:** 2026-05-11
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Git Commits:** `5594176`

## Context

The RAG pipeline needs a vector store to persist document embeddings between
sessions. Requirements include: local-only operation (no cloud databases),
persistent on-disk storage, support for metadata filtering, and compatibility
with LlamaIndex's `VectorStoreIndex` abstraction. The store must handle
moderate-scale personal document collections (hundreds to low thousands of
documents).

## Decision

Use **ChromaDB** (`chromadb` ≥ 0.5.0) with `PersistentClient` for local,
on-disk vector storage.

- Vectors stored in a configurable directory (`CHROMA_PERSIST_DIR`, default `./chroma_db`)
- Collection name configurable via `COLLECTION_NAME` (default `documents`)
- LlamaIndex integration via `ChromaVectorStore` adapter
- Metadata (source file path, page label) stored alongside vectors for
  result attribution

## Consequences

### Positive
- Zero-configuration local persistence; no server process required
- Built-in metadata storage enables source attribution in search results
- Works entirely offline — no network required after initial setup
- `EphemeralClient` variant enables fast in-memory testing without disk I/O
- Lightweight compared to dedicated vector databases (Milvus, Weaviate)

### Negative
- ChromaDB locks the vector dimension at collection creation time — switching
  embedding models requires deleting the entire store and re-indexing
- Not designed for high-concurrency workloads or distributed deployments
- SQLite-based persistence can be slow with very large collections (>100K chunks)

### Neutral
- Users must manage the `chroma_db/` directory (backups, cleanup, model switches)
- The test suite uses `EphemeralClient` monkeypatching to avoid disk I/O

## Alternatives Considered

| Tool | Rejected Because |
|------|-----------------|
| **FAISS** | No built-in persistence, no metadata support, C++ dependency |
| **Qdrant** | Requires running a separate server process |
| **Milvus** | Overkill for personal/local document collections |
| **Pinecone** | Cloud-only — violates the "no API keys, fully local" constraint |
| **pgvector** | Requires PostgreSQL server, adds operational complexity |

## References

- `src/rag_mcp/ingestion.py` — ChromaDB collection creation and document indexing
- `src/rag_mcp/retrieval.py` — ChromaDB query for semantic search
- `tests/conftest.py` — `EphemeralClient` monkeypatch for test isolation
