# Experiment 9a: Hybrid Retrieval Quality on FreshStack LangChain

**ID**: `9a-hybrid-retrieval-freshstack-langchain-2026-05-30`  
**Date planned**: 2026-05-30  
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  
**Status**: COMPLETED  
**Relation**: Follow-up to `experiments/9-hybrid-retrieval-2026-05-27/`; OpenSpec change `rag-hybrid-retrieval`; ADR-017 hybrid retrieval with RRF

---

## Why this experiment exists

Experiment 9 validated that the hybrid retrieval implementation runs end-to-end,
records fusion diagnostics, and does not regress the small semantic/mixed test
set. It did **not** prove that hybrid retrieval improves recall, because the
corpus saturated: only 55 chunks were indexed and `RERANK_MAX_FETCH=50` meant
that dense-only retrieval plus reranking effectively saw almost the entire
corpus. Dense-only therefore scored 100% Hit@1 on rare-term queries, leaving no
room for BM25 + RRF to show value.

Experiment 9a reruns the same product decision on a much harder, real technical
retrieval benchmark: the **LangChain** topic from FreshStack. FreshStack is a
benchmark for retrieval over code and technical documentation built from GitHub
repositories plus Stack Overflow questions. The LangChain topic contains 49,514
pre-chunked corpus documents and 203 test questions, so the reranker candidate
pool is no longer close to the full collection.

The decision under test is whether `HYBRID_ENABLED=true` can be recommended as
a future default for realistic technical-document retrieval, or whether it must
remain opt-in after Experiment 9's inconclusive ceiling result.

## Hypothesis

With hybrid retrieval enabled (`HYBRID_ENABLED=true`, BM25 sparse side, RRF
`k=60`) on the FreshStack LangChain corpus:

1. **Primary quality hypothesis**: hybrid + rerank improves nugget-level
   coverage and recall at K over dense-only + rerank by at least 5 percentage
   points on both FreshStack `Coverage@20` and `Recall@50`.
2. **Exact-token hypothesis**: hybrid + rerank improves identifier-heavy
   `Coverage@20` by at least 8 percentage points over dense-only + rerank on
   queries whose title/text contains code symbols, package names, version
   numbers, API paths, exception names, or camelCase/snake_case identifiers.
3. **Semantic guardrail**: hybrid does not materially regress semantic queries;
   `Coverage@20` for non-identifier-heavy queries stays within -2 percentage
   points of dense-only.
4. **Operational guardrail**: hybrid + rerank P95 latency is no more than 1.5x
   dense-only + rerank P95 on the same hardware and corpus subset.

## Background and prior evidence

- Experiment 9 (`experiments/9-hybrid-retrieval-2026-05-27/results.md`) failed
  only the rare-term lift criterion because dense-only already achieved 100%
  rare-term Hit@1 on a 55-chunk corpus.
- The OpenSpec design (`openspec/changes/rag-hybrid-retrieval/design.md`) chose
  BM25 + dense retrieval fused by Reciprocal Rank Fusion (RRF) because RRF is
  score-scale-agnostic and avoids per-corpus weight tuning.
- FreshStack (`freshstack/corpus-oct-2024`, `freshstack/queries-oct-2024`) is a
  realistic benchmark over technical documents. The LangChain topic comprises
  49,514 corpus chunks from 10 GitHub repositories and 203 Stack Overflow test
  queries with nugget-level relevance judgments.
- FreshStack's public leaderboard reports that `Qwen3-0.6B (Emb)` scores 0.262
  average `alpha@10`, BM25 scores 0.218, and a fusion run over BM25 + dense
  models scores 0.343. This suggests room for hybrid improvement while still
  keeping Qwen3-0.6B as the controlled embedding model.
- FreshStack's own examples use BEIR-style run files and metrics, but this
  experiment deliberately uses **Option 1: the project pipeline with LangChain
  corpus export**, so it tests ingestion, ChromaDB storage, dense retrieval,
  BM25 sparse retrieval, RRF, and reranking together.

