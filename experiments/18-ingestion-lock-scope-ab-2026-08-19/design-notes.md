# Ingestion Lock-Scope Design Survey (Stage 3B, task 3.6.2 pre-work)

Author: Dr Muhammad Aizat Bin Md Hawari
Date: 2026-08-19
Scope: read-only survey of the Stage 3A serialized replacement path against the
candidate lock-narrowing designs. Supports Experiment 18 (`18-ingestion-lock-scope-ab`).
Baseline: ADR-048 Accepted at `5fd97e7`; Stage 3B is optional and measurement-gated.

## 1. Current critical-section inventory

### 1.1 Stages inside the global `write_lock` (`replacement.py::_replace_sync`, lines 174-296)

Ordered sequence, with the timing counter that covers each stage:

| # | Stage | Code seam | Counter | Notes |
| --- | --- | --- | --- | --- |
| 1 | Lock acquisition | `with write_lock:` (line 176) | `lock_wait_seconds` | Timer starts *before* the `with`, read immediately after acquisition. Pure wait, excludes held time. |
| 2 | Shutdown re-check | line 178 | — (only `lock_wait_seconds` recorded) | Early return keeps lock hold near zero. |
| 3 | Embedding | `embedding_started` (186) → `with get_embed_semaphore(embed_concurrency)` (188) → `_embed_missing_nodes(nodes)` (194) | `embedding_seconds` | Timer **wraps semaphore acquisition**: embed-limiter wait pollutes this counter. Batch call via `LlamaIndexSettings.embed_model.get_text_embedding_batch`. |
| 4 | Shutdown re-check | line 204 | — | Prevents post-embed mutation after shutdown. |
| 5 | Attempt stamping + ID derivation | `stamp_source_attempt(...)` (215) | **Untimed** | Falls in the gap between `embedding_seconds` stop and `write_started` start. Stamps eight metadata keys and sets `node.id_ = sha256("{file_path}\0{attempt}\0{index}\0{original_id}")` (`source_state.py:251-253`). |
| 6 | Candidate store write | `write_started` (224) → `resolved_store.write_nodes(nodes, collection_name)` (226) | `store_write_seconds` | Covers **only** `write_nodes`. With Stage 3A pre-embedding this is adapter write, no embedding (see §2.1). |
| 7 | Durability verification | `count_where` with attempt + chunk-count filter (236-258) | **Untimed** | Falls in the gap between `store_write_seconds` stop and `cleanup_started` start. Its wall time is invisible to all four counters and only appears inside `total_seconds` residue. |
| 8 | Stale scan + delete | `cleanup_started` (260) → `_stale_source_ids` (bounded `iter_documents` scan, 262) → `delete_ids` (269) | `cleanup_seconds` | Covers both the paged Python-side scan and the ID deletion. Scan cost grows with collection size (ADR-048 negative consequence). |

**Measurement gap for Experiment 6**: stages 5 and 7 carry no counter. Any claim
that "store write dominates" or "verify dominates" is currently unattributable.
The A/B harness should add a `verify_seconds` (and optionally a stamp timing)
before comparing arms, or explicitly fold `count_where` into
`store_write_seconds` and state the fusion in the runtime manifest.

### 1.2 Every other code path acquiring the same process-global lock

`write_lock` is one `threading.Lock()` in `_state.py:18` (ADR-033-era process
singleton). All acquisition sites:

| Site | File:line | Lock covers |
| --- | --- | --- |
| `replace_source_nodes_async._replace_sync` | `replacement.py:176` | Embed + stamp + write + verify + stale delete (§1.1). |
| `embed_and_write_async._write_sync` | `writer.py:67` | Embed semaphore + `write_nodes`. Legacy single-shot path; after Stage 3A it has **no callers in `src/`** (exported API surface and tests only). |
| `remove_document` | `writer.py:190` | `delete_where` only. Note: `count_where` runs *outside* the lock (line 188), so the count/delete pair is already non-atomic against a concurrent replacement of the same file. Pre-existing; unchanged by every design below. |
| `remove_by_metadata` | `writer.py:250` | `delete_where` only; same outside-lock `count_where` shape. |
| `remove_collection` | `writer.py:288` | `delete_collection`. |

