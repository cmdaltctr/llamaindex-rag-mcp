# ADR-002: Adopt LlamaIndex for RAG Pipeline

**Date:** 2026-05-11
**Status:** Accepted
**Update:** Cloud constraint superseded by ADR-024 — local-first, cloud allowed as opt-in.
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Git Commits:** `5594176`

## Context

The project needs a framework for document loading, text chunking, embedding,
and retrieval. The core pipeline must support multiple file formats (PDF, DOCX,
PPTX, TXT, Markdown, HTML, CSV), produce consistent text chunks, and integrate
with a local embedding model (Ollama). The server must remain fully local — no
cloud API calls, no API keys.

Building a RAG pipeline from scratch requires substantial effort for document
parsing, chunking strategies, and vector store integration. Several mature
frameworks exist in the Python ecosystem.

## Decision

Use **LlamaIndex** (`llama-index` ≥ 0.11.0) as the RAG orchestration framework.

- `SimpleDirectoryReader` for multi-format document loading
- `SentenceSplitter` for text chunking (configurable `chunk_size` and `chunk_overlap`)
- `VectorStoreIndex` for indexing and retrieval
- `OllamaEmbedding` for local embeddings via the `llama-index-embeddings-ollama` package
- `ChromaVectorStore` integration via `llama-index-vector-stores-chroma`

## Consequences

### Positive

- Production-grade document readers for all supported formats out of the box
- Clean abstraction over embedding and retrieval; swapping models or vector
  stores requires minimal code changes
- Active community and extensive documentation
- Local-first: works entirely with Ollama, no API keys needed

### Negative

- LlamaIndex dependency tree is large (transitive dependencies)
- Tight coupling to LlamaIndex abstractions (`VectorStoreIndex`, `StorageContext`)
  means migrating away would require rewriting ingestion and retrieval layers

### Neutral

- `Settings.embed_model` is set globally via LlamaIndex's global settings;
  tests must mock this before importing application modules

## Alternatives Considered

| Tool                      | Rejected Because                                                             |
| ------------------------- | ---------------------------------------------------------------------------- |
| **LangChain**             | Heavier, more opinionated, steeper learning curve for simple RAG             |
| **Haystack**              | More suited to production pipelines with multiple processing stages          |
| **Custom implementation** | Significant effort for document parsing, chunking, and vector store adapters |
| **txtai**                 | Smaller ecosystem, fewer document readers                                    |

## References

- `src/rag_mcp/ingestion.py` — document loading, chunking, and indexing logic
- `src/rag_mcp/retrieval.py` — semantic search using LlamaIndex retriever
- `src/rag_mcp/config.py` — embedding model configuration via `Settings.embed_model`
