# Experiment 10: Reranker Technical Workload Calibration

**ID**: `10-reranker-technical-workload-calibration-2026-05-31`
**Date planned**: 2026-05-31
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: FAIL for current reranker policy; INCONCLUSIVE for effective pool-size sensitivity — reranking with an effective fetch pool of 500 substantially underperformed rerank-off retrieval on the technical workload. The intended labelled `RERANK_MAX_FETCH` sweep did not vary effective fetch size because `top_k=50` and `RERANK_FETCH_MULTIPLIER=10` forced all reranker-on cells to `fetch_k=500`. Recommends disabling reranking for technical/hybrid workloads while treating pool-size sensitivity as unresolved.
**Relation**: Follow-up to `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/`; OpenSpec change `rag-reranker-technical-workload-calibration`; ADR-018 balanced retrieval defaults

---

## Why this experiment exists

Experiment 9a demonstrated that hybrid BM25 + RRF retrieval genuinely improves
first-stage retrieval on realistic technical documentation (+4.6 pp Coverage@20
over dense-only). However, the existing reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`
with `RERANK_MAX_FETCH=50`) erased that advantage entirely, collapsing both
dense and hybrid modes to near-identical coverage (~0.54). The reranker even
hurt quality: both dense and hybrid modes scored _worse_ with reranking than
without on Coverage@20 and Recall@50.

The most plausible explanation is domain mismatch plus aggressive filtering.
The cross-encoder is trained on general web passage ranking, not code
identifiers, API names, error messages, and technical documentation. When fed
only 50 candidates from a 10,025-document corpus, it discards relevant
exact-match evidence that BM25/RRF recovered. Experiment 5 calibrated the pool
size on a tiny five-document fixture, so it could not detect this problem.

This experiment determines whether reranking should stay on by default for
technical corpora, use different pool sizing, use a different reranker model,
or be disabled when hybrid retrieval is active.

## Hypothesis

On the FreshStack LangChain technical documentation corpus (10,025 parents):

1. **Pool-size hypothesis**: Increasing `RERANK_MAX_FETCH` from 50 to ≥200
   recovers hybrid's first-stage advantage, improving Coverage@20 by at least
   3 pp over the current `RERANK_MAX_FETCH=50` default for hybrid retrieval.
2. **Dense-only pool hypothesis**: Increasing `RERANK_MAX_FETCH` also improves
   dense-only Coverage@20 by at least 2 pp, confirming the pool bottleneck
   affects both retrieval modes.
3. **Diminishing returns guard**: `RERANK_MAX_FETCH=500` does not improve
   Coverage@20 by more than 2 pp over `RERANK_MAX_FETCH=200` for hybrid,
   establishing a practical ceiling.
4. **Reranker-off baseline**: Reranker-off hybrid remains the strongest
   single-cell configuration, providing a ceiling reference for any reranker
   policy.

## Background and prior evidence

- Experiment 9a results (`experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/results.md`):
  - Hybrid no-rerank Coverage@20 = 0.738 vs dense no-rerank = 0.692 (+4.6 pp)
  - Hybrid rerank Coverage@20 = 0.540 vs dense rerank = 0.539 (+0.1 pp)
  - Reranker degraded both modes by ~15-20 pp
  - BM25 contributed real evidence (sparse rank < dense rank for all 10 improved queries)
- Experiment 5 (`experiments/5-reranker-pool-sizing-2026-05-27/`): Calibrated pool
  sizing on a 5-document corpus; `RERANK_MAX_FETCH=50` was sufficient because
  the corpus was smaller than the pool.
- ADR-018 (`docs/adr/018-balanced-retrieval-defaults.md`): Promotes
  `TOP_K=10`, `RERANK_ENABLED=true`, `CHUNK_OVERLAP=100` based on Qasper-style
  evidence retrieval. The ADR notes that technical workloads may need different
  reranker settings.
- Reranker model: `cross-encoder/ms-marco-MiniLM-L-6-v2` trained on MS MARCO
  passage ranking. Not specifically trained for code or technical documentation.

## Variables

| Type        | Variable           | Values / treatment                                                                             |
| ----------- | ------------------ | ---------------------------------------------------------------------------------------------- |
| Independent | Retrieval mode     | `dense-only` / `hybrid_bm25`                                                                   |
| Independent | Reranker policy    | `off` / `default` (max_fetch=50) / `gentle_200` (max_fetch=200) / `gentle_500` (max_fetch=500) |
| Dependent   | Coverage@20        | Proportion of answer nuggets covered in top 20                                                 |
| Dependent   | Recall@50          | Fraction of relevant corpus IDs retrieved by rank 50                                           |
| Dependent   | alpha-nDCG@10      | Nugget-aware diversity/relevance metric                                                        |
| Dependent   | Hit@10             | Whether any relevant parent is in top 10                                                       |
| Dependent   | MRR@10             | Mean reciprocal rank of first relevant hit                                                     |
| Dependent   | Latency            | Mean, P50, P95 per query and per cell                                                          |
| Controlled  | Corpus             | FreshStack LangChain 10,025 parents (reused from Exp 9a)                                       |
| Controlled  | Embedding model    | `qwen3-embedding:0.6b` via Ollama                                                              |
| Controlled  | Reranker model     | `cross-encoder/ms-marco-MiniLM-L-6-v2` ONNX (unchanged)                                        |
| Controlled  | Reranker threshold | ÷30 calibrated scaling (unchanged)                                                             |
| Controlled  | Fusion             | RRF `k=60`                                                                                     |
| Controlled  | Top-k              | 50 (to measure Recall@50)                                                                      |

## Corpus and ground truth

| Item             | Value                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------- |
| Source           | Reused from Experiment 9a                                                                         |
| Corpus path      | `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/corpus/langchain/`               |
| Manifest         | `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/corpus/langchain_manifest.jsonl` |
| Ground truth     | `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/output/ground-truth.json`        |
| Qrels            | `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/freshstack-qrels.json`           |
| Parent documents | 10,025 (10,005 FreshStack LangChain + 20 continuity)                                              |
| Queries          | 223 (203 FreshStack test + 20 continuity)                                                         |
| Query categories | 200 identifier-heavy, 3 semantic, 20 continuity                                                   |
| Selection mode   | qrels-plus-distractors (deterministic, seed 20260530)                                             |

We reuse the Experiment 9a data without modification. The corpus, ground truth,
qrels, and Chroma indexes are symlinked or copied. The indexes are rebuilt only
if the manifest has changed (it has not).

## Environment and prerequisites

| Requirement     | Version / value                                                  |
| --------------- | ---------------------------------------------------------------- |
| Python          | 3.12                                                             |
| Package manager | `uv`                                                             |
| Embedding model | `qwen3-embedding:0.6b` via Ollama                                |
| Reranker        | `cross-encoder/ms-marco-MiniLM-L-6-v2` ONNX path                 |
| Hardware        | Apple Silicon Mac, 16 GB RAM; record exact model in `results.md` |
| Key config      | `HYBRID_RRF_K=60`, `HYBRID_SPARSE_BACKEND=bm25`                  |

```bash
uv sync --extra hybrid
ollama list | grep qwen3-embedding
```

## Experimental design / cell matrix

### Minimum cells (8 cells)

| Run ID                 | Purpose                     | Key settings                                         | Expected interpretation     |
| ---------------------- | --------------------------- | ---------------------------------------------------- | --------------------------- |
| `1A-dense-off`         | Dense first-stage baseline  | `dense-only`, `rerank=false`                         | Dense quality ceiling       |
| `1B-dense-default`     | Current production dense    | `dense-only`, `rerank=true`, `RERANK_MAX_FETCH=50`   | Current default behaviour   |
| `1C-dense-gentle-200`  | Gentler pool dense          | `dense-only`, `rerank=true`, `RERANK_MAX_FETCH=200`  | Pool-size effect on dense   |
| `1D-dense-gentle-500`  | Wide pool dense             | `dense-only`, `rerank=true`, `RERANK_MAX_FETCH=500`  | Diminishing returns ceiling |
| `2A-hybrid-off`        | Hybrid first-stage baseline | `hybrid_bm25`, `rerank=false`                        | Hybrid quality ceiling      |
| `2B-hybrid-default`    | Current production hybrid   | `hybrid_bm25`, `rerank=true`, `RERANK_MAX_FETCH=50`  | Known-bad baseline from 9a  |
| `2C-hybrid-gentle-200` | Gentler pool hybrid         | `hybrid_bm25`, `rerank=true`, `RERANK_MAX_FETCH=200` | Pool-size effect on hybrid  |
| `2D-hybrid-gentle-500` | Wide pool hybrid            | `hybrid_bm25`, `rerank=true`, `RERANK_MAX_FETCH=500` | Diminishing returns ceiling |

### Phase stop rules

- Phase 1 stop rule: If the 9a corpus data is unavailable or corrupted, stop
  and mark `BLOCKED`. Do not regenerate corpus.
- Phase 2 stop rule: If any `RERANK_MAX_FETCH` value causes OOM or exceeds
  reasonable latency (>300s P95), skip that cell and record why.

## Metrics

### Primary metrics

- **Coverage@20**: Proportion of answer nuggets for which at least one
  supporting corpus document appears in the top 20.
- **Recall@50**: Proportion of relevant FreshStack corpus IDs retrieved by rank 50.
- **Coverage@20 lift**: Candidate minus baseline, restricted to identifier-heavy
  queries and all queries.

### Diagnostic metrics

- `alpha-nDCG@10`: FreshStack's nugget-aware ranking metric.
- Hit@5 / Hit@10 over FreshStack parent IDs.
- MRR@10 over FreshStack parent IDs.
- Mean, P50, P95 latency per cell.
- Reranker diagnostics: number of candidates scored, number of candidates
  surviving threshold.

## Procedure / reproduction commands

Commands are run from the repository root.

### Step 1: Verify corpus reuse

```bash
# Verify 9a data exists
ls experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/output/ground-truth.json
ls experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/corpus/langchain_manifest.jsonl
```

### Step 2: Build indexes (reuse from 9a or rebuild)

```bash
# Copy 9a indexes if they exist, otherwise build fresh
python experiments/10-reranker-technical-workload-calibration-2026-05-31/build_indexes.py
```

### Step 3: Run evaluation

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/10-reranker-technical-workload-calibration-2026-05-31/run_eval.py \
  --modes dense-only,hybrid_bm25 \
  --rerank-cross \
  --reranker-pools 50,200,500 \
  --resume \
  --k-values 5 10 20 50 \
  2>&1 | tee experiments/10-reranker-technical-workload-calibration-2026-05-31/output/run_eval.log
```

