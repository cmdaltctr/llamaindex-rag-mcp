## Why

The RAG pipeline already works, but the audit found several low-risk correctness and reliability gaps that make behaviour harder to trust under real use: chunking can block the async server on large files, MCP search cannot expose the metadata filtering that retrieval already supports internally, score scales differ between filtered and unfiltered retrieval paths, and Ollama metadata extraction has no retry or structured-output hardening.

These fixes should be handled before larger algorithmic upgrades because they reduce operational risk without changing the core embedding model, ChromaDB vector dimensionality, or calibrated reranker threshold semantics.

## What Changes

- Offload synchronous chunk splitting to a worker thread in the async ingestion path so large documents do not block the event loop.
- Expose optional `metadata_filter` on the `search_documents` MCP tool and pass it through to `retrieval.search()`.
- Align or explicitly normalise score semantics between metadata-filtered direct ChromaDB search and the default LlamaIndex retrieval path.
- Add explicit error-envelope handling for `search_documents` so MCP handlers do not raise raw exceptions.
- Harden Ollama metadata extraction with bounded retry, configurable timeout/retry settings, and more robust JSON parsing.
- Keep all new MCP parameters optional with backwards-compatible defaults.
- Do not change the embedding model, ChromaDB collection dimension, reranker model, or reranker threshold scaling factor.

## Capabilities

### New Capabilities
- `mcp-search-filtering`: MCP search clients can optionally restrict retrieval using ChromaDB-compatible metadata filters.

### Modified Capabilities
- `async-ingestion`: Async ingestion remains responsive while chunking large files.
- `metadata-extraction`: Ollama metadata extraction is more resilient to transient failures and imperfect JSON responses.
- `score-normalisation`: Search result scores remain comparable across filtered and unfiltered retrieval paths.

## Impact

- `src/rag_mcp/ingestion.py`: async chunking offload.
- `src/rag_mcp/server.py`: `search_documents` signature and error envelope handling.
- `src/rag_mcp/retrieval.py`: metadata-filter plumbing and score normalisation.
- `src/rag_mcp/metadata_extractor.py`: Ollama retry, timeout configuration, JSON parsing hardening.
- `src/rag_mcp/config.py`: optional configuration for metadata extraction timeout/retry behaviour if needed.
- Tests covering async responsiveness, MCP metadata filtering, score comparability, and Ollama retry/JSON parsing.

No new heavy runtime dependency is required. If retry is implemented, prefer a small manual async retry loop over adding `tenacity`.
