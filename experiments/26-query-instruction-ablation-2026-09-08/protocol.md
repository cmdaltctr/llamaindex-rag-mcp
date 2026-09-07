# Experiment 26 — Query-instruction ablation (task 5.3) — gates frozen

- **Status:** PLANNED (gates frozen 2026-09-08, task 1.6)
- **Date frozen:** 2026-09-08
- **Operator:** Dr Muhammad Aizat Bin Md Hawari with AI agent
- **OpenSpec stage:** Stage 5 candidate evaluation. Gates below were derived
  from Stage 1 baselines and committed BEFORE any candidate measurement.

## Purpose

Hold the Experiment 22 baseline index fixed and compare raw Qwen queries
with the same queries wrapped in the candidate instruction
(`EMBEDDING__QUERY_INSTRUCTION`). The instruction applies to queries
only and does not participate in index identity (task 4.8), so no
re-ingestion is required or permitted for this experiment.

## Frozen validity gates

Machine-readable form: [`plan.json`](./plan.json).

| Gate | Rule | Basis |
| --- | --- | --- |
| Quality | Paired mean R@5 lift ≥ **+0.0300** vs raw (absolute ≥ 0.2859) | Smallest lift clearing the paired bootstrap 95% noise floor (0.024838); +0.02 would sit inside noise |
| Regression | Identifier-heavy mean R@10 ≥ **0.2583** (n=200) | Baseline 0.278862 − paired half-width 0.020571; a preamble dilutes identifier tokens, taxing exact-token recall first |
| Latency | Query p95 ≤ **2,850 ms** | 1.5 × baseline p95 1,984.2 ms; clears the p95 estimator CI upper bound 2,334.3 ms. Runs must interleave raw and instructed queries to control network drift |

**Monitored, not gated:** continuity R@10 (n=20), bootstrap half-width
±0.15 — a hard gate would be noise. Recorded with that reason.

## Noise evidence

`experiments/22-raw-query-qwen4b-baseline-2026-09-07/output/gate_noise.json`
(bootstrap N=10,000, seed 20260908).

## Next steps

1. Select the candidate instruction text; record it verbatim in the
   runtime manifest before any measurement.
2. Write the runner with interleaved raw/instructed query order and
   cache isolation between arms; declare the full cell matrix here.
3. Run cells; evaluate against the frozen gates only.
