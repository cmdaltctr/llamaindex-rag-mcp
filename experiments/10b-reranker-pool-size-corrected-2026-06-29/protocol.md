**Status**: SUPERSEDED v1 design — repaired as the combined D17 factorial (protocol v2.0, Stage 4 task 4.3.2).

# Experiment 10b: Corrected Reranker Pool-Size Sweep

**ID**: `10b-reranker-pool-size-corrected-2026-06-29`  
**Date planned**: 2026-06-29  
**Operator**: Dr Aizat Md Hawari with AI build agent  
**Status**: PLANNED  
**Relation**: OpenSpec change `calibrate-rag-retrieval-defaults`; supersedes Exp 10 (design confound); informs ADR-019 / ADR-021

---

## Why this experiment exists

Experiment 10 attempted to sweep reranker pool sizes ({50, 200, 500}) but all
cells resolved to the same effective `fetch_k=500` due to the
`max(RERANK_MAX_FETCH, top_k × RERANK_FETCH_MULTIPLIER)` formula. With
`RERANK_FETCH_MULTIPLIER=10` and `top_k=50`, the formula produced
`max(50, 500)=500`, `max(200, 500)=500`, and `max(500, 500)=500` — three
identical cells labelled as distinct. The pool-size question was never answered.

TDR-005 added a `fetch_k` override parameter to `search()` and
`_resolve_fetch_k()` that bypasses the formula entirely. This experiment uses
that override to produce genuinely distinct pool sizes {50, 100, 200, 500} and
finally answers whether pool size matters for the cross-encoder reranker on
technical workloads.

## Hypothesis / Research question

1. **H1 (pool-size sensitivity)**: Increasing `fetch_k` from 50→500 will produce
   at least 3pp Coverage@20 lift on hybrid retrieval (the gate that Exp 10
   failed to test due to the confound).
2. **H2 (diminishing returns)**: The lift from 200→500 will be ≤ 2pp, indicating
   diminishing returns above ~200 candidates.
3. **H3 (reranker-off ceiling)**: Reranker-off will outperform all reranker-on
   cells, confirming ADR-019's decision to disable the reranker for technical
   workloads.

## Background and prior evidence

- Prior experiments: `experiments/10-reranker-technical-workload-calibration-2026-05-31/results.md`
  (voided by design confound), `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/results.md`
- ADRs: ADR-019 (reranker-off for technical), ADR-021 (fetch multiplier 10→3, max_fetch 50→100)
- TDR: TDR-005 (`fetch_k` override on `search()` and `_resolve_fetch_k()`)
- Relevant code: `rag_mcp.retrieval.search(fetch_k=...)`, `rag_mcp.retrieval._resolve_fetch_k(fetch_k_override=...)`
- Post-ADR-021 config: `RERANK_FETCH_MULTIPLIER=3`, `RERANK_MAX_FETCH=100`

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | `fetch_k` (candidate pool size) | 50, 100, 200, 500 (via `fetch_k=` override) |
| Independent | Retrieval mode | dense-only, hybrid_bm25 |
| Independent | Reranker | on (sweep), off (reference ceiling) |
| Dependent | Coverage@20 | Primary quality metric |
| Dependent | Recall@50, α-nDCG@10, Hit@5/10, MRR@10 | Diagnostic quality metrics |
| Dependent | P95 latency | Operational metric |
| Controlled | Corpus | FreshStack LangChain (seed 20260530, ~10,025 docs) |
| Controlled | Embedding model | `qwen3-embedding:0.6b` |
| Controlled | Reranker model | `cross-encoder/ms-marco-MiniLM-L-6-v2` (ONNX) |
| Controlled | `top_k` | 50 (experiment scale) |
| Controlled | `RERANK_FETCH_MULTIPLIER` | 3 (post-ADR-021, irrelevant when `fetch_k` is set) |
| Controlled | `RERANK_MAX_FETCH` | 100 (post-ADR-021, irrelevant when `fetch_k` is set) |

## Corpus and ground truth

| Item | Value |
| --- | --- |
| Source | FreshStack LangChain (reused from Exp 9a) |
| Local path | `experiments/10b-.../corpus/` |
| Size | ~10,025 parent docs, ~200+ queries |
| Ground truth path | `experiments/10b-.../output/ground-truth.json` |
| Evidence density | 100% (FreshStack qrels) |

Corpus is rebuilt from `prepare_freshstack.py` (seed 20260530) + `build_indexes.py`.
Exp 9a indexes are gitignored and not on disk.

## Environment and prerequisites

