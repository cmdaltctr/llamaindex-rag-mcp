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

## Chroma Cloud execution

Calibration harnesses can run against hosted Chroma Cloud instead of the
embedded local store. Storage mode is independent of the embedding provider.

### Prerequisites

1. Set `CHROMA_MODE=cloud` and `CHROMA_CLOUD_API_KEY` in `.env`.
2. Optionally set `CHROMA_CLOUD_TENANT` and `CHROMA_CLOUD_DATABASE`
   together, or omit both.
3. Run the opt-in smoke check first:

   ```bash
   uv run python scripts/chroma_cloud_smoke.py
   ```

   It ingests and queries a disposable collection, then deletes it. The API
   key is never printed.

### Storage helper

The six active calibration harnesses (10b, 10.1, 12, 9a-rerun, 13, 14)
obtain storage through `experiments/_lib/storage.py`, which resolves the
mode from runtime settings and constructs the store via the production
factory (`build_chroma_vector_store`). No harness imports `chromadb`
directly.

### Immutable-index reuse

A collection identifies an immutable index: experiment ID, corpus/config
identity, embedding provider and model, parser, and chunking configuration.
The derived name is deterministic — for example
`exp14-qasper-openrouter-qwen3-8b-liteparse-cs512-co100`. Cells and
repetitions that only change retrieval settings reuse the same index
read-only; their IDs live in checkpoint and result metadata, not the
collection name.

At most ONE process mutates a collection during a run. The BM25 invalidation
counter is process-local, so evaluation workers read completed indexes
read-only. Cross-process mutation of the same collection is unsupported.

Cloud checkpoints store identifiers, provider, model, and mode — never the
API key.

### Cost and reproducibility notes

Full cloud (OpenRouter embeddings + Chroma Cloud storage) avoids local
SQLite write locks and shares indexes across machines, so parallel
read-only evaluation cells do not contend. Local persist directories remain
in use for local mode.

OpenRouter supplies cloud embeddings; Chroma Cloud stores the vectors.
Fireworks is a compatible FUTURE cloud-compute adapter that would require a
new provider registration — it is not a vector store.

