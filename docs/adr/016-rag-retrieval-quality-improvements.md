# ADR-016: RAG Retrieval Quality Improvements

**Status**: Accepted
**Date**: 2026-05-27
**Change**: `2-rag-retrieval-quality-improvements`
**Deciders**: Dr Muhammad Aizat Bin Md Hawari
**Git Commits**: `0b91d03`, `abea2b5`, `483c4dd`, `796b132`, `8214605` (feature branch `feat/rag-retrieval-quality-tier-2`)

## Context

The Tier 1 reliability fixes (ADR-015) closed the comparability and
robustness gaps in the existing retrieval pipeline. Beyond those, the
audit identified four small-to-medium quality improvements grounded in
recent literature that do not require an embedding-model swap, vector
dimension change, or reranker recalibration.

The current ingestion path uses a single `SentenceSplitter` with
`chunk_size=512`, `chunk_overlap=64` for every file type — fine on prose,
weaker on structured Markdown where heading boundaries carry meaning
(Pham & Luong 2025; Lavarec & Du 2026). The reranker fetches only
`top_k * 2 = 10` candidates, starving the cross-encoder of pool depth and
producing the documented Colosseum failure case (`experiments/reranker-threshold-calibration-2026-05-12/`)
where a correct chunk scored only 0.015 because dense retrieval ranked it
below the cut-off (Lim 2026; Abirami et al. 2025). The default 64-token
overlap is below the 100-token sweet spot reported by Stäbler et al.
(2025). Every search re-embeds its query through Ollama, even when the
agent loop just embedded the same query a moment ago.

## Decision

Adopt four sub-decisions, all opt-out friendly via env vars, all
preserving the calibrated ÷30 reranker threshold scaling from ADR-005:

1. **Markdown branch chains `MarkdownNodeParser` → `SentenceSplitter`.**
   When a file has the `.md` extension, ingestion routes through
   `MarkdownNodeParser` first to respect heading boundaries, then through
   `SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)`
   to cap heading-bounded sections that exceed `CHUNK_SIZE`. Non-Markdown
   files retain the existing `SentenceSplitter`-only path. The chained
   structure is required because `MarkdownNodeParser` alone will emit
   one giant node per long heading section, defeating embedding-batch
   sizing.

2. **Reranker fetch pool grows to `max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)`.**
   Replaces the static `top_k * 2` with a configurable wider pool.
   Defaults: `RERANK_MAX_FETCH=50`, `RERANK_FETCH_MULTIPLIER=10`.
   `fetch_k` is clamped to `min(fetch_k, collection.count())` so small
   collections do not over-fetch. Implements the "Wide Net, Tight Filter"
   pattern. Latency target verified empirically by re-running the
   reranker calibration script (`experiments/5-reranker-pool-sizing-2026-05-27/`):

   - Pre-change baseline (`(20, 2)`, fetch_k=20): post-warmup mean **354 ms**, P95 **475 ms**
   - Post-change candidate (`(50, 10)`, fetch_k=50): post-warmup mean **298 ms**, P95 **377 ms**
   - Stress test (`(100, 20)`, fetch_k=100): post-warmup mean **272 ms**, P95 **298 ms**
   - Acceptance criterion: post-warmup P95 ≤ 500 ms — **PASS**
   - Final shipped defaults: **`(50, 10)`** — comfortably under the budget,
     full source / answer accuracy preserved, no fallback to `(30, 6)` required.

3. **Default `CHUNK_OVERLAP` bumped from 64 to 100.** Aligns the
   shipped default with Stäbler et al. (2025)'s empirical sweet spot.
   Existing `.env` overrides remain untouched. Existing collections
   continue to work at their previous overlap until re-ingested; the
   change is opt-in via re-ingest.

4. **Process-local `lru_cache(maxsize=128)` on query embeddings, with
   `search()` refactored to embed once at the top.** The cache is keyed
   on `(query, embed_model_name)` and resets on restart. The cache must
   apply uniformly across both retrieval branches, so `search()` is
   refactored: the query is embedded exactly once at the top via the
   cached helper, the resulting vector is threaded into both the
   metadata-filtered branch and the unfiltered branch, and the unfiltered
   branch's `VectorStoreIndex.from_vector_store(...).as_retriever(...).retrieve(query)`
   chain is replaced with a direct
   `collection.query(query_embeddings=[vec], n_results=fetch_k)` call.
   This refactor also collapses both branches onto the same code path,
   automatically satisfying ADR-015's score-normalisation contract on
   the unfiltered branch.

## Consequences

### Positive

- Heading boundaries on `.md` files are now respected, with no
  oversized chunks because of the chained sentence splitter.
- The reranker now sees a meaningfully larger candidate pool; the
  Colosseum-style failure mode where a correct chunk is buried below
  the dense-retrieval cut-off is recoverable.
- Repeat queries (common in agentic loops) skip the Ollama embedding
  call entirely on cache hit, reducing per-query latency.
- The unfiltered retrieval branch now uses the same direct
  `collection.query(...)` call as the filtered branch, so ADR-015's
  `1.0 / (1.0 + distance)` contract holds without any extra work in
  this tier.