| Requirement | Version / value |
| --- | --- |
| Python | 3.12 |
| Package manager | `uv` |
| Embedding model | `qwen3-embedding:0.6b` via Ollama |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` (ONNX Runtime) |
| Hardware | macOS (Apple Silicon) |
| Key config | `RERANK_FETCH_MULTIPLIER=3`, `RERANK_MAX_FETCH=100` |

```bash
uv sync
ollama list
```

## Experimental design / cell matrix

| Run ID | Purpose | Mode | Rerank | `fetch_k` | Expected interpretation |
| --- | --- | --- | --- | --- | --- |
| `dense_off` | Reranker-off ceiling | dense-only | off | — | Quality ceiling for dense |
| `hybrid_off` | Reranker-off ceiling | hybrid_bm25 | off | — | Quality ceiling for hybrid |
| `dense_on_50` | Smallest pool | dense-only | on | 50 | Worst reranker-on cell |
| `dense_on_100` | Small pool | dense-only | on | 100 | Post-ADR-021 production equivalent |
| `dense_on_200` | Medium pool | dense-only | on | 200 | Exp 10's intended medium |
| `dense_on_500` | Large pool | dense-only | on | 500 | Exp 10's effective pool (all cells) |
| `hybrid_on_50` | Smallest pool | hybrid_bm25 | on | 50 | Worst reranker-on hybrid |
| `hybrid_on_100` | Small pool | hybrid_bm25 | on | 100 | Post-ADR-021 production equivalent |
| `hybrid_on_200` | Medium pool | hybrid_bm25 | on | 200 | Exp 10's intended medium |
| `hybrid_on_500` | Large pool | hybrid_bm25 | on | 500 | Exp 10's effective pool (all cells) |

**Runtime assertion**: `run_eval.py` MUST assert that all four `fetch_k` values
produce distinct effective pool sizes. If any two collapse, the experiment
aborts with an error.

## Metrics

### Primary metrics

- Coverage@20: fraction of answer nuggets with ≥1 relevant doc in top 20
- P95 latency: 95th percentile per-query latency

### Diagnostic metrics

- Recall@50, α-nDCG@10, Hit@5, Hit@10, MRR@10
- Mean latency, P50 latency

## Procedure / reproduction commands

### Step 1: Prepare data

```bash
uv run python experiments/10b-reranker-pool-size-corrected-2026-06-29/prepare_freshstack.py \
  --topic langchain --seed 20260530 --prefer-full-corpus
```

### Step 2: Build indexes

```bash
uv run python experiments/10b-reranker-pool-size-corrected-2026-06-29/build_indexes.py
```

### Step 3: Run evaluation

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/10b-reranker-pool-size-corrected-2026-06-29/run_eval.py \
  --modes dense-only,hybrid_bm25 \
  --rerank-cross \
  --fetch-k-sizes 50 100 200 500 \
  --k-values 5 10 20 50 \
  --resume \
  2>&1 | tee experiments/10b-reranker-pool-size-corrected-2026-06-29/output/run_eval.log
```

### Step 4: Summarise results

```bash
uv run python experiments/10b-reranker-pool-size-corrected-2026-06-29/summarise_eval.py
```

## Success criteria / pass gates

| Criterion | Threshold | Why this threshold matters |
| --- | ---: | --- |
| Pool-size lift (hybrid 500 vs 50) | ≥ 3pp Coverage@20 | Confounds resolved; pool size matters |
| Diminishing returns (hybrid 500 vs 200) | ≤ 2pp | Identifies optimal pool size |
| Reranker-off ceiling | reranker-off ≥ best reranker-on | Validates ADR-019 |
| Pool sizes genuinely distinct | Runtime assertion passes | Experiment validity |
| Latency guardrail | P95(500) ≤ 3× P95(50) | Operational feasibility |

## Interpretation rules

- If H1 passes (≥3pp lift): pool size matters; the original Exp 10 confound
  masked a real effect. Document the optimal pool size.
- If H1 fails (<3pp lift): pool size does not meaningfully affect quality.
  ADR-019's reranker-off decision is robust regardless of pool size.
- If H2 passes (≤2pp from 200→500): optimal pool size is ~200. Document.
- If H2 fails (>2pp from 200→500): no diminishing returns; larger pools may
  still help. Flag for follow-up.
- If H3 passes (reranker-off ≥ best reranker-on): ADR-019 validated. No config
  change. Document negative result for reranker-on cells.
- If H3 fails (some reranker-on cell beats reranker-off): ADR-019 may need
  amendment. Draft amendment text (separate change).

## What to do if the experiment fails

1. Document negative result. Keep `RERANK_ENABLED=false` default (ADR-019).
2. If pool sizes are still not distinct (assertion fails), investigate
   `_resolve_fetch_k()` override path. This would indicate a TDR-005 regression.
3. Escalation: propose a new reranker model evaluation (separate change).

## Implementation notes