Known caveat: FreshStack corpus entries are already chunks. The preparation step
must preserve the FreshStack `_id` as parent metadata so evaluation can count a
hit when any project-ingested chunk maps back to a relevant FreshStack corpus ID.

## Variables

| Type                   | Variable                   | Values / treatment                                                  |
| ---------------------- | -------------------------- | ------------------------------------------------------------------- |
| Independent            | Retrieval mode             | `dense-only` / `hybrid_bm25`                                        |
| Independent            | Reranker                   | Off / On, with production decision based on rerank-on cells         |
| Independent diagnostic | Query subset               | all LangChain queries / identifier-heavy / non-identifier-heavy     |
| Dependent              | FreshStack `alpha-nDCG@10` | Nugget-aware diversity/relevance metric from FreshStack             |
| Dependent              | `Coverage@20`              | Whether retrieved evidence covers answer nuggets                    |
| Dependent              | `Recall@50`                | Fraction of relevant corpus IDs retrieved by rank 50                |
| Dependent              | Project metrics            | Hit@5/Hit@10 over parent FreshStack IDs, MRR@10                     |
| Dependent              | Latency                    | mean, P50, P95 per query and per cell                               |
| Diagnostic             | Fusion ranks               | dense rank, sparse rank, fused rank for relevant parent IDs         |
| Controlled             | Corpus                     | FreshStack LangChain October 2024 export plus Exp 9 continuity docs |
| Controlled             | Embedding model            | `qwen3-embedding:0.6b` via Ollama, matching project default         |
| Controlled             | Fusion                     | RRF `k=60`                                                          |
| Controlled             | Sparse backend             | `HYBRID_SPARSE_BACKEND=bm25`                                        |
| Controlled             | Chunking                   | Project defaults unless preparation disables re-chunking explicitly |
| Controlled             | Reranker                   | Existing ONNX cross-encoder and calibrated `÷30` scaling unchanged  |

Not changed: embedding model, reranker model, reranker threshold calibration,
RRF constant, native ChromaDB sparse-vector path, and production ChromaDB data.

## Corpus and ground truth

| Item                     | Value                                                                                           |
| ------------------------ | ----------------------------------------------------------------------------------------------- |
| Source corpus            | `freshstack/corpus-oct-2024`, config `langchain`, split `train`                                 |
| Source queries           | `freshstack/queries-oct-2024`, config `langchain`, split `test`                                 |
| Source corpus size       | 49,514 FreshStack corpus chunks                                                                 |
| Continuity corpus        | Exp 1/9 named cases: Colosseum and Exp 9 rare-term pack copied as labelled parent documents     |
| Source query size        | 203 Stack Overflow questions plus Exp 9 named-case queries                                      |
| FreshStack corpus schema | `_id`, `text`, `metadata.url`, `metadata.start_byte`, `metadata.end_byte`                       |
| FreshStack query schema  | `query_id`, `query_title`, `query_text`, `nuggets`, `answer_id`, `answer_text`, `metadata.tags` |
| Local path               | `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/corpus/langchain/`             |
| Ground truth path        | `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/ground-truth.json`             |
| Evaluation qrels path    | `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/freshstack-qrels.json`         |
| Local cache path         | `.cache/freshstack/` or HuggingFace default cache; do not commit raw Parquet files              |
| Symlinks?                | No; exported files should be real files or metadata-preserving generated manifests              |

The preparation script should write one project-ingestable file per FreshStack
corpus record or a bounded sampled subset if full ingestion is too slow for
local hardware. The preferred export format is front-matter Markdown because the
existing file ingester can preserve the parent ID without requiring one file per
metadata sidecar:

```markdown
---
freshstack_id: langchain/docs/docs_skeleton/docs/how_to/output_parser_json.md_0_4315
source_url: https://github.com/langchain-ai/langchain/...
topic: langchain
source_kind: freshstack-parent
---

<the FreshStack text field>
```

If the existing ingestion path does not preserve front-matter metadata, use an
experiment-specific direct ingestion helper that writes ChromaDB metadata
explicitly. A JSONL export is acceptable only if paired with such a helper; do
not point `rag-mcp ingest` at raw JSONL and assume metadata will survive.

