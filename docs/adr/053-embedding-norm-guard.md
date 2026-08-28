# ADR-053: Embedding Norm Guard

**Date:** 2026-08-28
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `guard-embedding-normalisation` (`feat/guard-embedding-normalisation`)

## Context

Dense retrieval ranks by L2 distance over raw embedding vectors and converts
to cosine-like similarity at the store boundary (`core/vectordb/score.py`,
the `dense_similarity_v1` contract). L2 ordering equals cosine ordering only
when every vector is unit-normalised. Nothing in the code enforced that
property — correctness rested on an undocumented behaviour of the embedding
model.

A 2026-08-23 investigation verified the property holds today: the Ollama
`qwen3-embedding:0.6b` path emits unit vectors, and all 10,024 vectors in the
frozen Experiment 10b index are unit-norm within float32 rounding
(deviation ~1e-7). It also proved the missing normalisation cannot explain
the D17 reranker harm: both experiment arms share one dense ordering and the
campaign ran at threshold 0.0, so the ADR-019 verdict is unaffected. *(The
investigation note itself is not present in the repository — its parent
change archived without it — so its evidence is restated here from the
change proposal and re-verified below for the llama.cpp path.)*

So nothing is broken today. The gap is contractual: swap the embedding
model or move to the quantised llama.cpp production path, and L2 silently
stops behaving like cosine. Long documents would win on vector magnitude
rather than meaning, with no error and no warning.

## Decision

**Guard the unit-norm property at both embedding boundaries; do not
normalise vectors and do not change the store metric.**

1. **One shared helper** (`core/norm_guard.py`, pure functions plus injected
   policy) computes L2 norms and applies the boundary policy. Ingest
   (`core/ingestion/replacement.py`, after the embed step, before any
   `write_nodes`) and query (`core/retrieval/dense.py`, after the cached
   embed call) both call it with the injected settings; neither boundary
   imports the other.
2. **Ingest fails closed.** A vector whose norm deviates from 1.0 beyond the
   tolerance raises `EmbeddingNormViolationError` — naming the model, the
   observed norm, the tolerance, and the controlling setting — inside the
   attributed embedding stage, so `write_nodes` never sees it and
   failure-safe ordering (ADR-048) keeps the previous version searchable.
   NaN norms always violate (NaN never wins a deviation comparison, so it
   is tracked explicitly). The observed norm band is recorded in the file's
   ingest report as `embedding_norm_band`.
3. **Query warns and continues.** A violation logs once per process per
   model and attaches a `norm_guard` diagnostic
   (`{enabled, tolerance, observed_norm, violation}`) to every result row
   when diagnostics are enabled. Results are always returned: a degraded
   answer beats an outage, and the ingest-side guard still prevents
   persistence.
4. **Configuration is explicit and visible.** New nested settings
   `EMBEDDING__NORM_GUARD_ENABLED` (default `true`) and
   `EMBEDDING__NORM_TOLERANCE` (default `0.001`, inclusive, must be
   positive). Disabling the guard logs a startup warning naming the
   setting. The tolerance default gives three orders of headroom over the
   observed ~1e-7 float32 rounding band. The config-facing
   `EmbeddingSettings` lives in `core/settings.py` beside its
   `EmbeddingBlock` twin: placing it under `core/providers/embeddings/`
   would transitively leak the quarantined providers package into every
   module that imports `config` (import-linter contracts forbid that).

## Evidence

- **Ollama path** (2026-08-23 investigation, restated): `qwen3-embedding:0.6b`
  emits unit vectors; 10,024/10,024 frozen Experiment 10b vectors unit-norm
  within float32 rounding.
- **llama.cpp path** (this change, task 3.1): one probe through a local
  `llama-server` (v9960) serving the production GGUF
  `Qwen3-Embedding-0.6B-Q8_0.gguf` (sha256 `06507c7b…`, byte-identical to the
  Ollama blob) returned 1024-dim vectors with L2 norms `0.99999995` and
  `0.99999997` — deviation ≤ `4.8e-08`, four orders of magnitude inside the
  default tolerance. Audit §11 is closed for both locally supported provider
  paths.
- **D17 independence:** missing normalisation cannot explain the reranker
  harm (shared dense ordering, threshold 0.0 campaign), so the ADR-019 and
  Experiment 10b verdicts stand unchanged.

## Rejected Alternatives

- **Normalise at both boundaries** (divide each vector by its norm):
  stronger guarantee for future non-unit models, but a measured no-op today
  (all stored vectors are already unit-norm) that changes stored bytes for
  no benefit and forces every index identity to be revisited. Revisit if a
  deliberately non-unit model is ever adopted.
- **Switch LanceDB to a cosine or inner-product metric:**
  `score.py` intentionally rejects non-L2 metrics for the
  `dense_similarity_v1` contract (TDR-015 lineage), and with unit vectors
  the ordering is identical — a metric switch buys nothing for real
  migration cost.
- **Re-embedding / index migration:** unnecessary — existing indexes
  already satisfy the contract (verified across the frozen index).
- **Reranker policy changes:** out of scope; D17 shows the reranker verdict
  is independent of this gap.

## Consequences

- The unit-norm assumption is now an enforced contract rather than an
  inherited one; a model or provider swap that breaks it fails loudly at
  ingest (before persistence) and visibly at query (warn-once plus
  diagnostics) instead of silently degrading ranking.
- Cost: one `fsum` pass per vector at ingest and one per query embedding —
  negligible against embedding inference, and the query-side cost sits
  after the existing LRU cache so cached queries only pay the norm.
- Structural vectors (empty, NaN) that previously surfaced at the
  store-write validator on the replacement path now abort one stage earlier
  (embedding stage, `EmbeddingNormViolationError`); the store-level
  validator still guards direct `upsert_precomputed` callers. The two
  affected write-contract test expectations were updated accordingly.
- The shared test mock emits unit vectors (`_UnitNormMockEmbedding`); the
  stock LlamaIndex `MockEmbedding` constant vector (norm ~9.8 at dim=384)
  would fail the guard. Normalisation is score-neutral because the vector
  stays constant.
- Guard-disabled deployments are visible in the startup log; a quiet
  `norm_guard: disabled` diagnostic was deliberately rejected (diagnostics
  report what ran, not what did not).
