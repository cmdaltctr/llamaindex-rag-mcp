# Experiment 26 — Query-instruction ablation (task 5.3)

**ID**: `26-query-instruction-ablation-2026-09-08`
**Date planned**: 2026-09-08
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: PLANNED (validity gates frozen 2026-09-08, task 1.6)
**Relation**: `improve-rag-input-quality-5` task 5.3; experiment 22 baseline; task 4.8 identity rule

## Why this experiment exists

Qwen embedding models accept a task instruction that can reshape query
vectors without touching document vectors. The query instruction is
deliberately excluded from index identity (task 4.8), so it can be
evaluated on the frozen Experiment 22 index with no re-ingestion. Its
effect on identifier-heavy technical queries is unknown and could be
negative (preamble dilutes identifier tokens).

## Hypothesis

> Wrapping raw queries in the candidate instruction lifts paired mean
> R@5 by at least +0.0300 over the raw baseline (absolute ≥ 0.2859)
> without dropping identifier-heavy R@10 below 0.2583 and within the
> query p95 latency cap.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | query instruction | `raw_none` vs `candidate_instruction` |
| Dependent | paired mean R@5 lift | promotion gate |
| Dependent | identifier-heavy R@10, query p95 | guard + latency gate |
| Controlled | index | Experiment 22 baseline (preserved; held fixed) |
| Controlled | corpus, qrels, queries | Experiment 22 (sha `ccd3bc5732d69a37…`) |
| Controlled | retrieval | hybrid RRF k=60, rerank off, top_k 50 |

Not changed: documents, index, chunker, worker, routing.

## Corpus and ground truth

| Item | Value |
| --- | --- |
| Index | `~/Development/DATA/omrg/experiments/exp22-lancedb` (preserved; read-only) |
| Ground truth | `experiments/22-.../output/ground-truth.json` (223 queries, fixed) |
| Instruction text | fixed verbatim and recorded in the runtime manifest BEFORE measurement |

## Metrics

### Primary (gated)

- Paired mean R@5 lift vs raw on identical queries (≥ +0.0300)
- Identifier-heavy mean R@10, n=200 (≥ 0.2583)
- Query p95 latency (≤ 2,850 ms)

### Diagnostic (recorded, not gated)

- R@1/R@3, MRR@10, α-nDCG@10, Hit@10
- Semantic subset (n=3 — illustrative only, never conclusive)
- Per-query rank deltas raw vs instructed

## Frozen validity gates

Machine-readable form: [`plan.json`](./plan.json). Noise basis:
`gate_noise.json` (N=10,000, seed 20260908) — paired R@5 95% half-width
0.024838; R@10 half-width 0.020571; p95 estimator CI upper 2,334.3 ms.

| Gate | Rule | Basis |
| --- | --- | --- |
| Quality | Paired mean R@5 lift ≥ +0.0300 (absolute ≥ 0.2859) | smallest lift clearing the noise floor; +0.02 would sit inside noise |
| Regression | Identifier-heavy R@10 ≥ 0.2583 | 0.278862 − 0.020571; preamble dilutes identifier tokens first |
| Latency | Query p95 ≤ 2,850 ms | 1.5 × baseline 1,984.2 ms; arms must be interleaved to control network drift |

**Monitored, not gated:** continuity R@10 (n=20; half-width ±0.15 — hard
gate would be noise; reason recorded in the plan).

## Interpretation rules

- All gates pass → candidate eligible per task 5.5 for `EMBEDDING__QUERY_INSTRUCTION`.
- Lift below +0.0300 → negative result; keep instruction unset as packaged default; commit the numbers.
- Regression gate fails → instruction harms technical lookups; do not tune the text to pass — record and stop.
- Latency gate fails only → check network drift between arms before concluding (interleaving exists for this).

## Procedure

```bash
# 1. Fix the candidate instruction text; record verbatim in the manifest.
# 2. Point STORE_URI at the preserved baseline index (read-only).
# 3. Run interleaved raw/instructed cells with cache isolation.
uv run python experiments/26-query-instruction-ablation-2026-09-08/run_eval.py --resume
# 4. Summarise + gate check
uv run python experiments/26-query-instruction-ablation-2026-09-08/summarise_eval.py
```

## Cleanup

No index is built or modified — the baseline index is read-only. Query
embeddings are paid API calls (~223 × 2); checkpoints make interruption
safe. Raw JSON and summaries are committed.

## Artefacts expected

| File | Description | Required |
| --- | --- | :--: |
| `protocol.md` / `plan.json` | this plan + gates | ✅ |
| `run_eval.py` / `summarise_eval.py` | runner chain | to write |
| `results.md` + `output/*.json` | outcomes | ✅ |
