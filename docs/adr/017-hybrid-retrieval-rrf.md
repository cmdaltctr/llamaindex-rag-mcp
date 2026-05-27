# ADR-017: Hybrid Retrieval with Reciprocal Rank Fusion

**Status**: Proposed
**Date**: <TODO: YYYY-MM-DD on archive>
**Change**: `rag-hybrid-retrieval`
**Deciders**: Dr Muhammad Aizat Bin Md Hawari
**Git Commits**: <TODO: list relevant SHAs once landed>

## Context

The retrieval pipeline established by ADR-005 (cross-encoder reranker)
and tuned by ADR-016 (wider reranker pool, query-embedding cache) is
single-stage dense vector search optionally followed by reranking. Two
failure modes are well documented and structurally similar:

1. The reranker pool is sourced from dense retrieval only, so any chunk
   ranked below the dense-retrieval cut-off can never be reranked. The
   Colosseum case in `experiments/reranker-threshold-calibration-2026-05-12/`
   is a concrete instance — the correct chunk scored only 0.015 because
   it was never a candidate.
2. Rare or exact-match terms (product codes, legal citations, gene
   names, identifiers) are systematically harder for dense embeddings
   than for keyword matching. ADR-016's wider pool helps but does not
   fix the root cause: the dense retriever is producing the wrong
   ranking, not running out of candidates.

Recent literature converges on hybrid retrieval — dense plus sparse,
fused via Reciprocal Rank Fusion — as the standard mitigation. Mala,
Gezici & Giannotti (2025) report weighted RRF achieving the highest
accuracy and lowest hallucination rate on HaluBench. Airy & Baranwal
(2025) report a 93.3% hallucination reduction with hybrid RAG. Akarsu
et al. (2026) show BM25 outperforming dense retrieval on financial
documents. Abirami et al. (2025) demonstrate hybrid RRF lifting
Recall@100 to 0.997. The original RRF paper (Cormack, Clarke & Buettcher,
2009) remains the de facto fusion algorithm.

Adding a sparse retriever and fusing with RRF before the existing
reranker is structurally clean: ADR-005's calibrated ÷30 threshold
scaling stays valid because the reranker still scores `(query, chunk)`
pairs the same way; hybrid only changes which candidates enter the pool.

## Decision

Adopt eight sub-decisions, all opt-in via `HYBRID_ENABLED=false` and a
per-call `hybrid: bool = False` parameter, all preserving ADR-005's ÷30
threshold scaling:

1. **Reciprocal Rank Fusion with `k=60`.** Use
   `score(d) = Σ_r 1 / (k + rank_r(d))` with `k=60` (Cormack, Clarke &
   Buettcher, 2009). Configurable via `HYBRID_RRF_K`. Robust across
   mismatched score scales between dense and sparse retrievers and
   needs no per-corpus weight tuning.

2. **Sparse backend defaults to `bm25` for v1.** `HYBRID_SPARSE_BACKEND`
   accepts `auto`, `native`, `bm25`. The v1 default is `bm25`, not
   `auto`, because the ChromaDB sparse-vector / BM25 / SPLADE API has
   been a moving target across recent minor versions. Promotion of the
   default to `auto` belongs in a follow-up change after the new
   calibration experiment confirms the native path on the pinned
   `chromadb`. Explicit `HYBRID_SPARSE_BACKEND=native` falls back to
   `bm25` with a WARNING when the installed ChromaDB does not support
   sparse vectors, rather than crashing.

3. **Hybrid is opt-in by default.** `HYBRID_ENABLED=false` and per-call
   `hybrid: bool = False`. The default flip to `true` is intentionally
   a separate small change following the calibration experiment in
   `experiments/hybrid-retrieval-<TODO: date>/`.