Minimum valid corpus size: **10,000 FreshStack parent documents**. If local
hardware permits, ingest all 49,514 LangChain parent documents. A run below
10,000 parent documents is considered a pilot only and cannot support a default
flip recommendation.

### Identifier-heavy query tagging

Before running retrieval, classify the 203 FreshStack queries into:

- `identifier-heavy`: query title or body contains likely exact-match tokens,
  including backticked code, dotted package paths, slash paths, camelCase,
  snake_case, all-caps constants, exception names, version strings, or API/library
  names.
- `semantic`: no such token after stripping boilerplate and code blocks.

Important: Stack Overflow tags such as `langchain`, `openai`, `chroma`,
`llama-index`, `pydantic`, and `fastapi` are **diagnostic metadata**, not
sufficient evidence by themselves. If tags alone make almost every query
identifier-heavy, the partition becomes invalid. The classifier must report the
number of queries in each category and write the exact regex/rule hits to
`ground-truth.json` before any retrieval cells are run.

## Environment and prerequisites

| Requirement         | Version / value                                                                                                                          |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Python              | 3.12                                                                                                                                     |
| Package manager     | `uv`                                                                                                                                     |
| Additional packages | `datasets`, `pandas`, `pyarrow`, `freshstack`, `beir`, `rank_bm25`                                                                       |
| Embedding model     | `qwen3-embedding:0.6b` via Ollama                                                                                                        |
| Reranker            | Existing `cross-encoder/ms-marco-MiniLM-L-6-v2` ONNX path                                                                                |
| Reranker pool       | Record `RERANK_MAX_FETCH` and `RERANK_FETCH_MULTIPLIER`; production decision assumes `RERANK_MAX_FETCH=50` unless Exp 5 defaults changed |
| Hardware            | Apple Silicon Mac, 16 GB RAM; record exact model in `results.md`                                                                         |
| Key config          | `HYBRID_ENABLED`, `HYBRID_SPARSE_BACKEND=bm25`, `HYBRID_RRF_K=60`                                                                        |

```bash
uv sync --extra hybrid
uv run python -c "import datasets, pyarrow, pandas; import freshstack; import beir"
ollama list | grep qwen3-embedding
```

If these imports fail, install the experiment-only packages in a local
experiment environment or add them as dev-only dependencies after review. Do not
alter production runtime dependencies unless a follow-up OpenSpec change requires
it.

## Experimental design / cell matrix

| Run ID                | Purpose                    | Baseline / candidate | Key settings                                                        | Expected interpretation                         |
| --------------------- | -------------------------- | -------------------- | ------------------------------------------------------------------- | ----------------------------------------------- |
| `1A-dense-no-rerank`  | First-stage dense baseline | Baseline             | `HYBRID_ENABLED=false`, `rerank=false`                              | Measures dense retrieval before reranker rescue |
| `1B-hybrid-no-rerank` | Fusion isolation           | Candidate            | `HYBRID_ENABLED=true`, `HYBRID_SPARSE_BACKEND=bm25`, `rerank=false` | Shows pure BM25 + RRF effect                    |
| `2A-dense-rerank`     | Production baseline        | Baseline             | `HYBRID_ENABLED=false`, `rerank=true`                               | Matches current production-style pipeline       |
| `2B-hybrid-rerank`    | Production candidate       | Candidate            | `HYBRID_ENABLED=true`, `HYBRID_SPARSE_BACKEND=bm25`, `rerank=true`  | Main default-flip decision cell                 |

Run all cells on the same exported corpus and query set. Use fresh ChromaDB
persist directories per mode to avoid cache bleed:

- `chroma_dense/`
- `chroma_hybrid_bm25/`

Phase stop rules:

- If data preparation cannot export at least 10,000 FreshStack parent documents,
  stop and mark the experiment `BLOCKED`.