`delete_ids` implementations: Chroma via `PagedReadMixin` (`paged.py:116`),
LanceDB via `LancePagedReadMixin` (`lance_paged.py:130`). Both bump generation
exactly once on successful non-empty mutation.

### 1.3 Real in-process contention sources

The pipeline loop (`pipeline.py:182-332`) is a **sequential** per-file
`for` loop; single-stream ingestion never contends with itself. Contention
arises only from concurrent callers in one process:

1. **Watch daemon**: `DocumentIngestHandler` throttles with
   `BoundedSemaphore(MAX_CONCURRENT_INGESTS = 2)` (`watcher.py:37,92`) and each
   debounce thread runs `asyncio.run(ingest_path_async(...))`
   (`watcher.py:302`). Two single-file ingests can therefore hold
   `write_lock` waits against each other — the one genuine same-collection
   ingestion contention in production paths. `_do_delete` timer threads also
   call `remove_document` unthrottled (`watcher.py:155`).
2. **MCP server process**: concurrent tool calls (delete tool during an ingest
   tool) contend through `writer.py` removals vs `replacement.py`.

The daemon is a standalone CLI process (`rag-mcp watch`), so daemon-vs-server
cross-process concurrency is *not* serialised by this lock at all — only the
in-process cases above are. Pre-existing wrinkle worth recording: each
`ingest_path_async` call starts with `shutdown_requested.clear()`
(`pipeline.py:101`), so two overlapping daemon ingests clear each other's
shutdown flag. No candidate design changes this; fix or flag separately.

## 2. Candidate designs

### 2.1 D1 — Embed + stamp outside the lock; mutation inside

**Surveyed shape (handoff premise)**: precompute embeddings outside the lock,
then mutate via `VectorStore.upsert_precomputed` on both stores.

**KEY QUESTION verdict: `upsert_precomputed` cannot reproduce `write_nodes`
row identity and layout exactly — and it does not need to.**

What `write_nodes` actually writes (both adapters route through upstream
LlamaIndex adapters with throwaway per-call construction):

- `chroma.py::write_nodes` (166-184): `_check_or_stamp_identity` →
  `_LlamaChromaVectorStore(chroma_collection=collection)` →
  `StorageContext.from_defaults` → `VectorStoreIndex(nodes, storage_context=...)`
  → `bump_generation`. Upstream `ChromaVectorStore.add()`
  (`llama_index/vector_stores/chroma/base.py:284`) derives each row as
  `ids=[node.node_id]`, `documents=[node.get_content(metadata_mode=MetadataMode.NONE)]`,
  `metadatas=[node_to_metadata_dict(node, remove_text=True, flat_metadata=...)]`
  with `None` coerced to `""`.
- `lancedb.py::write_nodes` (197-229): identity guard →
  `_widen_null_adapter_columns` → `_evolve_for_nodes` → throwaway
  `_LlamaLanceVectorStore(mode="create")` behind `redirect_stdout` →
  intent flush → `bump_generation`. The adapter writes internal columns into
  the metadata struct: `INTERNAL_METADATA_KEYS = {"_node_content", ...,
  "doc_id", "ref_doc_id"}` (`lance_paged.py:20-26`).

What `upsert_precomputed` writes:

- `chroma.py::upsert_precomputed` (186-217): direct
  `collection.upsert(ids, documents, metadatas, embeddings)`. The caller must
  reproduce upstream `node_to_metadata_dict` semantics (flat_metadata
  handling, `None`→`""`, `remove_text`) by hand — version-fragile
  duplication of code this repo does not own.
- `lancedb.py::upsert_precomputed` (258-317): `rows_to_arrow` mirrors the
  adapter column layout `(id, doc_id, vector, text, metadata struct)` but
  fills `doc_id` with **nulls** (`lance_rows.py:22-44`), and a table *created*
  by this path lacks the adapter's internal metadata keys entirely — the
  repo's own comment at `lancedb.py::_evolve_for_nodes` says so and later
  adapter writes must widen the struct to compensate. Mixed tables read
  consistently only because `strip_internal_metadata` normalises reads.

Using `upsert_precomputed` for the replacement mutation would therefore be a
**contract change beyond lock scope**: the ABC docstring scopes it to
calibration harnesses (`base.py:51-66`), its only callers are
`experiments/{9a,10.1,13,14}/build_indexes.py`, and row layout would diverge
from every adapter-written row (`doc_id` null vs derived; `_node_content`
absent vs present).