4. **Reranker integration is unchanged.** The fused candidate list
   feeds the existing cross-encoder reranker when `rerank=True`, sized
   per ADR-016's `RERANK_FETCH_MULTIPLIER` / `RERANK_MAX_FETCH`. ADR-005's
   ÷30 threshold scaling remains valid because the reranker's scoring
   function is unchanged — hybrid only changes which candidates enter
   the pool. The calibration experiment from
   `experiments/reranker-threshold-calibration-2026-05-12/` does not
   need to be re-run for this reason.

5. **No automatic re-ingestion required.** When the native sparse path
   is selected, only newly ingested chunks gain sparse vectors;
   existing chunks remain dense-only. RRF naturally handles missing
   ranks by excluding them from one term of the sum. A CLI command
   supports a deliberate re-ingest for users who want full hybrid
   coverage immediately.

6. **BM25 cache invalidation tied to the ingestion write lock.** The
   in-memory BM25 index is cached per collection and invalidates
   whenever ingestion writes to or deletes from that collection. A
   per-collection generation counter (process-local, guarded by the
   existing `_write_lock` in `_embed_and_write_async`) increments on
   every successful write; deletion paths (`remove_document`,
   `remove_by_metadata`, `remove_collection`) also bump the counter.
   The sparse retriever caches `(collection_name, generation,
   bm25_index)` and rebuilds lazily when the live generation has
   advanced past the cached one. Lazy rebuild is preferred over eager
   rebuild during ingest because rebuilds can be expensive on large
   collections and ingestion is already on the critical path.

7. **Mixed-coverage collections trigger a one-shot WARNING.** When the
   native sparse path is active and a collection contains a mix of
   chunks with and without sparse vectors, the system emits a
   WARNING-level log on the first hybrid query against that
   collection within the process lifetime. The warning names the
   collection and includes a remediation hint to re-ingest. Subsequent
   queries against the same collection in the same process do not
   re-emit. The BM25 path is unaffected because it always indexes
   every chunk it sees.

8. **Hybrid exposed via both MCP and CLI.** The `hybrid: bool`
   parameter is added to the MCP `search_documents` tool and to the
   CLI `search` subcommand as `--hybrid / --no-hybrid`, mirroring the
   existing `--rerank` parity. CLI-only or MCP-only exposure was
   rejected as creating a quiet asymmetry.

## Consequences

### Positive

- The Colosseum-style rare-term failure mode is recoverable; a
  documented regression test fails on `hybrid=False` and passes on
  `hybrid=True`.
- RRF needs no per-corpus weight tuning, so the system stays robust
  across diverse corpora.
- ADR-005's reranker calibration is explicitly preserved; no
  experiment re-run is required for that ADR.
- BM25 cache invalidation is correct under all ingestion paths
  (writes and deletes).
- Mixed-coverage behaviour is operationally visible rather than
  silent; operators see one clear log line, not a flood.
- CLI and MCP surfaces stay in parity, matching the established
  pattern from ADR-007 / ADR-008 / ADR-014.

### Negative

- In-memory BM25 footprint scales with collection size. Acceptable
  for the local single-user MCP server; documented in the module
  docstring. <TODO: record measured memory on the experiment corpus>.
- Optional `rank_bm25` dependency added under a `hybrid` extra. Users
  who never enable hybrid retrieval do not install it.
- Two retrievers running concurrently increase per-query latency
  even with `asyncio.gather`. Bounded by ADR-016's pool sizing;
  measured in the new calibration experiment as <TODO: measured
  hybrid + rerank P95 ms>.

### Neutral

- The deliberate `bm25` v1 default keeps the native path opt-in
  until the experiment validates it. A second small ADR (or a
  status-only amendment to this one) records the eventual default
  flip.
- Three new env vars (`HYBRID_ENABLED`, `HYBRID_RRF_K`,
  `HYBRID_SPARSE_BACKEND`) added with backwards-compatible defaults.
