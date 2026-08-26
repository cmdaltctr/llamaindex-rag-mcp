# Proposal: implement-native-sparse-backend-strategy

> **Re-targeted 2026-08-22** for the post-ADR-049 topology. The original
> proposal committed to "a real native sparse query adapter for the
> supported ChromaDB runtime"; that runtime is now the quarantined,
> opt-in `chroma` extra. Building the flagship sparse path against a
> quarantined backend contradicts the quarantine's intent. The default
> target is now the qualified LanceDB store, whose native full-text
> search (Tantivy-based FTS) provides the sparse execution path.

## Why

`RETRIEVAL__HYBRID_SPARSE_BACKEND=bm25|native` looks like a configured
strategy family, but only BM25 has a working registry implementation. The
current `native` path logs that native querying is unavailable and
delegates to BM25. Registering that placeholder as a native implementation
would misrepresent capability and could change ranking, mixed-coverage
handling, and fallback behaviour. Native query execution therefore needs
real implementation behind the vector-store contract, with empirical
validation before any default change.

## What Changes

- Implement a real native sparse query adapter for the LanceDB backend,
  backed by LanceDB's native full-text search index (Tantivy FTS over the
  documents column).
- Define one sparse-query contract on the `VectorStore` ABC shared by
  native and BM25 implementations; native execution happens inside the
  LanceDB adapter, never in the retrieval pipeline (ADR-034 confinement).
- Register both concrete backends (`bm25`, `native`); keep `auto` as a
  composition-root capability policy resolving to a concrete registered
  name, informed by the registry's backend capability metadata.
- Preserve explicit diagnostics and BM25 fallback when native capability
  is absent (no FTS index) or fails safely at query time.
- Calibrate ranking quality and latency against BM25 on representative
  corpora before considering any default change; the Stage 6 D17 hybrid
  evidence informs whether the campaign is warranted.
- Chroma native sparse remains out of scope while the runtime is
  quarantined; a Chroma adapter could later implement the same contract
  without pipeline changes.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `hybrid-retrieval`: Add operational native sparse execution and registry
  dispatch while preserving BM25 fallback semantics.

## Impact

- Code: `core/retrieval/sparse.py`, `core/retrieval/pipeline.py`,
  `core/retrieval/registry.py`, `core/vectordb/{base,lancedb}.py`, and
  `compose.py`.
- Configuration: accepted values remain `auto|native|bm25`; the default
  remains `bm25` unless a later calibrated decision changes it.
- Stored data: FTS index creation is additive on existing `.lance`
  tables; collections without an FTS index keep working with explicit
  mixed-coverage diagnostics. No embedding re-computation.
- Dependencies: none new — LanceDB FTS ships with the existing `lancedb`
  base dependency.
- Experiments: compare retrieval quality, latency, and coverage against
  BM25 before promotion.

## Filed by

`add-pluggable-community-detection` task 4.8. The registry eligibility
audit deferred this behaviour-changing migration; re-targeted per the
`harden-pipeline` task 7.8 re-evaluation.
