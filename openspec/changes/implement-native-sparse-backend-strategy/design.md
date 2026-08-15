## Context

Hybrid retrieval accepts `auto|native|bm25`. BM25 is registered and operational. The native path currently warns and delegates to BM25 because the vector-store abstraction cannot issue a native sparse query. Registering the placeholder would imply a capability that does not exist and would invalidate experiment labels.

## Goals / Non-Goals

**Goals:**

- Implement real native sparse querying through the vector-store abstraction.
- Give native and BM25 one query contract and lazy registry.
- Keep `auto` as a composition-root capability policy.
- Preserve BM25 default, fallback, mixed-coverage diagnostics, and result shape.
- Measure quality and latency before any default promotion.

**Non-Goals:**

- Change the v1 BM25 default.
- Force re-ingestion of existing collections.
- Add a cloud service or new base dependency.

## Decisions

### 1. Extend the vector-store capability first

A native sparse backend must call a typed vector-store method. The implementation will not reach into ChromaDB from the retrieval pipeline, preserving ADR-034 confinement.

### 2. Register only real concrete implementations

The registry contains `bm25` and `native` after native execution exists. `auto` performs capability selection and returns one of those names.

### 3. Keep fallback outside the strategy

Capability absence is resolved at composition time. Runtime native failures emit one warning and invoke the BM25 strategy through the same contract. Results record the backend that actually ran for diagnostics.

### 4. Preserve mixed coverage

Chunks without sparse vectors remain in dense rankings and are absent only from native sparse rankings. The existing one-shot warning and re-ingestion hint remain.

## Risks / Trade-offs

- Vector-store API changes affect every adapter. Add a capability method with explicit unsupported behaviour.
- Native and BM25 scores are incomparable before RRF. Contract tests pin rank inputs, not raw score scales.
- Partial sparse coverage can bias fusion. Keep diagnostics and calibrate representative corpora.

## Migration Plan

1. Add failing tests proving the current native path delegates to BM25.
2. Extend the vector-store contract and Chroma adapter with native sparse query capability.
3. Add the shared sparse backend registry and register both implementations.
4. Route `auto` and explicit selections through composition-time capability resolution.
5. Run quality, latency, mixed-coverage, and lowest-direct validation.

Rollback unregisters native, restores the warning-to-BM25 path, and leaves stored vectors untouched.
