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

| Convention       | Rule                                                                                      |
| ---------------- | ----------------------------------------------------------------------------------------- |
| **Naming**       | `<what-was-tested>-<YYYY-MM-DD>` (e.g., `reranker-threshold-calibration-2026-05-12`)      |
| **Isolation**    | Use `CHROMA_PERSIST_DIR=./chroma_db_test` — never touch production data                   |
| **Ground truth** | Write queries and expected answers BEFORE running the experiment                          |
| **Operator**     | Record who (or what agent) ran the experiment                                             |
| **Raw data**     | Always save machine-readable results (JSON) alongside human-readable summaries (Markdown) |
| **Status**       | Mark each experiment: `PLANNED`, `PASS`, `FAIL`, or `INCONCLUSIVE`                        |
| **Cleanup**      | Document how to remove experiment artefacts (temp ChromaDB, generated files)              |

## Scientific Flow (Lightweight)

Every experiment follows this structure, even if some sections are brief:

```
Hypothesis → Variables → Method → Results → Conclusion
```

- **Hypothesis**: A testable statement predicting the outcome (e.g., "If X, then Y")
- **Variables**: What's being changed (independent), measured (dependent), and held constant (controlled)?
- **Method**: Step-by-step reproduction commands — copy-paste should work
- **Results**: Data tables, key findings, score distributions
- **Conclusion**: What decision was made? What changed in the codebase as a result?

## Index

