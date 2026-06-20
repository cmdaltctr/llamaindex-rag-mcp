# Experiment 10 Results: Reranker Technical Workload Calibration

**ID**: `10-reranker-technical-workload-calibration-2026-05-31`
**Date run**: 2026-05-31
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: FAIL for current reranker policy; INCONCLUSIVE for effective pool-size sensitivity
**Outcome**: Reranking with an effective candidate pool of 500 substantially degrades FreshStack technical retrieval. The intended `RERANK_MAX_FETCH` sweep did not vary the effective fetch size, so this experiment does not prove pool size is irrelevant.
**Raw data**: [`output/eval_results.json`](./output/eval_results.json), [`output/eval_results.summary.json`](./output/eval_results.summary.json)

---

## TL;DR / Decision

- **Decision**: Disable `RERANK_ENABLED` by default for technical/hybrid workloads using the current `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker.
- **Winning configuration**: `hybrid_bm25`, `rerank=false`, `top_k=50` — Coverage@20 = 0.738, Hit@10 = 0.825, P95 latency = 2.2 s.
- **Main measured effect**: Hybrid rerank-on retrieval at effective `fetch_k=500` drops Coverage@20 from 0.738 to 0.540 and raises mean latency from 753 ms to ~14.3–14.9 s.
- **Important methodological correction**: The labelled `RERANK_MAX_FETCH` cells (50, 200, 500) all resolved to the same effective fetch size because `top_k=50` and `RERANK_FETCH_MULTIPLIER=10`, so `fetch_k=max(RERANK_MAX_FETCH, 500)=500` for every reranker-on cell.
- **Therefore**: The experiment supports disabling the current reranker for this technical workload, but it does **not** validly measure pool-size sensitivity.

## Hypothesis / Purpose

The pre-registered hypothesis was:

> Increasing `RERANK_MAX_FETCH` from 50 to ≥200 recovers hybrid's first-stage advantage, improving Coverage@20 by at least 3 pp over the current `RERANK_MAX_FETCH=50` default for hybrid retrieval. Increasing `RERANK_MAX_FETCH` should also improve dense-only Coverage@20 by at least 2 pp.

**Verdict**: The policy hypothesis failed, but the pool-size hypothesis is methodologically inconclusive. The experiment shows that reranking is harmful even with an effective wide pool of 500 candidates. It does not show that effective pools of 50, 200, and 500 behave identically, because those effective pool sizes were not actually evaluated.

## Background

Experiment 9a showed that hybrid BM25 + RRF retrieval improves first-stage retrieval on FreshStack LangChain technical documentation (+4.6 pp Coverage@20 over dense-only), but the existing reranker erased that advantage. The most plausible pre-run explanation was a pool-size bottleneck: perhaps the reranker only saw 50 candidates and discarded BM25-recovered exact-match evidence before it could help.

Experiment 10 was intended to test whether wider reranker pools (200 or 500 candidates) could recover the hybrid first-stage advantage.

## Variables

| Type | Variable | Values actually labelled/run |
| --- | --- | --- |
| Independent | Retrieval mode | `dense-only`, `hybrid_bm25` |
| Independent | Labelled `RERANK_MAX_FETCH` | 50, 200, 500 |
| Independent | Reranker enabled | `true`, `false` baseline |
| Dependent | Coverage@20 | Proportion of answer nuggets covered in top 20 |
| Dependent | Recall@50 | Fraction of relevant corpus IDs retrieved by rank 50 |
| Dependent | α-nDCG@10 | Nugget-aware diversity/relevance metric |
| Dependent | Hit@10 | Whether any relevant parent is in top 10 |
| Dependent | MRR@10 | Mean reciprocal rank of first relevant hit |
| Dependent | Latency | Mean, P50, P95 per query and per cell |
| Controlled | Corpus | FreshStack LangChain 10,025 parents, reused from Exp 9a |
| Controlled | Embedding model | `qwen3-embedding:0.6b` via Ollama |
| Controlled | Reranker model | `cross-encoder/ms-marco-MiniLM-L-6-v2` ONNX |
| Controlled | Fusion | RRF `k=60` |
| Controlled | Requested final top-k | 50 |
| Controlled | Rerank fetch multiplier | 10 |

### Effective fetch-size caveat

The retrieval code computes reranker candidate pool size as:

```python
fetch_k = max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)
```

This experiment requested `top_k=50` and used `RERANK_FETCH_MULTIPLIER=10`, so:

```text
top_k * RERANK_FETCH_MULTIPLIER = 50 * 10 = 500
```

Therefore all labelled reranker-on pool cells had the same effective fetch size:

| Labelled `RERANK_MAX_FETCH` | Effective `fetch_k` |
| ---: | ---: |
| 50 | 500 |
| 200 | 500 |
| 500 | 500 |

This means the labelled pool sweep did not test distinct effective pool sizes. Any interpretation of the results must treat the reranker-on cells as repeated evaluations of an effective `fetch_k=500` configuration, not as a valid 50/200/500 pool-size comparison.

## Environment and corpus

| Item | Value |
| --- | --- |
| Python | 3.12 |
| Package manager | `uv` |
| Embedding model | `qwen3-embedding:0.6b` via Ollama |
| Reranker model | `cross-encoder/ms-marco-MiniLM-L-6-v2` ONNX |
| LLM | Not used; retrieval-only evaluation |
| Hardware | Apple Silicon Mac, arm64, macOS 26.5, 16 GB RAM |
| Corpus source | FreshStack LangChain, reused from Experiment 9a |
| Parent documents | 10,025: 10,009 FreshStack + 16 continuity docs |
| Queries | 223: 200 identifier-heavy FreshStack, 3 semantic FreshStack, 20 continuity |
| Selection mode | qrels-plus-distractors-subset, seed 20260530 |
| ChromaDB indexes | Copied from Exp 9a: `chroma_dense/`, `chroma_hybrid_bm25/` |

The raw summary originally double-counted continuity rows because continuity queries had both `category="continuity"` and `source_kind="continuity-query"`. `summarise_eval.py` has been corrected; the regenerated summary now reports **20** continuity queries per cell.

## Method / reproduction

### Step 1: Verify corpus reuse

```bash
ls experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/output/ground-truth.json
ls experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/corpus/langchain_manifest.jsonl
```

### Step 2: Build indexes

```bash
uv run python experiments/10-reranker-technical-workload-calibration-2026-05-31/build_indexes.py
```

### Step 3: Run evaluation

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/10-reranker-technical-workload-calibration-2026-05-31/run_eval.py \
  --modes dense-only,hybrid_bm25 \
  --rerank-cross \
  --reranker-pools 50 200 500 \
  --resume \
  --k-values 5 10 20 50 \
  2>&1 | tee experiments/10-reranker-technical-workload-calibration-2026-05-31/output/run_eval.log
```