The runner saves raw per-query results, parent-ID mappings, latency, and
reranker diagnostics to `eval_results.json`.

**Checkpoint and resume**: The runner saves an atomic checkpoint to
`eval_results_checkpoint.json` after each completed cell (mode × rerank pool
combination). Use `--resume` to load the checkpoint and skip already-completed
cells if the experiment is interrupted.

### Step 4: Summarise raw results

```bash
uv run python experiments/10-reranker-technical-workload-calibration-2026-05-31/summarise_eval.py
```

## Success criteria / pass gates

| Criterion                                          |                                               Threshold | Why this threshold matters                             |
| -------------------------------------------------- | ------------------------------------------------------: | ------------------------------------------------------ |
| Pool-size lift (hybrid, pool=200 vs pool=50)       |                                     Coverage@20 ≥ +0.03 | Confirms pool bottleneck is the cause of 9a failure    |
| Pool-size lift (dense, pool=200 vs pool=50)        |                                     Coverage@20 ≥ +0.02 | Confirms pool bottleneck affects both modes            |
| Diminishing returns (hybrid, pool=500 vs pool=200) |                                Coverage@20 lift ≤ +0.02 | Establishes practical pool-size ceiling                |
| Reranker-off ceiling                               | Reranker-off hybrid Coverage@20 ≥ best reranker-on cell | Reranker-off must be at least as good (reference cell) |
| Latency guardrail                                  |                       P95 for pool=200 ≤ 3× pool=50 P95 | Keeps latency within acceptable budget                 |
| Non-regression on continuity                       |             Continuity Coverage@20 ≥ 0.90 for all cells | Preserves Exp 9 named-case guarantees                  |