### Negative

- Reranker latency rises into the 250–450 ms post-warmup range with
  the default `(50, 10)` pool, bounded by the 500 ms P95 ceiling. On
  slow CPUs users may need to lower `RERANK_FETCH_MULTIPLIER` and / or
  `RERANK_MAX_FETCH` per the calibration experiment recording.
- The unfiltered branch no longer goes through LlamaIndex's
  `VectorStoreIndex` wrapper; the API surface narrows, callers
  depending on LlamaIndex-specific node hooks need to migrate.

### Neutral

- New env vars `RERANK_FETCH_MULTIPLIER` and `RERANK_MAX_FETCH` carry
  documented defaults; existing reranker behaviour without env vars is
  the new wider pool, not the old `top_k * 2`.
- Embedding cache is process-local; multi-process deployments do not
  share state, which is fine for the local-MCP use case.

## Alternatives Considered

| Option | Rejected because |
|--------|------------------|
| `MarkdownNodeParser` alone without size cap | Long H2 sections produce single 10K-character chunks, defeating embedding batches |
| Replace `SentenceSplitter` globally with a recursive splitter | Non-Markdown files (PDF, DOCX, TXT) do not benefit equally; risk-reward asymmetric |
| Decorate `Settings.embed_model.get_query_embedding` and accept the unfiltered-branch miss | The unfiltered branch is the default path; the cache would silently fail to satisfy its primary scenario |
| Persistent on-disk embedding cache | Overkill for a local single-user MCP server |
| Keep `top_k * 2` and rely on better embeddings | The reranker is the most precise stage and is the one currently starved of candidates; addressing the embedding model is a separate, larger change |
| Change `CHUNK_SIZE` alongside `CHUNK_OVERLAP` | The existing reranker calibration data uses 512; touching `CHUNK_SIZE` would invalidate it |
| Semantic / hierarchical / proposition chunking | Qu, Tu & Bao (2024) do not show consistent gains worth the compute overhead |
| HyDE-style query expansion | Adds an LLM call per query and a known hallucination risk |

## References

- ADR-005: [Cross-Encoder Reranker with ONNX Runtime](./005-cross-encoder-reranker-with-onnx-runtime.md) — the calibrated ÷30 scaling and the original `top_k * 2` pool that this ADR widens
- ADR-015: [RAG Reliability and Correctness Fixes](./015-rag-reliability-correctness-fixes.md) — the score-normalisation contract that Decision 4's refactor satisfies on both branches
- OpenSpec change: `openspec/changes/rag-retrieval-quality-improvements/`
- Specs:
  - `openspec/changes/rag-retrieval-quality-improvements/specs/markdown-aware-chunking/spec.md`
  - `openspec/changes/rag-retrieval-quality-improvements/specs/reranking/spec.md`
  - `openspec/changes/rag-retrieval-quality-improvements/specs/query-embedding-cache/spec.md`
  - `openspec/changes/rag-retrieval-quality-improvements/specs/async-ingestion/spec.md`
- Experiments:
  - `experiments/5-reranker-pool-sizing-2026-05-27/results.md` — pool latency sweep, P95 confirmation, shipped defaults
  - `experiments/6-markdown-chunking-quality-2026-05-27/results.md` — Markdown chunker non-regression on a structured corpus
  - `experiments/7-chunk-overlap-sensitivity-2026-05-27/results.md` — overlap sweep, non-regression confirmation
  - `experiments/8-query-embedding-cache-2026-05-27/results.md` — cache speedup measurement (≥ 30 % warm-trace reduction)
  - `experiments/1-reranker-threshold-calibration-2026-05-12/results.md` — original ÷30 threshold calibration that this ADR widens
- Source:
  - `src/rag_mcp/ingestion.py` — Markdown branch with chained splitter
  - `src/rag_mcp/retrieval.py` — refactored `search()` with embed-once-at-top and cache
  - `src/rag_mcp/config.py` — `RERANK_FETCH_MULTIPLIER`, `RERANK_MAX_FETCH`, `CHUNK_OVERLAP=100`
- Tests:
  - `tests/test_markdown_chunking.py` — heading boundaries, long-section split, non-Markdown isolation, heading-less Markdown
  - `tests/test_rerank_fetch_pool.py` — default pool, env override, small-collection clamp
  - `tests/test_chunk_overlap_default.py` — source-level contract for `CHUNK_OVERLAP=100`
  - `tests/test_query_embedding_cache.py` — cache hits on filtered/unfiltered branches, distinct queries, LRU eviction
- Literature:
  - Pham & Luong (2025) — heading-aware chunking gains on structured documents
  - Lavarec & Du (2026) — hierarchical chunking benchmarks
  - Lim (2026) — "Wide Net, Tight Filter" cross-encoder pattern
  - Abirami et al. (2025) — reranker pool sizing study
  - Stäbler et al. (2025) — empirical chunk-overlap sweet spot
  - Qu, Tu & Bao (2024) — semantic chunking compute-overhead findings