- Code path under test: `rag_mcp.retrieval.search(fetch_k=...)` → `_resolve_fetch_k(fetch_k_override=...)`
- The `fetch_k=` parameter bypasses `max(RERANK_MAX_FETCH, top_k × RERANK_FETCH_MULTIPLIER)` entirely
- Post-ADR-021 config (`MULTIPLIER=3`, `MAX_FETCH=100`) is the baseline; `fetch_k` override is per-cell
- The reranker (`reranker.py`) is unchanged — it processes whatever candidates it receives
- Known risk: FreshStack corpus must be rebuilt (gitignored, not on disk)

## Cleanup

```bash
rm -rf experiments/10b-reranker-pool-size-corrected-2026-06-29/output/chroma_*
```

Keep raw JSON and Markdown summaries. Remove only large generated indexes.

## Artefacts expected

| File / directory | Description | Required? |
| --- | --- | :--: |
| `protocol.md` | This plan | ✅ |
| `results.md` | Human-readable result report | ✅ |
| `run_eval.py` | Evaluation runner | ✅ |
| `summarise_eval.py` | Results summariser | ✅ |
| `build_indexes.py` | Index builder | ✅ |
| `prepare_freshstack.py` | Corpus preparation (symlink or copy from Exp 9a) | ✅ |
| `eval_results.json` | Raw machine-readable results | ✅ |
| `eval_results.summary.json` | Aggregated summary | ✅ |
| `output/*.log` | Run logs | Optional |

## References

- Exp 10: `experiments/10-reranker-technical-workload-calibration-2026-05-31/`
- Exp 9a: `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/`
- ADR-019: `docs/adr/019-reranker-disabled-for-technical-workloads.md`
- ADR-021: `docs/adr/021-reranker-fetch-reduction-and-speed-optimization.md`
- TDR-005: `docs/tdr/005-fetch-k-override-for-experiment-pool-sweeps.md`

---

## v2 repaired design (Stage 4)

The v1 runner executed dense-only reranker-on cells while the protocol
declared a dense × hybrid matrix, shared no reranker-off controls across
modes, and lacked the 150 pool. Stage 4 of OpenSpec change
`harden-pipeline-correctness-before-calibration` (design decision D17;
tasks 4.3.1–4.3.4, 4.3.7) repaired the experiment as the combined
paired factorial — one run answers both "is reranking still harmful at
the current 150 pool?" and "does pool size causally change that
conclusion?", and provides the reranker-off hybrid contrast. The invalid
v1 runner is retained for provenance as `run_eval_v1_pre_hardening.py`
— do not use it for decision evidence.

### Cell matrix (12 cells; machine truth in `plan.json`)

| Cell | Retrieval | Rerank | fetch_k | Role |
| --- | --- | --- | ---: | --- |
| `dense_off` | dense | off | — | shared control: dense ceiling |
| `hybrid_off` | hybrid_bm25 | off | — | shared control: hybrid ceiling |
| `dense_on_{50,100,150,200,500}` | dense | on | 50/100/150/200/500 | pool sweep |
| `hybrid_on_{50,100,150,200,500}` | hybrid_bm25 | on | 50/100/150/200/500 | pool sweep |

Shared-control semantics: the two reranker-off cells carry no `fetch_k`
(the candidate pool is meaningless without a reranker) and are never
duplicated per pool — 12 cells, not 20.

Counterbalancing: cells execute in a deterministic seeded order
(`counterbalanced_order`, seed 20260819; rotate with `--order-iteration`)
so time, thermal and cache drift are not confounded with treatment
order. Every query is evaluated in every applicable cell (paired design).

Pool 150 rationale: `top_k=50 × RERANK_FETCH_MULTIPLIER=3` is the
current post-ADR-021 production-equivalent pool at experiment scale;
v1 lacked it, so the production point was never measured.

Machine truth: `plan.json` (loadable via
`experiments/_lib/plan.py::ExperimentPlan`) is the authoritative cell
matrix; `run_eval.py` asserts runner/plan agreement at start-up, builds
a D13 runtime manifest per cell, and gates measured queries behind D14
preflight assertions (no fallback, threshold 0.0, index and embedding
identity, fetch_k distinctness). Summaries use paired bootstrap CIs
(seed 20260819) over measured rows only — warm-up rows are recorded
with `phase="warmup"` and excluded from aggregates.

Corrected run command:

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/10b-reranker-pool-size-corrected-2026-06-29/run_eval.py \
  --k-values 5 10 20 50 \
  --resume \
  2>&1 | tee experiments/10b-reranker-pool-size-corrected-2026-06-29/output/run_eval.log
```

Execution at corpus scale is Stage 6 work; this directory holds the
repaired harness only.
