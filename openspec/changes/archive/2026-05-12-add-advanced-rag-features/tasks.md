## Phase 1 — Core Implementation

- [x] 1.1 Add new dependencies to `pyproject.toml`: `optimum`, `onnxruntime`, `sentence-transformers`
- [x] 1.2 Create `src/rag_mcp/reranker.py` with `CrossEncoderReranker` class:
  - Singleton init (lazy load model + tokenizer)
  - `rerank(query, nodes, top_k) -> list[dict]`
  - Graceful fallback on model failure
- [x] 1.3 Update `src/rag_mcp/retrieval.py`:
  - Integrate reranker into `search()` pipeline
  - Add `similarity_threshold` filtering
  - Fetch `top_k * 2` candidates when reranking is enabled
  - Expose `rerank` and `similarity_threshold` parameters
- [x] 1.4 Update `src/rag_mcp/server.py`:
  - Add `similarity_threshold` (float, default 0.0) to `search_documents` tool
  - Add `rerank` (bool, default False) to `search_documents` tool
- [x] 1.5 Update `.env.example` with new config options:
  - `RERANK_MODEL`, `RERANK_ENABLED`, `SIMILARITY_THRESHOLD`
- [x] 1.6 Update `README.md` with new parameters and usage examples

## Verification

- [x] 2.1 Regression: basic ingest → search → list flow unchanged
- [x] 2.2 Reranker: `search_documents(query, rerank=True)` returns re-scored results (verify scores differ from vector search)
- [x] 2.3 Threshold: `search_documents(query, similarity_threshold=0.9)` returns empty or fewer results
- [x] 2.4 Fallback: simulate model load failure → returns un-reranked results without crashing
- [x] 2.5 MCP Inspector discovers new parameters correctly
- [x] 2.6 `uv sync` installs new dependencies without errors
