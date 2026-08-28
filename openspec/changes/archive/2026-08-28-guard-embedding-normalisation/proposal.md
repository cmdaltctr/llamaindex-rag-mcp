# Proposal: guard-embedding-normalisation

## Why

A 2026-08-23 implementation audit (rag-mcp-implementation-audit.md, §7 and
§11) found the pipeline applies no application-level vector normalisation:
stored and query embeddings reach LanceDB raw, and dense ranking uses L2
(converted to `1/(1+sqrt(d))` at the store boundary). Correctness of that
ranking therefore rests on an undocumented property of the embedding model:
that it emits unit-normalised vectors.

The follow-up investigation
(`openspec/changes/harden-pipeline-correctness-before-calibration/normalisation-investigation-2026-08-23.md`)
verified empirically that this holds today: the Ollama `qwen3-embedding:0.6b`
path emits unit vectors, and every one of the 10,024 vectors in the frozen
Experiment 10b index is unit-norm within float32 rounding. It also proved the
missing normalisation cannot explain the D17 reranker harm (both experiment
arms share one dense ordering; the campaign ran at threshold 0.0), so the
ADR-019 verdict is unaffected.

So nothing is broken today. The gap is contractual: swap the embedding model,
or move to the quantised llama.cpp production path (norms still unverified),
and L2 silently stops behaving like cosine. Long documents would win on
vector magnitude rather than meaning, with no error and no warning.

## What Changes

- Add a norm guard at both embedding boundaries: stored vectors at ingest and
  query vectors before dense search. The guard computes the vector L2 norm
  and compares it against a configurable tolerance.
- Ingest is fail-closed: a vector outside tolerance raises an actionable
  error naming the model, the observed norm, and the tolerance. Bad vectors
  never persist.
- Query is warn-and-continue: a violation logs loudly once per process and
  attaches a norm diagnostic to search results (diagnostics mode), so
  retrieval stays available while the misbehaviour is visible.
- Surface the effective guard state (enabled, tolerance, last observed norm
  band) in search diagnostics and ingestion reports.
- Validate the llama.cpp path empirically as part of this change: the guard
  exercises it automatically on first use; the acceptance task records the
  observed norms.

## Capabilities

### New Capabilities
- `embedding-norm-guard`: A boundary guard that verifies embedding vectors
  are unit-normalised within tolerance at ingest (fail-closed) and query
  (warn-and-continue) time, making the L2-as-cosine assumption explicit and
  enforced rather than inherited from model behaviour.

### Modified Capabilities
- None. The `score-normalisation` contract is untouched: no metric switch,
  no change to the `dense_similarity_v1` conversion, no re-embedding of
  existing indexes.

## Impact

- Core: new small module under `core/` (norm helper plus guard policy), wired
  into the ingest write path (`core/ingestion/replacement.py` embed step) and
  the query path (`core/retrieval/dense.py`), both behind injected settings
  (ADR-037 pattern; no singleton imports).
- Config: one new nested setting (tolerance, enable flag) documented in
  `.env.example` and the configuration guide.
- Tests: fail-first unit tests for both boundaries and the policy split;
  mocked providers covering norm 1.0 (pass), 0.7 (fail), 1.4 (fail).
- Documentation: ADR recording the guarantee decision (guard vs normalise vs
  metric switch), closing audit §11 for both provider paths.
- No re-embedding, no index rebuilds, no reranker policy changes: the D17
  and ADR-019 conclusions stand and are explicitly out of scope.

## Non-Goals

- No vector normalisation (division by norm) in the pipeline: recorded in the
  ADR as the rejected alternative for now, revisited only if a model or
  provider is adopted that does not emit unit vectors.
- No LanceDB metric change to cosine or inner product: `score.py` deliberately
  rejects non-L2 metrics for the `dense_similarity_v1` contract, and with
  unit vectors L2 ordering equals cosine ordering.
- No re-embedding or migration of existing indexes.
- No revisit of the reranker verdicts from Experiment 10b/D17.
