## Why

The audit's most evidence-backed recommendation is hybrid retrieval. The existing pure-dense vector search has a documented failure mode: in `experiments/reranker-threshold-calibration-2026-05-12/`, a correct chunk ("Colosseum") was scored only 0.015 by the reranker because it was buried below the dense-retrieval cut-off and the reranker never received it as a candidate. Rare-term, exact-match, and code/legal/identifier queries are the canonical weakness of dense-only retrieval.

Recent literature converges on the same conclusion. Mala, Gezici & Giannotti (2025) report that weighted Reciprocal Rank Fusion achieves the highest accuracy and lowest hallucination rate on HaluBench. Airy & Baranwal (2025) report a 93.3% hallucination reduction with hybrid RAG. Akarsu et al. (2026) show BM25 outperforming dense retrieval on financial documents. Abirami et al. (2025) demonstrate hybrid RRF lifting Recall@100 to 0.997. The original RRF paper (Cormack, Clarke & Buettcher, 2009) remains the de facto fusion algorithm.

Adding a sparse retriever and fusing results via Reciprocal Rank Fusion before the existing reranker reuses the calibrated ÷30 threshold scaling unchanged, because the reranker continues to score `(query, chunk)` pairs the same way; hybrid only changes which candidates enter the pool.

## What Changes

- Introduce an opt-in hybrid retrieval mode that combines dense vector search with a sparse keyword retriever (BM25 or ChromaDB-native sparse vectors, depending on detected ChromaDB capabilities).
- Fuse the dense and sparse rankings using Reciprocal Rank Fusion with the standard constant `k=60` to produce a single combined candidate list.
- Feed the fused candidate list into the existing cross-encoder reranker pipeline unchanged.
- Add a `hybrid: bool = False` parameter to the `search_documents` MCP tool and to `retrieval.search()`.
- Detect ChromaDB version capabilities at startup to decide between native sparse-vector path and an in-memory BM25 fallback (e.g., via `rank_bm25`), without requiring a database migration to use the in-memory path.
- Keep the calibrated reranker threshold scaling factor and reranker model unchanged.
- Do not change the embedding model, vector dimension, or any existing default behaviour when `hybrid=False`.

## Capabilities

### New Capabilities

- `hybrid-retrieval`: Optional dense + sparse retrieval with reciprocal rank fusion, integrated with the existing reranker.

### Modified Capabilities

- `reranking`: Reranker accepts a fused dense+sparse candidate set as input when hybrid retrieval is enabled.

## Impact

- `src/rag_mcp/retrieval.py`: hybrid query path, RRF fusion, hybrid search entry point.
- `src/rag_mcp/ingestion.py`: optional sparse-index construction or sparse-vector write alongside dense vectors.
- `src/rag_mcp/config.py`: `HYBRID_ENABLED`, `HYBRID_RRF_K`, `HYBRID_SPARSE_BACKEND` env vars and capability-detection logic.
- `src/rag_mcp/server.py`: `hybrid` parameter on `search_documents`.
- New module `src/rag_mcp/sparse_retriever.py` (or equivalent) for the BM25 fallback path.
- `pyproject.toml`: optional addition of `rank_bm25` if the BM25 fallback path is required.
- Tests for the rare-term failure case, RRF math, hybrid integration with reranker, capability detection, and backwards compatibility when `hybrid=False`.
- A new experiment under `experiments/hybrid-retrieval-<date>/` with the Colosseum failure case as a regression target.
