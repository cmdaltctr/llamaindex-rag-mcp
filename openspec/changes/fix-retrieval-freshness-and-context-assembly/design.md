# Design: fix-retrieval-freshness-and-context-assembly

## Context

Verified against `v3` at `c9d2906`.

- `BM25SparseRetriever._get_or_build_index` (`core/retrieval/sparse.py:237`)
  keys its cache on `(store.cache_identity, collection)` and compares
  `store.get_generation(collection)`.
- `LanceVectorStore._generations` (`core/vectordb/lancedb.py:99`) is an
  instance dict. `lance_fts.py`'s module docstring already states the counter
  is process-local and is used for the in-memory BM25 cache only.
- LanceDB exposes `table.version`, and ordinary commits advance it across
  store handles, but overwrite-based schema evolution and recreation restart
  the numeric history. `versions()[0]["timestamp"]` differs across recreation
  in a local experiment, but old-version cleanup can prune the original entry,
  so it is not a stable dataset identity.
- `search()` (`core/retrieval/pipeline.py:127`) ends with `results.sort(...)`,
  `results[:top_k]`, `_strip_internal_result_fields`.
- Every result row already carries `source_id`, `source_version`, `chunk_id`,
  `source_chunk_index`, `source_chunk_count` (`dense.py:90`), on both the
  dense and sparse paths.
- `matches_metadata_filter` (`core/retrieval/filters.py`) is the store-neutral
  predicate evaluator; `count_where`/`delete_where` accept the same shape.
- `daemon/watcher.py` subclasses `PatternMatchingEventHandler` and implements
  `on_created`, `on_modified`, `on_deleted` — not `on_moved`.
- `_stale_source_ids` (`core/ingestion/replacement.py:112`) iterates
  `store.iter_documents(collection)` for every replaced source.

## Goals / Non-Goals

**Goals**

- Sparse retrieval reflects writes made by any process against the same data.
- Provide the capability a document store would have provided — neighbour and
  span lookup — without adding a second store.
- Stop returning the same text twice.
- Keep the index consistent with the filesystem across renames.

**Non-Goals**

- Switching the default sparse backend. Experiment 19 settled that.
- MMR. It needs vectors returned from `query_dense`, widening the ABC. The
  redundancy MMR would partly mask is better removed at source by merging;
  measure after.
- Query transformation, answer synthesis, re-ranking or scoring changes.
- A document store. See D2.

## Decisions

### D1: Lance cache validity combines an OMRG epoch with table version

Add `get_data_version(collection) -> str | None` to the `VectorStore` ABC.
The public value is an opaque token. LanceDB implements it from:

```
(omrg_dataset_epoch, table.version)
```

`omrg_dataset_epoch` is a random UUID stored in the current table's schema
metadata through the existing Lance metadata/mixin seam. It is an identity for
one incarnation of the dataset:

- new table creation writes a new epoch;
- ordinary add, upsert and delete operations preserve it while
  `table.version` advances;
- delete/recreate and every `mode="overwrite"` rebuild write a new epoch,
  even when the numeric version restarts at a previously cached value;
- old-version cleanup and optimisation do not alter it because it lives in
  current schema metadata rather than version history.

A pre-existing table without the marker is not mutated by a read. Its
`get_data_version()` returns `None` until the next OMRG-controlled writer,
under the existing write lock, installs an epoch before its row mutation. The
transition from a tagged local fallback token to a tagged durable token is
itself cache invalidation. A table recreated by an external writer without the
marker likewise returns `None` and the reduced guarantee is reported rather
than inheriting an old identity.

The implementation must prove that a long-lived store handle observes a changed
epoch after another process rebuilds or recreates the table. If LanceDB caches
schema metadata on that handle, `get_data_version()` must use the supported
refresh/reopen path before reading it. Failure of this qualification blocks the
Lance durable-token implementation; it must not be hidden behind a TTL.

Chroma returns `None` where it cannot meet the guarantee. The BM25 cache uses
an explicitly tagged validity value—durable `(epoch, version)` or local
generation—so changing capability modes cannot compare equal accidentally.

Alternatives considered:

- *Numeric Lance table version alone* — ordinary commits advance it, but
  overwrite and recreation can restart the history at the cached number.
- *`versions()[0]["timestamp"]`* — recreation changes it, but pruning can
  remove the real genesis; reading history on cache validation is also the
  wrong cost shape.
- *Tag version 1* — prevents cleanup of historical data and still requires
  history/tag reads.
- *Row-count probe* — misses delete-plus-insert mutations of equal size.
- *Sidecar marker or control table* — creates a second failure-consistency
  problem rejected elsewhere in this architecture.
- *Switch the default to native FTS* — Experiment 19 rejected that default on
  the measured platform; revisit only if the current-schema epoch cannot be
  observed correctly across processes.

### D2: The docstore equivalent is a lineage navigator, not a document store

