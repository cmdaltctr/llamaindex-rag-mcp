# ADR-023: Document graph via embedding similarity

**Date:** 2026-01-15  
**Status:** Proposed  
**Change:** `add-fast-context-codebase-map`

## Context

The `get_codebase_map` MCP tool needs a document graph to detect topic clusters and cross-links between documentation and code. This requires measuring semantic similarity between document chunks already stored in ChromaDB.

## Decision

Use **pairwise cosine similarity** between existing ChromaDB embeddings to build document graph edges, combined with **metadata-based edges** (shared categories, shared keywords) and **heading hierarchy edges**.

### Edge Types

1. **Similarity edges** (weight = cosine similarity): Chunks with cosine similarity ≥ `DOC_SIMILARITY_THRESHOLD` (default 0.85) get an edge. Only `document/*` content-type chunks are compared — code chunks are excluded.

2. **Category edges** (weight = 1.0): Chunks sharing the same `category` metadata field get an edge.

3. **Keyword edges** (weight = 0.5): Chunks sharing any keyword in their `keywords` metadata field get an edge, with the shared keywords stored on the edge.

4. **Heading hierarchy edges** (weight = 1.0): Parent-child relationships derived from the `header_path` metadata field set by the Markdown ingestion pipeline.

### Community Detection

Louvain community detection on the undirected document graph. Communities are labelled with their most common category. Communities with fewer than 5 chunks are merged.

### Cross-Links

Cross-links between code and document communities use three matching strategies:
- **Filename matching** (≥2 path segments required to avoid false positives)
- **Symbol matching** (exported class/function names appearing in document file paths)
- **Category keyword overlap** (code directory names matching document categories/keywords)

## Consequences

- **Positive:** Reuses existing embeddings — no additional model calls.
- **Positive:** Metadata edges capture relationships that similarity alone would miss.
- **Negative:** Pairwise similarity is O(n²) — may be slow for large collections.
- **Mitigation:** Threshold filtering reduces edge count; computation is offloaded to a worker thread.
- **Negative:** `DOC_SIMILARITY_THRESHOLD` default (0.85) needs calibration experiment.
- **Mitigation:** Configurable via environment variable; experiment task 10.1 will calibrate.

## Alternatives Considered

- **LLM-based topic modelling:** Non-deterministic, requires network. Rejected.
- **BM25 similarity:** Already available via hybrid retrieval extra, but operates on text, not embeddings. Rejected for inconsistency with embedding-based retrieval.
- **Hierarchical clustering:** More rigid than Louvain. Rejected — Louvain allows overlapping community structure.