### Step 4: Summarise raw results

```bash
uv run python experiments/10-reranker-technical-workload-calibration-2026-05-31/summarise_eval.py
```

## Results

### Main summary table

All metrics below are aggregated over all 223 queries.

| Config / cell | Effective fetch_k | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | Mean ms | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dense-only, rerank off | 50 | 0.692 | 0.519 | 0.388 | 0.776 | 0.513 | 926 | 3,078 |
| **hybrid_bm25, rerank off** | 50 | **0.738** | **0.549** | **0.426** | **0.825** | **0.578** | **753** | **2,218** |
| dense-only, labelled pool=50 | 500 | 0.539 | 0.353 | 0.262 | 0.601 | 0.346 | 15,240 | 26,100 |
| dense-only, labelled pool=200 | 500 | 0.539 | 0.353 | 0.262 | 0.601 | 0.346 | 14,313 | 22,092 |
| dense-only, labelled pool=500 | 500 | 0.539 | 0.353 | 0.262 | 0.601 | 0.346 | 13,669 | 20,017 |
| hybrid_bm25, labelled pool=50 | 500 | 0.540 | 0.354 | 0.262 | 0.596 | 0.346 | 14,346 | 24,765 |
| hybrid_bm25, labelled pool=200 | 500 | 0.540 | 0.354 | 0.262 | 0.596 | 0.346 | 14,892 | 25,059 |
| hybrid_bm25, labelled pool=500 | 500 | 0.540 | 0.354 | 0.262 | 0.596 | 0.346 | 14,365 | 25,006 |