**The minimal, contract-preserving D1**: Stage 3A already pre-embeds via
`_embed_missing_nodes`, and `write_nodes` **reuses populated embeddings**.
Upstream `embed_nodes()` (`llama_index/core/indices/utils.py:170`) passes
through any node whose `embedding is not None` and embeds only the rest, with
`get_content(metadata_mode=MetadataMode.EMBED)` — the same text mode
`_embed_missing_nodes` uses. The Chroma adapter then reads
`node.get_embedding()`. So the correct seam is:

1. Hoist the embed block (`embedding_started` … `_embed_missing_nodes`, lines
   186-202) and `stamp_source_attempt` (215-222) **above** `with write_lock:`,
   keeping the embed semaphore around the embed call.
2. Keep `write_nodes` + `count_where` verification + stale scan + `delete_ids`
   inside the lock, unchanged.

Analysis:

- **ADR-048 failure table**: intact. Write→verify→stale-delete order untouched;
  embedding failure still occurs before any mutation (row 3 unchanged);
  exactly-once generation per mutation preserved (still one `write_nodes` plus
  one conditional `delete_ids`); last-good survival and interrupted mixed-state
  detection unchanged — the stamps are identical wherever they are computed.
- **Memory**: one retained bounded unit per source, exactly as today. Peak RSS
  unaffected. Two retained units would only appear with a pipeline-loop
  restructure (embed source N+1 while committing source N), which exceeds
  task 3.6.2's scope.
- **Thread-safety of stamp/embed outside the lock**: safe. The node list is
  created per source by `read_and_chunk_file_async`, held only by the
  pipeline-loop local, and passed solely to `replace_source_nodes_async`;
  between parse and write no other consumer exists. `stamp_source_attempt`
  mutates `node.metadata`, exclusion key sets, and `node.id_` in place —
  caller-private state. Embedding text is stamp-order independent: the stamp
  adds all source keys to `excluded_embed_metadata_keys` *and*
  `excluded_llm_metadata_keys` (`source_state.py:247-250`), so vectors are
  bit-identical whether stamping happens before or after embedding. Keep the
  current order (embed → stamp) to match the tested Stage 3A path exactly.
- **ID/metadata contract**: unchanged — IDs are derived by
  `stamp_source_attempt` in ingestion code *before* `write_nodes`, not inside
  the adapters, so the same derivation applies outside the lock.
- **Lock ordering**: today both embed paths take `write_lock` → embed
  semaphore. After D1, replacement takes the semaphore alone, releases it,
  then takes `write_lock`; `writer.py` keeps `write_lock` → semaphore. No
  cycle is possible because the D1 path never holds the semaphore while
  acquiring `write_lock`.
- **Shutdown semantics**: the mid-embed shutdown check moves out with the
  embed; the lock-side check before `write_nodes` remains, so no
  post-shutdown mutation. A shutdown arriving mid-embed wastes at most one
  bounded source's embed work.
- **Code seams**: `replacement.py::_replace_sync` only. `WriteTimings` and
  its consumers unchanged; `embedding_seconds` is now captured outside the
  lock, and `lock_wait_seconds` measures the narrowed section — Experiment 6
  must treat arm-B `lock_wait_seconds` as a different quantity from baseline.
- **Estimated diff**: ~40-60 lines in `replacement.py` (block moves, timer
  plumbing, docstring) plus new tests. No `vectordb/`, `writer.py`, `_state.py`
  changes.
- **Risks**: low. Chief risk is silent drift between the hoisted embed's
  error wrapping (`IngestionStageError("embedding", ...)`) and its new
  location; the second is misreading `lock_wait_seconds` across arms (see
  above).

**What D1 does and does not change**: it reduces lock *hold* time by the
embedding stage, improving concurrent-call latency and aggregate throughput
when ≥2 threads ingest or when deletes run during ingestion. It does **not**
change single-stream sequential throughput: `ingest_path_async` is a
sequential `for` loop, so embed(N+1) never overlaps write(N) unless the loop
itself is restructured into a prefetch pipeline — a larger change than
3.6.2 authorises. D1's benefit is confined to the §1.3 contention sources.

### 2.2 D2 — Per-collection locks replacing the global lock

