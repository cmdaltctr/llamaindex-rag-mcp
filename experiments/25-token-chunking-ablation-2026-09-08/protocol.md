# Experiment 25 — Token-aware chunking ablation (task 5.2) — gates frozen

- **Status:** PLANNED (gates frozen 2026-09-08, task 1.6)
- **Date frozen:** 2026-09-08
- **Operator:** Dr Muhammad Aizat Bin Md Hawari with AI agent
- **OpenSpec stage:** Stage 5 candidate evaluation. Gates below were derived
  from Stage 1 baselines and committed BEFORE any candidate measurement.

## Purpose

Build a comparable index from the same canonical FreshStack corpus with
the merged model-token-aware Markdown chunker (ADR-063,
`semantic-text-splitter` + Qwen tokenizer) and compare retrieval against
the Experiment 22 baseline splitter on the identical 223 queries and
qrels.

## Frozen validity gates

Machine-readable form: [`plan.json`](./plan.json). Every threshold is
baseline minus measured noise — no preference numbers.

| Gate | Rule | Basis |
| --- | --- | --- |
| Quality (non-inferiority) | Mean R@5 ≥ **0.2310** over all 223 queries | Baseline 0.255884 − paired bootstrap 95% half-width 0.024838 (`gate_noise.json`) |
| Regression | Identifier-heavy mean R@10 ≥ **0.2583** (n=200) | Baseline 0.278862 − paired half-width 0.020571; heading prefixes and identifier splitting make this the at-risk workload |
| Cost | Embedded tokens ≤ **1.15 ×** baseline build total; query p95 ≤ **2,850 ms** | Baseline token total recomputed with the same tokenizer counter at run time and recorded in the manifest; latency cap is 1.5 × baseline p95 and clears the p95 estimator CI (upper 2,334 ms) |

**Monitored, not gated:** continuity R@10 (n=20). Its bootstrap 95%
half-width is ±0.15 — any hard gate would be pure noise. Recorded and
inspected instead, with this stated reason in the plan.

## Noise evidence

`experiments/22-raw-query-qwen4b-baseline-2026-09-07/output/gate_noise.json`
(bootstrap N=10,000, seed 20260908): paired R@5 CI95 half-width 0.024838,
paired R@10 half-width 0.020571, hybrid p95 1,900 ms with estimator CI
[1,518.9, 2,334.3].

## Next steps

1. Recompute the baseline embedded-token total over the exp 22 corpus
   manifest with the production tokenizer counter; record it.
2. Write the ablation runner; declare the full cell matrix here before
   running (baseline splitter cell may reuse exp 22 checkpoints only if
   the runtime manifest matches).
3. Run cells; evaluate against the frozen gates only.