| #        | Experiment                                                                                          | Date       | Status              | Key Finding / Purpose                                                                                                                                                                                                                                                                                        |
| -------- | --------------------------------------------------------------------------------------------------- | ---------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1        | [Reranker threshold calibration](./1-reranker-threshold-calibration-2026-05-12/)                    | 2026-05-12 | PASS                | Reranker fixes 12.5% of failures; ÷30 threshold scaling calibrated                                                                                                                                                                                                                                           |
| 2        | [Embedding model comparison](./2-embedding-model-comparison-2026-05-19/)                            | 2026-05-19 | PASS                | qwen3:0.6b = perfect retrieval (100% Hit@1), 13× faster than 8b                                                                                                                                                                                                                                              |
| 3        | [E2E smoke test — LlamaIndex metadata extraction](./3-e2e-smoke-test-metadata-2026-05-20/)          | 2026-05-20 | PASS                | Full pipeline 100% Hit@1 on 17 queries across 6 diverse documents                                                                                                                                                                                                                                            |
| 4        | [Async chunking responsiveness](./4-async-chunking-responsiveness-2026-05-27/)                      | 2026-05-27 | PASS                | Large-corpus replication confirms search P95 remains within the 2× responsiveness contract during ingest; one startup stall remains diagnostic only                                                                                                                                                          |
| 5        | [Reranker pool sizing recalibration](./5-reranker-pool-sizing-2026-05-27/)                          | 2026-05-27 | PASS                | Small-corpus calibration selected `(RERANK_MAX_FETCH=50, RERANK_FETCH_MULTIPLIER=10)`; later superseded for technical workloads by Exp 10                                                                                                                                                                    |
| 6        | [Markdown-aware chunking quality](./6-markdown-chunking-quality-2026-05-27/)                        | 2026-05-27 | PARTIAL             | Non-regression confirmed; heading-lift not measurable because baseline saturated at 100% Hit@1; chunk-size failure was a token/character unit mismatch                                                                                                                                                       |
| 7        | [Chunk overlap sensitivity](./7-chunk-overlap-sensitivity-2026-05-27/)                              | 2026-05-27 | PASS                | `CHUNK_OVERLAP=100` non-regressive on the small smoke corpus with bounded chunk growth                                                                                                                                                                                                                       |
| 8        | [Query embedding cache](./8-query-embedding-cache-2026-05-27/)                                      | 2026-05-27 | PASS                | LRU cache validated on warm-vs-cold traces; confirmed cache hits on both filtered and unfiltered retrieval branches                                                                                                                                                                                          |
| 9        | [Hybrid retrieval (dense + BM25 + RRF)](./9-hybrid-retrieval-2026-05-27/)                           | 2026-05-30 | PARTIAL             | Hybrid implementation works and does not regress, but small corpus saturated; keep hybrid opt-in pending FreshStack-scale follow-up                                                                                                                                                                          |
| 7a       | [Chunk overlap sensitivity on Qasper](./7a-chunk-overlap-evidence-2026-05-29/)                      | 2026-05-29 | INCONCLUSIVE        | Qasper is a stress case: overlap 64 beats 100 at rerank-on `top_k=5`; keep global default 100 but document corpus-specific override guidance                                                                                                                                                                 |
| 8a       | [Query embedding cache full-size evaluation](./8a-query-embedding-cache-fullsize-2026-05-29/)       | 2026-05-29 | PASS                | Full-size traces confirm 76% warm speedup, 87% agent-loop speedup, no cold-query penalty, and cache hits on both retrieval branches                                                                                                                                                                          |
| 9a       | [Hybrid retrieval on FreshStack LangChain](./9a-hybrid-retrieval-freshstack-langchain-2026-05-30/)  | 2026-05-31 | FAIL                | Hybrid helps at first retrieval (+4.6pp Coverage@20) but reranker bottleneck (max_fetch=50) erases the advantage; keep HYBRID_ENABLED=false default                                                                                                                                                          |
| 10       | [Reranker technical workload calibration](./10-reranker-technical-workload-calibration-2026-05-31/) | 2026-05-31 | FAIL / INCONCLUSIVE | Reranking with effective `fetch_k=500` degrades technical retrieval (hybrid Coverage@20 0.738 → 0.540, ~19× mean latency). Intended pool-size sweep is inconclusive because labelled pools 50/200/500 all resolved to effective `fetch_k=500`; recommend disabling reranking for technical/hybrid workloads. |
| 11       | [LiteParse PDF quality and speed](./11-liteparse-pdf-quality-2026-06-20/)                           | 2026-06-20 | PARTIAL             | Validation gate for OpenSpec change `use-liteparse-as-pdf-reader`. H1 PASS (+6.9% nDCG@10, 100% vs 96% Hit@5). H2 FAIL (parsing 5.5× faster but embedding dominates; LiteParse extracts 15% more chunks). H3 FAIL (corpus saturation). H4 PASS. LiteParse adopted via factory (ADR-020).                     |
| 10b      | [Reranker pool-size corrected](./10b-reranker-pool-size-corrected-2026-06-29/)                      | 2026-06-29 | PLANNED             | Corrected pool-size sweep using `fetch_k` override; tests fetch_k ∈ {50, 100, 200, 500} with reranker-on to find optimal pool size                                                                                                                                                                           |
| 10.1     | [Doc similarity threshold calibration](./10.1-doc-similarity-threshold-calibration-2026-06-29/)     | 2026-07-16 | PASS                | Current default (0.85) validated. FP rate 0%, modularity within 0.4% of degenerate optimum. Similarity edges are <2.5% of total graph edges — threshold has limited leverage over modularity. No ADR-023 amendment warranted.                                                                                  |
| 12       | [Hybrid default promotion](./12-hybrid-default-promotion-2026-06-29/)                               | 2026-06-29 | PLANNED             | Tests whether hybrid retrieval (dense + BM25) should be promoted to default with post-ADR-021 reranker config; bootstrap CI on Coverage@20 lift                                                                                                                                                              |
| 9a-rerun | [Post-ADR-021 reranker validation](./9a-rerun-post-adr021-reranker-2026-06-29/)                     | 2026-06-29 | PLANNED             | Re-runs Exp 9a 4-cell grid with post-ADR-021 config (fetch_k=150 vs 500) to validate ADR-019 reranker-off decision                                                                                                                                                                                           |
| 13       | [HARD_TECHNICAL_THRESHOLD calibration](./13-hard-technical-threshold-calibration-2026-06-29/)       | 2026-06-29 | PLANNED             | Sweeps threshold ∈ {0.1, 0.2, 0.3, 0.5, 0.7} on mixed FreshStack + Qasper corpus to calibrate reranker auto-disable threshold                                                                                                                                                                                |
| 14       | [LiteParse Qasper promotion](./14-liteparse-qasper-promotion-2026-06-29/)                           | 2026-06-29 | PLANNED             | Re-runs LiteParse vs pypdf on harder Qasper corpus (≥ 30 PDFs, ≥ 100 queries); validates H3 (reranker benefit) and H2 (speed) with post-ADR-021 optimisations                                                                                                                                                |
| 16       | [Reranker CoreML fp16 latency](./16-reranker-coreml-fp16-2026-08-03/)                               | 2026-08-03 | FAIL                | fp16 crashes on ORT 1.25.1 (`SimplifiedLayerNormFusion` bug) but fixable with `disabled_optimizers`. With fix: fp16+CoreML loads but is 2.3× slower than int8+CPU (5393ms vs 2348ms P50). CoreML does not accelerate cross-encoder models. Keep int8+CPU as swap default; add `disabled_optimizers` safety net to `reranker.py` |

## Standalone Benchmarks

Quick performance measurements that don't follow the full experiment protocol.
These are useful reference data but not structured for full reproducibility.