Shape: `_state.py` grows a registry `dict[str, threading.Lock]` behind a small
mutex; all five §1.2 sites swap `write_lock` for `collection_write_lock(name)`.
Every site already knows its collection name, and no path acquires two
collection locks, so no ordering deadlock.

- **Benefit ceiling**: parallelism only *across* collections. Both real
  contention sources (§1.3) target the default `"documents"` collection —
  the daemon's two concurrent ingests and delete-during-ingest serialise on
  the same per-collection lock exactly as today. Gains accrue only to
  multi-collection users (documents + codebase).
- **Chroma client thread safety**: one `PersistentClient` backs all
  collections; the embedded SQLite store is a single-writer engine, so
  cross-collection write parallelism gains little and each concurrent write
  still funnels through internal serialisation. Documented client thread
  safety covers concurrent calls, not concurrent write throughput.
- **LanceDB**: concurrent writes to *different* tables through one connection
  are supported; same-table `merge_insert` is the conflict-prone operation —
  which the per-collection lock still prevents.
- **BM25 generation**: `bump_generation` is an unsynchronised
  read-modify-write on a per-store dict. Today safe under the global lock;
  under D2 it stays safe only if every mutator of a collection holds that
  collection's lock — true for the five converted sites, but the invariant is
  now per-collection and must be stated in `_state.py`.
- **Cross-collection deletion paths**: `remove_collection` /
  `remove_by_metadata` / `remove_document` are each single-collection; the
  registry keeps lock identity stable across drop/create cycles for the same
  name.
- **Embedding stays inside the lock**: D2 does not shorten the critical
  section; two same-collection ingests still serialise embedding against each
  other. It composes with D1 but is not a substitute.
- **Diff**: ~60-100 lines (`_state.py` + five call sites) plus test updates —
  `test_concurrent_write_lock_serialises` pins the *global* primitive and
  would need a per-collection companion test.
- **Risk**: moderate. Correct for the audited sites, but it removes a
  process-wide guarantee that any future cross-collection writer might have
  relied on silently.

### 2.3 D3 — Batched writes under a short lock

Shape: accumulate N sources' stamped, pre-embedded candidates; acquire the
lock once; one combined mutation; verify and stale-clean per source.

- **ADR-048 failure-table impact**: the write→verify→stale-delete order can be
  preserved per source, but "Store write before complete candidate" now
  leaves up to N sources' partial candidates beside their old rows on a
  single store failure. Recovery semantics per source are unchanged
  (completeness gate rejects mixed state per `file_path`), yet the blast
  radius and transient storage multiply by N.
- **Exactly-once generation**: one combined `write_nodes` would be *one*
  mutation for N sources — one generation bump instead of N. The letter of
  "exactly once per successful non-empty mutation" survives, but per-source
  mutation bookkeeping and the audit regressions
  (`test_each_vector_store_mutation_owns_generation_invalidation`) become
  harder to reason about.
- **Memory**: violates ADR-048 Decision 1 and the `ingest_path_async`
  docstring contract ("at most one source file's node set is retained"),
  which `test_generated_corpus_retains_only_one_source_node_set` pins.
  Only N ≤ 2 stays inside the two-bounded-units ceiling, and N=2 is really
  D1 plus a loop restructure — out of 3.6.2 scope.
- **Per-source failure attribution**: a batch-level store error must be
  decomposed into per-file `failure_stage` entries the current `file_details`
  contract expects.
- **Verdict**: reject as a standalone design; revisit only as part of a
  pipeline restructure proposal with its own ADR.

### 2.4 D4 — Reject (no change)

Correct when: (i) measured `lock_wait_seconds` is negligible across
single-stream, dual-stream daemon, and delete-during-ingest workloads; or
(ii) measurement shows store-write/verify/cleanup dominating the critical
section so that hoisting embedding barely shortens it; or (iii) no
concurrent-call latency requirement exists for the daemon/MCP surfaces.
Task 3.GB.2 explicitly accepts "not warranted by measurement" recorded in the
gate notes as a full outcome (design constraint D12).

## 3. Comparison table

