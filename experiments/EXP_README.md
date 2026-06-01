# Experiments

Empirical evaluations of the RAG pipeline. Each experiment tests a specific
hypothesis about retrieval quality, performance, or configuration.

## How to Add an Experiment

1. Copy `TEMPLATE.md` into a new directory named `<descriptive-slug>-<YYYY-MM-DD>/`
2. Fill in the template sections (at minimum: Purpose, Variables, Method, Success Criteria)
3. Write ground-truth queries **before** running the experiment (avoids confirmation bias)
4. Run the experiment and record results
5. Add an entry to the index below

## Conventions

| Convention        | Rule                                                                                     |
| ----------------- | ---------------------------------------------------------------------------------------- |
| **Naming**        | `<what-was-tested>-<YYYY-MM-DD>` (e.g., `reranker-threshold-calibration-2026-05-12`)     |
| **Isolation**     | Use `CHROMA_PERSIST_DIR=./chroma_db_test` — never touch production data                  |
| **Ground truth**  | Write queries and expected answers BEFORE running the experiment                          |
| **Operator**      | Record who (or what agent) ran the experiment                                            |
| **Raw data**      | Always save machine-readable results (JSON) alongside human-readable summaries (Markdown) |
| **Status**        | Mark each experiment: `PLANNED`, `PASS`, `FAIL`, or `INCONCLUSIVE`                       |
| **Cleanup**       | Document how to remove experiment artefacts (temp ChromaDB, generated files)              |

## Scientific Flow (Lightweight)

Every experiment follows this structure, even if some sections are brief:

```
Hypothesis → Variables → Method → Results → Conclusion
```

- **Hypothesis**: What question are we answering?
- **Variables**: What's being changed (independent), measured (dependent), and held constant (controlled)?
- **Method**: Step-by-step reproduction commands — copy-paste should work
- **Results**: Data tables, key findings, score distributions
- **Conclusion**: What decision was made? What changed in the codebase as a result?

## Index

| # | Experiment | Date | Status | Key Finding / Purpose |
| - | ---------- | ---- | ------ | --------------------- |
| 1 | [Reranker threshold calibration](./1-reranker-threshold-calibration-2026-05-12/) | 2026-05-12 | PASS | Reranker fixes 12.5% of failures; ÷30 threshold scaling calibrated |
| 2 | [Embedding model comparison](./2-embedding-model-comparison-2026-05-19/) | 2026-05-19 | PASS | qwen3:0.6b = perfect retrieval (100% Hit@1), 13× faster than 8b |
| 3 | [E2E smoke test — LlamaIndex metadata extraction](./3-e2e-smoke-test-metadata-2026-05-20/) | 2026-05-20 | PASS | Full pipeline 100% Hit@1 on 17 queries across 6 diverse documents |
| 4 | [Async chunking responsiveness](./4-async-chunking-responsiveness-2026-05-27/) | 2026-05-27 | PLANNED | Confirms `asyncio.to_thread` chunk-splitter offload (Tier 1) keeps search P95 ≤ 2× idle baseline during ingest |
| 5 | [Reranker pool sizing recalibration](./5-reranker-pool-sizing-2026-05-27/) | 2026-05-27 | PLANNED | Picks Tier 2 defaults for `RERANK_MAX_FETCH` / `RERANK_FETCH_MULTIPLIER`; mandated by design Decision 2 |
| 6 | [Markdown-aware chunking quality](./6-markdown-chunking-quality-2026-05-27/) | 2026-05-27 | PLANNED | Validates Tier 2 Markdown chunker improves heading-targeted Hit@1 by ≥ 5 pp without hurting general queries |
| 7 | [Chunk overlap sensitivity](./7-chunk-overlap-sensitivity-2026-05-27/) | 2026-05-27 | PLANNED | Confirms Tier 2 `CHUNK_OVERLAP=100` default is non-regressive vs the previous default of 64 |
| 8 | [Query embedding cache](./8-query-embedding-cache-2026-05-27/) | 2026-05-27 | PLANNED | Validates Tier 2 LRU cache delivers ≥ 30 % warm-trace speedup and zero overhead on cold traces, both retrieval branches |
| 9 | [Hybrid retrieval (dense + BM25 + RRF)](./9-hybrid-retrieval-2026-05-27/) | 2026-05-27 | PLANNED | Mandated by Tier 3 Migration Plan; Colosseum regression target + rare-term/semantic partition; informs follow-up `HYBRID_ENABLED` default flip |
| 7a | [Chunk overlap sensitivity on Qasper](./7a-chunk-overlap-evidence-2026-05-29/) | 2026-05-29 | INCONCLUSIVE | Qasper is a stress case: overlap 64 beats 100 at rerank-on `top_k=5`; keep global default 100 but document corpus-specific override guidance |
| 8a | [Query embedding cache full-size evaluation](./8a-query-embedding-cache-fullsize-2026-05-29/) | 2026-05-29 | PASS | Full-size traces confirm 76% warm speedup, 87% agent-loop speedup, no cold-query penalty, and cache hits on both retrieval branches |
| 9a | [Hybrid retrieval on FreshStack LangChain](./9a-hybrid-retrieval-freshstack-langchain-2026-05-30/) | 2026-05-31 | FAIL | Hybrid helps at first retrieval (+4.6pp Coverage@20) but reranker bottleneck (max_fetch=50) erases the advantage; keep HYBRID_ENABLED=false default |
| 10 | [Reranker technical workload calibration](./10-reranker-technical-workload-calibration-2026-05-31/) | 2026-05-31 | FAIL / INCONCLUSIVE | Reranking with effective `fetch_k=500` degrades technical retrieval (hybrid Coverage@20 0.738 → 0.540, ~19× mean latency). Intended pool-size sweep is inconclusive because labelled pools 50/200/500 all resolved to effective `fetch_k=500`; recommend disabling reranking for technical/hybrid workloads. |