- If ingestion of the full LangChain topic exceeds local resource limits, fall
  back once to a deterministic subset sampled by query qrels plus distractors.
  The subset must include all LangChain documents cited in qrels for the 203
  queries, all Exp 9 continuity documents, and at least 9,000 randomly sampled
  non-relevant LangChain parent documents. Use a fixed RNG seed and record it in
  `ground-truth.json`.
- If fewer than 30 identifier-heavy queries remain after tagging, add Angular as
  a second FreshStack topic rather than weakening the classifier.

## Metrics

Primary metrics are gated. Diagnostic metrics explain the result but do not
alone decide pass/fail unless included under success criteria.

### Primary metrics

- **FreshStack `Coverage@20`**: proportion of answer nuggets for which at least
  one supporting corpus document appears in the top 20, using FreshStack's
  nugget-level qrels.
- **FreshStack `Recall@50`**: proportion of relevant FreshStack corpus IDs
  retrieved by rank 50.
- **Identifier-heavy `Coverage@20` lift**: candidate minus baseline, restricted
  to identifier-heavy queries.
- **Semantic/non-identifier `Coverage@20` regression**: candidate minus baseline,
  restricted to non-identifier-heavy queries.
- **P95 latency**: measured end-to-end per query, including retrieval, fusion,
  and reranking for rerank-on cells.

### Diagnostic metrics

- `alpha-nDCG@10`: FreshStack's nugget-aware ranking metric; useful for comparing
  with the public leaderboard.
- Hit@5 / Hit@10 over FreshStack parent IDs: simple sanity check that at least
  one relevant parent document was retrieved.
- MRR@10 over FreshStack parent IDs: rank sensitivity for first relevant hit.
- Dense/sparse/fused ranks for relevant parent IDs: confirms whether BM25 is
  contributing the evidence that dense misses.
- BM25 index build time and cache reuse: confirms cache behaviour from OpenSpec
  tasks 3.x.
- Chunk counts after project ingestion: detects accidental double-chunk explosion.

## Procedure / reproduction commands

Commands are intended to be run from the repository root.

### Step 1: Prepare data

```bash
uv run python experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/prepare_freshstack.py \
  --topic langchain \
  --queries-repo freshstack/queries-oct-2024 \
  --corpus-repo freshstack/corpus-oct-2024 \
  --output-dir experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30 \
  --min-parent-docs 10000 \
  --prefer-full-corpus
```

The script must create:

- `corpus/langchain/` with exported front-matter Markdown files, or JSONL plus
  a direct ingestion helper;
- `freshstack-qrels.json` preserving nugget-level qrels;
- `ground-truth.json` with query text, FreshStack query ID, relevant parent IDs,
  nugget IDs, query category, identifier-rule hits, RNG seed, and the Exp 9
  named-case queries/categories.

### Step 2: Build indexes / fixtures

```bash
CHROMA_PERSIST_DIR=experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/chroma_dense \
HYBRID_ENABLED=false \
uv run rag-mcp ingest experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/corpus/langchain

CHROMA_PERSIST_DIR=experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/chroma_hybrid_bm25 \
HYBRID_ENABLED=true HYBRID_SPARSE_BACKEND=bm25 HYBRID_RRF_K=60 \
uv run rag-mcp ingest experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/corpus/langchain
```

If the project CLI does not preserve the required FreshStack parent metadata,
use a small experiment-specific ingestion helper instead of the CLI and record
that helper as an artefact.

### Step 3: Run evaluation

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/run_eval.py \
  --modes dense-only,hybrid_bm25 \
  --rerank-cross \
  --resume \
  --k-values 5 10 20 50
```

The runner must assert that `retrieval.search()` exposes `hybrid` and must fail
loudly if not. It must save raw per-query results, parent-ID mappings, latency,
and fusion diagnostics to `eval_results.json`.

**Checkpoint and resume**: The runner saves an atomic checkpoint to
`eval_results_checkpoint.json` after each completed cell (mode × rerank combination).
Use `--resume` to load the checkpoint and skip already-completed cells if the
experiment is interrupted. The checkpoint is written atomically (write to `.tmp`
then rename) to prevent corruption. This allows the experiment to be safely
resumed without losing progress from earlier cells.

### Step 4: Summarise raw results

```bash
uv run python experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/summarise_eval.py \
  --input experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/eval_results.json \
  --output experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/eval_results.summary.json