## Interpretation rules

- If pool-size lift passes for both modes: recommend updating `RERANK_MAX_FETCH`
  to 200 (or the value that passes with best latency) and update the ADR.
- If pool-size lift passes for hybrid but not dense: recommend larger pool
  specifically for hybrid mode (conditional policy).
- If pool=500 shows meaningful improvement over pool=200: consider even larger
  pools, but flag latency concerns.
- If no pool size helps (pool=500 still far below reranker-off): recommend
  disabling reranking for technical/hybrid workloads. The cross-encoder model
  is fundamentally mismatched for this workload.
- If pool=200 passes quality but fails latency: document the trade-off and
  keep reranking opt-in for technical workloads.

## What to do if the experiment fails

1. **Pool sizing does not help**: Record a negative result. Recommend
   `RERANK_ENABLED=false` for technical workloads. Propose model research
   (technical-document reranker) as a follow-up.
2. **Latency too high at large pools**: Document the quality-latency trade-off.
   Consider two-stage reranking or faster models as follow-up.
3. **Corpus data unavailable**: Mark as `BLOCKED`. Re-run `prepare_freshstack.py`
   from Experiment 9a to regenerate.
4. **Inconclusive results**: Mark as `INCONCLUSIVE`. Propose extending to more
   FreshStack topics (Angular, React) for broader evidence.