## Standalone Benchmarks

Quick performance measurements that don't follow the full experiment protocol.
These are useful reference data but not structured for full reproducibility.

| Report | Date | Summary |
| ------ | ---- | ------- |
| [Embedding performance](./ARCHIVED/embedding-performance.md) | 2026-05-19 | qwen3:0.6b delivers 13.2× speedup over 8b (8.35 vs 0.63 chunks/sec) |

## Cross-References

Experiments often inform code changes. Key links:

| Experiment | Resulting / Related Change |
| ---------- | -------------------------- |
| 1 — reranker-threshold-calibration-2026-05-12 | `_effective_threshold()` in `retrieval.py` — ÷30 scaling factor |
| 2 — embedding-model-comparison-2026-05-19 | Default `EMBED_MODEL` switched to `qwen3-embedding:0.6b` |
| 3 — e2e-smoke-test-metadata-2026-05-20 | Validated `enhance-metadata-extraction` ADR; exposed `_strip_llm_prefix` bugs (ADR-014) |
| 4 — async-chunking-responsiveness-2026-05-27 | OpenSpec `rag-reliability-correctness-fixes` (Tier 1), task 1.x |
| 5 — reranker-pool-sizing-2026-05-27 | OpenSpec `rag-retrieval-quality-improvements` (Tier 2), task 2.x — picks shipped defaults |
| 6 — markdown-chunking-quality-2026-05-27 | OpenSpec `rag-retrieval-quality-improvements` (Tier 2), task 1.x |
| 7 — chunk-overlap-sensitivity-2026-05-27 | OpenSpec `rag-retrieval-quality-improvements` (Tier 2), task 3.x |
| 8 — query-embedding-cache-2026-05-27 | OpenSpec `rag-retrieval-quality-improvements` (Tier 2), task 4.x |
| 9 — hybrid-retrieval-2026-05-27 | OpenSpec `rag-hybrid-retrieval` (Tier 3), task 9.x — informs follow-up default flip |
| 7a — chunk-overlap-evidence-2026-05-29 | Follow-up evidence-level validation for ADR-016 overlap default; documents Qasper-specific `CHUNK_OVERLAP=64` preference at `top_k=5` |
| 8a — query-embedding-cache-fullsize-2026-05-29 | Follow-up validation for ADR-016 query embedding cache using full-size traces and true cache-off cells |
| 9a — hybrid-retrieval-freshstack-langchain-2026-05-30 | FreshStack-scale follow-up for Exp 9; informs future reranker pool sizing experiment (Exp 5 revisit) |
| 10 — reranker-technical-workload-calibration-2026-05-31 | OpenSpec `rag-reranker-technical-workload-calibration`; shows reranking at effective `fetch_k=500` degrades technical retrieval; pool-size sensitivity remains inconclusive; resulted in ADR-019 disabling reranker by default |