Switching the embedding model, parser, or chunking configuration means a NEW
collection: the index identity changes and the corpus must be re-embedded.
Migrated runners call the v2 surface `rag_mcp.core.retrieval.search` with an
injected store and per-call retrieval knobs. Legacy local output dirs with
the collection `documents` need one rebuild, because experiment collections
now use derived names by default.

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
| 10b      | [Reranker pool-size corrected](./10b-reranker-pool-size-corrected-2026-06-29/)                      | 2026-06-29 | REBUILT — Stage 6 pending | The 2026-06-29 planned harness is superseded by the repaired D17 factorial runner (commit `181a726`, harden-pipeline Stage 4): 12-cell dense/hybrid × rerank × pool {50, 100, 150, 200, 500} matrix with shared reranker-off controls. See the supersession section in its [protocol.md](./10b-reranker-pool-size-corrected-2026-06-29/protocol.md). Campaign cells not yet run |
| 10.1     | [Doc similarity threshold calibration](./10.1-doc-similarity-threshold-calibration-2026-06-29/)     | 2026-07-16 | PASS                | Current default (0.85) validated. FP rate 0%, modularity within 0.4% of degenerate optimum. Similarity edges are <2.5% of total graph edges — threshold has limited leverage over modularity. No ADR-023 amendment warranted.                                                                                  |
| 12       | [Hybrid default promotion](./12-hybrid-default-promotion-2026-06-29/)                               | 2026-06-29 | SUPERSEDED by D17 | The planned campaign is subsumed by the Stage 6.1 D17 factorial (harden-pipeline): the shared reranker-off dense/hybrid controls answer the hybrid-lift question on the same corpus with paired CIs. Change archived 2026-08-22 |
| 9a-rerun | [Post-ADR-021 reranker validation](./9a-rerun-post-adr021-reranker-2026-06-29/)                     | 2026-06-29 | SUPERSEDED by D17 | The planned 4-cell grid (dense/hybrid × rerank at fetch_k 150) is a subset of the D17 factorial matrix, which sweeps pools 50–500 on both retrieval modes. Change archived 2026-08-22 |
| 13       | [HARD_TECHNICAL_THRESHOLD calibration](./13-hard-technical-threshold-calibration-2026-06-29/)       | 2026-06-29 | REBUILT — Stage 6 pending | The 2026-06-29 planned harness is superseded by the repaired D18 harness (commit `b92f152`, harden-pipeline Stage 4) with D13 manifest, D14 preflight, and D16 per-query rows — see its [protocol.md](./13-hard-technical-threshold-calibration-2026-06-29/protocol.md). Threshold sweep is conditional on Stage 6.1 reranker evidence and MUST adjudicate the TDR-015 ÷30 revalidation obligation. Cells not yet run |
| 14       | [LiteParse Qasper promotion](./14-liteparse-qasper-promotion-2026-06-29/)                           | 2026-06-29 | REBUILT — Stage 6 pending | The 2026-06-29 planned harness is superseded by the rebuilt D19 harness (commit `205ec0e`, harden-pipeline Stage 4) with pinned fixture PDFs (`fixtures/doc1_climate.pdf`, `fixtures/doc2_quantum.pdf`, blob-identical to canonical fixtures) — see its [protocol.md](./14-liteparse-qasper-promotion-2026-06-29/protocol.md). Extended 2026-08-23 (user-ratified) to a three-parser A/B/C — pypdf, liteparse, pdf-inspector × rerank {off,on}, 6 cells — see the protocol's v2.1 extension section. Cells not yet run |
| 16       | [Reranker CoreML fp16 latency](./16-reranker-coreml-fp16-2026-08-03/)                               | 2026-08-03 | FAIL                | fp16 crashes on ORT 1.25.1 (`SimplifiedLayerNormFusion` bug) but fixable with `disabled_optimizers`. With fix: fp16+CoreML loads but is 2.3× slower than int8+CPU (5393ms vs 2348ms P50). CoreML does not accelerate cross-encoder models. Keep int8+CPU as swap default; add `disabled_optimizers` safety net to `reranker.py` |
| 17       | [Reranker MPS vs ONNX CPU latency](./17-reranker-mps-vs-onnx-cpu-2026-08-11/)                       | 2026-08-11 | FAIL                | H1–H4 PASS: MPS is 4.5× faster than ONNX CPU (54.9ms vs 245.3ms P50), cold start 2.9×, RSS 1.54×. H5 FAIL: ONNX int8 and torch fp32 produce different rankings on 2/5 queries (near-tied documents). 17B==17C rankings match — device change is clean; divergence is backend precision (int8 vs fp32). Keep ONNX CPU as default; torch backend retains automatic MPS for opt-in. ADR-043 records the verdict |
| 18       | [Ingestion lock-scope baseline and conditional A/B](./18-ingestion-lock-scope-ab-2026-08-19/)        | 2026-08-19 | PASS                | Stage 3B measurement gate (design D12). Phase A: H1–H5 all PASS (bounded units, RSS ≤2× per 4× files, failure safety, swap, unchanged skip). Timing: single-stream lock wait ≈0 (sequential by construction); 2-stream contended with real Ollama embeddings is fully serialised — contender lock wait 95.6% of wall, speedup 1.002. Phase B A/B (3 interleaved reps/arm): narrow lock retained — real-embed contended throughput +34.7% (5.49 → 7.40 docs/s), lock wait 96.7% → 0.0%, H6/H7 pass, correctness re-run green; TDR-013 |
| 19       | [Native FTS vs BM25 sparse backend](./19-native-fts-vs-bm25-sparse-2026-08-29/)                    | 2026-08-29 | FAIL (promotion gates) | Task 4.1 evidence for `implement-native-sparse-backend-strategy`. G1 PASS (sparse Recall@10 parity 0.850/0.850, hybrid 0.950/0.950 on the Exp 9 corpus, 53 chunks), G2 PASS (both fully deterministic), G4 PASS (native peak RSS −7.4%), G3 FAIL (native warm p50 138.7× BM25: 5.7 ms vs ~0.04 ms in-process at this corpus scale; native cold start 10.8× faster). Decision per pre-registered rule: **keep `bm25` default**; native registered as capability-resolved alternative |
| 20       | [Citation faithfulness](./20-citation-faithfulness-2026-09-02/)                                    | 2026-09-02 | PLANNED               | `add-grounded-answer-synthesis-3` task 7.2 / security F4 follow-up. Does an LLM judge detect unsupported claims (recall ≥ 0.80, false rejection ≤ 0.10, P95 ≤ 5 s) where a lexical baseline cannot (gap ≥ 0.20)? Decides whether `ok` gains claim-support verification, verification ships as opt-in diagnostics, or the referential-only guarantee stays. Protocol and gates pre-registered; ground truth and runner to be written before any run |

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
