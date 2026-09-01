# Tasks: fix-retrieval-freshness-and-context-assembly

Groups 1–3 are independent of groups 4–6 and can land separately if the change
is split during review. No re-ingest is required by anything here.

## 1. Red-first coverage for the current defects

- [ ] 1.1 Add a test using two `LanceVectorStore` instances over one database:
  build a BM25 cache on instance B, mutate through instance A, assert B's next
  hybrid query returns the new rows. Confirm it FAILS today.
- [ ] 1.2 Add a test asserting that two adjacent chunks returned by one search
  do not repeat the overlap text. Confirm it FAILS today.
- [ ] 1.3 Add a watcher test for a rename inside the watch tree asserting the
  old path's chunks are gone and the new path's are present. Confirm it FAILS
  today.
- [ ] 1.4 Add a test asserting stale selection reads a bounded number of rows
  (spy on `iter_documents`) when replacing one source in a many-source
  collection. Confirm it FAILS today.

## 2. Durable data version

- [ ] 2.1 Add `get_data_version(collection_name) -> str | None` to
  `core/vectordb/base.py` with a default returning `None`.
- [ ] 2.2 Implement it in `LanceVectorStore` as `str(table.version)`; return
  `None` for an absent table.
- [ ] 2.3 Leave `ChromaVectorStore` on the default `None` and document why in
  the adapter docstring.
- [ ] 2.4 Add the method to the differential store-contract test suite so
  every registered store is checked.
- [ ] 2.5 Confirm the version advances after write, upsert, delete-where and
  delete-ids, and is stable without mutation.

## 3. BM25 invalidation

- [ ] 3.1 Change `_get_or_build_index` to resolve a validity token:
  `store.get_data_version(c)` when not `None`, else `store.get_generation(c)`.
- [ ] 3.2 Store the token on `_CachedBM25` in place of the bare generation.
- [ ] 3.3 Warn once per collection per process when falling back to the
  process-local counter, naming the reduced guarantee.
- [ ] 3.4 Verify 1.1 passes. Verify the existing store-isolation and
  invalidate-on-mutation tests still pass unchanged.
- [ ] 3.5 Confirm no change to the default sparse backend. Add a comment in
  `core/retrieval/settings.py` pointing at Experiment 19 so the `bm25` default
  is not "fixed" to `auto` by a future reader of the audit.

## 4. Lineage navigation (the docstore equivalent)

- [ ] 4.1 Create `core/retrieval/lineage.py` with `is_adjacent(a, b)`,
  `neighbours(rows, store, collection, window)` and
  `span(store, collection, source_id, source_version, start, end)`.
- [ ] 4.2 Key adjacency on `(source_id, source_version)` and consecutive
  `source_chunk_index`; clamp to `[0, source_chunk_count)`.
- [ ] 4.3 Treat rows lacking lineage as inert — skip, never raise.
- [ ] 4.4 Read through the store's metadata-filter contract, bounded by the
  requested window; never scan the collection.
- [ ] 4.5 Unit tests for all `chunk-lineage-navigation` scenarios, including
  the cross-source and cross-version negative cases.

## 5. Context assembly

- [ ] 5.1 Create `core/retrieval/assembly.py` with
  `assemble(rows, *, chunk_overlap, expand_window, store, collection)`.
- [ ] 5.2 Implement contiguity-driven merging: union the text with the
  configured overlap present once; carry constituent `chunk_id` values, lowest
  `source_chunk_index`, best score and that constituent's `score_kind`.
- [ ] 5.3 Implement bounded, opt-in neighbour expansion using group 4; mark
  expanded rows and give them no retrieval score.
- [ ] 5.4 Compose expansion with merging (expanded neighbours of a retrieved
  chunk merge into it).
- [ ] 5.5 Guarantee no chunk's unique text is lost, and that retrieved rows are
  never dropped to honour `top_k` after expansion.
- [ ] 5.6 Call `assemble` from `pipeline.py` once, after truncation, before
  diagnostics attachment.
- [ ] 5.7 Add an `expand_window` parameter to `search()`, defaulting to 0, and
  surface it on the MCP tool and the CLI.
- [ ] 5.8 Add `assembly_seconds` to the timing report; add merge/expansion
  markers to diagnostics rows only.
- [ ] 5.9 Extend `_strip_internal_result_fields` so assembly-internal fields
  are stripped from public results.
- [ ] 5.10 Verify 1.2 passes and every `retrieval-context-assembly` scenario
  is covered.
- [ ] 5.11 Confirm `pipeline.py` stays under the 500-line ceiling.

## 6. Watcher move handling and bounded stale selection

- [ ] 6.1 Add `on_moved` to `DocumentIngestHandler`: `_do_delete(src_path)`
  then `_schedule_ingest(dest_path)`.
- [ ] 6.2 Confirm the existing traversal guard rejects a destination outside
  the watch root, leaving the delete applied.
- [ ] 6.3 Clear the moved path's hash-cache entry so a later re-creation at the
  old path is not skipped as unchanged.
- [ ] 6.4 Verify 1.3 passes and all four move scenarios are covered.
- [ ] 6.5 Rewrite `_stale_source_ids` to read only rows matching
  `{source_id: S}` through the store filter, keeping the Python-side
  `source_attempt` comparison and its existing comment about missing-key
  inequality.
- [ ] 6.6 Verify 1.4 passes and the five Stage-3 failure-path tests still pass.

## 7. Contract and gate

- [ ] 7.1 Add the optional merge/expansion fields to `SearchResult` in
  `transports/api/openapi.yaml`.
- [ ] 7.2 Re-run Tier 1; re-run Tier 2 against real Ollama; commit the
  re-measured baseline. Recall MUST NOT regress — merged text is a superset,
  so a regression means the merge is wrong, not the floor.
- [ ] 7.3 `uv run pytest -m "not slow" --cov=rag_mcp` — green, floors held.
- [ ] 7.4 `uv run lint-imports` — clean, no stale ignores.
- [ ] 7.5 `openspec validate fix-retrieval-freshness-and-context-assembly --strict`.

## 8. Documentation

- [ ] 8.1 Document the assembly stage in `docs/guides/mcp-tools.md`, stating
  what callers now get: overlap removed by default, expansion available, and
  that the client still owns final context budgeting.
- [ ] 8.2 Update `AGENTS.md` gotcha list: BM25 cache validity is now durable
  where the store supports it.
- [ ] 8.3 Write ADR: "Lineage navigation replaces a document store" recording
  D1, D2 and D3, and pointing at the change-detection D2 precedent.
