# Deviation record: ambient machine load during D17 campaign

Date: 2026-08-23, 16:41 local.
Ratified by: Dr Muhammad Aizat Bin Md Hawari (option 1 — run now, timing flagged).

## Condition

Load averages around launch window: 27.56 / 22.57 / 18.67 (1/5/15 min) on
8 physical cores, 32 GB RAM. Transient spikes to ~43 observed (Spotlight
`mds_stores`, short-lived `top` probes).

Active consumers that could not be stopped:

1. phpunit suite (separate work session).
2. Microsoft Edge renderer tabs.
3. mediaanalysisd (macOS Photos analysis; killed at launch, macOS restarts it).
4. Two opencode sessions (one is the campaign operator, kept lightweight).

## Effect on evidence

- Quality metrics (nDCG, recall, hit fractions): VALID. The pipeline is
  deterministic for rankings: frozen LanceDB index, fixed query set, ONNX
  reranker. CPU contention changes wall-clock, not ordering.
- Latency metrics (mean_latency_ms, p95_latency_ms): INVALID for the
  protocol.md latency guardrail "P95(500) <= 3x P95(50)" (protocol.md,
  Dependent variables and guardrail table). Ambient contention inflates and
  adds variance to per-query wall-clock timing.

## Disposition

1. ADR-019 pool-size adjudication (task 6.1.6/6.1.7) proceeds on paired
   quality deltas and confidence intervals only.
2. Latency guardrail adjudication is DEFERRED. Re-run the pool-50 and
   pool-500 timing cells on a quiet machine before any latency-based claim.
3. results.md and the gate 6.GA record must reference this note.