## Implementation notes

- Code path under test: `rag_mcp.retrieval.search()`, reranker integration in
  `rag_mcp.reranker.py`, config `RERANK_MAX_FETCH` / `RERANK_FETCH_MULTIPLIER`.
- The runner patches `RERANK_MAX_FETCH` and `RERANK_FETCH_MULTIPLIER` per cell
  via environment variables and module-level globals.
- Reranker model and ÷30 threshold scaling remain unchanged across all cells.
- Corpus is reused verbatim from Experiment 9a. No re-ingestion needed.
- ChromaDB indexes are copied from 9a's `output/chroma_dense/` and
  `output/chroma_hybrid_bm25/` directories.
- Candidate-pool semantics are consistent: each cell uses the same
  `RERANK_FETCH_MULTIPLIER=10` with varying `RERANK_MAX_FETCH`.
- Keep the calibrated reranker ÷30 threshold scaling unchanged.

## Cleanup

```bash
# Remove copied Chroma indexes if desired
rm -rf experiments/10-reranker-technical-workload-calibration-2026-05-31/output/chroma_*
```

Keep `eval_results.json`, `eval_results.summary.json`, `ground-truth.json`,
and `results.md`. Do not delete the 9a corpus data.

## Artefacts expected

| File / directory                      | Description                            | Required? |
| ------------------------------------- | -------------------------------------- | :-------: |
| `protocol.md`                         | This plan                              |    ✅     |
| `results.md`                          | Human-readable result report           |    ✅     |
| `run_eval.py`                         | Evaluation runner with pool-size sweep |    ✅     |
| `summarise_eval.py`                   | Aggregates raw results                 |    ✅     |
| `build_indexes.py`                    | Copies or builds Chroma indexes        |    ✅     |
| `output/eval_results.json`            | Raw per-query results                  |    ✅     |
| `output/eval_results.summary.json`    | Aggregated metrics                     |    ✅     |
| `output/eval_results_checkpoint.json` | Cell-by-cell checkpoint                |  Usually  |
| `output/*.log`                        | Run logs                               | Optional  |

## References

- `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/results.md` —
  Experiment 9a results showing reranker bottleneck.
- `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/protocol.md` —
  Experiment 9a protocol with cell design.
- `experiments/5-reranker-pool-sizing-2026-05-27/` — Original pool-size
  calibration on tiny corpus.
- `docs/adr/018-balanced-retrieval-defaults.md` — Current balanced defaults.
- `openspec/changes/rag-reranker-technical-workload-calibration/` — OpenSpec
  change driving this experiment.
- Thakur et al. (2025). _FreshStack: Building Realistic Benchmarks for
  Evaluating Retrieval on Technical Documents_. arXiv:2504.13128.