`core/retrieval/lineage.py` provides `neighbours(rows, window)`,
`span(source_id, start, end)` and `is_adjacent(a, b)` over the metadata
ingestion already persists. The `VectorStore` ABC gains one minimal filtered
row-read operation implemented by both adapters; lineage navigation and stale
selection use that store-neutral seam, never a retrieval-to-ingestion import
or a backend-specific branch.

Why not adopt LlamaIndex's `PrevNextNodePostprocessor` or
`AutoMergingRetriever` directly: both take a `BaseDocumentStore` as a required
constructor field. Adopting them means persisting a second store.

Why not persist a document store: the failure-safe replacement path
(`replacement.py`) writes under an attempt id, verifies the exact durable row
count, and only then deletes the previous version. With two stores, every one
of those five failure paths acquires a second thing to reconcile, and a
half-failed write can leave a chunk in one store and not the other. The
`add-ingestion-change-detection` design already rejected a sidecar state file
for precisely this reason (decision D2: "introduces a second store that can
drift"). A docstore is that sidecar with a nicer name.

What is actually lost by not having one, stated plainly: no `PARENT`/`CHILD`
hierarchy, and no exact full-document reconstruction (chunk overlap and
Markdown small-chunk dropping make reassembly approximate). Neither is needed
by anything in this change. If hierarchy is wanted later, the honest route is
`SentenceWindowNodeParser` plus `MetadataReplacementPostProcessor`, which
achieve parent context through **metadata** and therefore fit this
architecture without a second store.

Adjacency is keyed on `(source_id, source_version)`, not `source_id` alone, so
chunks from two versions of a document are never treated as neighbours.

### D3: Merging is contiguity-driven, not similarity-driven

Two rows merge when they are adjacent in the same source version. Because
`chunk_overlap` is a token budget rather than a stored character boundary, the
merge removes only the longest exact suffix/prefix text match whose tokenised
size is within that budget. If there is no exact match, it concatenates without
removal. It never trims a configured number of characters and never uses fuzzy
matching, so unique text cannot be lost.

Merging is on by default because returning the same sentence twice is never
what a caller wanted, and the merged row is a strict superset of each input's
unique content. Expansion is off by default because it adds evidence the
ranker did not select, which is a retrieval-policy decision the caller should
make.

Alternatives considered:

- *Near-duplicate removal by text similarity* — needs a threshold, and a
  threshold needs calibration. Contiguity is exact and free.
- *Drop the lower-scoring duplicate* — loses the unique tail of the dropped
  chunk. Merging keeps everything.

The merged row's score is the best constituent score rather than an average or
a sum: it answers "how relevant is this passage", and the best-matching part
is what made it relevant. Averaging would penalise a merge, creating a
perverse incentive against assembly.

### D4: Assembly is a distinct module, not more code in `search()`

`core/retrieval/assembly.py` takes the ranked rows plus resolved settings and
returns rows. `pipeline.py` calls it in one place, after truncation.
`pipeline.py` is at 441 lines against the project's 500-line ceiling, so this
also keeps that invariant satisfiable.

### D5: `on_moved` is delete-then-ingest, reusing both existing paths

`on_moved` reuses the existing delete and ingest paths, but deletion must
return an explicit success result. The destination ingest is scheduled only
after old-path cleanup succeeds; a failed cleanup is retried/reported and does
not silently fork the source under two path-derived identities. The
existing symlink-traversal guard already runs inside `_do_ingest`, so a move
whose destination resolves outside the watch root is rejected there.

Destination outside the tree: watchdog still delivers the event, and
`PatternMatchingEventHandler` matches on both paths; the ingest is skipped by
the existing traversal guard, leaving the delete — which is the correct
outcome.

### D6: Stale selection is store-filtered, then attempt-compared in Python

Select with the new filtered row-read operation on `{source_id: S}`, then compare
`source_attempt` in Python. This preserves the original reason for the Python
comparison — backends disagree on whether a missing metadata key satisfies
`$ne` — while bounding the read to one source's rows.

## Risks

| Risk | Mitigation |
| --- | --- |
| Merging changes returned text and moves quality-gate numbers | Re-measure Tier 1 and Tier 2; merged text is a superset of constituent content, so Recall must not fall. If it does, the merge implementation is wrong, not the floor |
| A caller parses result rows positionally and breaks on merged rows | Result rows are dicts with additive keys; merged rows add keys rather than removing them. The OpenAPI `SearchResult` gains optional fields only |
| A long-lived Lance handle caches schema metadata across another process's rebuild | The cross-process qualification must prove refresh/reopen exposes the new epoch; otherwise Lance returns `None` and this part of the change remains blocked |
| Chroma users silently keep the old behaviour | The fallback logs once per collection naming the reduced guarantee, so it is visible rather than assumed |
| Expansion inflates context and costs the caller tokens | Off by default, bounded by window, and reported in diagnostics |
