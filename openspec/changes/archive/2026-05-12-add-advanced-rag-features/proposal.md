## Why

The current RAG MCP server does basic vector search: embed query → cosine similarity → return top N chunks. This works but has two known weaknesses we observed in the AnythingLLM comparison:

1. **Precision** — cosine distance is a broad measure; the top 5 results often include chunks that are vaguely related but not actually relevant
2. **No score floor** — there's no way to say "don't return results below this confidence level," so even garbage chunks get returned

AnythingLLM addresses these with a cross-encoder reranker and a configurable similarity threshold. Both are self-contained, local-first improvements that don't require API keys or external services.

## What Changes

### New files

| File | Purpose |
|------|---------|
| `src/rag_mcp/reranker.py` | Cross-encoder reranker using ONNX (Xenova/ms-marco-MiniLM-L-6-v2) |

### Modified files

| File | Change |
|------|--------|
| `src/rag_mcp/retrieval.py` | Add reranker integration + similarity threshold filtering |
| `src/rag_mcp/server.py` | `search_documents` gains `similarity_threshold` and `rerank` params |
| `.env.example` | New env vars: `RERANK_MODEL`, `RERANK_ENABLED`, `SIMILARITY_THRESHOLD` |
| `pyproject.toml` | Add `optimum`, `onnxruntime`, `sentence-transformers` (for ONNX pipeline) |
| `README.md` | Document new parameters and how to configure/optimise them |

## Capabilities

### New capabilities
- `reranking`: Cross-encoder re-ranking for higher precision. Uses a small ONNX model (23MB) to re-score initial vector search results by evaluating query-chunk pairs directly.

### Modified capabilities
- `search-documents`: Gains two optional parameters:
  - `similarity_threshold` (float, 0.0–1.0) — minimum relevance score to include a result
  - `rerank` (bool) — enable cross-encoder re-ranking after initial search

## Non-Goals (explicitly excluded from this change)

- Hybrid search (BM25 + vector) — good but not needed yet
- Multi-query expansion — adds LLM latency, unclear benefit for this use case
- Semantic chunking — SentenceSplitter is adequate for now
- Query transformation / HyDE — power feature, not the bottleneck
- Namespace isolation / multi-tenant — if we need this, we'll do it separately
- Source window backfill — this is a host-side (OpenChamber) concern, not server-side

## Impact

- **Dependencies**: adds `optimum`, `onnxruntime`, and `sentence-transformers` (all already compatible with our macOS ARM setup)
- **Disk**: ~23MB for `ms-marco-MiniLM-L-6-v2` ONNX model (downloaded on first use)
- **Latency**: reranking adds ~50–200ms for 5–10 candidate chunks on a MacBook; off by default
- **Backward compatibility**: all new params optional with sensible defaults; existing integrations unchanged