| Report                                                       | Date       | Summary                                                             |
| ------------------------------------------------------------ | ---------- | ------------------------------------------------------------------- |
| [Embedding performance](./ARCHIVED/embedding-performance.md) | 2026-05-19 | qwen3:0.6b delivers 13.2× speedup over 8b (8.35 vs 0.63 chunks/sec) |

## Cross-References

Experiments often inform code changes. Key links:

| Experiment                                              | Resulting / Related Change                                                                                                                                                                                                     |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1 — reranker-threshold-calibration-2026-05-12           | `_effective_threshold()` in `retrieval.py` — ÷30 scaling factor                                                                                                                                                                |
| 2 — embedding-model-comparison-2026-05-19               | Default `EMBED_MODEL` switched to `qwen3-embedding:0.6b`                                                                                                                                                                       |
| 3 — e2e-smoke-test-metadata-2026-05-20                  | Validated `enhance-metadata-extraction` ADR; exposed `_strip_llm_prefix` bugs (ADR-014)                                                                                                                                        |
| 4 — async-chunking-responsiveness-2026-05-27            | OpenSpec `rag-reliability-correctness-fixes` (Tier 1), task 1.x                                                                                                                                                                |
| 5 — reranker-pool-sizing-2026-05-27                     | OpenSpec `rag-retrieval-quality-improvements` (Tier 2), task 2.x — picks shipped defaults                                                                                                                                      |
| 6 — markdown-chunking-quality-2026-05-27                | OpenSpec `rag-retrieval-quality-improvements` (Tier 2), task 1.x                                                                                                                                                               |
| 7 — chunk-overlap-sensitivity-2026-05-27                | OpenSpec `rag-retrieval-quality-improvements` (Tier 2), task 3.x                                                                                                                                                               |
| 8 — query-embedding-cache-2026-05-27                    | OpenSpec `rag-retrieval-quality-improvements` (Tier 2), task 4.x                                                                                                                                                               |
| 9 — hybrid-retrieval-2026-05-27                         | OpenSpec `rag-hybrid-retrieval` (Tier 3), task 9.x — informs follow-up default flip                                                                                                                                            |
| 7a — chunk-overlap-evidence-2026-05-29                  | Follow-up evidence-level validation for ADR-016 overlap default; documents Qasper-specific `CHUNK_OVERLAP=64` preference at `top_k=5`                                                                                          |
| 8a — query-embedding-cache-fullsize-2026-05-29          | Follow-up validation for ADR-016 query embedding cache using full-size traces and true cache-off cells                                                                                                                         |
| 9a — hybrid-retrieval-freshstack-langchain-2026-05-30   | FreshStack-scale follow-up for Exp 9; informs future reranker pool sizing experiment (Exp 5 revisit)                                                                                                                           |
| 10 — reranker-technical-workload-calibration-2026-05-31 | OpenSpec `rag-reranker-technical-workload-calibration`; shows reranking at effective `fetch_k=500` degrades technical retrieval; pool-size sensitivity remains inconclusive; resulted in ADR-019 disabling reranker by default |

## Experiment Analysis Workflow (Jupytext)

Experiment analysis scripts use [Jupytext](https://jupytext.readthedocs.io/) percent format to pair a plain Python file (`analysis.py`) with a Jupyter notebook (`analysis.ipynb`). This keeps analysis version-controlled while still allowing interactive exploration.

### Roles

| File             | Role                                      | Tracked in Git  |
| ---------------- | ----------------------------------------- | --------------- |
| `analysis.py`    | Source of truth — Jupytext percent format | Yes             |
| `analysis.ipynb` | Derived notebook for interactive use      | No (gitignored) |

### Conventions

- **`analysis.py` is the source of truth.** Edit this file; the notebook syncs automatically via the Jupytext VS Code extension or CLI.
- **`analysis.ipynb` is gitignored.** It is generated from `analysis.py` and exists only for interactive cell-by-cell execution.
- **Analysis scripts must never run experiment logic or modify environment variables.** They only load saved JSON results and produce pandas summaries + matplotlib plots.
- **Only experiments with local JSON evaluation data get an `analysis.py`.** Smoke tests or remote-only experiments (e.g., Exp 3) are skipped.

### Workflow

1. `jupytext --to notebook analysis.py` → generate notebook
2. Open in Jupyter, run all cells → plots appear inline
3. Optionally `plt.savefig()` specific plots you want in `results.md`
4. Close notebook
5. `jupytext --sync` → any code edits you made in Jupyter go back to `analysis.py`
6. `git add analysis.py` → commit the code, not the outputs
