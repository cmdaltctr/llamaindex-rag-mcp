# Fix retrieval freshness and add lineage-based context assembly

## Why

Three retrieval-side defects, all verified at runtime during the 2026-09-01
audit. Each is silent: no error, no warning, no failing test.

**1. Sparse retrieval cannot see writes from another process.** The BM25 index
is cached per `(store identity, collection)` and invalidated when the store's
generation counter advances. That counter is `self._generations` — a plain
dict on the store *instance*, process-local by design. Reproduced with two
store handles over one database:

```
writer ingests one.txt →  reader generation counter: 0,  table.version: 1
writer ingests two.txt →  reader generation counter: 0   ← UNCHANGED
                          table.version: 2               ← the durable signal
```

`rag-mcp watch` is documented as running as a separate process from the MCP
server. When the daemon ingests, the server's counter never moves, so the
server serves a BM25 index built before that document existed — for the life
of the process. The `codebase` profile enables hybrid by default, so this is
the default experience for that profile.

Switching the default to native FTS is **not** the fix: Experiment 19 already
pre-registered that comparison and decided to keep BM25, because native failed
the latency gate at 138.7× BM25's warm p50. The audit's original suggestion to
default to `auto` contradicted that evidence and is withdrawn here.

**2. There is no context-assembly stage at all.** `search()` ends at
`results.sort(...)`, `results[:top_k]`, and a field strip. No de-duplication,
no near-duplicate removal, no neighbour or parent expansion, no ordering
strategy, no token budgeting. With `chunking.chunk_overlap=100`, adjacent chunks are returned as separate
results and may repeat splitter-produced overlap. An audit snapshot observed
substantial duplicate text, but it did not record a reproducible corpus,
query and command, so this proposal does not use the unverified 19.7% figure
as acceptance evidence. The statically verified defect is the absent assembly
stage and duplicated adjacent content.

This is the gap that looks like "we should have used a docstore". We should
not — see below — but the *capability* a docstore provides is genuinely
missing and needs an equivalent.

**3. A moved file silently forks the index.** The watcher subclasses
`PatternMatchingEventHandler` and implements `on_created`, `on_modified` and
`on_deleted`, but not `on_moved`. A rename inside the watch tree fires neither
a delete nor an ingest, so the old path's rows stay indexed and the new path
is never indexed. Confirmed at runtime: after a move plus re-ingest the store
held the same content under two paths.

A fourth, related item is included because it lives in the same write path and
is genuinely load-bearing at scale: `_stale_source_ids` iterates **every row in
the collection**, in Python, for every source file replaced — inside the global
write lock. Cost is O(files × collection size); re-ingesting 500 files into a
50,000-chunk collection performs 25 million row visits with all other
ingestion blocked.

## What Changes

- Sparse-cache invalidation moves from the process-local counter to a durable,
  cross-process data token supplied by the vector store. LanceDB uses
  `(omrg_dataset_epoch, table.version)`: an OMRG-owned random epoch stored in
  current table schema metadata plus the backend version. Ordinary mutations
  preserve the epoch and advance the version; creation, recreation and every
  overwrite-based rebuild replace the epoch. Numeric `table.version` alone is
  insufficient because version history restarts, while history-derived genesis
  timestamps are unsafe under pruning. BM25 stays the default backend, keeping
  Experiment 19's latency result intact.
- A new **chunk-lineage navigation** capability provides, from stored metadata
  alone, what a document store would have provided from node relationships:
  fetch a chunk's neighbours, fetch a source's ordered chunk set, reconstruct
  contiguous spans. This is the docstore equivalent, and it is strictly more
  queryable than the thing it replaces.
- A new **context-assembly** stage runs between retrieval and return: adjacent
  overlapping chunks are merged rather than returned twice, and neighbour
  expansion is available behind a flag. Default behaviour changes only by
  removing duplicated text, never by removing evidence.
- The watcher handles `on_moved`.
- Stale-row selection is scoped to the source instead of scanning the
  collection.

Not in scope: MMR (needs vectors returned from the store — a wider ABC change,
and de-duplication should be measured first), query transformation, answer
synthesis (separate change), any change to ranking or scoring.

## Capabilities

### New Capabilities

- `chunk-lineage-navigation`: neighbour, span and ordered-set lookup for
  stored chunks, derived from persisted lineage metadata rather than a
  document store.
- `retrieval-context-assembly`: the stage between final ranking and return —
  overlap merging, optional expansion, and the ordering contract.

### Modified Capabilities

- `vectordb-abstraction`: stores expose a durable collection data version for
  derivative-cache invalidation.
- `hybrid-retrieval`: the sparse cache is invalidated by that durable version,
  so cross-process writes are visible.
- `watch-command`: move events are handled.
- `document-deletion`: stale-row selection is source-scoped rather than a full
  collection scan.

## Impact

- **No re-ingest required.** Stored vectors and row metadata are unchanged.
  LanceDB tables gain one schema-metadata epoch when first created or next
  mutated; this is cache identity, not indexed content.
- Result-shape change: merged rows carry the union of their constituents'
  lineage and a marker naming what was merged. Callers that ignore unknown
  keys are unaffected; the strict OpenAPI `SearchResult` gains optional fields.
- Code: `core/vectordb/{base,lancedb,chroma}.py`, `core/retrieval/sparse.py`,
  new `core/retrieval/lineage.py` and `core/retrieval/assembly.py`,
  `core/retrieval/pipeline.py`, `core/ingestion/replacement.py`,
  `daemon/watcher.py`.
- Retrieval-quality gate: overlap merging changes returned text, so Tier 1 and
  Tier 2 must be re-measured. Recall must not regress; the merged text is a
  superset of what each constituent contributed.
- No new dependencies.
