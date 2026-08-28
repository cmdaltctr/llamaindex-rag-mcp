# Experiment 13: HARD_TECHNICAL_THRESHOLD Calibration

**ID**: `13-hard-technical-threshold-calibration-2026-06-29`  
**Date planned**: 2026-06-29  
**Status**: PLANNED  
**Relation**: OpenSpec change `calibrate-rag-retrieval-defaults`; informs ADR-019

---

## Why this experiment exists

`HARD_TECHNICAL_THRESHOLD` (default 0.3) controls when the reranker is
automatically disabled for "technical" queries. Exp 10 showed the cross-encoder
is harmful at ≥30% identifier-heavy queries, but the exact threshold boundary
has never been calibrated. This experiment sweeps the threshold across
{0.1, 0.2, 0.3, 0.5, 0.7} on a mixed technical-plus-semantic corpus to find the
value that preserves semantic reranker benefit while minimising technical
regression.

## Hypothesis / Research question

1. **H1 (semantic benefit)**: At the calibrated threshold, semantic queries
   retain ≥ +1pp Coverage@20 from the reranker.
2. **H2 (technical guard)**: At the calibrated threshold, technical queries
   have ≤ −1pp Coverage@20 regression from the reranker.
3. **H3 (current default)**: The current default (0.3) is within the acceptable
   range.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | `HARD_TECHNICAL_THRESHOLD` | {0.1, 0.2, 0.3, 0.5, 0.7} |
| Independent | Technical-query fraction | {100%, 90%, 75%, 50%, 25%, 0%} |
| Dependent | Coverage@20 (technical) | Primary metric for technical queries |
| Dependent | Coverage@20 (semantic) | Primary metric for semantic queries |
| Dependent | Recall@50, Hit@10, MRR@10 | Diagnostic metrics |
| Controlled | Corpus | FreshStack LangChain (technical) + Qasper (semantic) |
| Controlled | Embedding model | `qwen3-embedding:0.6b` |
| Controlled | Reranker model | `cross-encoder/ms-marco-MiniLM-L-6-v2` (ONNX) |
| Controlled | Post-ADR-021 config | `RERANK_FETCH_MULTIPLIER=3`, `RERANK_MAX_FETCH=100` |
| Controlled | `top_k` | 50 |
| Controlled | Seed | 20260629 |

## Corpus and ground truth

| Item | Value |
| --- | --- |
| Technical source | FreshStack LangChain (identifier-heavy queries) |
| Semantic source | Qasper dev set (`allenai/qasper` from HuggingFace) |
| Minimum queries per cell | 30 |
| Ground truth | FreshStack qrels + Qasper dev annotations |

### Corpus preparation

1. Download Qasper dev set from HuggingFace (`allenai/qasper`).
2. Export queries and PDFs.
3. Combine with FreshStack LangChain ground truth.
4. Tag each query as `technical` or `semantic`.

## Experimental design / cell matrix

5 thresholds × 6 fractions = 30 cells. Each cell evaluates retrieval with
reranker-on at the given `HARD_TECHNICAL_THRESHOLD`, measuring Coverage@20
for technical and semantic queries separately.

| Threshold | Fraction 100% | 90% | 75% | 50% | 25% | 0% |
| --- | --- | --- | --- | --- | --- | --- |
| 0.1 | cell | cell | cell | cell | cell | cell |
| 0.2 | cell | cell | cell | cell | cell | cell |
| 0.3 | cell | cell | cell | cell | cell | cell |
| 0.5 | cell | cell | cell | cell | cell | cell |
| 0.7 | cell | cell | cell | cell | cell | cell |

Each cell contains ≥ 30 queries (subsample if needed; flag cells below this).

## Metrics

### Primary metrics

- Coverage@20 (technical queries, per threshold × fraction)
- Coverage@20 (semantic queries, per threshold × fraction)

### Diagnostic metrics

- Recall@50, Hit@10, MRR@10

## Success criteria / pass gates

| Criterion | Threshold |
| --- | --- |
| Semantic benefit | ≥ +1pp Coverage@20 on semantic queries |
| Technical guard | ≤ −1pp Coverage@20 regression on technical queries |
| Minimum queries | ≥ 30 queries per cell |
| Current default in range | 0.3 is within the acceptable threshold range |

## Interpretation rules

- If a threshold satisfies both semantic benefit and technical guard gates:
  that threshold is **acceptable**.
- The **recommended** threshold is the one that maximises semantic benefit
  while satisfying the technical guard.
- If 0.3 is within the acceptable range: current default is confirmed.
- If 0.3 is outside the acceptable range: recommend changing the default.
  Draft ADR-019 amendment (separate change).
- If no threshold satisfies both gates: the reranker may not be beneficial
  for any mixed workload. ADR-019 is confirmed as-is.

## Procedure / reproduction commands

### Step 1: Prepare Qasper corpus

```bash
uv run python experiments/13-hard-technical-threshold-calibration-2026-06-29/prepare_qasper.py
```

### Step 2: Prepare FreshStack corpus (reuse from Exp 9a)

```bash
uv run python experiments/13-hard-technical-threshold-calibration-2026-06-29/prepare_freshstack.py --topic langchain --seed 20260530 --prefer-full-corpus
```

### Step 3: Build indexes

```bash
uv run python experiments/13-hard-technical-threshold-calibration-2026-06-29/build_indexes.py
```

### Step 4: Run evaluation

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/13-hard-technical-threshold-calibration-2026-06-29/run_eval.py \
  --k-values 5 10 20 50 \
  --resume \
  2>&1 | tee experiments/13-hard-technical-threshold-calibration-2026-06-29/output/run_eval.log
```

### Step 5: Summarise

```bash
uv run python experiments/13-hard-technical-threshold-calibration-2026-06-29/summarise_eval.py
```

## Artefacts expected

| File | Description | Required? |
| --- | --- | :--: |
| `protocol.md` | This plan | ✅ |
| `results.md` | Human-readable report | ✅ |
| `prepare_qasper.py` | Qasper corpus preparation | ✅ |
| `build_indexes.py` | Index builder | ✅ |
| `run_eval.py` | Evaluation runner | ✅ |
| `summarise_eval.py` | Results summariser | ✅ |
| `eval_results.json` | Raw results | ✅ |
| `eval_results.summary.json` | Aggregated summary | ✅ |

## References

- Exp 10: `experiments/10-reranker-technical-workload-calibration-2026-05-31/`
- ADR-019: `docs/adr/019-reranker-disabled-for-technical-workloads.md`
- ADR-021: `docs/adr/021-reranker-fetch-reduction-and-speed-optimization.md`
