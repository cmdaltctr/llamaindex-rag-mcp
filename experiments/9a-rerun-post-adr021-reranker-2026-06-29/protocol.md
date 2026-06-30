# Experiment 9a-rerun: Post-ADR-021 Reranker Validation

**ID**: `9a-rerun-post-adr021-reranker-2026-06-29`  
**Date planned**: 2026-06-29  
**Status**: PLANNED  
**Relation**: OpenSpec change `calibrate-rag-retrieval-defaults`; validates ADR-019

---

## Why this experiment exists

Exp 9a ran with the original reranker config (`RERANK_FETCH_MULTIPLIER=10`,
`RERANK_MAX_FETCH=200`, giving `fetch_k=500` at `top_k=50`). ADR-021 reduced
these to `MULTIPLIER=3`, `MAX_FETCH=100` (giving `fetch_k=150`). ADR-019 then
disabled the reranker for technical workloads based on Exp 10's finding that
the cross-encoder is harmful. This experiment re-runs the Exp 9a cell grid with
the post-ADR-021 config to determine whether the reranker is still harmful at
the reduced pool size, or whether ADR-019 should be amended.

## Hypothesis / Research question

1. **H1 (reranker still degrades)**: With post-ADR-021 config (`fetch_k=150`),
   reranker-on still degrades Coverage@20 compared to reranker-off.
2. **H2 (latency improvement)**: Post-ADR-021 reranker-on latency is
   significantly lower than original Exp 9a reranker-on latency.
3. **H3 (ADR-019 validation)**: ADR-019 (reranker disabled by default) is
   validated if H1 passes; uncertain if H1 fails by a small margin; invalidated
   if reranker-on improves Coverage@20.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | Retrieval mode | dense-only, hybrid_bm25 |
| Independent | Reranker | off, on (post-ADR-021 config) |
| Dependent | Coverage@20 | Primary quality metric |
| Dependent | Recall@50, α-nDCG@10, Hit@5/10, MRR@10 | Diagnostic quality metrics |
| Dependent | P95 latency | Operational metric |
| Controlled | Corpus | FreshStack LangChain (seed 20260530) |
| Controlled | Embedding model | `qwen3-embedding:0.6b` |
| Controlled | Reranker model | `cross-encoder/ms-marco-MiniLM-L-6-v2` (ONNX) |
| Controlled | Post-ADR-021 config | `RERANK_FETCH_MULTIPLIER=3`, `RERANK_MAX_FETCH=100` |

## Corpus and ground truth

| Item | Value |
| --- | --- |
| Source | FreshStack LangChain (reused from Exp 9a) |
| Size | ~10,025 parent docs, ~200+ queries |
| Ground truth | FreshStack qrels (100% evidence density) |

## Experimental design / cell matrix

| Run ID | Mode | Rerank | Config |
| --- | --- | --- | --- |
| `dense_off` | dense-only | off | — |
| `dense_on` | dense-only | on | MULTIPLIER=3, MAX_FETCH=100 |
| `hybrid_off` | hybrid_bm25 | off | — |
| `hybrid_on` | hybrid_bm25 | on | MULTIPLIER=3, MAX_FETCH=100 |

Effective `fetch_k=150` at `top_k=50` (vs original Exp 9a `fetch_k=500`).

## Metrics

### Primary metrics

- Coverage@20 (all queries + technical/semantic split)
- P95 latency (comparison to original Exp 9a)

### Diagnostic metrics

- Recall@50, α-nDCG@10, Hit@5, Hit@10, MRR@10

## Success criteria / pass gates

| Criterion | Threshold |
| --- | --- |
| Reranker degradation | Coverage@20(rerank-on) < Coverage@20(rerank-off) for both modes |
| Latency improvement | P95(rerank-on, 9a-rerun) < P95(rerank-on, 9a original) |
| ADR-019 conclusion | Validated if degradation confirmed; uncertain if within ±1pp; invalidated if reranker improves |

## Interpretation rules

- If H1 passes: ADR-019 validated. Reranker is harmful even at reduced pool size.
- If H1 fails by ≤ 1pp: ADR-019 is uncertain. Recommend Exp 10b for deeper
  pool-size investigation.
- If H1 fails (reranker improves): ADR-019 may need amendment. The reduced pool
  size fixes the reranker. Draft ADR-019 amendment (separate change).

## Procedure / reproduction commands

### Step 1: Prepare data and build indexes

```bash
uv run python experiments/9a-rerun-post-adr021-reranker-2026-06-29/prepare_freshstack.py --topic langchain --seed 20260530 --prefer-full-corpus
uv run python experiments/9a-rerun-post-adr021-reranker-2026-06-29/build_indexes.py
```

### Step 2: Run evaluation

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/9a-rerun-post-adr021-reranker-2026-06-29/run_eval.py \
  --k-values 5 10 20 50 \
  --resume \
  2>&1 | tee experiments/9a-rerun-post-adr021-reranker-2026-06-29/output/run_eval.log
```

### Step 3: Summarise

```bash
uv run python experiments/9a-rerun-post-adr021-reranker-2026-06-29/summarise_eval.py
```

## Artefacts expected

| File | Description | Required? |
| --- | --- | :--: |
| `protocol.md` | This plan | ✅ |
| `results.md` | Human-readable report with comparison to Exp 9a | ✅ |
| `run_eval.py` | Evaluation runner | ✅ |
| `summarise_eval.py` | Results summariser with Exp 9a comparison | ✅ |
| `prepare_freshstack.py` | Symlink from Exp 9a | ✅ |
| `build_indexes.py` | Symlink from Exp 9a | ✅ |
| `eval_results.json` | Raw results | ✅ |
| `eval_results.summary.json` | Aggregated summary | ✅ |

## References

- Exp 9a: `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/`
- ADR-019: `docs/adr/019-reranker-disabled-for-technical-workloads.md`
- ADR-021: `docs/adr/021-reranker-fetch-reduction-and-speed-optimization.md`