```

## Success criteria / pass gates

| Criterion               |                                                                                                                          Threshold | Why this threshold matters                                       |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------: | ---------------------------------------------------------------- |
| Corpus validity         |                                                                                                             `parent_docs >= 10000` | Prevents the Experiment 9 ceiling effect from recurring          |
| Production quality lift |  `hybrid_rerank Coverage@20 >= dense_rerank Coverage@20 + 0.05` **and** `hybrid_rerank Recall@50 >= dense_rerank Recall@50 + 0.05` | Supports default flip on realistic technical retrieval           |
| Identifier-heavy lift   |                                         `hybrid_rerank Coverage@20 >= dense_rerank Coverage@20 + 0.08` on identifier-heavy queries | Tests the exact failure mode hybrid was built for                |
| Semantic guardrail      |                                                                                non-identifier `Coverage@20 >= dense_rerank - 0.02` | Avoids trading semantic retrieval quality for rare-token recall  |
| Latency guardrail       |                                                                                      `hybrid_rerank P95 <= 1.5 * dense_rerank P95` | Keeps production responsiveness within Tier 3 budget             |
| BM25 contribution       | For at least 25% of improved identifier-heavy queries, a relevant parent has `sparse_rank < dense_rank` or no dense rank in top 50 | Demonstrates BM25/RRF, not noise, caused the lift                |
| Continuity cases        |                                                                               Exp 9 named cases do not regress under hybrid rerank | Preserves original Colosseum and rare-term regression guarantees |

A recommendation to flip `HYBRID_ENABLED=true` requires all gates to pass.
A recommendation to keep hybrid opt-in requires any primary quality gate or
semantic/latency guardrail to fail.

## Interpretation rules

- If all gates pass: recommend a small follow-up change to flip
  `HYBRID_ENABLED=true` while keeping `HYBRID_SPARSE_BACKEND=bm25` until native
  sparse retrieval is separately validated.
- If quality improves only without reranking: keep hybrid opt-in and investigate
  reranker pool size, because the production pipeline did not benefit.
- If identifier-heavy queries improve but semantic queries regress: keep hybrid
  opt-in and propose a weighted-RRF follow-up experiment.
- If latency fails but quality passes: keep hybrid opt-in, document the quality
  benefit, and investigate BM25 index construction, cache reuse, and concurrent
  dispatch.
- If corpus validity fails or dense-only again saturates: mark the experiment
  inconclusive and escalate to all FreshStack topics or CQADupstack.

## What to do if the experiment fails

1. **Corpus too small or too slow**: switch from full LangChain to a deterministic
   qrels-plus-distractors subset with at least 10,000 parent documents.
2. **Too few identifier-heavy queries**: add the FreshStack Angular topic, whose
   queries include Angular 16/17/18 API and TypeScript identifiers.
3. **Quality does not improve**: record a negative result and keep
   `HYBRID_ENABLED=false`; inspect dense/sparse rank diagnostics before changing
   fusion logic.
4. **Semantic regression**: inspect BM25-injected false positives and consider a
   future weighted-RRF experiment rather than changing this experiment post hoc.
5. **Latency breach**: verify BM25 cache reuse, collection scan paging, and
   `asyncio.gather`/thread offload before proposing implementation changes.

## Implementation notes

- Code path under test: `rag_mcp.retrieval.search(..., hybrid=...)`,
  `rag_mcp.sparse_retriever.BM25SparseRetriever`, RRF fusion helper, and the
  existing reranker path.
- **Retrieval candidate pool fixes** (applied before this experiment run):
  - `_hybrid_query_rows()` now caps the fused RRF union to `[:fetch_k]` to ensure
    hybrid mode sends ~500 candidates to the reranker (matching dense mode), rather
    than ~1000 (dense + sparse union). This fixes an experimental inconsistency where
    hybrid had an unfair advantage due to larger candidate pool size.
  - `search()` now enforces `results = results[:top_k]` after final sorting to
    guarantee the returned result count matches the requested `top_k` in all modes
    (dense, hybrid, reranked, non-reranked).
  - All 4 cells (dense/hybrid × rerank on/off) were rerun with the patched
    `retrieval.py` to ensure fair comparison under consistent conditions (Option B).
- Use parent FreshStack IDs as the evaluation unit. If project ingestion creates
  multiple chunks per FreshStack parent, collapse retrieved chunks back to their
  `freshstack_id` before computing metrics.
- FreshStack documents are already chunks. Avoid unnecessary re-chunking if the
  ingestion API supports metadata-preserving direct chunk insertion. If it does
  not, record the observed project chunk count and treat it as diagnostic.
- Do not use FreshStack's native BEIR evaluator as the sole result. It may be
  used to cross-check metrics, but the main result must run through the project
  ChromaDB + BM25 + RRF + reranker pipeline.
- FreshStack leaderboard metrics are reference context only. Do not compare
  absolute scores as if they were equivalent unless query text, corpus subset,
  chunking, model, and evaluation code are identical.
- Keep the calibrated reranker `÷30` threshold scaling unchanged. Hybrid changes
  candidate generation, not reranker scoring.

## Cleanup

```bash
rm -rf experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/chroma_dense \
       experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/chroma_hybrid_bm25
