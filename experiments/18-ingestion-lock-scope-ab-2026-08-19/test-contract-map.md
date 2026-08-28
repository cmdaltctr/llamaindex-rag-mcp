# Test Contract Map — Ingestion Lock Scope (Stage 3B input)

One deliverable from the test-contract-mapper worker. Read-only inventory of every
existing test that pins the current `write_lock` / generation / replacement behaviour,
so a narrow-lock candidate knows exactly what it must keep green.

Scope searched: `tests/` including `tests/unit/`, for `write_lock`,
`get_embed_semaphore`, `_replace_sync`, `replace_source_nodes_async`,
`upsert_precomputed`, `delete_ids`, `bump_generation`, `get_generation`,
`source_attempt`, `source_version`, `stamp_source_attempt`, `IngestionStageError`,
`embed_and_write_async`, `remove_document`, `remove_by_metadata`, `iter_documents`,
`count_where`, sequential/skip semantics, `metadata_degraded`, and
`shutdown_requested`.

Headline finding: **no existing test asserts that embedding happens inside the lock**.
The only test that materially breaks under a narrow lock is
`test_partial_store_write_preserves_old_version_and_recovers`, because its failure
injection targets `store.write_nodes` and a narrow-lock write path that calls
`upsert_precomputed` would never trigger it (it then fails loudly, not silently).

---

## 1. Contract inventory

### tests/test_ingestion_stage3.py (fixture `stage3_store`: parametrised `chroma` | `lancedb` via `set_default_store`; chroma arm = conftest EphemeralClient)