The reranker-on aggregate metrics are identical across labelled pool sizes because the effective fetch size is identical. This equality should not be interpreted as evidence that pool size is irrelevant; it is a consequence of the fetch-size formula and the chosen `top_k`/multiplier settings.
### Reranker impact at effective fetch_k=500

The meaningful comparison is not labelled pool=50 vs 200 vs 500. The meaningful comparison is rerank-off vs rerank-on with effective `fetch_k=500`.

#### Hybrid mode

| Metric | Hybrid rerank off | Hybrid rerank on, effective fetch_k=500 | Absolute Δ | Relative Δ |
| --- | ---: | ---: | ---: | ---: |
| Coverage@20 | 0.738 | 0.540 | −0.198 | −26.8% |
| Recall@50 | 0.549 | 0.354 | −0.195 | −35.5% |
| α-nDCG@10 | 0.426 | 0.262 | −0.164 | −38.5% |
| Hit@10 | 0.825 | 0.596 | −0.229 | −27.8% |
| MRR@10 | 0.578 | 0.346 | −0.232 | −40.2% |
| Mean latency | 753 ms | 14,346–14,892 ms | +13.6–14.1 s | ~19× slower |
| P95 latency | 2,218 ms | 24,765–25,059 ms | +22.5–22.8 s | ~11× slower |

#### Dense-only mode

| Metric | Dense rerank off | Dense rerank on, effective fetch_k=500 | Absolute Δ | Relative Δ |
| --- | ---: | ---: | ---: | ---: |
| Coverage@20 | 0.692 | 0.539 | −0.153 | −22.1% |
| Recall@50 | 0.519 | 0.353 | −0.167 | −32.1% |
| Hit@10 | 0.776 | 0.601 | −0.175 | −22.5% |
| MRR@10 | 0.513 | 0.346 | −0.168 | −32.7% |
| Mean latency | 926 ms | 13,669–15,240 ms | +12.7–14.3 s | ~15–16× slower |
| P95 latency | 3,078 ms | 20,017–26,100 ms | +16.9–23.0 s | ~7–8× slower |

### Pass/fail against criteria

| Criterion | Protocol threshold | Measured | Verdict |
| --- | ---: | ---: | :--: |
| Corpus validity | ≥10,000 docs | 10,025 | ✅ pass |
| Hybrid pool lift, labelled 200 vs 50 | Coverage@20 ≥ +0.03 | 0.000 | ⚠️ invalid as pool test |
| Dense pool lift, labelled 200 vs 50 | Coverage@20 ≥ +0.02 | 0.000 | ⚠️ invalid as pool test |
| Diminishing returns, labelled 500 vs 200 | Coverage@20 lift ≤ +0.02 | 0.000 | ⚠️ invalid as pool test |
| Reranker-off ceiling | rerank-off ≥ best rerank-on | 0.738 ≥ 0.540 | ✅ pass |
| Latency guardrail, labelled pool=200 | ≤3× labelled pool=50 P95 | 1.01× | ⚠️ same effective pool |
| Continuity non-regression | all cells ≥0.90 Coverage@20 | all cells ≥0.90 | ✅ pass |

The original automated pass-gate calculation reports the pool-size gates as failed or passed based on labelled pools. After auditing the effective fetch-size formula, those pool-size gates should be treated as **invalid for pool-size sensitivity**. The reranker-off ceiling and technical-workload regression conclusion remain valid.

### Identifier-heavy queries (n = 200)

| Config | Coverage@20 | Recall@50 | Hit@10 | MRR@10 |
| --- | ---: | ---: | ---: | ---: |
| dense-only, rerank off | 0.677 | 0.486 | 0.775 | 0.482 |
| **hybrid_bm25, rerank off** | **0.721** | **0.513** | **0.825** | **0.557** |
| dense-only, rerank on, effective fetch_k=500 | 0.504 | 0.296 | 0.580 | 0.298 |
| hybrid_bm25, rerank on, effective fetch_k=500 | 0.502 | 0.297 | 0.570 | 0.297 |