```

Keep `eval_results.json`, `eval_results.summary.json`, `ground-truth.json`,
`freshstack-qrels.json`, and `results.md`. The FreshStack-exported corpus can be
regenerated, but if retained it must be documented in `artifacts.md` if too large
for git.

## Results summary

**Date completed**: 2026-05-31  
**Recommendation**: KEEP `HYBRID_ENABLED=false` default; hybrid remains opt-in  
**Pass gates**: 4 of 7 passed; 3 primary quality gates failed

| Gate                                    | Threshold          |     Observed | Pass? |
| --------------------------------------- | ------------------ | -----------: | :---: |
| Corpus validity                         | ≥ 10,000 parents   |       10,025 |  ✅   |
| Production coverage lift (rerank)       | ≥ +0.05            |       +0.001 |  ❌   |
| Production recall lift (rerank)         | ≥ +0.05            |       +0.002 |  ❌   |
| Identifier-heavy coverage lift (rerank) | ≥ +0.08            |       −0.002 |  ❌   |
| Semantic guardrail                      | ≥ −0.02 regression |       +0.167 |  ✅   |
| Latency P95 ratio                       | ≤ 1.5×             |        0.61× |  ✅   |
| BM25 contribution                       | ≥ 25% sparse-help  | 100% (10/10) |  ✅   |
| Continuity non-regression               | No regression      |    0.9 = 0.9 |  ✅   |

**Key finding**: Hybrid BM25 retrieval without reranking improves Coverage@20 by
+4.6 pp over dense-only without reranking (0.738 vs 0.692), confirming that BM25
adds genuine retrieval value. However, the existing reranker collapses both
modes to near-identical coverage (~0.54), eliminating the hybrid advantage. The
reranker's candidate pool (`RERANK_MAX_FETCH=50`) is too small relative to the
10,025-document corpus, causing it to discard hybrid's first-stage gains. BM25
is contributing real evidence (sparse rank < dense rank for all 10 improved
identifier-heavy queries), but the reranker bottleneck prevents that evidence
from reaching the final result set.

**Next steps**: Investigate reranker pool sizing (`RERANK_MAX_FETCH ≥ 200`) or a
two-stage reranker cascade before reconsidering the default flip. See full
results in `output/results.md`.

## Artefacts

Files committed to git (✓) vs. gitignored generated artefacts (✗).
Ignored files are reproducible from `prepare_freshstack.py` and `build_indexes.py`.
See experiment-level `.gitignore` for the full ignore list.

| File / directory                      | Description                                                        |   In git?    |
| ------------------------------------- | ------------------------------------------------------------------ | :----------: |
| `protocol.md`                         | This plan                                                          |      ✅      |
| `prepare_freshstack.py`               | Downloads/exports FreshStack LangChain corpus and qrels            |      ✅      |
| `run_eval.py`                         | Runs dense/hybrid × rerank grid through project retrieval pipeline |      ✅      |
| `summarise_eval.py`                   | Aggregates raw results into tables                                 |      ✅      |
| `build_indexes.py`                    | Experiment-specific ChromaDB direct ingestion helper               |      ✅      |
| `freshstack-qrels.json`               | Nugget-level qrels preserving FreshStack structure (3.9 MB)        |      ✅      |
| `output/results.md`                   | Human-readable result narrative and default recommendation         |      ✅      |
| `output/eval_results.summary.json`    | Aggregated metrics by cell and query category (8.3 KB)             |      ✅      |
| `output/index_build.json`             | Index build metadata and corpus counts                             |      ✅      |
| `ground-truth.json`                   | Query categories and relevant parent IDs (5.4 MB)                  | ✗ root rule  |
| `corpus/`                             | Exported corpus + continuity docs (66 MB, ~10k files)              | ✗ root rule  |
| `output/eval_results.json`            | Raw per-query results (21 MB)                                      | ✗ root rule  |
| `output/eval_results_checkpoint.json` | Cell-by-cell checkpoint (21 MB)                                    | ✗ local rule |
| `output/chroma_dense/`                | ChromaDB index for dense mode (315 MB)                             | ✗ local rule |
| `output/chroma_hybrid_bm25/`          | ChromaDB index for hybrid mode (310 MB)                            | ✗ local rule |
| `output/*.log`                        | Run logs                                                           | ✗ local rule |

## References

- `experiments/9-hybrid-retrieval-2026-05-27/protocol.md` — original hybrid
  retrieval experiment protocol.
- `experiments/9-hybrid-retrieval-2026-05-27/results.md` — Experiment 9 ceiling
  result: dense-only saturated on 55 chunks, so rare-term lift was 0 pp.
- `openspec/changes/rag-hybrid-retrieval/design.md` — Tier 3 hybrid retrieval
  design: BM25 sparse backend, RRF `k=60`, unchanged reranker integration.
- `openspec/changes/rag-hybrid-retrieval/tasks.md` — experiment tasks 9.x and
  validation tasks 12.x/13.x.
- `docs/adr/017-hybrid-retrieval-rrf.md` — architectural record for BM25 + RRF
  hybrid retrieval and default-flip decision boundary.
- Thakur, N., Lin, J., Havens, S., Carbin, M., Khattab, O. & Drozdov, A. (2025).
  _FreshStack: Building Realistic Benchmarks for Evaluating Retrieval on
  Technical Documents_. arXiv:2504.13128. https://arxiv.org/abs/2504.13128
- FreshStack HuggingFace organisation: https://huggingface.co/freshstack
- FreshStack corpus dataset: `freshstack/corpus-oct-2024`, especially config
  `langchain`; dataset card reports 49,514 LangChain corpus documents and the
  schema `_id`, `text`, `metadata`.
- FreshStack query dataset: `freshstack/queries-oct-2024`, especially config
  `langchain`; dataset card reports 203 LangChain test queries with nuggets,
  relevant corpus IDs, accepted answers, and metadata tags.
- FreshStack GitHub repository and evaluation examples:
  https://github.com/fresh-stack/freshstack
- Cormack, G. V., Clarke, C. L. A. & Buettcher, S. (2009). _Reciprocal rank
  fusion outperforms Condorcet and individual rank learning methods_.
  Proceedings of SIGIR 2009, 758–759. DOI: `10.1145/1571941.1572114`.
- Robertson, S. & Zaragoza, H. (2009). _The Probabilistic Relevance Framework:
  BM25 and Beyond_. Foundations and Trends in Information Retrieval, 4(1–2),
  1–174. DOI: `10.1561/1500000019`.
- FreshStack leaderboard snapshot cited from the project README: Qwen3-0.6B
  embedding average `alpha@10` 0.262, BM25 0.218, and fusion run 0.343.
