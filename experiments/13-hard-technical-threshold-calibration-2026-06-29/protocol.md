# Experiment 13: HARD_TECHNICAL_THRESHOLD Calibration

**ID**: `13-hard-technical-threshold-calibration-2026-06-29`  
**Date planned**: 2026-06-29  
**Status**: REPAIRED (v2.0, Stage 4 task 4.3.5) — policy mode rerank=None, fixed fraction blocks, reference envelope arms  
**Relation**: OpenSpec change `calibrate-rag-retrieval-defaults`; informs ADR-019. Repaired under OpenSpec change `harden-pipeline-correctness-before-calibration` (design D18).

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

42 cells (v2.0). **`plan.json` is the machine-readable truth** for this
matrix; the runner aborts if its generated cells disagree with the plan
(D15 agreement test).

- **30 policy cells** (5 thresholds × 6 fractions): the runner calls
  `search(..., rerank=None)` so the policy resolver decides reranking from
  the per-cell `EffectiveSettings` carrying the swept
  `HARD_TECHNICAL_THRESHOLD`.
- **12 reference envelope cells** (6 fractions × 2 arms):
  `reranker_off` (`search(..., rerank=False)`, no-rerank floor) and
  `reranker_on` (`search(..., rerank=True)`, forced-rerank ceiling).
  These carry no threshold factor — they are threshold-independent and
  are run once per fraction, never duplicated per threshold.

| Threshold | Fraction 100% | 90% | 75% | 50% | 25% | 0% |
| --- | --- | --- | --- | --- | --- | --- |
| 0.1 | policy | policy | policy | policy | policy | policy |
| 0.2 | policy | policy | policy | policy | policy | policy |
| 0.3 | policy | policy | policy | policy | policy | policy |
| 0.5 | policy | policy | policy | policy | policy | policy |
| 0.7 | policy | policy | policy | policy | policy | policy |
| — | off/on | off/on | off/on | off/on | off/on | off/on |

Query blocks are **fixed per fraction** and reused verbatim for every
threshold and arm of that fraction: each block is drawn once from
`random.Random(f"{20260629}:{fraction}")` and persisted to
`output/fixed_blocks.json`, so all comparisons pair by `query_id`
(D18/D16). The fraction axis is a blocked analysis factor, never a
source of fresh per-cell samples. Each block contains ≥ 30 queries
(subsample if needed; flag cells below this). Warm-up queries are
recorded with `phase="warmup"` and excluded from measured aggregates.

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
| `plan.json` | Machine-readable 42-cell matrix (v2.0 truth) | ✅ |
| `results.md` | Human-readable report | ✅ |
| `prepare_qasper.py` | Qasper corpus preparation | ✅ |
| `build_indexes.py` | Index builder | ✅ |
| `run_eval.py` | Evaluation runner (v2.0) | ✅ |
| `summarise_eval.py` | Results summariser (paired CIs) | ✅ |
| `eval_results.json` | Raw results (per-query rows, D16) | ✅ |
| `eval_results.summary.json` | Aggregated summary | ✅ |
| `output/fixed_blocks.json` | Fixed per-fraction query blocks | ✅ |

## References

- Exp 10: `experiments/10-reranker-technical-workload-calibration-2026-05-31/`
- ADR-019: `docs/adr/019-reranker-disabled-for-technical-workloads.md`
- ADR-021: `docs/adr/021-reranker-fetch-reduction-and-speed-optimization.md`

## Repair history

### v1 (2026-06-29, superseded)

The original design declared 30 cells (5 thresholds × 6 fractions) and
intended each cell to evaluate retrieval with the reranker active at the
given `HARD_TECHNICAL_THRESHOLD`. The v1 runner implemented that
literally — `search(..., rerank=True)` in every cell — which bypassed
the policy resolver entirely, so the swept threshold never affected
routing: the experiment measured a forced reranker arm, not the
threshold policy it claimed to calibrate. Two further defects:
`_sample_queries` drew a fresh random sample per (threshold × fraction)
cell (rng state advanced between cells, so thresholds were compared on
different query sets), and no reference arms existed. The v1 runner is
preserved in git history (repaired in place per the Stage 4 repair
plan); no v1 result is interpretable as threshold-policy evidence.

### v2.0 (2026-08-19, Stage 4 task 4.3.5)

Repaired per design D18 of `harden-pipeline-correctness-before-
calibration`: policy cells pass `rerank=None` with the swept threshold
carried in per-cell `EffectiveSettings`; one fixed query block per
fraction (seeded `random.Random(f"{SEED}:{fraction}")`) is reused across
every threshold and arm; threshold-independent `reranker_off` /
`reranker_on` reference envelope arms run once per fraction. Added
per-query D16 rows with warm-up separation, per-cell D13 runtime
manifests with D14 preflight assertions (including
`assert_policy_rerank_mode` for policy cells), controlled-variable
pinning across cells, and the machine-readable `plan.json` whose
42-cell matrix is enforced against the runner by agreement tests
(`tests/test_experiment_13_harness.py`) and at run start. The
summariser now reports paired bootstrap CIs for the semantic-benefit
and technical-guard contrasts against the same-fraction reference arms.
Audit regression:
`tests/test_precalibration_audit_regressions.py::test_experiment_13_threshold_cells_do_not_force_reranking`.