The identifier-heavy subset is the main evidence for disabling reranking on technical workloads. Hybrid BM25 without reranking gives the best result, while reranking collapses both dense and hybrid modes to around 0.50 Coverage@20.
### FreshStack semantic queries (n = 3)

| Config | Coverage@20 | Recall@50 | Hit@10 | MRR@10 |
| --- | ---: | ---: | ---: | ---: |
| dense-only, rerank off | 0.333 | 0.216 | 0.333 | 0.333 |
| hybrid_bm25, rerank off | 0.444 | 0.271 | 0.333 | 0.167 |
| dense-only, rerank on, effective fetch_k=500 | 0.500 | 0.174 | 0.333 | 0.167 |
| hybrid_bm25, rerank on, effective fetch_k=500 | 0.667 | 0.221 | 0.667 | 0.278 |

This sample is too small to support a broad conclusion about semantic corpora. It is included for completeness only.

### Continuity queries (20 unique queries)

| Config | Coverage@20 | Recall@50 | Hit@10 | MRR@10 | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| dense-only, rerank off | 0.900 | 0.900 | 0.850 | 0.850 | 169 |
| **hybrid_bm25, rerank off** | **0.950** | **0.950** | **0.900** | **0.850** | **214** |
| dense-only, rerank on, effective fetch_k=500 | 0.900 | 0.950 | 0.850 | 0.850 | 11,859–11,976 |
| hybrid_bm25, rerank on, effective fetch_k=500 | 0.900 | 0.950 | 0.850 | 0.850 | 12,103–12,356 |

The reranker does not degrade this small continuity regression set, but it also does not improve it and adds substantial latency. These continuity queries should not be treated as a representative semantic benchmark.

## Analysis

### What the experiment proves

1. **The current reranker is harmful on the FreshStack technical workload at effective `fetch_k=500`.** Hybrid rerank-off is clearly better than hybrid rerank-on across Coverage@20, Recall@50, α-nDCG@10, Hit@10, MRR@10, and latency.
2. **Hybrid BM25 + RRF remains valuable as a first-stage retriever.** Without reranking, hybrid beats dense-only on the all-query and identifier-heavy subsets.
3. **The current default reranker policy should not be used blindly for technical corpora.** The loss is large enough to justify a default-off policy while a domain-specific reranker is researched.

### What the experiment does not prove

1. **It does not prove pool size is irrelevant.** The effective pool size did not vary across reranker-on cells.
2. **It does not prove the cross-encoder always fails on every semantic workload.** The FreshStack semantic subset has only 3 queries, and the continuity set is a small regression fixture.
3. **It does not prove the exact reranker threshold/survivor mechanism.** The raw results do not include reranker survivor counts or score distributions sufficient to prove that the same candidates survived every pool label.

### Corrected interpretation

The original pre-run suspicion was that `RERANK_MAX_FETCH=50` was too small. Due to the fetch formula, this experiment actually evaluated the reranker with an effective pool of 500 candidates in every reranker-on cell. That makes the negative result stronger in one way and weaker in another:

- **Stronger**: even a wide effective pool of 500 candidates does not rescue the current reranker on technical documentation.
- **Weaker**: we still do not know whether effective pools of 50, 100, 200, and 500 differ, because that comparison was not run.

For the configuration decision, the practical conclusion is still clear: the current reranker should be disabled by default for technical/hybrid workloads. For the scientific pool-size question, a corrected follow-up would need to vary effective `fetch_k` directly, e.g. by using `top_k=20` with multiplier 1, or by adding a runner option that directly controls fetch size.
## Conclusion / Decision

### Decision

Disable the current reranker by default for technical/hybrid workloads. The best measured configuration is:

```text
HYBRID_ENABLED=true
HYBRID_SPARSE_BACKEND=bm25
RERANK_ENABLED=false
TOP_K=10 for normal production use; top_k=50 was used here for evaluation metrics
```

