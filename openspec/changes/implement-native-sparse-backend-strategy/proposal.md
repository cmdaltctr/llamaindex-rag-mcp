## Why

`RETRIEVAL__HYBRID_SPARSE_BACKEND=bm25|native` looks like a configured strategy family, but only BM25 has a working registry implementation. The current `native` path logs that native querying is unavailable and delegates to BM25. Registering that placeholder as a native implementation would misrepresent capability and could change ranking, mixed-coverage handling, and fallback behaviour. Native query execution therefore needs a separate change with empirical validation.

## What Changes

- Implement a real native sparse query adapter for the supported ChromaDB runtime.
- Define one sparse-query contract shared by native and BM25 implementations.
- Register both concrete backends; keep `auto` as a composition-root capability policy.
- Preserve explicit diagnostics and BM25 fallback when native capability is absent.
- Calibrate ranking quality and latency before considering any default change.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `hybrid-retrieval`: Add operational native sparse execution and registry dispatch while preserving BM25 fallback semantics.

## Impact

- Code: `core/retrieval/sparse.py`, `core/retrieval/pipeline.py`, `core/retrieval/registry.py`, `core/vectordb/`, and `compose.py`.
- Configuration: accepted values remain `auto|native|bm25`; the default remains `bm25` unless a later calibrated decision changes it.
- Stored data: native sparse vectors and mixed-coverage migration require explicit compatibility checks.
- Experiments: compare retrieval quality, latency, and coverage against BM25 before promotion.

## Filed by

`add-pluggable-community-detection` task 4.8. The registry eligibility audit deferred this behaviour-changing and persisted-data-sensitive migration.
