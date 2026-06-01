# ADR-018: Balanced Retrieval Defaults

**Status**: Superseded by [ADR-019](./019-reranker-disabled-for-technical-workloads.md)
**Date**: 2026-05-29
**Deciders**: Dr Muhammad Aizat Bin Md Hawari
**Related experiments**: Experiment 7a and Experiment 8a

## Context

ADR-016 shipped three retrieval-quality defaults: `CHUNK_OVERLAP=100`, a
wider reranker fetch pool, and a process-local query embedding cache. Later
Qasper experiments showed that evidence-heavy academic QA is more sensitive to
chunk overlap and final retrieval depth than the original smoke corpus.

Experiment 7a (`experiments/7a-chunk-overlap-evidence-2026-05-29/`) tested
`CHUNK_OVERLAP ∈ {32,64,100,128}` on Qasper-dev with evidence-level metrics.
At the production-shaped `rerank=True, top_k=5` cell, overlap 64 had better
Evidence Recall@5 than overlap 100. However, keeping overlap 100 and raising
`top_k` to 10 recovered the Recall@5 loss while avoiding the much higher
latency of `top_k=20`.

Experiment 8a (`experiments/8a-query-embedding-cache-fullsize-2026-05-29/`)
re-ran the query embedding cache benchmark with full-size traces and a true
cache-disabled baseline. It confirmed that repeated-query workloads benefit
substantially from the existing cache: 76.16% warm-trace mean speedup and
86.71% agent-loop mean speedup, with no cold-query penalty.

The project is primarily used for serious document and evidence retrieval,
not ultra-low-latency keyword lookup. The default profile should therefore
optimise for reliable evidence coverage while keeping latency acceptable.

## Decision

Adopt the balanced retrieval profile as the default:

```text
CHUNK_OVERLAP=100
RERANK_ENABLED=true
TOP_K=10
```

`CHUNK_OVERLAP=100` remains the global ingestion default from ADR-016.
`RERANK_ENABLED=true` makes the cross-encoder the default precision stage.
`TOP_K=10` replaces the previous final result depth of 5.

The public surfaces must use `config.py` as the single source of truth:

- `retrieval.search()` already defaults to `TOP_K` and `RERANK_ENABLED`.
- `server.search_documents()` now defaults to `TOP_K` and `RERANK_ENABLED`.
- `cli search` now defaults to `TOP_K` and `RERANK_ENABLED`.
- `.env.example` documents the balanced profile.

CLI JSON output must remain valid JSON even when reranking lazily imports
third-party libraries that write warnings to stdout/stderr. The CLI therefore
suppresses third-party stdout/stderr noise around `do_search()` when
`--json` is active.

## Evidence

Experiment 7a key Qasper results for overlap 100 with reranking enabled:

| top_k | Evidence Recall@5 | Evidence Recall@10 | MRR | P95 latency |
| ----: | ----------------: | -----------------: | --: | ----------: |
| 5 | 58.49% | 58.49% | 0.3827 | 1468 ms |
| 10 | 62.26% | 67.92% | 0.3905 | 2902 ms |
| 20 | 60.38% | 67.92% | 0.3928 | 6199 ms |

`top_k=10` is the best balance: it recovers Recall@5, matches `top_k=20` on
Recall@10, and has less than half the P95 latency of `top_k=20`. It is not
perfect: overlap 64 still has slightly better MRR in one comparison, meaning
the first correct evidence chunk can appear slightly higher. For this project,
recovering evidence coverage is the more important default trade-off.

Experiment 8a key cache results:

| Trace | Cache effect |
| ----- | ------------ |
| warm repeated queries | 76.16% mean speedup |
| agent-loop repeated queries | 86.71% mean speedup |
| cold unique queries | -2.78% overhead, within noise |
| filtered / unfiltered branches | both cache correctly |

This supports default reranking despite higher per-query latency because
agentic repeated-query workloads recover a substantial part of the embedding
cost through cache hits.

## Supersession note

Experiment 9a (`experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/`) later showed that the default reranker can hurt FreshStack-like technical documentation retrieval: both dense and hybrid first-stage results degraded when `cross-encoder/ms-marco-MiniLM-L-6-v2` reranking was applied to the 10,025-document LangChain subset.

Experiment 10 (`experiments/10-reranker-technical-workload-calibration-2026-05-31/`) completed the follow-up calibration. Its corrected interpretation is that reranking with an effective candidate pool of 500 still substantially underperformed rerank-off retrieval on the FreshStack technical workload. ADR-019 supersedes this ADR by changing the default reranker policy while preserving `CHUNK_OVERLAP=100` and `TOP_K=10`.

## Consequences

### Positive

- Better default evidence coverage for Qasper-like academic QA.
- Reranker precision is active by default rather than opt-in.
- MCP, CLI, and direct retrieval now share the same defaults through
  `config.py`, reducing configuration drift.
- Query embedding cache results show repeated-query workloads remain efficient
  even with stronger default retrieval.

### Negative

- Default searches return 10 chunks instead of 5, which can increase context
  volume and downstream LLM prompt size.
- Default reranking increases latency. In 7a, overlap 100 with rerank on and
  `top_k=10` had P95 latency around 2.9 seconds.
- Users who need very fast lightweight search may want to override with
  `RERANK_ENABLED=false` or `TOP_K=5`.

### Neutral

- Existing ChromaDB collections are not migrated. `CHUNK_OVERLAP=100` only
  affects newly ingested or re-ingested documents.
- The reranker fetch-pool rules from ADR-016 remain unchanged:
  `fetch_k = max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)`.
  With `TOP_K=10`, the default rerank pool is 100 candidates.

## Alternatives Considered

| Option | Rejected because |
| ------ | ---------------- |
| Keep `TOP_K=5`, `RERANK_ENABLED=false` | Too weak for evidence-heavy document QA; 7a showed overlap 100 underperformed at this shape. |
| Change global overlap back to 64 | Qasper favours 64 at `top_k=5`, but the broader ADR-016 rationale and non-Qasper results still support 100 as the global overlap default. |
| Set `TOP_K=20` | Similar or worse Recall@5 than `top_k=10` for overlap 100, same Recall@10, and more than double the P95 latency in 7a. |
| Enable reranking only for Qasper-like workflows | Requires users to identify workflow type correctly; default should be robust for serious document QA. |
| Leave MCP / CLI hardcoded at 5 | Violates ADR-006 / AGENTS.md config-as-single-source-of-truth rule and creates confusing divergence from direct `retrieval.search()`. |

## References

- ADR-006: Config as Single Source of Truth
- ADR-016: RAG Retrieval Quality Improvements
- Experiment 7a: `experiments/7a-chunk-overlap-evidence-2026-05-29/results.md`
- Experiment 8a: `experiments/8a-query-embedding-cache-fullsize-2026-05-29/results.md`
- Source changes:
  - `src/rag_mcp/config.py`
  - `src/rag_mcp/server.py`
  - `src/rag_mcp/cli.py`
  - `.env.example`
- Tests:
  - `tests/test_mcp_tools.py::test_search_documents_defaults_follow_config`
  - `tests/test_cli.py::TestSearchErrorHandling::test_search_cli_defaults_follow_config`
