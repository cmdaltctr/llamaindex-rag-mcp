# Design: fix-retrieval-freshness-and-context-assembly

## Context

Verified against `v3` at `c9d2906`.

- `BM25SparseRetriever._get_or_build_index` (`core/retrieval/sparse.py:237`)
  keys its cache on `(store.cache_identity, collection)` and compares
  `store.get_generation(collection)`.
- `LanceVectorStore._generations` (`core/vectordb/lancedb.py:99`) is an
  instance dict. `lance_fts.py`'s module docstring already states the counter
  is process-local and is used for the in-memory BM25 cache only.
- LanceDB exposes `table.version` — durable, monotonic, and visible to any
  process opening the same database. Verified at runtime: two store handles
  over one database, `table.version` moved 1 → 2 across an out-of-process
  write while `get_generation` stayed at 0.
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

### D1: Cache validity uses a durable data version, with the counter as fallback

Add `get_data_version(collection) -> str | None` to the `VectorStore` ABC.
LanceDB returns `str(table.version)`; Chroma returns `None` (its Python client
exposes no durable version), and callers fall back to the process-local
counter with a one-shot warning naming the reduced guarantee.

The BM25 cache key becomes `(cache_identity, collection)` with validity token
`data_version if data_version is not None else generation`.

Alternatives considered:

- *Row-count probe* — cheap, but a delete-plus-insert of equal size is
  invisible. Silent staleness is exactly the bug being fixed.
- *A file watch on the database directory* — a second moving part, and
  LanceDB's on-disk layout is not a contract.
- *Switch the default to native FTS* — this was the audit's original
  suggestion and it is withdrawn. Experiment 19 pre-registered the comparison
  and native failed gate G3 at 138.7× BM25's warm p50, with a +0.00 pp quality
  delta. Fixing invalidation keeps BM25's latency advantage and fixes
  correctness; switching would trade a 138× latency regression for a bug fix
  that costs ten lines.

Keeping the process-local counter is deliberate: it is still the correct and
cheapest signal for same-process mutation, and it is what the existing
"advances exactly once per mutation" contract is written against.

### D2: The docstore equivalent is a lineage navigator, not a document store

`core/retrieval/lineage.py` provides `neighbours(rows, window)`,
`span(source_id, start, end)` and `is_adjacent(a, b)` over the metadata
ingestion already persists, using the existing metadata-filter contract.

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

Two rows merge when they are adjacent in the same source version. The overlap
removed is the chunker's configured `chunk_overlap`, which is known exactly —
no fuzzy matching, no similarity threshold, no tuning knob.

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

`on_moved` calls the existing `_do_delete(src_path)` and then the existing
`_schedule_ingest(dest_path)`. No new ingestion or deletion logic. The
existing symlink-traversal guard already runs inside `_do_ingest`, so a move
whose destination resolves outside the watch root is rejected there.

Destination outside the tree: watchdog still delivers the event, and
`PatternMatchingEventHandler` matches on both paths; the ingest is skipped by
the existing traversal guard, leaving the delete — which is the correct
outcome.

### D6: Stale selection is store-filtered, then attempt-compared in Python

Select with `count_where`/a scoped read on `{source_id: S}`, then compare
`source_attempt` in Python. This preserves the original reason for the Python
comparison — backends disagree on whether a missing metadata key satisfies
`$ne` — while bounding the read to one source's rows.

## Risks

| Risk | Mitigation |
| --- | --- |
| Merging changes returned text and moves quality-gate numbers | Re-measure Tier 1 and Tier 2; merged text is a superset of constituent content, so Recall must not fall. If it does, the merge implementation is wrong, not the floor |
| A caller parses result rows positionally and breaks on merged rows | Result rows are dicts with additive keys; merged rows add keys rather than removing them. The OpenAPI `SearchResult` gains optional fields only |
| `table.version` semantics change in a future LanceDB | The version read is behind the ABC and covered by the differential store-contract tests; a change surfaces there, not in retrieval |
| Chroma users silently keep the old behaviour | The fallback logs once per collection naming the reduced guarantee, so it is visible rather than assumed |
| Expansion inflates context and costs the caller tokens | Off by default, bounded by window, and reported in diagnostics |
