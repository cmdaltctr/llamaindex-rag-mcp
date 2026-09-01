# Tasks: fix-retrieval-freshness-and-context-assembly

Groups 1–3 are independent of groups 4–6 and can land separately if the change
is split during review. No re-ingest is required by anything here.

## 1. Red-first coverage for the current defects

- [ ] 1.1 Add unit and subprocess tests using long-lived Lance store handles:
  build a BM25 cache in reader B, then have writer A perform an ordinary
  mutation, an overwrite rebuild, and a delete/recreate reaching the same
  numeric version. Assert B observes a different token and its next hybrid
  query reflects the new rows without restarting. Confirm they FAIL today.
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
- [ ] 2.2 Add an `omrg_dataset_epoch` UUID to current Lance table schema
  metadata through the existing metadata/mixin seam. Create a new epoch for
  table creation, delete/recreate and every `mode="overwrite"` rebuild;
  preserve it for ordinary writes. Do not use version history, timestamps,
  tags, row counts or a sidecar marker. Keep `lancedb.py` at most 500 lines.
- [ ] 2.3 Leave `ChromaVectorStore` on the default `None` and document why in
  the adapter docstring.
- [ ] 2.4 Add the method to the differential store-contract test suite so
  every registered store is checked.
- [ ] 2.5 Implement the Lance token as a tagged durable value containing
  `(omrg_dataset_epoch, table.version)`. Confirm ordinary write, upsert,
  delete-where and delete-ids preserve the epoch and change the version;
  confirm overwrite and delete/recreate replace the epoch even when the
  numeric version collides. Prove a long-lived reader observes the new epoch
  after a separate-process refresh/reopen; if it cannot, stop rather than add
  a TTL workaround.
- [ ] 2.6 For an existing Lance table without an epoch, return `None` on reads;
  under the existing write lock, install an epoch before its next
  OMRG-controlled row mutation. Confirm cleanup/optimisation preserves the
  current epoch and that an external recreation without the marker returns
  `None` rather than inheriting a cached identity.
- [ ] 2.7 Add a store-neutral filtered row-read method to the ABC and both
  adapters, with differential tests for equality filters, absence and no
  matches. Push filtering into each backend.

## 3. BM25 invalidation

- [ ] 3.1 Change `_get_or_build_index` to resolve an explicitly tagged
  validity token: durable `(epoch, version)` when `get_data_version(c)` is
  available, else tagged local `store.get_generation(c)`. A transition between
  modes MUST compare unequal.
- [ ] 3.2 Store the token on `_CachedBM25` in place of the bare generation.
- [ ] 3.3 Warn once per collection per process when falling back to the
  process-local counter, naming the reduced guarantee.
- [ ] 3.4 Read the validity token before fetching BM25 rows and again before
  publishing the cache. Publish only when the tagged tokens match; otherwise
  discard and retry within a bounded policy. Test a separate-process mutation
  and recreation during the build.
- [ ] 3.5 Verify 1.1 passes. Verify the existing store-isolation and
  invalidate-on-mutation tests still pass unchanged.
- [ ] 3.6 Confirm no change to the default sparse backend. Add a comment in
  `core/retrieval/settings.py` pointing at Experiment 19 so the `bm25` default
  is not "fixed" to `auto` by a future reader of the audit.

## 4. Lineage navigation (the docstore equivalent)

- [ ] 4.1 Create `core/retrieval/lineage.py` with `is_adjacent(a, b)`,
  `neighbours(rows, store, collection, window)` and
  `span(store, collection, source_id, source_version, start, end)`.
- [ ] 4.2 Key adjacency on `(source_id, source_version)` and consecutive
  `source_chunk_index`; clamp to `[0, source_chunk_count)`.
- [ ] 4.3 Treat rows lacking lineage as inert — skip, never raise.
- [ ] 4.4 Read through the new store-neutral filtered row-read contract,
  bounded by the requested window; never scan the collection and never import
  a concrete adapter from retrieval.
- [ ] 4.5 Unit tests for all `chunk-lineage-navigation` scenarios, including
  the cross-source and cross-version negative cases.

## 5. Context assembly

- [ ] 5.1 Create `core/retrieval/assembly.py` with
  `assemble(rows, *, chunk_overlap, expand_window, store, collection)`.
- [ ] 5.2 Implement contiguity-driven, lossless merging: remove only the
  longest exact suffix/prefix match within the configured token budget, else
  concatenate without deletion. Carry constituent `chunk_id` values, lowest
  `source_chunk_index`, best score and that constituent's `score_kind`; test
  repeated phrases, heading prepends, whitespace differences and no match.
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
- [ ] 5.11 Confirm `pipeline.py` and `lancedb.py` stay at or below the
  500-line ceiling; use cohesive existing/new mixins rather than adding
  methods directly to the already-full adapter.

## 6. Watcher move handling and bounded stale selection

- [ ] 6.1 Make `_do_delete` return an explicit result and add `on_moved` to
  `DocumentIngestHandler`: schedule destination ingest only after old-path
  cleanup succeeds; on failure report and retry/defer rather than forking.
- [ ] 6.2 Confirm the existing traversal guard rejects a destination outside
  the watch root, leaving the delete applied.
- [ ] 6.3 Clear the moved path's hash-cache entry so a later re-creation at the
  old path is not skipped as unchanged.
- [ ] 6.4 Verify 1.3 passes and all move scenarios are covered, including a
  deletion failure that must not ingest the destination.
- [ ] 6.5 Rewrite `_stale_source_ids` to read only rows matching
  `{source_id: S}` through the new store-neutral filtered read, keeping the Python-side
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
