# ADR-056: Lineage Navigation Replaces a Document Store

**Date:** 2026-09-02
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The 2026-09-01 audit found three silent retrieval defects. First, the BM25
sparse index was cached against a process-local generation counter, so a
watcher daemon writing from another process never invalidated the server's
cache — the server served an index built before those documents existed, for
the life of the process. Second, retrieval had no context-assembly stage at
all: with `chunking.chunk_overlap=100`, adjacent chunks returned as separate
rows and repeated the splitter-produced overlap text. Third, the obvious fix
for the second defect looks like "add a document store", because the
neighbour and parent lookups a docstore provides are exactly what assembly
needs.

Three forces shaped the decision:

1. **A second store breaks failure-safe replacement.** The replacement path
   (ADR-048) writes under an attempt id, verifies the durable row count, and
   only then deletes the previous version. With two stores, each of those
   failure paths acquires a second thing to reconcile, and a half-failed
   write can leave a chunk in one store and not the other. The
   `add-ingestion-change-detection` design already rejected a sidecar state
   file for exactly this reason (its decision D2: it "introduces a second
   store that can drift"). A document store is that sidecar with a nicer
   name.
2. **The lineage metadata already exists.** Every stored row carries
   `source_id`, `source_version`, `chunk_id`, `source_chunk_index` and
   `source_chunk_count` (ADR-052), on both dense and sparse paths. What a
   docstore would provide from node relationships is derivable from data
   already persisted.
3. **Durable cache identity is non-trivial on Lance.** The numeric
   `table.version` advances on ordinary commits but restarts under
   overwrite-based schema evolution and table recreation, so it alone cannot
   key a cross-process cache. History-derived genesis timestamps are unsafe
   under pruning.

LlamaIndex's own assembly machinery — `PrevNextNodePostprocessor`,
`AutoMergingRetriever` — takes a `BaseDocumentStore` as a required
constructor field, so adopting it means persisting a second store.

## Decision

1. **Cache validity is a durable epoch+version token (design D1).** The
   `VectorStore` ABC gains `get_data_version(collection) -> str | None`. The
   value is an opaque token. Lance implements it as a tagged pair of
   `omrg_dataset_epoch` — a random UUID stored in the *current* table schema
   metadata through the existing metadata seam — plus `table.version`.
   Ordinary writes preserve the epoch and advance the version. Table
   creation, delete/recreate, and every `mode="overwrite"` rebuild replace
   the epoch, so a rebuilt table can never collide with a cached token even
   when its numeric version restarts. A pre-existing marker-less table is
   not mutated by reads; it returns `None` until the next OMRG-controlled
   writer installs an epoch under the write lock. Chroma returns `None`
   where it cannot meet the guarantee, with the reason in the adapter
   docstring. The BM25 cache resolves an explicitly tagged validity token —
   durable `(epoch, version)` or local generation — so a transition between
   modes can never compare equal, and the local fallback warns once per
   collection naming the reduced guarantee. The default sparse backend
   stays BM25 (Experiment 19; native FTS failed the latency gate at
   138.7× BM25's warm p50).

2. **The docstore equivalent is a lineage navigator (design D2).**
   `core/retrieval/lineage.py` provides `is_adjacent(a, b)`,
   `neighbours(rows, store, collection, window)` and
   `span(store, collection, source_id, source_version, start, end)`. They
   read through one minimal store-neutral filtered row-read operation added
   to the ABC and implemented by both adapters, so the collection is never
   scanned and no retrieval-to-ingestion or adapter-specific import exists.
   Adjacency is keyed on `(source_id, source_version)` plus consecutive
   `source_chunk_index`, so chunks from two versions of one document are
   never neighbours. Rows without lineage are inert — skipped, never
   raised. This is strictly more queryable than the node-relationship
   store it replaces for this project's needs, and it cannot drift because
   it has no state of its own.

3. **Merging is contiguity-driven and lossless (design D3).** Two returned
   rows merge only when adjacent in the same source version. Because
   `chunk_overlap` is a token budget rather than a stored character
   boundary, the merge removes only the longest exact suffix/prefix text
   match whose tokenised size fits that budget; with no fitting match it
   concatenates without deletion. It never trims a configured number of
   characters and never fuzzy-matches, so unique text cannot be lost. The
   merged row carries the `chunk_id` of every constituent (`chunk_ids`),
   the lowest `source_chunk_index`, the best constituent score, and that
   constituent's `score_kind` — the merged row answers "how relevant is
   this passage", and averaging would penalise a merge. Merging is on by
   default: returning the same sentence twice is never what a caller
   wanted, and the merged row is a strict superset of each input's unique
   content. Neighbour expansion is off by default and bounded by a window
   (`expand_window`), because it adds evidence the ranker did not select —
   a retrieval-policy decision the caller should make.

Supporting decisions in the same change: assembly is a distinct module
(`core/retrieval/assembly.py`, design D4) rather than more code in
`search()`; `on_moved` is delete-then-ingest (design D5); stale-row
selection is store-filtered then attempt-compared in Python (design D6).

## Consequences

### Positive

- Sparse retrieval reflects writes made by any process against the same
  Lance data, with no inter-process signalling and no re-ingest required.
- The same sentence is no longer returned twice; a merged row's
  `chunk_ids` keep citations verifiable, because each id resolves to
  exactly one stored chunk.
- There is no second store to reconcile against the vector store, so the
  ADR-048 failure paths keep exactly one thing to verify.
- Lineage queries are available to any caller, not just assembly.

### Negative

- Chroma deployments keep the reduced same-process guarantee; this is
  logged once per collection rather than assumed silently.
- A caller that sets `expand_window` carelessly inflates its own context;
  the server does not budget tokens for the client.
- Merged rows change returned text, so the quality gate must be re-measured
  whenever the merge rules change.

### Neutral

- The OpenAPI `SearchResult` gains optional fields only (`chunk_ids`, plus
  diagnostics-only assembly markers); the required set is unchanged.
- Rows added purely by expansion carry no retrieval score, by design.
- No stored vector or row metadata changed; Lance tables gain one
  schema-metadata epoch when first written by this version.

## Alternatives Considered

| Option | Rejected because |
| --- | --- |
| Numeric Lance `table.version` alone | Overwrite and recreation restart the history at a previously cached value. |
| `versions()[0]["timestamp"]` as dataset identity | Old-version cleanup can prune the real genesis; reading history on cache validation is the wrong cost shape. |
| Tag version 1 | Prevents cleanup of historical data and still needs history reads. |
| Row-count probe | Misses delete-plus-insert mutations of equal size. |
| Sidecar marker or control table | Creates a second failure-consistency problem, rejected elsewhere in this architecture. |
| Switch the default sparse backend to native FTS | Experiment 19 measured it at 138.7× BM25's warm p50; it failed the latency gate. |
| Adopt `PrevNextNodePostprocessor` / `AutoMergingRetriever` | Both require a `BaseDocumentStore` constructor field, i.e. persisting a second store. |
| Persist a document store | Every failure-safe replacement path acquires a second store to reconcile; a half-failed write can leave the two stores disagreeing. The `add-ingestion-change-detection` D2 precedent rejected the same shape for change-detection state. |
| Near-duplicate removal by text similarity | Needs a threshold, and a threshold needs calibration; contiguity is exact and free. |
| Drop the lower-scoring duplicate | Loses the dropped chunk's unique tail; merging keeps everything. |

## References

- OpenSpec change:
  `openspec/changes/fix-retrieval-freshness-and-context-assembly-2/`
  (design decisions D1–D6; capability specs `chunk-lineage-navigation`,
  `retrieval-context-assembly`, `vectordb-abstraction`,
  `hybrid-retrieval`)
- Second-store precedent:
  `openspec/changes/archive/2026-08-15-add-ingestion-change-detection/design.md`
  decision D2 (hash storage on chunk metadata, sidecar rejected)
- Contract owners: `src/rag_mcp/core/vectordb/base.py`
  (`get_data_version`, filtered row reads), `src/rag_mcp/core/vectordb/lancedb.py`
  (dataset epoch), `src/rag_mcp/core/retrieval/lineage.py`,
  `src/rag_mcp/core/retrieval/assembly.py`,
  `src/rag_mcp/core/retrieval/sparse.py` (tagged validity token)
- Quality-gate evidence: commit `996d105` — after assembly, Tier 1
  Recall@10 1.0 and MRR@10 1.0 at floor; Tier 2 (`qwen3-embedding:0.6b`,
  Ollama 0.32.13) Recall@10 1.0 and MRR@10 1.0 against 0.97/0.97 floors;
  `tests/quality/baseline.json`
- Related decisions: ADR-048 (bounded failure-safe ingestion), ADR-052
  (stable source and chunk lineage), ADR-054 (native sparse backend, kept
  non-default), ADR-055 (embedding text contract)
