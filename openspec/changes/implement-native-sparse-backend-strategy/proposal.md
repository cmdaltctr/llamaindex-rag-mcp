# Proposal: implement-native-sparse-backend-strategy

> **Re-targeted 2026-08-22** for the post-ADR-049 topology (default
> store LanceDB; Chroma quarantined behind the opt-in extra).
> **Corrected 2026-08-26** against v3: the previously named mechanism —
> "Tantivy-based FTS over the documents column" — is wrong on two
> counts. The locked LanceDB 0.37.1 / pylance 10.0.0 no longer ships a
> Tantivy-backed FTS mode; native FTS is the implementation strategy.
> And the stored text column is `text`, not `documents`.

## Why

`RETRIEVAL__HYBRID_SPARSE_BACKEND=bm25|native` looks like a configured
strategy family, but only BM25 has a working registry implementation.
The current `native` path logs that native querying is unavailable and
delegates to BM25. Registering that placeholder as a native
implementation would misrepresent capability and could change ranking,
mixed-coverage handling, and fallback behaviour. Native query execution
therefore needs real implementation behind the vector-store contract,
with empirical validation before any default change.

API availability is not the blocker: LanceDB 0.37.1 exposes native FTS.
What remains open is (a) a locked-version contract for the native FTS
API surface (index configuration, `"fts"` search, filtering, result
shape, score semantics, refresh/freshness behaviour) and (b) the
design/spec corrections recorded here.

## What Changes

- Implement a real native sparse query adapter for the LanceDB backend,
  backed by **LanceDB native FTS** over the stored `text` column.
- Define one sparse-query contract on the `VectorStore` ABC shared by
  native and BM25 implementations; native execution happens inside the
  LanceDB adapter, never in the retrieval pipeline (ADR-034
  confinement).
- Define the FTS index lifecycle as its own behaviour — initial
  creation, refresh after writes and replacements, delete/stale-node
  handling, freshness, indexed versus unindexed rows, and failure and
  fallback diagnostics. The process-local store generation counter is
  **not** durable FTS-index maintenance; it remains a cache-invalidation
  mechanism only (PR #63 semantics preserved unchanged).
- Register both concrete backends (`bm25`, `native`); keep `auto` as a
  composition-root capability policy resolving to a concrete registered
  name, informed by the selected store's registry capability metadata
  and a real native-FTS probe.
- Preserve explicit diagnostics and BM25 fallback when native
  capability is absent (no FTS index) or fails safely at query time.
- Calibrate ranking quality and latency against BM25 on representative
  corpora before considering any default change. D17 (archived Stage 6)
  is complete and shows hybrid value with reranking disabled, but it
  does **not** prove native FTS is preferable to BM25; comparative
  evidence is still required for that question.
- Chroma native sparse remains out of scope while the runtime is
  quarantined; a Chroma adapter could later implement the same contract
  without pipeline changes.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `hybrid-retrieval`: Add operational native sparse execution and
  registry dispatch while preserving BM25 fallback semantics. The delta
  now MODIFIES the existing Chroma-era requirements (backend selection
  via ChromaDB capability detection; mixed coverage via sparse vectors)
  to store-neutral, FTS-based wording instead of only adding new
  requirements alongside them.

## Impact

- Code: `core/retrieval/sparse.py`, `core/retrieval/pipeline.py`,
  `core/retrieval/registry.py`, `core/vectordb/{base,lancedb}.py`, and
  `compose.py`. `compose.py` (497 lines), `lancedb.py` (497 lines), and
  `chroma.py` (499 lines) sit at the 500-line ceiling — additions land
  in small focused seam modules (following `lance_rows.py` precedent),
  not inline growth.
- Configuration: accepted values remain `auto|native|bm25`; the default
  remains `bm25` unless a later calibrated decision changes it.
  Accepted-name validation moves from the hard-coded settings tuple to
  registry-owned validation at the composition boundary (`config/`
  stays a leaf).
- Stored data: FTS index creation is additive on existing `.lance`
  tables; collections without an FTS index keep working with explicit
  mixed-coverage diagnostics. No embedding re-computation.
- Dependencies: none new — native FTS ships with the existing
  `lancedb` base dependency. (A residual `tantivy` entry in `uv.lock`
  does not restore a Tantivy-backed FTS mode; do not build against it.)
- Experiments: compare retrieval quality, latency, and coverage against
  BM25 before promotion.

## Sequencing (binding on implementation planning)

- Implement **after** `validate-embedding-write-contract`: both touch
  the LanceDB/base adapter write path, and the shared write boundary
  must land first.
- Do not implement concurrently with `register-document-backend-strategies`
  (both touch `compose.py`) or with `add-per-collection-persist-dirs`
  (both touch the LanceDB/Chroma adapters). Land on sequenced branches.

## Filed by

`add-pluggable-community-detection` task 4.8. The registry eligibility
audit deferred this behaviour-changing migration; re-targeted per the
`harden-pipeline` task 7.8 re-evaluation.