| Test | Contract pinned (from the actual assertions) |
|---|---|
| `test_repeated_ingest_skips_complete_matching_version` | Same bytes + same index identity: second run `files_indexed == 0`, `files_skipped_unchanged == 1`, `chunks_created == 0`, `chunks_removed == 0`; `store.count(coll) == first["chunks_created"]`. Unchanged skip requires the *complete* version match (`is_complete_current_version` counts must agree incl. `SOURCE_CHUNK_COUNT_KEY == total`). |
| `test_content_edit_replaces_only_old_source_version` | Changed bytes: `chunks_removed == first["chunks_created"]`; every stored text for the source excludes "version alpha" and includes "version beta changed". Old rows deleted only after new verified. |
| `test_index_identity_change_forces_reprocessing` (params: embed-model change, parser-selector change) | Embedding model or `pdf_reader` selector change invalidates skip: `files_indexed == 1`, `files_skipped_unchanged == 0`, `chunks_removed == first chunks_created`. |
| `test_chunk_setting_change_forces_reprocessing` | Per-call `chunk_size`/`chunk_overlap` overrides participate in identity: same reprocess arithmetic as above. |
| `test_parse_failure_preserves_last_searchable_version` | `pipeline.read_and_chunk_file_async` raising → run `status == "error"`; old sentinel texts survive, new sentinel absent. (Patch target: `pipeline.read_and_chunk_file_async`.) |
| `test_embedding_failure_preserves_last_searchable_version` | `replacement._embed_missing_nodes` raising `RuntimeError` → `status == "error"`, `error_type == "embedding"`; old rows searchable, no new rows. (Patch target: `replacement._embed_missing_nodes` — gotcha 8b.) |
| `test_partial_store_write_preserves_old_version_and_recovers` | `store.write_nodes` writing 1 node then raising → `status == "error"`, old sentinel survives; after restoring `write_nodes`, retry: `status == "ok"`, old gone, new present. Pins: partial candidate + old rows coexist detectably and a retry converges. |
| `test_cleanup_failure_with_old_and_new_versions_recovers` | `store.delete_ids` raising → `status == "error"` with old AND new sentinels coexisting (verified new kept); retry with restored `delete_ids`: `ok`, old gone. |
| `test_generated_corpus_retains_only_one_source_node_set` (params: 5, 40 files) | Peak live nodes `max_alive == node_count` (exactly one file's node set) and `alive == 0` after the run. Fakes `pipeline.replace_source_nodes_async` returning `SimpleNamespace(chunks_written, chunks_removed=0, timings)` whose `timings.as_dict()` returns the four `WriteTimings` keys. |
| `test_ingestion_exposes_stage_timings_and_peak_rss` | `result["timings"]` contains all seven keys (`change_detection_seconds`, `parse_chunk_seconds`, `embedding_seconds`, `store_write_seconds`, `lock_wait_seconds`, `cleanup_seconds`, `total_seconds`), each `>= 0.0`; `file_details[0]["timings"]["total_seconds"] >= 0.0`; `peak_rss_bytes` is `None` or `> 0`. |

### tests/test_ingestion_stage3_legacy.py (fixture `legacy_store`: chroma | lancedb)

| Test | Contract pinned |
|---|---|
| `test_legacy_row_without_attempt_is_replaced_by_id_once` | Pre-Stage-3 row (no `source_attempt`) is stale by the Python-side `_stale_source_ids` scan (missing key ≠ current attempt). One successful replacement performs exactly two store mutations: `get_generation == generation_before + 2` (candidate write bump + `delete_ids` bump); `chunks_removed == 1`; all surviving rows carry truthy `source_attempt`. Also pins: legacy seed `write_nodes` sets generation to 1. |

### tests/test_ingestion_stage3_runtime_identity.py

| Test | Contract pinned |
|---|---|
| `test_index_identity_tracks_actual_process_embedder` | `build_index_identity(...)` values differ when `source_state._runtime_embedding_identity` returns a different class/model. Process-global embedder is part of index identity. |

### tests/test_ingestion_parallel.py

| Test | Contract pinned |
|---|---|
| `TestSequentialIngestPath::test_directory_ingest` / `test_single_file_ingest` | Sequential ingest: `status == "ok"`, `files_indexed > 0`, `chunks_created > 0`. |
| `TestSequentialIngestPath::test_repeated_ingest_skips_unchanged_files` | Second run: `files_indexed == 0`, `files_skipped_unchanged == r1["files_indexed"]`, `chunks_created == 0`, `chunks_removed == 0`. |
| `TestErrorIsolation::test_corrupt_file_skipped` | Corrupt PDF among good files: overall `status == "ok"`, `files_indexed >= 1` (per-file isolation). |
| `TestErrorIsolation::test_nonexistent_path_returns_error` | `status == "error"`, "not found" in message. |
| `TestConcurrencyPrimitives::test_concurrent_write_lock_serialises` | The `_state.write_lock` object itself: `max_concurrent == 1` across 4 threads. Pins the primitive, not its scope of use. |
| `TestConcurrencyPrimitives::test_embed_semaphore_limits_concurrency` | `get_embed_semaphore(2)` caps concurrent holders at 2. |
| `TestConcurrencyPrimitives::test_parallel_shutdown_early_exit` | Shutdown set at `progress_callback(phase == "read", current >= 2)` mid-run → `files_indexed < 5`; `shutdown_requested.clear()` in `finally`. |

### tests/test_async_ingest_responsiveness.py

| Test | Contract pinned |
|---|---|
| `test_search_responsive_during_inflight_ingest`, `test_list_collections_responds_during_ingest` | Event loop answers concurrent MCP calls while ingest is paused inside a patched `pipeline.read_and_chunk_file_async` (chunk-size change defeats the unchanged-skip gate); ingest task must not complete while paused. Pins loop yield during parse, not lock scope. |
| `test_async_search_offloads_blocking_retrieval` | Slow sync search runs in a worker, not on the loop. |
| `test_blocking_call_causes_responsiveness_failure` | A `time.sleep(2)` inserted in the async parse path makes total elapsed `> 2.0`s (the safety net proves the suite can detect blocking). |
| `test_search_responsive_during_blocking_splitter` | A slow `SentenceSplitter.get_nodes_from_documents` (threading.Event gated) does not stall a concurrent search. |

### tests/test_vectordb_contract.py (fixture `store`: chroma EphemeralClient | lancedb under `tmp_path`)

| Test | Contract pinned |
|---|---|
| `TestABCCompliance::test_all_abstract_methods_implemented` | Both backends implement the 15 abstract methods (`write_nodes`, `count_where`, `delete_where`, `bump_generation`, `get_generation`, `iter_documents`, …). |
| `TestWriteAndQuery::test_write_nodes_then_query` | `write_nodes` then `query_dense` returns rows with `score_kind == "dense_similarity_v1"`, `0.0 < score <= 1.0`, no `distance` key. |
| `TestWriteAndQuery::test_precomputed_vectors_have_cross_store_semantic_score_parity` | `upsert_precomputed` rows rank `["exact", "near", "far"]` for `[1.0, 0.0]`, top score `approx(1.0)`, monotonic descending, same `score_kind` on both stores. |
| `TestCount::test_count_where` and `test_missing_field_filter_semantics_match_chroma` | `count_where` equality/`$ne`/`$in`/`$nin` semantics identical on both backends, incl. keys absent from rows and absent from schema. Load-bearing for `_stale_source_ids` correctness (it avoids `$ne` for this reason). |
| `TestDelete::test_delete_where` / `test_delete_where_empty_filter_rejected` | Filter delete removes matching rows; empty `{}` filter raises `ValueError` and deletes nothing. |
| `TestGenerationCounter::test_initial_generation_zero` / `test_bump_advances_counter` / `test_generations_are_per_collection` | Generation starts 0, `bump_generation` increments by exactly 1, counters are per-collection. |
| `TestGenerationCounter::test_upsert_precomputed_advances_generation` | A direct `upsert_precomputed` call advances generation 0 → 1. **This is the load-bearing pin for a narrow-lock write path built on `upsert_precomputed`.** |
| `TestGenerationCounter::test_each_successful_mutation_advances_exactly_once` | `write_nodes` → 1, `delete_where` → 2, `delete_collection` → 3: each successful mutation bumps exactly once. |
| `TestGenerationCounter::test_pipeline_mutations_do_not_add_caller_owned_bumps` | `writer.embed_and_write_async` then `writer.remove_document`: generation 1 then 2; orchestration adds no caller-owned `bump_generation`. |
| `TestDimensionLocking::test_dimension_locked_on_first_write` | Dimension is locked at first write; mismatched-dimension `write_nodes` raises. (A narrow-lock `upsert_precomputed` path must respect the same lock.) |
| `TestMissingCollection` (7 tests) | Missing collections: `count`/`count_where` → 0, `delete_where` no error, iterators/query empty, metadata `None`. |

### tests/test_hybrid_retrieval.py (generation invalidation, BM25 cache)

| Test | Contract pinned |
|---|---|
| `test_bm25_reuses_cached_index_when_generation_is_unchanged` | Equal generation between queries → one store scan (`get_calls == 1`). |
| `test_bm25_rebuilds_when_generation_advances` | `bump_generation` → second scan; new row found. |
| `test_remove_document_generation_rebuild_excludes_deleted_chunk` | Delete + bump → rebuild; cached entry records `generation == 1`. |
| `test_bm25_cache_namespaces_same_collection_by_store` | Equal collection/generation in two stores cannot cross-contaminate. |
| `test_remove_collection_generation_invalidates_cache` | Collection-drop bump invalidates the cached BM25 index. |

These pin the downstream consequence of every replacement mutation: the BM25 cache
is keyed on `(store, collection, generation)`, so the exactly-once bump arithmetic
in sections above is what keeps sparse retrieval correct.

### tests/test_signal_handling.py

| Test | Contract pinned |
|---|---|
| `test_shutdown_flag_cleared_on_new_ingest` | `ingest_path_async` clears `shutdown_requested` at entry; a pre-set flag does not fail the run. |
| `test_shutdown_flag_stops_sequential_early` | Shutdown set after first source completes → `files_indexed == 1` exactly (per-source commit, ADR-048; the completed source stays written). |
| `TestEmbedAndWriteShutdown::test_returns_zero_when_shutdown_set`, `test_embed_and_write_for_empty_nodes`, `TestLockRecheckOnShutdown::test_embed_and_write_bails_inside_lock` | `writer.embed_and_write_async` returns 0 when shutdown set or nodes empty; the in-lock recheck path returns 0 (indistinguishable from the pre-lock check in this test, but pins the outcome contract). |
| `TestPathResolution` (2 tests) | `~` expansion and relative-path resolution produce `ok` runs. |

### tests/test_ingestion.py (writer-level deletion + reingestion upsert)

| Test | Contract pinned |
|---|---|
| `TestIngestPathValidation` (3 tests) | Non-existent path → error "not found"; unsupported extension → error "unsupported"; empty dir → `ok` with zero counts. |
| `TestCollectionRouting` (3 tests) | `collection_name` routing isolates collections; default is `"documents"`. |
| `TestDocumentDeletion::test_remove_document_deletes_existing_chunks` | `remove_document` → `status ok`, `chunks_removed == total_before`, store empty after. |
| `TestDocumentDeletion::test_remove_document_non_existent_file` / `_non_existent_collection` | Missing file (collection exists) → `ok`, `chunks_removed == 0` (idempotent); missing collection → `error` "does not exist". |
| `TestDocumentDeletion::test_remove_by_metadata_*` (3 tests) | Filter delete removes matching rows; empty filter → `error` "empty"; missing collection → `error`. |
| `TestDocumentDeletion::test_remove_collection_*` (2 tests) | Drop collection → `ok`, gone from `list_collections`; missing → `error`. |
| `TestDocumentDeletion::test_reingestion_replaces_chunks` | Modified re-ingest: total after == `chunks_created` of run 2 (no duplicates) and `chunks_removed == chunks1`. |
| `TestDocumentDeletion::test_reingestion_first_time_no_removed` | First ingest: `chunks_removed == 0`. |
| `TestListDocuments::test_list_documents_scans_multiple_metadata_pages` | Chunk counts span metadata pages (`chroma_scan_page_size=2` injected). |

### tests/test_metadata_degradation.py (seam-relevant subset)

| Test | Contract pinned |
|---|---|
| `TestMetadataDegradationAggregation::test_no_degradation_reports_zero` / `test_one_file_degrades` | `metadata_degraded` count and per-file flag are computed at observation time. Fakes `pipeline.read_and_chunk_file_async` (returns `_ChunkResult` with real `TextNode`s) and `pipeline.replace_source_nodes_async` (async stand-in returning an object with `chunks_written`, `chunks_removed`, `source_attempt`, `timings=WriteTimings()`). |
| `TestMetadataDegradationAggregation::test_embedding_error_preserves_degradation_count` | `_embed_missing_nodes` raising → run `status == "error"`, `error_type == "embedding"`, and `metadata_degraded == 1` survives in the aggregate. (Patch target: `rag_mcp.core.ingestion.replacement._embed_missing_nodes`.) |
| `test_path_not_found_includes_zero_degraded` | Every result dict, even early exits, carries `metadata_degraded: 0`. |
| `TestMetadataShapeUnchanged` | Degraded extraction keeps `category: "uncategorised"` with no extra keys in node metadata. |

### tests/unit/test_type_aware_ingestion.py (seam-relevant)

| Test | Contract pinned |
|---|---|
| `TestBinarySkip::test_binary_file_skipped` | Magika `binary/*` files get `status == "skipped"` details; the code file beside it still indexes. Patches `rag_mcp.integrations.magika._is_magika_available=False`, `codebase_map.detect_file_types`, `pipeline.gather_supported_files`, and `pipeline.replace_source_nodes_async` (AsyncMock returning a `SimpleNamespace` with a real `WriteTimings()`). |
| `TestContentTypeDispatch` / `TestCodeSplitterDispatch` / `TestConfigFileChunking` | `content_type` metadata drives chunking dispatch (code/config/fallback/precedence). Upstream of the lock; unaffected. |

### tests/test_watcher.py (seam-relevant)

| Test | Contract pinned |
|---|---|
| `TestIngestPathAllFilesFail::test_all_files_fail_returns_file_error_type`, `test_no_files_returns_ok` | All-fail → `status == "error"`, `error_type == "file"`; no files → `ok`. |
| `TestIngestPathAllFilesFail::test_connection_error_type` | `_embed_missing_nodes` raising `ConnectionError` → `error_type == "connection"` (ConnectionError passes through un-wrapped). |
| `TestIngestPathAllFilesFail::test_embedding_error_type` | `_embed_missing_nodes` raising `RuntimeError` → `error_type == "embedding"`. |
| `TestShutdownRequestedBypass` (2 tests) | Daemon watcher's own `handler._shutdown_requested` skips `_schedule_ingest`/`_do_ingest`; `mock_ingest.assert_not_called()`. Daemon flag, not the ingestion `_state` event — out of lock scope. |
| Patch seam `_INGEST_PATH_TARGET = "rag_mcp.core.ingestion.ingest_path_async"` | Watcher tests patch the ingestion entry point, not the lock; any internal restructure is invisible here. |

### tests/test_lancedb_store.py, tests/test_chroma_cloud.py (upsert_precomputed seam coverage)

| Test | Contract pinned |
|---|---|
| `test_lancedb_store.py::test_bm25_cache_isolated_between_chroma_and_lance` | Same-named collection in two backends, both generation 1 via `upsert_precomputed`, sparse queries stay isolated. |
| Lance upsert behaviours: empty batch no-op (no table created), null-only metadata upgrades to string, `test_upsert_into_written_collection`, `test_upsert_precomputed_introduces_new_field` | `upsert_precomputed` on Lance: empty batch is a no-op; a later real write still creates a usable table; schema grows for new metadata keys; upserts merge into adapter-written tables. |
| `tests/test_chroma_cloud.py::test_upsert_writes_rows_and_stamps_identity`, `test_upsert_rejects_identity_mismatch` | Hosted store `upsert_precomputed` writes rows and enforces the embedding-identity triple. |
| `TestEmbeddingIdentity` (lancedb) | Identity triple round-trips across store instances; mismatched writes rejected. |

### tests/test_cli.py

| Test | Contract pinned |
|---|---|
| `test_delete_metadata_real_execution`, `test_delete_error_result_display` | CLI patch targets `rag_mcp.core.ingestion.remove_by_metadata` / `remove_document` — the package re-export seam, not `writer.py` directly. Unaffected by lock changes; listed so new tests follow the same re-export convention. |

### tests/test_precalibration_audit_regressions.py (source-inspection contracts adjacent to this work)

| Test | Contract pinned |
|---|---|
| `test_each_vector_store_mutation_owns_generation_invalidation` | `write_nodes`, `delete_where`, `delete_collection` on both stores contain `self.bump_generation` in their source. A narrow-lock refactor must not strip these bumps (it has no reason to). |
| `test_orchestration_does_not_duplicate_store_generation_bumps` | None of `writer.embed_and_write_async`, `remove_document`, `remove_by_metadata`, `remove_collection` contain `resolved_store.bump_generation`. **Red line for Stage 3B: `replacement.py` must equally rely on store-owned bumps, never add caller-owned ones.** |

---

## 2. Lock-sensitivity classification

Proposed Stage 3B shape (for classification): embed + `stamp_source_attempt` move
OUTSIDE the lock; inside the lock only the store mutation (via precomputed
embeddings / `upsert_precomputed`), durability verify (`count_where`), and stale
cleanup (`_stale_source_ids` + `delete_ids`).

### UNAFFECTED (design keeps green with zero edits)

- `tests/test_ingestion_stage3.py`: `test_repeated_ingest_skips_complete_matching_version`,
  `test_content_edit_replaces_only_old_source_version`,
  `test_index_identity_change_forces_reprocessing`,
  `test_chunk_setting_change_forces_reprocessing`,
  `test_parse_failure_preserves_last_searchable_version`,
  `test_embedding_failure_preserves_last_searchable_version` (embed failure before the
  lock trivially preserves old rows; patch target `replacement._embed_missing_nodes`
  must keep its name and module),
  `test_cleanup_failure_with_old_and_new_versions_recovers` (cleanup stays in the lock),
  `test_ingestion_exposes_stage_timings_and_peak_rss` (key presence + `>= 0.0` only;
  `lock_wait_seconds` shrinking to exclude embed time is not pinned anywhere).
- `tests/test_ingestion_stage3_legacy.py::test_legacy_row_without_attempt_is_replaced_by_id_once`
  — **load-bearing**: pins generation arithmetic write-bump + delete-bump = +2 and
  exactly-once per mutation. A narrow lock using `upsert_precomputed` (bumps once,
  pinned separately) + `delete_ids` (bumps once per non-empty) preserves it.
- `tests/test_ingestion_stage3_runtime_identity.py::test_index_identity_tracks_actual_process_embedder`.
- `tests/test_ingestion_parallel.py`: all of `TestSequentialIngestPath`,
  `TestErrorIsolation`, `TestConcurrencyPrimitives::test_concurrent_write_lock_serialises`
  (pins the lock object, not its scope — narrowing scope does not change `max_concurrent == 1`
  for holders), `test_embed_semaphore_limits_concurrency`,
  `test_parallel_shutdown_early_exit`.
- `tests/test_async_ingest_responsiveness.py`: all five — they pin event-loop yield
  during parse/splitter/search, which a narrow lock only improves.
- `tests/test_vectordb_contract.py`: all generation-counter tests, ABC compliance,
  precomputed score parity, count_where semantics, dimension locking, missing-collection
  behaviour. `test_upsert_precomputed_advances_generation` and
  `test_precomputed_vectors_have_cross_store_semantic_score_parity` become the
  load-bearing pins for the new in-lock write primitive.
- `tests/test_hybrid_retrieval.py`: all generation-invalidation tests (downstream
  consumers of the bump arithmetic; invariant is exactly-once bumps, unchanged).
- `tests/test_signal_handling.py`: all — shutdown clear-at-entry, per-source commit
  (`files_indexed == 1`), writer shutdown zeros, path resolution.
- `tests/test_ingestion.py`: all writer-deletion and reingestion-upsert contracts.
- `tests/test_metadata_degradation.py`: all four seam-relevant tests — the fake replaces
  `pipeline.replace_source_nodes_async` wholesale (orchestrator seam survives any
  internal lock restructure as long as the function name/signature/return shape stay),
  and the embed-failure test patches `_embed_missing_nodes` which remains the embed helper.
- `tests/unit/test_type_aware_ingestion.py::TestBinarySkip` and dispatch tests.
- `tests/test_watcher.py`: the four ingest-path tests (patch targets `pipeline.*`,
  `replacement._embed_missing_nodes`); the daemon-shutdown pair uses the watcher's own flag.
- `tests/test_lancedb_store.py`, `tests/test_chroma_cloud.py`: upsert/identity/cache-isolation tests.
- `tests/test_cli.py` delete tests (package re-export seam).
- `tests/test_precalibration_audit_regressions.py`: `test_each_vector_store_mutation_owns_generation_invalidation`
  and `test_orchestration_does_not_duplicate_store_generation_bumps` — provided Stage 3B
  neither strips store-owned bumps nor adds caller-owned ones (see §5 red lines).

### AFFECTED-but-adaptable

- `tests/test_ingestion_stage3.py::test_partial_store_write_preserves_old_version_and_recovers`
  — **the one mandatory adaptation**. Failure injection wraps `store.write_nodes`
  (write 1 node, then raise). If the in-lock write switches to `upsert_precomputed`,
  the injected failure never fires and the test fails loudly at
  `assert failed["status"] == "error"`. Adaptation: retarget the wrapper at
  `upsert_precomputed` (same partial-then-raise shape, same recovery assertions).
  The underlying contract — old rows survive a partial candidate, retry converges —
  is exactly what Stage 3B must preserve, so the test content survives; only the
  patch target moves.
- `tests/test_ingestion_stage3.py::test_generated_corpus_retains_only_one_source_node_set`
  — pins `max_alive == node_count` (exactly one file's nodes). The minimal narrow-lock
  (embed outside lock, still one source at a time in the sequential loop) keeps this
  green. It breaks only if Stage 3B additionally pipelines parse-next-while-writing,
  where the bound becomes two units; then relax to `<= 2 * node_count` as a conscious
  decision (and see §4 recommendation 6).
- Patch-target-sensitive but green as-is (listed here so nobody "fixes" them):
  `test_embedding_failure_preserves_last_searchable_version`,
  `test_metadata_degradation.py::test_embedding_error_preserves_degradation_count`,
  `test_watcher.py::test_connection_error_type` / `test_embedding_error_type` —
  all patch `rag_mcp.core.ingestion.replacement._embed_missing_nodes`. Keep that
  helper name and module as the single embed seam (gotcha 8b).

### WOULD-BREAK-BY-DESIGN

- **None found.** No test asserts that embedding happens inside `write_lock`, that the
  lock is held during embedding, that the embed semaphore is acquired during
  replacement under the lock, or any numeric `lock_wait_seconds` value that would
  include embedding time. The timing test asserts key presence and non-negativity only.
  No blocking-probe test wraps or monkeypatches `write_lock` around the replacement
  path (`test_concurrent_write_lock_serialises` exercises the bare primitive).

---

## 3. Seams a Stage 3B change would touch

| Seam (file :: symbol) | Role today | Existing tests exercising it |
|---|---|---|
| `src/rag_mcp/core/ingestion/replacement.py :: _replace_sync` (nested in `replace_source_nodes_async`) | Everything under `write_lock`: shutdown recheck, embed (under `get_embed_semaphore`), `stamp_source_attempt`, `write_nodes`, `count_where` verify, `_stale_source_ids` + `delete_ids`. The restructure site. | Indirectly via every stage3/legacy/parallel test; no test references `_replace_sync` by name. |
| `replacement.py :: _embed_missing_nodes` | Module-level embed helper; batch-embeds nodes missing `node.embedding`; raises on count mismatch. Moves outside the lock. | `test_embedding_failure_preserves_last_searchable_version`; `test_metadata_degradation.py::test_embedding_error_preserves_degradation_count`; `test_watcher.py::test_connection_error_type`, `test_embedding_error_type`. |
| `replacement.py :: replace_source_nodes_async` | Public async entry; early empty/shutdown return; `asyncio.to_thread(_replace_sync)`; progress callbacks. Keep name/signature/`ReplaceSourceOutcome` shape. | Orchestrator fakes: `test_generated_corpus_retains_only_one_source_node_set`, `test_metadata_degradation.py` (×2), `TestBinarySkip`. |
| `source_state.py :: stamp_source_attempt` (call site in `_replace_sync`) | Stamps `file_path` + `SOURCE_*` keys, sets `excluded_embed_metadata_keys`/`excluded_llm_metadata_keys`, rewrites `node.id_` to `sha256(file_path\0attempt\0index\0original_id)`. If moved before embedding, embed text parity must hold (exclusions apply). | `test_ingestion_stage3_legacy.py` (attempt stamped on all rows), stage3 edit/skip tests (identity keys survive). |
| `_state.py :: write_lock / get_embed_semaphore / shutdown_requested` | Process singletons. Narrow lock may add a second, narrower primitive or reuse `write_lock` for mutations only. | `test_concurrent_write_lock_serialises`, `test_embed_semaphore_limits_concurrency`, all shutdown tests. |
| `vectordb/base.py :: VectorStore.upsert_precomputed` (default raises `NotImplementedError`) | The precomputed-embedding write primitive; implementations: `chroma.py:186`, `lancedb.py:258`, hosted cloud store. Already bumps generation exactly once. | `test_upsert_precomputed_advances_generation`, `test_precomputed_vectors_have_cross_store_semantic_score_parity`, lancedb upsert behaviours, chroma cloud upsert tests. |
| `vectordb/base.py :: VectorStore.delete_ids` (default raises; impls in `paged.py:116` chroma mixin, `lance_paged.py:130`) | Empty list / absent collection = no-op (no bump); successful non-empty delete bumps once. | `test_ingestion_stage3_legacy.py` (+2 arithmetic), `test_cleanup_failure_with_old_and_new_versions_recovers` (raises propagate as `stale_cleanup`). Empty-list no-bump is **untested** (see §4.11). |
| `replacement.py :: _stale_source_ids` | Python-side bounded scan over `iter_documents`; missing `source_attempt` treated as stale (legacy rows). | Legacy test; edit-replacement test. |
| `store.write_nodes` / `store.count_where` / `store.iter_documents` | Write, verify, and scan operations used inside `_replace_sync`. | `test_vectordb_contract.py` (all), `test_partial_store_write...` (write_nodes), `TestCount`/missing-field semantics (count_where). |
| `writer.py :: embed_and_write_async / remove_document / remove_by_metadata / remove_collection` | Independent `write_lock` holders (deletions, legacy write path). **Design question for Stage 3B**: if replacement narrows its lock, writer deletions must still serialise against replacement mutations or a concurrent `remove_document` can interleave between verify and cleanup. | `test_vectordb_contract.py::test_pipeline_mutations_do_not_add_caller_owned_bumps`; `tests/test_ingestion.py` deletion suite; `tests/test_signal_handling.py` writer shutdown tests; audit `test_orchestration_does_not_duplicate_store_generation_bumps`. |
| `pipeline.py :: ingest_path_async` | Clears `shutdown_requested` at entry; sequential per-source loop; `del nodes` bounded-memory discipline; `_error_type` mapping (`IngestionStageError.stage` → public classes). | Every end-to-end test above; `test_shutdown_flag_cleared_on_new_ingest`, `test_shutdown_flag_stops_sequential_early`. |
| `pipeline.py` re-exports: `replace_source_nodes_async`, `read_and_chunk_file_async`, `gather_supported_files`, `get_default_store`, `is_complete_current_version` | The patch seams tests rely on (gotcha 8b: patch where the function lives for the *caller* — orchestrator fakes patch `pipeline.*`). | All fakes listed in §1. |

### Fixture/patch patterns to reuse in new regression tests

- `conftest.effective_settings(**overrides)` factory — flat (`top_k`) and dotted
  (`retrieval.top_k`) routing; unknown overrides raise `TypeError` (design D9).
  Ad-hoc scripts should follow ADR-037: construct
  `EffectiveSettings(metadata=MetadataBlock(extraction_mode="disabled"))` explicitly.
- Autouse fixtures already active per test: `_patch_chromadb` (shared EphemeralClient,
  `reset_default_store()`), `_install_default_effective_settings`
  (`extraction_mode="disabled"`, `pdf_reader="pypdf"`), `_patch_embed_model`
  (`MockEmbedding(embed_dim=384)` deterministic), `_isolate_env`, `_clear_registry_caches`.
- Store fixtures: `stage3_store` / `legacy_store` (parametrised chroma | lancedb,
  `set_default_store(LanceVectorStore(uri=str(tmp_path / ...)))` for the lance arm);
  `test_vectordb_contract.py::store` for direct store-level tests.
- Shutdown reset discipline: `try: ... finally: _shutdown_requested.clear()` (see
  `test_ingestion_parallel.py`, `test_signal_handling.py`). Note `ingest_path_async`
  clears the flag itself at entry.
- Failure-injection style: wrap the real method, mutate, raise
  (`partial_then_fail` in stage3), then restore via a second monkeypatch for the
  recovery half. Binary/degradation fakes: `patch("rag_mcp.core.ingestion.pipeline.replace_source_nodes_async", new_callable=AsyncMock, return_value=SimpleNamespace(..., timings=WriteTimings()))`
  — import `WriteTimings` from `replacement` inside the helper to avoid scoping bugs.
- 500-line ceiling: `tests/test_file_size_ceiling.py` fails any `src/rag_mcp/**.py`
  over 500 lines — constraint on wherever the new lock code lands, noted for the
  implementer.

---

## 4. New-test recommendations (write FIRST, before the narrow-lock implementation)

1. `test_narrow_lock_generation_exactly_once_per_replacement` — fresh source: one
   successful replacement advances generation exactly +1 (write bump, empty stale set,
   no delete bump); with a legacy row present: exactly +2. Guards the write→delete
   pair against double- or missed bumps when the write primitive changes.
2. `test_embed_failure_before_lock_leaves_old_rows_and_no_candidate` — embed step
   raising outside the lock: old rows intact, `error_type == "embedding"`, and zero
   rows carry the new `source_attempt` id (no half-stamped candidate can exist).
3. `test_store_write_failure_inside_lock_old_rows_survive_and_partial_candidate_detectable`
   — the retargeted `test_partial_store_write...`: wrap `upsert_precomputed`
   (partial-then-raise) inside the lock; old rows survive, partial candidate is
   distinguishable by attempt id, retry converges. Fails on any implementation that
   keeps embedding in the lock only by accident of the old injection point.
4. `test_verify_failure_preserves_old_and_new_for_retry` — `count_where` raising
   during the verify step → `status == "error"` (stage `store_verify` maps to public
   `error_type == "store"`), old + new coexist, retry converges. Currently untested
   for the replacement path.
5. `test_cleanup_failure_verified_new_and_old_coexist` — already exists
   (`test_cleanup_failure_with_old_and_new_versions_recovers`); listed as must-keep-green,
   do not weaken it.
6. `test_replacement_bounded_memory_at_most_two_units` — if (and only if) the design
   pipelines parse/embed of the next source while the previous writes, assert peak live
   nodes `<= 2 * node_count` and zero after; otherwise keep the existing one-unit
   `max_alive == node_count` pin green.
7. `test_concurrent_replacements_different_sources_same_collection_correct` — two
   sources replaced concurrently into one collection under the narrow lock: both
   verified (`SOURCE_CHUNK_COUNT` matches per source), no cross-source stale deletion,
   generation advanced exactly once per mutation, final texts contain both sources.
8. `test_shutdown_semantics_preserved_under_narrow_lock` — shutdown set while embedding
   (outside the lock): outcome is a 0-chunk result with no store mutation; shutdown set
   between embed and lock acquisition: in-lock recheck returns 0-chunk with
   `lock_wait_seconds >= 0` recorded and nothing written.
9. `test_stamp_before_embed_keeps_embed_text_parity` — with stamping moved before
   embedding, `node.get_content(metadata_mode=MetadataMode.EMBED)` excludes every
   `SOURCE_*` key, so identical content produces identical vectors to the old
   `write_nodes` path (MockEmbedding is text-deterministic — assert vector equality
   old-path vs new-path, and that a re-ingest still hits the unchanged skip).
10. `test_replacement_versus_remove_document_concurrency` — a `remove_document`
    (writer, holds the wide lock today) racing a replacement must not leave a
    half-replaced source or a missing generation bump; decides the writer-lock-sharing
    question empirically before the design is declared safe.
11. `test_delete_ids_empty_list_does_not_bump_generation` — pins the no-op half of the
    `delete_ids` contract (docstring promises it; nothing asserts it today).
12. `test_narrow_path_respects_dimension_lock` — a `upsert_precomputed`-based
    replacement into an existing collection must fail loudly on dimension mismatch,
    mirroring `TestDimensionLocking` for the new write primitive.

---

## 5. Stage 4 red lines

`tests/test_precalibration_audit_regressions.py` — the three deferred reds are:

- `test_experiment_10b_runner_contains_hybrid_and_dense_treatments` — AST-scans
  `experiments/10b-reranker-pool-size-corrected-2026-06-29/run_eval.py` for literal
  `hybrid`/`rerank` values.
- `test_experiment_13_threshold_cells_do_not_force_reranking` — AST-scans
  `experiments/13-hard-technical-threshold-calibration-2026-06-29/run_eval.py`.
- `test_experiment_14_build_path_reads_real_pdf_bytes` — string-scans
  `experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py`.

All three read experiment runner source files only. They import no ingestion module,
touch no lock, no store mutation, and no vector database. **Confirmed: they cannot be
affected by moving embedding outside the replacement lock.** Do not touch them; they
stay red until Stage 4 by design.

Two sibling tests in the same file do border this work and must stay green without
edit: `test_each_vector_store_mutation_owns_generation_invalidation` (source-inspects
`write_nodes`/`delete_where`/`delete_collection` for `self.bump_generation`) and
`test_orchestration_does_not_duplicate_store_generation_bumps` (asserts the writer
functions contain no `resolved_store.bump_generation`). A narrow-lock change satisfies
both by construction: rely on store-owned bumps, add none of its own.
