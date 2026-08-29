# ADR-054: Native Sparse Backend over LanceDB FTS

**Date:** 2026-08-29
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `implement-native-sparse-backend-strategy` (`feat/implement-native-sparse-backend-strategy`)

## Context

`RETRIEVAL__HYBRID_SPARSE_BACKEND` advertised a strategy family
(`auto|native|bm25`) with only one working member: BM25. The `native`
path warned and delegated to BM25, capability detection was
Chroma-specific (`detect_native_sparse_capability` probing
`PersistentClient.query_sparse` — always absent), and registering the
placeholder would have misrepresented capability and could have changed
ranking silently.

LanceDB became the default store (ADR-049) and its locked runtime
(lancedb 0.37.1 / pylance 10.0.0) exposes a native inverted-index FTS
over the stored `text` column. A pre-implementation contract test
pinned that API surface before any adapter code depended on it
(`tests/test_lancedb_native_fts_contract.py`, mutation-verified; raw
semantics recorded in the change's `feasibility-notes.md`). Two findings
shaped the design:

1. **FTS is fresh-by-construction.** Unindexed rows are scanned at query
   time and deletions are tombstoned, so a served ranking never misses
   post-index writes. "Staleness" is a durable, observable property
   (`list_indices()` reports `num_unindexed_rows`), not a correctness
   risk.
2. **The design's worst case cannot occur.** The lifecycle requirement
   ("never return stale native results as successful") is satisfied by
   the engine; refresh (`optimize()`) keeps the durable index tracking
   and the diagnostics honest rather than guarding correctness.

The stored-text column is `text`, not `documents` (the pre-correction
proposal named the wrong column and a Tantivy mode the locked versions
no longer ship).

## Decision

**Register a real native sparse backend executed as a typed
vector-store capability, keep `bm25` as the default, and own the FTS
lifecycle separately from the BM25 cache machinery.**

1. **Capability contract.** `VectorStore.query_native_sparse()` returns
   canonical higher-is-better rows (`native_fts_v1`); stores without a
   native engine fail honestly through the default
   `NotImplementedError` instead of returning an empty ranking that
   reads upstream as "no matches". Execution lives in the
   `lance_fts.py` adapter seam (the `lance_rows.py` precedent), so the
   retrieval pipeline never imports `lancedb` (ADR-034 confinement) and
   `lancedb.py` stays under the 500-line ceiling.

2. **One sparse-backend registry** (`core/retrieval/sparse_registry.py`)
   holds the concrete `bm25` and `native` implementations behind one
   query contract; the hybrid pipeline dispatches through it with no
   inline backend branching. `auto` stays an unregistered
   composition-root policy resolved through the selected store's
   registry metadata plus a real FTS probe — replacing the
   Chroma-specific route, which is removed (the quarantined Chroma
   extra declares no native capability; a future adapter can register
   one without pipeline changes).

3. **FTS lifecycle is its own behaviour.** Index creation is additive
   and triggered on first native use; durable staleness is observed via
   index statistics and healed by a query-time `optimize()`; mixed
   coverage triggers a one-shot warning restated for indexed versus
   unindexed rows; lifecycle or query failures fall back to BM25 with a
   visible warning, and the `sparse_backend` diagnostic reports the
   backend that actually ran — a fallen-back query is never labelled
   native. The process-local store generation counter (PR #63) remains
   a BM25 cache-invalidation mechanism only.

4. **The default stays `bm25`.** Experiment 19
   (`experiments/19-native-fts-vs-bm25-sparse-2026-08-29/`) is the
   comparative evidence D17 never was: quality parity (sparse
   Recall@10 0.850 vs 0.850; hybrid 0.950 vs 0.950), both backends
   deterministic, native peak RSS −7.4%, but native warm p50 is
   138.7× BM25's at the 53-chunk corpus scale (5.7 ms vs ~0.04 ms
   in-process; native cold start is 10.8× faster). The pre-registered
   promotion rule (win by ≥2 pp AND pass all gates AND user sign-off)
   keeps `bm25`.

5. **Name validation is registry-owned.** Accepted
   `RETRIEVAL__HYBRID_SPARSE_BACKEND` names are validated at the
   composition boundary (`capabilities.validate_sparse_backend`),
   listing `auto` plus the registered concrete names on failure;
   `config/` keeps only the §6.10 whitespace idiom (the
   `document_backend` / `community_algorithm` precedent — `config/`
   stays a leaf).

## Consequences

### Positive

- `native` and `auto` now mean what they say; selection is store-neutral
  and fails loudly on unknown names.
- The locked-version contract test turns any future LanceDB upgrade
  that changes the FTS surface into a CI failure, not a silent ranking
  change.
- Existing collections need no re-ingestion: first native use creates
  the index additively and synchronously; rollback is a settings change
  (stored data and FTS indexes are left untouched and inert).
- One file + one `register()` line remains the extension path for any
  future sparse backend (including a post-quarantine Chroma adapter).

### Negative

- Per-query native latency pays an engine round-trip: at small-corpus
  scale BM25 is decisively faster warm, so `native` is opt-in until
  evidence on larger corpora changes the trade.
- FTS indexes add per-collection disk footprint and a refresh
  (`optimize()`) on the first query after writes.
- Two coverage signals now coexist (FTS index statistics and the
  Chroma-era `has_sparse_vector` scan); the dispatch picks by store
  capability, which is one more behaviour to keep honest in tests.

### Neutral

- Native and BM25 scores are incomparable before RRF by design; only
  rank order feeds fusion (`native_fts_v1` claims ranking within one
  query, nothing more).
- The Experiment 19 corpus is small; the recorded caveat means the
  latency ratio is scale-dependent, not a constant.

## Alternatives Considered

| Option                                                     | Rejected Because                                                                                                                       |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Register the placeholder as `native`                        | Misrepresents capability; an empty ranking would read as "no matches"; violates the "never label placeholder as native" spec            |
| Use the process-local generation counter for FTS maintenance | A process-local counter cannot maintain a cross-process on-disk index (design decision 4); PR #63 semantics would be silently repurposed |
| Refresh the FTS index on every write path                   | `optimize()` per ingest batch is wasteful; the durable stale marker plus query-time refresh reaches the same state lazily               |
| Keep Chroma-specific capability detection                   | Capability belongs to the selected store, not an installed extra; the route could never answer for lancedb                              |
| Promote `native` to default                                 | Fails the pre-registered promotion rule: no quality win and a 138.7× warm-latency regression at measured scale                          |
| Build native sparse into the retrieval pipeline directly     | Breaks ADR-034 confinement (pipeline importing `lancedb`) and the 500-line ceiling on `pipeline.py`/`lancedb.py`                        |

## References

- Change: `openspec/changes/implement-native-sparse-backend-strategy/`
  (proposal, design decisions 1–5, feasibility-notes.md, tasks)
- Locked-version FTS contract: `tests/test_lancedb_native_fts_contract.py`
- Adapter seam: `src/rag_mcp/core/vectordb/lance_fts.py`
- Registry + dispatch: `core/retrieval/sparse_registry.py`,
  `core/retrieval/sparse_dispatch.py`, `core/retrieval/native_sparse.py`
- Composition resolution: `src/rag_mcp/capabilities.py`
  (`resolve_sparse_backend`, `validate_sparse_backend`)
- Calibration evidence: `experiments/19-native-fts-vs-bm25-sparse-2026-08-29/`
  (protocol with pre-registered gates, results, analysis)
- User guide: `docs/guides/reranker.md` (sparse retrieval backends section)
- Related: ADR-034 (vector-store abstraction), ADR-046 (LanceDB backend),
  ADR-049 (Chroma quarantine), ADR-017/018 (hybrid defaults)