The experiment supports ADR-019's direction: preserve `CHUNK_OVERLAP=100` and `TOP_K=10`, but supersede ADR-018's default-on reranker policy.

### What should change

1. Set `RERANK_ENABLED=false` as the safe default.
2. Mark ADR-018 as superseded by ADR-019.
3. Use ADR-019 to document the corrected technical-workload reranker policy.
4. Keep hybrid retrieval infrastructure intact; the first-stage hybrid retriever is still beneficial.
5. Research or evaluate a technical-document-specific reranker before re-enabling reranking by default.

### What should not be claimed

- Do not claim Experiment 10 proved pool size is irrelevant.
- Do not claim effective pools 50, 200, and 500 were compared.
- Do not claim the reranker uses the same exact candidate set or survivor set unless a direct diagnostic is added.
- Do not claim `HARD_TECHNICAL_THRESHOLD=0.3` is empirically calibrated by Experiment 10; it is a conservative policy heuristic.

## Follow-ups

| Follow-up | Reason | Priority |
| --- | --- | --- |
| Disable reranking in `config.py` (`RERANK_ENABLED=false`) | Reranking at effective `fetch_k=500` severely degrades FreshStack technical retrieval | high |
| Update ADR-018 / ADR-019 | ADR-018 default-on reranking is no longer the authoritative policy | high |
| Add or implement semantic/technical workload policy logic | `RERANK_ENABLED_FOR_SEMANTIC` and `HARD_TECHNICAL_THRESHOLD` are policy knobs and require retrieval-side logic | high |
| Run a corrected effective fetch-size experiment | Needed if we still want calibrated pool-size sensitivity | medium |
| Research technical-document reranker models | Current MS MARCO cross-encoder is not appropriate for identifier-heavy technical retrieval | medium |

## Corrected reproduction note

The original command is reproducible, but it should be understood as evaluating effective `fetch_k=500` for all reranker-on labelled pool cells:

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/10-reranker-technical-workload-calibration-2026-05-31/run_eval.py \
  --modes dense-only,hybrid_bm25 \
  --rerank-cross \
  --reranker-pools 50 200 500 \
  --resume \
  --k-values 5 10 20 50 \
  2>&1 | tee experiments/10-reranker-technical-workload-calibration-2026-05-31/output/run_eval.log
```

A corrected pool-size experiment should either vary `RERANK_FETCH_MULTIPLIER`, lower `top_k`, or add a direct `fetch_k` override to ensure that effective candidate pools are actually distinct.

## Artefacts

| File / directory | Description |
| --- | --- |
| `protocol.md` | Pre-run plan and pass criteria |
| `results.md` | This corrected report |
| `run_eval.py` | Evaluation runner with labelled pool-size sweep |
| `summarise_eval.py` | Aggregates raw results; corrected to avoid continuity double-counting |
| `output/eval_results.json` | Raw per-query results |
| `output/eval_results.summary.json` | Regenerated aggregate metrics with continuity n=20 |
| `output/ground-truth.json` | Ground truth copied from Exp 9a |
| `output/run_eval.log` | Full evaluation log |

## References

- [`protocol.md`](./protocol.md) — Pre-registered plan and pass criteria
- [`output/eval_results.summary.json`](./output/eval_results.summary.json) — Regenerated summary metrics
- [`../9a-hybrid-retrieval-freshstack-langchain-2026-05-30/`](../9a-hybrid-retrieval-freshstack-langchain-2026-05-30/) — Upstream FreshStack hybrid retrieval experiment
- [`../../docs/adr/018-balanced-retrieval-defaults.md`](../../docs/adr/018-balanced-retrieval-defaults.md) — Superseded balanced defaults ADR
- [`../../docs/adr/019-reranker-disabled-for-technical-workloads.md`](../../docs/adr/019-reranker-disabled-for-technical-workloads.md) — Corrected reranker policy ADR
- Thakur et al. (2025). *FreshStack: Building Realistic Benchmarks for Evaluating Retrieval on Technical Documents*. arXiv:2504.13128.
