## Why

Once Tier 1 reliability fixes have shipped, the audit found four small-to-medium changes that should noticeably improve retrieval quality without changing the embedding model or vector dimension: structure-aware chunking for Markdown files, a larger reranker candidate pool, a tuned chunk overlap, and a query-embedding cache for repeated queries.

These improvements are grounded in recent literature. Heading-aware chunking has been shown to improve retrieval on structured documents (Pham & Luong, 2025; Lavarec & Du, 2026). A larger reranker candidate pool follows the "Wide Net, Tight Filter" principle for cross-encoder reranking (Lim, 2026; Abirami et al., 2025). A 100-token overlap is the empirical sweet spot in the largest published chunking benchmark to date (Stäbler et al., 2025).

## What Changes

- Add a Markdown-aware chunking branch so `.md` files use a heading-aware node parser instead of the default `SentenceSplitter`, while non-Markdown files retain current behaviour.
- Raise the reranker candidate pool from `top_k * 2` to a configurable larger pool (default `max(50, top_k * 10)`) so the cross-encoder sees more candidates while the final returned set stays at `top_k`.
- Bump the default `CHUNK_OVERLAP` from 64 to 100 to better match recent empirical chunking benchmarks.
- Add an LRU cache for query embeddings so repeated identical queries do not re-hit Ollama for the embedding step.
- Keep all new MCP and CLI parameters optional with backwards-compatible defaults.
- Do not change the embedding model, vector dimension, ChromaDB schema, reranker model, or the calibrated ÷30 reranker threshold scaling factor.

## Capabilities

### New Capabilities

- `query-embedding-cache`: Repeated query embeddings are reused within a process to avoid redundant Ollama calls.
- `markdown-aware-chunking`: Markdown documents are chunked using heading-aware boundaries.

### Modified Capabilities

- `reranking`: Reranker candidate pool size is configurable and defaults to a larger pool to improve precision.
- `async-ingestion`: Ingestion routes Markdown files to the heading-aware chunker.

## Impact

- `src/rag_mcp/ingestion.py`: Markdown file branch in chunking.
- `src/rag_mcp/retrieval.py`: query-embedding cache and reranker fetch sizing.
- `src/rag_mcp/reranker.py`: optional refinements only if needed for batching at larger pool sizes.
- `src/rag_mcp/config.py`: `CHUNK_OVERLAP` default change and new `RERANK_FETCH_MULTIPLIER` / `RERANK_MAX_FETCH` env vars.
- Tests for: Markdown heading boundaries, configurable rerank fetch size, embedding cache hits/misses, default overlap regression.
- `AGENTS.md` reranker section updated to document the new fetch sizing behaviour and env vars.