- Hybrid generation counter is process-local; multi-process
  deployments do not share state, which is fine for the local-MCP
  use case (matches ADR-016's embedding cache scoping).

## Alternatives Considered

| Option | Rejected because |
|--------|------------------|
| Weighted convex combination `α·dense + (1−α)·sparse` | Requires per-corpus weight tuning; brittle to score-distribution shifts between corpora |
| Require a specific minimum ChromaDB version for native sparse | Forces a pinned-version upgrade for an opt-in feature; not friendly to existing deployments |
| Default `HYBRID_SPARSE_BACKEND=auto` for v1 | The chromadb sparse-vector API is a moving target; v1 with `auto` would yield mystery failures during rollout |
| Refuse hybrid on partially-covered collections until re-ingested | Too aggressive for an opt-in feature; some users want partial hybrid as a stepping stone |
| Silently proceed on partial coverage (no warning) | Score changes look like a bug to operators who do not know about the underlying coverage gap |
| Persistent on-disk BM25 index | Overkill for a local single-user MCP server; rebuild-per-process is cheap on the corpus sizes the project targets |
| Rebuild BM25 index eagerly during ingestion | Puts the rebuild on the ingestion critical path; lazy rebuild on stale generation amortises cost across queries |
| MCP-only exposure (skip CLI parity) | The CLI surface already has slots for every other retrieval flag; adding `--hybrid` is trivial and avoids asymmetry |
| Re-run the ADR-005 reranker calibration experiment | Reranker scoring is unchanged; the experiment data remains valid by construction |

## References

- ADR-005: [Cross-Encoder Reranker with ONNX Runtime](./005-cross-encoder-reranker-with-onnx-runtime.md) — the reranker the fused list feeds into; calibrated ÷30 scaling preserved
- ADR-014: [Async Ingestion Path](./014-async-ingestion-path.md) — the async patterns this ADR composes with (`asyncio.gather` for parallel dense / sparse, `_write_lock` for the generation counter)
- ADR-016: [RAG Retrieval Quality Improvements](./016-rag-retrieval-quality-improvements.md) — provides `RERANK_FETCH_MULTIPLIER` / `RERANK_MAX_FETCH` that size the rerank pool fed from the fused list
- OpenSpec change: `openspec/changes/rag-hybrid-retrieval/`
- Specs:
  - `openspec/changes/rag-hybrid-retrieval/specs/hybrid-retrieval/spec.md`
  - `openspec/changes/rag-hybrid-retrieval/specs/reranking/spec.md`
- Experiment: `experiments/hybrid-retrieval-<TODO: date>/results.md` — corpus, queries (including Colosseum-style rare-term cases), metrics (Recall@k, MRR, nDCG@k), and configurations (`dense-only`, `hybrid + bm25`, `hybrid + native` if available, `hybrid + rerank`)
- Source:
  - `src/rag_mcp/sparse_retriever.py` — `BM25SparseRetriever` with generation-aware cache
  - `src/rag_mcp/retrieval.py` — `hybrid` parameter, RRF fusion, dual-retriever orchestration
  - `src/rag_mcp/ingestion.py` — generation counter increments under `_write_lock`
  - `src/rag_mcp/server.py` — `hybrid` parameter on `search_documents`
  - `src/rag_mcp/cli.py` — `--hybrid / --no-hybrid` flag on `search` subcommand
  - `src/rag_mcp/config.py` — `HYBRID_ENABLED`, `HYBRID_RRF_K`, `HYBRID_SPARSE_BACKEND`
- Tests: <TODO: list the regression and fusion tests added, plus the rare-term regression test>
- Literature:
  - Cormack, Clarke & Buettcher (2009) — original RRF paper; `k=60` constant
  - Mala, Gezici & Giannotti (2025) — weighted RRF on HaluBench
  - Airy & Baranwal (2025) — 93.3% hallucination reduction with hybrid RAG
  - Akarsu et al. (2026) — BM25 outperforming dense retrieval on financial documents
  - Abirami et al. (2025) — hybrid RRF Recall@100 = 0.997
