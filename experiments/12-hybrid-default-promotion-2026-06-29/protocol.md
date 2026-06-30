# Experiment 12: Hybrid Default Promotion Test (Post-ADR-019)

**ID**: `12-hybrid-default-promotion-2026-06-29`  
**Date planned**: 2026-06-29  
**Status**: PLANNED  
**Relation**: OpenSpec change `calibrate-rag-retrieval-defaults`; informs ADR-016 / ADR-019

---

## Why this experiment exists

ADR-019 disabled the reranker by default for technical workloads. With the
reranker off, the question arises: should hybrid retrieval (dense + BM25) be
promoted to the default? Exp 9a tested hybrid with the reranker on; this
experiment tests hybrid with the reranker off, using the revised 3pp quality
gate (not the original 5pp) and bootstrap 95% confidence intervals.

## Hypothesis / Research question

1. **H1 (hybrid promotion)**: Hybrid BM25 retrieval with reranker-off produces
   ≥ 3pp Coverage@20 lift over dense-only with reranker-off.
2. **H2 (semantic guardrail)**: Semantic query Coverage@20 does not regress by
   more than 2pp when switching from dense-only to hybrid.
3. **H3 (statistical confidence)**: The bootstrap 95% CI on the Coverage@20 lift
   does not include zero.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | Retrieval mode | dense-only, hybrid_bm25 |
| Independent | Reranker | off (decision cells), on (reference only) |
| Dependent | Coverage@20 | Primary quality metric |
| Dependent | Recall@50, α-nDCG@10, Hit@5/10, MRR@10 | Diagnostic quality metrics |
| Dependent | P95 latency | Operational metric |
| Controlled | Corpus | FreshStack LangChain (seed 20260530, ~10,025 docs) |
| Controlled | Embedding model | `qwen3-embedding:0.6b` |
| Controlled | Reranker model | `cross-encoder/ms-marco-MiniLM-L-6-v2` (ONNX) |
| Controlled | `top_k` | 50 |
| Controlled | Post-ADR-021 config | `RERANK_FETCH_MULTIPLIER=3`, `RERANK_MAX_FETCH=100` |

## Corpus and ground truth

| Item | Value |
| --- | --- |
| Source | FreshStack LangChain (reused from Exp 9a) |
| Size | ~10,025 parent docs, ~200+ queries |
| Ground truth | FreshStack qrels (100% evidence density) |

## Experimental design / cell matrix

| Run ID | Purpose | Mode | Rerank | Decision? |
| --- | --- | --- | --- | --- |
| `dense_off` | Decision cell | dense-only | off | ✅ |
| `hybrid_off` | Decision cell | hybrid_bm25 | off | ✅ |
| `dense_on` | Reference only | dense-only | on | ❌ |
| `hybrid_on` | Reference only | hybrid_bm25 | on | ❌ |

Rerank-on cells use post-ADR-021 config (`MULTIPLIER=3`, `MAX_FETCH=100`),
giving `fetch_k=150` at `top_k=50` — not the original Exp 9a `fetch_k=500`.

## Metrics

### Primary metrics

- Coverage@20 (all queries + semantic subset)
- Bootstrap 95% CI on Coverage@20 lift (hybrid_off vs dense_off)

### Diagnostic metrics

- Recall@50, α-nDCG@10, Hit@5, Hit@10, MRR@10
- P95 latency

## Success criteria / pass gates

| Criterion | Threshold |
| --- | --- |
| Hybrid Coverage@20 lift | ≥ 3pp over dense (all queries) |
| Semantic guardrail | Semantic query Coverage@20 regression ≤ 2pp |
| Statistical confidence | Bootstrap 95% CI on lift excludes zero |
| Non-regression | No metric regresses by more than 5pp |

## Interpretation rules

- If all gates pass: RECOMMEND promoting `HYBRID_ENABLED=true` as default.
  Draft ADR-016 amendment (separate change).
- If lift < 3pp: hybrid is not worth the complexity. Keep dense-only default.
- If CI includes zero: result is not statistically significant. Do not promote.
- If semantic guardrail fails: hybrid helps technical but hurts semantic.
  Keep dense-only default; consider per-query-type hybrid selection.

## Procedure / reproduction commands

### Step 1: Prepare data and build indexes

```bash
uv run python experiments/12-hybrid-default-promotion-2026-06-29/prepare_freshstack.py --topic langchain --seed 20260530 --prefer-full-corpus
uv run python experiments/12-hybrid-default-promotion-2026-06-29/build_indexes.py
```

### Step 2: Run evaluation

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/12-hybrid-default-promotion-2026-06-29/run_eval.py \
  --k-values 5 10 20 50 \
  --resume \
  2>&1 | tee experiments/12-hybrid-default-promotion-2026-06-29/output/run_eval.log
```

### Step 3: Summarise

```bash
uv run python experiments/12-hybrid-default-promotion-2026-06-29/summarise_eval.py
```

## Artefacts expected

| File | Description | Required? |
| --- | --- | :--: |
| `protocol.md` | This plan | ✅ |
| `results.md` | Human-readable report | ✅ |
| `run_eval.py` | Evaluation runner | ✅ |
| `summarise_eval.py` | Results summariser with bootstrap CI | ✅ |
| `build_indexes.py` | Index builder | ✅ |
| `prepare_freshstack.py` | Corpus preparation (symlink from Exp 9a) | ✅ |
| `eval_results.json` | Raw results | ✅ |
| `eval_results.summary.json` | Aggregated summary with CI | ✅ |

## References

- Exp 9a: `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/`
- ADR-016: `docs/adr/016-rag-retrieval-quality-improvements.md`
- ADR-019: `docs/adr/019-reranker-disabled-for-technical-workloads.md`
- ADR-021: `docs/adr/021-reranker-fetch-reduction-and-speed-optimization.md`
