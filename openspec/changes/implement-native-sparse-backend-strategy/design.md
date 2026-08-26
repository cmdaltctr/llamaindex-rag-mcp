# Design: implement-native-sparse-backend-strategy

## Context

Hybrid retrieval accepts `auto|native|bm25`. BM25 is registered and
operational (`BM25SparseRetriever`, generation-aware cache keyed by
store identity + collection — PR #63). The native path warns and
delegates to BM25 (`_native_sparse_query` in
`core/retrieval/pipeline.py`); capability detection today is
Chroma-specific (`detect_native_sparse_capability` in
`core/vectordb/chroma.py`, surfaced through the vectordb registry's
`native_sparse_probe` metadata, which LanceDB declares as absent).

Locked versions: `lancedb` 0.37.1, `pylance` 10.0.0. Native FTS is
available; the Tantivy-backed FTS mode is gone from these versions. The
stored text lives in the `text` column (`core/vectordb/lance_rows.py`
schema: `id`, `doc_id`, `vector`, `text`, `metadata`).

## Goals / Non-Goals

**Goals:**

- Implement real native sparse querying (LanceDB native FTS over the
  `text` column) through the vector-store abstraction.
- Give native and BM25 one query contract and lazy registry.
- Keep `auto` as a composition-root capability policy.
- Preserve BM25 default, fallback, mixed-coverage diagnostics, and
  result shape.
- Define the FTS lifecycle explicitly, independent of the BM25 cache
  machinery.
- Measure quality and latency before any default promotion.

**Non-Goals:**

- Change the BM25 default.
- Reuse or extend the process-local generation counter as durable FTS
  index maintenance.
- Force re-ingestion or FTS-index rebuilding of existing collections
  (index creation is additive and explicitly triggered).
- Native sparse for the quarantined Chroma extra (the contract admits a
  later Chroma implementation).
- Add a cloud service or new base dependency.

## Decisions

### 1. Extend the vector-store capability first

A native sparse backend must call a typed vector-store method. The
implementation will not reach into `lancedb` from the retrieval
pipeline, preserving ADR-034 confinement. `VectorStore` gains a
sparse-query capability method with explicit unsupported behaviour; the
LanceDB adapter implements it over a **native FTS index on the `text`
column**, configured and queried through the locked LanceDB version's
documented FTS API (index configuration + `"fts"` search). A
pre-implementation contract test pins that API surface (see task 0.1)
so a dependency bump that changes it fails loudly.

### 2. Register only real concrete implementations

The registry contains `bm25` and `native` after native execution
exists. `auto` performs capability selection through the selected
store's registry metadata plus a real native-FTS probe, and returns one
of those names. The Chroma-specific `detect_native_sparse_capability`
probe is superseded by store-neutral capability resolution at the
composition boundary.

### 3. Keep fallback outside the strategy

Capability absence is resolved at composition time. Runtime FTS
failures emit one warning and invoke the BM25 strategy through the same
contract. Results record the backend that actually ran for diagnostics,
reusing the existing effective-backend diagnostic surface (PR #63)
rather than duplicating it.

### 4. FTS lifecycle is its own behaviour, not the generation counter

The store generation counter (PR #63) exists for cache invalidation: a
process-local signal that sparse-visible rows changed. An FTS index is
a persistent on-disk structure shared across processes; a process-local
counter cannot maintain it. The design therefore specifies FTS
lifecycle separately:

- **Creation:** additive, explicitly triggered index creation on the
  `text` column; existing collections without an index keep working.
- **Refresh:** defined behaviour after ingest writes and source
  replacements so indexed content tracks row content.
- **Deletion/stale nodes:** defined behaviour when rows are deleted or
  replaced, including stale-node handling.
- **Freshness:** the query path must be able to tell fresh from stale
  index state and surface it in diagnostics.
- **Coverage:** indexed versus unindexed rows are distinguished;
  unindexed rows remain in dense rankings and are absent only from
  native sparse rankings (the mixed-coverage contract, restated for FTS
  instead of sparse vectors).
- **Failure:** FTS failures fall back to BM25 with a visible warning;
  diagnostics name the failure.

### 5. Preserve PR #63 invariants untouched

The BM25 cache remains keyed by store identity + collection and
generation-checked exactly as the `hybrid-retrieval` requirement
"BM25 fallback index is scoped by store and collection and invalidates
on every mutation" specifies. This change adds a sibling execution
path; it does not modify that requirement.

## Risks / Trade-offs

- Vector-store API changes affect every adapter. The capability method
  has explicit unsupported behaviour so adapters without native sparse
  (Chroma extra) fail honestly rather than silently.
- Native FTS scores and BM25 scores are incomparable before RRF.
  Contract tests pin rank inputs, not raw score scales; the
  pre-implementation feasibility task records the locked version's
  score semantics.
- FTS indexes add disk footprint per collection and need refresh on
  writes; the lifecycle decision above governs this.
- Partial FTS coverage can bias fusion. Keep diagnostics and calibrate
  on representative corpora.
- Locked-version API drift: the contract test added in task 0.1 fails
  loudly on a LanceDB upgrade that changes the FTS surface.

## Migration Plan

0. Contract/feasibility: pin the locked-version native FTS behaviour
   (task 0.1) before any production change.
1. Baseline regression tests for the placeholder already exist; extend
   only where the delta requires.
2. Extend the vector-store contract and the LanceDB adapter with the
   FTS sparse query capability (additive index creation) in a focused
   seam module.
3. Add the shared sparse backend registry and register both
   implementations.
4. Route `auto` and explicit selections through composition-time
   capability resolution; move accepted-name validation to the
   composition boundary.
5. Run quality, latency, mixed-coverage, and lowest-direct validation.

Rollback unregisters native, restores the warning-to-BM25 path, and
leaves stored data and FTS indexes untouched (unused indexes are
inert).

## Sequencing constraints

- After `validate-embedding-write-contract` (shared LanceDB/base
  adapter write path).
- Not concurrent with `register-document-backend-strategies`
  (shared `compose.py`) or `add-per-collection-persist-dirs` (shared
  LanceDB/Chroma adapters).

## Calibration evidence position

Archived Stage 6 records D17 as complete: hybrid beats dense with
reranking disabled. That justifies hybrid's existence, not native FTS
over BM25. Any preference claim for native FTS requires a comparative
experiment on representative corpora; until then the default stays
`bm25`.