| Design | Throughput benefit (conditional on measurement) | Correctness risk | Contract changes required | Diff size | Rollback ease |
| --- | --- | --- | --- | --- | --- |
| D1 (minimal: hoist embed+stamp; keep `write_nodes` in lock) | High for concurrent callers *iff* `embedding_seconds` dominates lock hold and contention exists (§1.3); zero for single-stream | Low — failure table untouched | None (stays on `write_nodes`) | ~40-60 lines, one file | Trivial (revert one commit) |
| D1 via `upsert_precomputed` (handoff premise) | Same as above | High — row-layout divergence (`doc_id` nulls, missing internal keys on Lance; upstream metadata-derivation duplication on Chroma) | Yes — ABC scope change + two adapter contracts | 150+ lines across `vectordb/` + `replacement.py` | Poor (schema/row drift persists after revert) |
| D2 per-collection locks | Only cross-collection; both real contention sources are same-collection → ~0 for default workload | Moderate — per-collection bump_generation invariant; future cross-collection writers unprotected | Lock primitive semantics (internal) | ~60-100 lines, six files | Easy |
| D3 batched writes | Amortises lock acquisition; unproven | High — multi-source blast radius, generation bookkeeping, N-unit retention | Breaks bounded-retention contract + `file_details` granularity | Large (pipeline + replacement + tests) | Moderate |
| D4 reject | None | None | None | None | None |

## 4. Conditional recommendation

Let E6 denote the Experiment 6 baseline (Stage 3A, sequential) and E6-C the
contended arm (two concurrent ingests, and/or delete-during-ingest):

- **(a) Single-stream `lock_wait_seconds` ≈ 0; E6-C fully serialised with
  `embedding_seconds` dominating the held section** → Implement **minimal
  D1** (§2.1 seam: hoist `_embed_missing_nodes` + `stamp_source_attempt`
  above `with write_lock:` in `replacement.py::_replace_sync`). Do **not**
  use `upsert_precomputed`. Re-run E6-C as arm B; retain only if throughput
  improves with no gate regressions; write TDR-013.
- **(b) E6-C already partially parallel (small `lock_wait_seconds`, overlap
  observed)** → Same as (a), but expect smaller gains; the semaphore-wait
  component inside `embedding_seconds` (§1.1 stage 3) should be separated in
  the harness before crediting D1.
- **(c) Store-write/verify/cleanup dominates the held section** → D1 narrows
  little. First fix the §1.1 attribution gap (`verify_seconds`), then
  re-measure. If verify/scan still dominates, the correct follow-up is
  store-side (index the scan, batch `count_where`) — outside 3.6.2; choose
  **D4 reject** with the attribution fix as the recorded outcome.
- **(d) `lock_wait_seconds` negligible everywhere including E6-C** → **D4
  reject**; record in gate 3.GB.2 notes that no change is warranted by
  measurement.

**Critical caveat that must accompany any decision**: moving embedding
outside the lock does **not** change single-stream sequential throughput.
`ingest_path_async` is a sequential `for` loop over files; embed(N+1) cannot
overlap write(N) without restructuring that loop into a prefetch pipeline,
which exceeds task 3.6.2's authorised scope (and would need its own
bounded-retention analysis, §2.3). D1's benefit is strictly the
concurrent-call latency/throughput of §1.3.

## 5. What a minimal-D1 implementation must preserve (checklist → pinned tests)

Ordered by the invariant, with the existing tests that pin it. All must stay
green without modification except where noted:

1. Global lock serialises concurrent mutations (primitive itself unchanged):
   `test_ingestion_parallel.py::test_concurrent_write_lock_serialises`,
   `test_ingestion_parallel.py::test_embed_semaphore_limits_concurrency`.
2. Shutdown cannot cause a post-shutdown mutation; writer path untouched:
   `test_signal_handling.py::test_embed_and_write_bails_inside_lock`.
3. Skip only a complete matching version:
   `test_ingestion_stage3.py::test_repeated_ingest_skips_complete_matching_version`.
4. Replacement touches only the source's own rows, by stamped IDs:
   `test_ingestion_stage3.py::test_content_edit_replaces_only_old_source_version`,
   `test_ingestion_stage3_legacy.py::test_legacy_row_without_attempt_is_replaced_by_id_once`
   (also pins single-ID-deletion of legacy rows without attempt metadata).
5. Index identity forces reprocessing (stamps derive from settings hash):
   `test_ingestion_stage3.py::test_index_identity_change_forces_reprocessing`,
   `test_ingestion_stage3.py::test_chunk_setting_change_forces_reprocessing`.
