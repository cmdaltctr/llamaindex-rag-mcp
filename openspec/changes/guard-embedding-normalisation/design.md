# Design: guard-embedding-normalisation

## Context

The dense retrieval path ranks by L2 distance over raw model vectors and
converts to similarity at the store boundary (`core/vectordb/score.py`). L2
ranking equals cosine ranking only when vectors are unit-normalised. Today
that property comes from the embedding model's training, verified empirically
for the Ollama `qwen3-embedding:0.6b` path (2026-08-23 investigation), but
enforced nowhere in code.

## Goals

- Make the unit-norm assumption an enforced contract, not an inherited one.
- Catch model or provider swaps (including the unverified llama.cpp
  quantised path) before they silently degrade ranking.
- Change nothing about existing vectors, scores, or index identities.

## Decisions

### D1: guard, do not normalise

Verify norms and refuse or warn; do not divide by the norm.

- Rationale: existing vectors are already unit-norm (verified across the
  whole frozen index), so normalisation today is a no-op plus float noise.
  A guard converts the implicit contract into an explicit failure mode at
  minimal code cost, with zero effect on the hot path beyond one norm
  computation per batch.
- Alternative (rejected for now): normalise at both boundaries. Stronger
  guarantee for future non-unit models, but it changes stored bytes for no
  measured benefit today and would force every index identity to be
  revisited. Revisit if a non-unit model is ever adopted.
- Alternative (rejected): switch LanceDB to a cosine or inner-product metric.
  `score.py` intentionally rejects non-L2 metrics for the
  `dense_similarity_v1` contract (TDR-015 lineage), and with unit vectors the
  ordering is identical. A metric switch buys nothing for real migration cost.

### D2: fail-closed at ingest, warn-and-continue at query

- Ingest: a violating vector aborts the file's replacement before write.
  Failure-safe replacement ordering then keeps the previous searchable
  version intact, so the store never gains a bad vector. The error names the
  model, observed norm, tolerance, and the setting that controls it.
- Query: a violation logs loudly (once per process per model) and attaches a
  `norm_guard` diagnostic when diagnostics are enabled. Search still returns
  results: a degraded answer beats an outage, and the diagnostic makes the
  degradation visible.
- Alternative (rejected): fail-closed at query too. A misbehaving provider
  would take retrieval down entirely; warn-and-diagnose preserves
  availability while the ingest-side guard still prevents persistence.

### D3: tolerance and configuration

- Default tolerance `1e-3` (observed float32 rounding band is ~1e-7; three
  orders of headroom catches real drift without false alarms).
- New nested settings under the existing schema (ADR-037 style):
  `EMBEDDING__NORM_GUARD_ENABLED` (default true) and
  `EMBEDDING__NORM_TOLERANCE` (default 0.001). Guard disabled is an explicit,
  logged escape hatch for exotic providers, not a silent default.

### D4: single choke point

One helper module computes norms and applies the policy; both boundaries call
it. The ingest boundary sits in the embed step of
`core/ingestion/replacement.py` (before `write_nodes`); the query boundary in
`core/retrieval/dense.py` (after the cached embed call). Settings are
injected, never imported as a singleton (repo invariant #9). No cross-imports
between ingestion and retrieval; the shared helper lives in `core/` where
both may import it without violating invariant #2 (settings-only sharing is
the existing pattern; the helper is pure functions plus injected policy, no
business logic).

### D5: llama.cpp validation is an acceptance criterion, not a separate change

The guard exercises any provider the first time it runs. The acceptance task
embeds one query through a local `llama-server` with the production GGUF and
records the observed norm band, closing audit §11 for the second provider
path. No production index may be built on that path before this task passes.

## Risks / Trade-offs

- One extra norm computation per embed batch and per query: negligible
  against embedding inference cost; per-query cost is amortised by the
  existing query-embedding cache (the guard sits after the cache).
- False positives from an exotic-but-valid provider: mitigated by the
  configurable tolerance and the explicit disable switch, both logged.
- The ADR must state plainly that this closes a contract gap, not a measured
  defect: no quality change is expected or claimed.

## Migration Plan

None. No stored data changes, no index identity changes, no config breakage
(new keys default to the active guard).

## Open Questions

- Should the warn-and-continue query diagnostic also fire when the guard is
  explicitly disabled (a quiet `norm_guard: disabled` field vs silence)?
  Default proposal: silence, matching the diagnostics philosophy of reporting
  what ran, not what did not.
