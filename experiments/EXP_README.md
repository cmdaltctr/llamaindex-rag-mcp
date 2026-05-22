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

| # | Experiment | Date | Status | Key Finding |
| - | ---------- | ---- | ------ | ----------- |
| 1 | [Reranker threshold calibration](./reranker-threshold-calibration-2026-05-12/) | 2026-05-12 | PASS | Reranker fixes 12.5% of failures; ÷30 threshold scaling calibrated |
| 2 | [Embedding model comparison](./embedding-model-comparison-2026-05-19/) | 2026-05-19 | PASS | qwen3:0.6b = perfect retrieval (100% Hit@1), 13× faster than 8b |
| 3 | [E2E smoke test — LlamaIndex metadata extraction](./e2e-smoke-test-metadata-2026-05-20/) | 2026-05-20 | PASS | Full pipeline 100% Hit@1 on 17 queries across 6 diverse documents |

## Standalone Benchmarks

Quick performance measurements that don't follow the full experiment protocol.
These are useful reference data but not structured for full reproducibility.

| Report | Date | Summary |
| ------ | ---- | ------- |
| [Embedding performance](./embedding-performance.md) | 2026-05-19 | qwen3:0.6b delivers 13.2× speedup over 8b (8.35 vs 0.63 chunks/sec) |

## Cross-References

Experiments often inform code changes. Key links:

| Experiment | Resulting Change |
| ---------- | ---------------- |
| reranker-threshold-calibration-2026-05-12 | `_effective_threshold()` in `retrieval.py` — ÷30 scaling factor |
| embedding-model-comparison-2026-05-19 | Default `EMBED_MODEL` switched to `qwen3-embedding:0.6b` |
| e2e-smoke-test-metadata-2026-05-20 | Validated `enhance-metadata-extraction` ADR; exposed `_strip_llm_prefix` bugs (ADR-014) |