6. Failure table rows (fault injection; these also pin `IngestionStageError`
   stage attribution via `failure_stage` — the exception class has **no
   direct name references in tests/**; the assertion surface is the result
   fields):
   `test_parse_failure_preserves_last_searchable_version`,
   `test_embedding_failure_preserves_last_searchable_version`,
   `test_partial_store_write_preserves_old_version_and_recovers`,
   `test_cleanup_failure_with_old_and_new_versions_recovers`.
7. Bounded retention (one source unit at a time):
   `test_ingestion_stage3.py::test_generated_corpus_retains_only_one_source_node_set`.
8. Timing/RSS diagnostics shape:
   `test_ingestion_stage3.py::test_ingestion_exposes_stage_timings_and_peak_rss`
   (arm-B semantics note: `embedding_seconds` becomes an outside-lock
   measurement; if the harness adds `verify_seconds`, this test's key set
   grows — additive keys only).
9. Store-owned generation, exactly once per mutation, orchestration never
   bumps directly:
   `test_vectordb_contract.py::test_pipeline_mutations_do_not_add_caller_owned_bumps`,
   `test_precalibration_audit_regressions.py::test_each_vector_store_mutation_owns_generation_invalidation`,
   `test_precalibration_audit_regressions.py::test_orchestration_does_not_duplicate_store_generation_bumps`,
   `test_vectordb_contract.py::test_bump_advances_counter`,
   `test_vectordb_contract.py::test_generations_are_per_collection`,
   `test_lancedb_store.py::test_write_and_delete_advance_generation_and_rebuild_bm25`.
10. BM25 cache invalidation on generation advance:
    `test_hybrid_retrieval.py::test_bm25_reuses_cached_index_when_generation_is_unchanged`,
    `test_hybrid_retrieval.py::test_bm25_rebuilds_when_generation_advances`,
    `test_hybrid_retrieval.py::test_remove_document_generation_rebuild_excludes_deleted_chunk`,
    `test_hybrid_retrieval.py::test_remove_collection_generation_invalidates_cache`.
11. Dimension lock on first write (unchanged by D1 since `write_nodes` is
    retained): `test_vectordb_contract.py::test_dimension_locked_on_first_write`.
12. Precomputed path stays calibration-only (D1 must not touch it):
    `test_vectordb_contract.py::test_upsert_precomputed_advances_generation`,
    `test_vectordb_contract.py::test_precomputed_vectors_have_cross_store_semantic_score_parity`,
    `test_lancedb_store.py::test_upsert_precomputed_introduces_new_field`.

New tests a minimal D1 must add (regression-first per repo discipline):

- Embedding of source B proceeds while source A holds `write_lock` (the
  concurrency improvement is the behaviour under test).
- Stamped node IDs/metadata are identical whether embedding succeeded inside
  or outside the lock (golden-row comparison against Stage 3A output).
- Embed failure outside the lock still produces `failure_stage == "embedding"`
  and zero store mutations.

Grep terms used for this inventory (per-file hit counts, `tests/`):
`write_lock` → `test_signal_handling.py` (1), `test_ingestion_parallel.py` (3);
`get_embed_semaphore` → `test_ingestion_parallel.py` (2);
`delete_ids` → `test_ingestion_stage3.py` (3), `test_ingestion_stage3_legacy.py` (1);
`bump_generation` → `test_vectordb_contract.py` (6), `test_hybrid_retrieval.py` (5),
`test_precalibration_audit_regressions.py` (2);
`source_attempt` → `tests/unit/test_type_aware_ingestion.py` (1),
`test_metadata_degradation.py` (1), `test_ingestion_stage3_legacy.py` (2);
`IngestionStageError` → no direct references.

## 6. Source files surveyed

`src/rag_mcp/core/ingestion/{replacement,_state,writer,pipeline,source_state}.py`,
`src/rag_mcp/core/vectordb/{base,chroma,lancedb,paged,lance_paged,lance_rows}.py`,
`src/rag_mcp/daemon/{runner,watcher}.py`,
`docs/adr/048-bounded-failure-safe-ingestion.md`, and the installed
LlamaIndex sources for `ChromaVectorStore.add`,
`VectorStoreIndex._get_node_with_embedding`, and `embed_nodes` (version
pinned by `uv.lock`).
