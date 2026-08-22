# Design: implement-native-sparse-backend-strategy

## Context

Hybrid retrieval accepts `auto|native|bm25`. BM25 is registered and
operational. The native path currently warns and delegates to BM25
because the vector-store abstraction cannot issue a native sparse query.
Post-ADR-049 the default store is LanceDB, whose tables support native
full-text search indexes (Tantivy) over the documents column; the
registry's capability metadata already carries a `native_sparse_probe`
marker per backend (Chroma declares one; LanceDB currently declares
none). Registering the placeholder would imply a capability that does
not exist and would invalidate experiment labels.

## Goals / Non-Goals

**Goals:**

- Implement real native sparse querying (LanceDB FTS) through the
  vector-store abstraction.
- Give native and BM25 one query contract and lazy registry.
- Keep `auto` as a composition-root capability policy.
- Preserve BM25 default, fallback, mixed-coverage diagnostics, and result
  shape.
- Measure quality and latency before any default promotion.

**Non-Goals:**

- Change the v1 BM25 default.
- Force re-ingestion or FTS-index rebuilding of existing collections
  (index creation is additive and explicitly triggered).
- Native sparse for the quarantined Chroma extra (out of scope until the
  quarantine lifts; the contract admits a later Chroma implementation).
- Add a cloud service or new base dependency.

## Decisions

### 1. Extend the vector-store capability first

A native sparse backend must call a typed vector-store method. The
implementation will not reach into `lancedb` from the retrieval pipeline,
preserving ADR-034 confinement. `VectorStore` gains a sparse-query
capability method with explicit unsupported behaviour; the LanceDB
adapter implements it over a Tantivy FTS index on the documents column.

### 2. Register only real concrete implementations

The registry contains `bm25` and `native` after native execution exists.
`auto` performs capability selection (FTS index present and healthy) and
returns one of those names. The registry's per-backend
`native_sparse_probe` metadata flips to a real probe for LanceDB.

### 3. Keep fallback outside the strategy

Capability absence is resolved at composition time. Runtime FTS failures
emit one warning and invoke the BM25 strategy through the same contract.
Results record the backend that actually ran for diagnostics.

### 4. Preserve mixed coverage

Chunks without FTS coverage remain in dense rankings and are absent only
from native sparse rankings — identical semantics to the Chroma-era
design. The existing one-shot warning and explicit re-index hint remain.

## Risks / Trade-offs

- Vector-store API changes affect every adapter. The capability method
  has explicit unsupported behaviour so adapters without native sparse
  (Chroma extra) fail honestly rather than silently.
- Tantivy FTS scores and BM25 scores are incomparable before RRF.
  Contract tests pin rank inputs, not raw score scales.
- FTS indexes add disk footprint per collection and must be invalidated
  on writes; index maintenance follows the same invalidation counter as
  the BM25 cache.
- Partial FTS coverage can bias fusion. Keep diagnostics and calibrate
  on representative corpora.

## Migration Plan

1. Add failing tests proving the current native path delegates to BM25.
2. Extend the vector-store contract and the LanceDB adapter with the FTS
   sparse query capability (additive index creation).
3. Add the shared sparse backend registry and register both
   implementations.
4. Route `auto` and explicit selections through composition-time
   capability resolution.
5. Run quality, latency, mixed-coverage, and lowest-direct validation.

Rollback unregisters native, restores the warning-to-BM25 path, and
leaves stored data and FTS indexes untouched (unused indexes are inert).
