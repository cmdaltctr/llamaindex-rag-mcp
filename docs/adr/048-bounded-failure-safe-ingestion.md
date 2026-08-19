# ADR-048: Bounded and Failure-Safe Ingestion

**Date:** 2026-08-19
**Status:** Accepted (Pause Gate 3A closed 2026-08-19; see validation evidence)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The pre-calibration audit found two ingestion properties that could invalidate
later evidence even when retrieval logic itself was correct.

First, `ingest_path_async` retained every parsed node from a directory in one
`all_nodes` list and embedded/wrote only after all files had been read. Peak
node retention therefore scaled with corpus size instead of a bounded source
unit.

Second, re-ingestion deleted a source's old rows before parsing, embedding, and
writing its replacement. A parse, embedding-provider, or store failure could
therefore remove the last durable searchable version before a replacement
existed.

The archived change
`openspec/changes/archive/2026-08-15-add-ingestion-change-detection/` remains
useful design input for shared source hashing and unchanged-file detection, but
its content-hash-only design explicitly deferred embedding, parser, and
chunking identity. Its unchecked task list is historical material, not evidence
that the current pre-calibration Stage 3 was already complete.

ADR-047 also established that embedding-provider selection is process scoped.
Stage 3 must preserve that contract and must not imply that
`embed_concurrency > 1` means effective embedding concurrency while the global
write lock still serializes embedding and mutation.

## Decision

1. **Process one source at a time.** `ingest_path_async` hashes,
   parses/chunks, embeds, verifies, and commits one source before moving to the
   next. The orchestrator no longer accumulates directory-sized node sets.

2. **Bind reuse to content plus complete index identity.** Stored rows carry
   `source_content_hash`, `source_index_identity`, and `source_version`. The
   index identity includes the effective embedding provider/model, parser and
   document-backend selectors, detected content type, effective chunking
   configuration/overrides, and metadata-shaping selectors that can alter
   embedding text. Retry and timeout budgets are excluded because they affect
   failure behavior rather than a successful index representation.

3. **Skip only a complete matching version.** A source is unchanged only when
   all rows stored for its `file_path` match the content hash and index identity
   and their declared `source_chunk_count` agrees with the durable row count.
   Legacy rows, partial writes, mixed attempts, and old-plus-new interrupted
   states therefore fail the skip gate and are reprocessed.

4. **Give every replacement a unique attempt identity.** New rows carry a
   `source_attempt` UUID and IDs derived from source path, attempt, chunk index,
   and original node ID. Old and new rows can coexist while durability is being
   established without accidental ID overwrite.

5. **Write and verify before stale deletion.** The replacement path embeds the
   bounded node set, writes the candidate attempt, and verifies the exact
   expected durable row count for that attempt. Only after verification does a
   bounded `iter_documents` scan identify rows for the same `file_path` whose
   `source_attempt` differs from the verified attempt. A missing attempt key is
   deliberately stale, so pre-Stage-3 rows are recoverable too. The selected
   stable row IDs are deleted through the store-neutral `VectorStore.delete_ids`
   extension. This avoids depending on backend-specific inequality semantics
   for missing metadata keys.

6. **Keep ID deletion store owned.** ChromaDB implements `delete_ids` with the
   collection's native ID deletion and LanceDB translates the same stable IDs
   through its existing typed literal/filter path. Each successful non-empty ID
   deletion advances the collection generation exactly once. Ingestion
   orchestration never calls `bump_generation` directly.

7. **Preserve the last searchable version on failure.** Parse/chunk and
   embedding failures happen before a new mutation. A store-write failure may
   leave a distinguishable partial candidate beside the old rows, but does not
   delete the old rows first. A stale-cleanup failure leaves a verified new
   attempt and the prior rows together; the next ingest detects the mixed state
   and retries rather than treating it as unchanged.

8. **Keep Stage 3A serialized.** Embedding, candidate write, durability
   verification, stale scan, and cleanup remain inside the existing global
   write lock. Stage 3A instruments the serialized design; it does not widen
   effective ingestion concurrency. Lock narrowing or parallel embedding is a
   Stage 3B question only after Pause Gate 3A evidence exists.
   *Stage 3B follow-up (2026-08-19): answered by measurement — embedding and
   attempt-stamping now run before the lock; the mutation section (write →
   verify → stale-delete) remains inside it. See TDR-013 and Experiment 18
   (`experiments/18-ingestion-lock-scope-ab-2026-08-19/`, commit `b4b01b6`).*

9. **Expose attribution before optimization.** Ingestion results add timings
   for change detection, parse/chunk, embedding, store write, lock wait,
   cleanup, and total elapsed time, plus best-effort process peak RSS. These are
   Stage 3 evidence inputs, not Stage 5 calibration claims.

## Failure and Recovery Semantics

| Failure point | Durable state after failure | Next ingest |
| --- | --- | --- |
| Source hashing | Previous searchable version unchanged | Hash again; no deletion occurred |
| Parse/chunk | Previous searchable version unchanged | Parse again |
| Embedding | Previous searchable version unchanged | Embed again |
| Store write before complete candidate | Old rows plus possible partial candidate | Completeness gate rejects the mixed/partial state; rewrite and clean stale IDs after verification |
| Durability verification | Old rows plus whatever candidate rows were written | Mixed/incomplete state prevents unchanged skip |
| Stale ID scan/delete | Old rows plus a complete verified new attempt | Mixed attempts prevent skip; next verified attempt removes stale IDs |

An empty parse/chunk result is a failed replacement, not a valid empty source
that is allowed to erase the prior searchable version. Intentional source
deletion remains a separate document-deletion operation.

## Validation Plan - Pause Gate 3A

Acceptance required fresh local or CI execution of the Stage 3A gate,
including:

- generated-corpus bounded-node-lifetime tests;
- parse, embedding, partial store-write, and stale-cleanup fault injection;
- repeated ingest, content edit, embedding-model change, parser-selector
  change, chunk-setting change, and legacy-row migration on both ChromaDB and
  LanceDB where the contract applies;
- exact generation behavior for the candidate-write plus stale-ID-delete path;
- existing Stage 0-2 regressions, while leaving the three known Stage 4
  experiment-runner defects deferred rather than weakening those assertions;
- Ruff check/format, import-linter contracts, the repository file-size ceiling,
  and strict OpenSpec validation.

The Stage 3A implementation as originally delivered reached commit
`be18df8c107c7f1dc4cf8f996208d33479878c9a`. That SHA was implementation
state, not gate evidence; the validation-evidence subsections below record
the tested SHAs and concrete command results that closed the gate.

The repository CI workflow does not run automatically for pushes to this
feature branch; it currently targets pushes and pull requests to `main` and
`v3`. Therefore branch commits alone are not evidence that this gate ran.

### Pause Gate 3A validation evidence (2026-08-19)

Executed on the operator's Mac (macOS aarch64, Python 3.12.10, `uv sync
--frozen`, 208 packages, lockfile unchanged). Tested implementation SHA:
`65695dad6f9fdb27b0620694e11b948cfa2fd9ff` (commits after this SHA are
documentation-only).

| Command | Result |
| --- | --- |
| Stage 3A group: `pytest tests/test_ingestion_stage3_runtime_identity.py tests/test_ingestion_stage3.py tests/test_ingestion_stage3_legacy.py tests/test_ingestion_parallel.py tests/test_async_ingest_responsiveness.py -q` | 41 passed |
| `pytest tests/test_precalibration_audit_regressions.py -q` | 7 passed, 3 failed — exactly the deferred Stage 4 Experiment 10b/13/14 defects |
| `pytest -m "not slow" -q` (full fast suite) | 1611 passed, 17 skipped, 10 failed (see below) |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 634 files already formatted |
| `lint-imports` | 8 contracts kept, 0 broken |
| `openspec validate harden-pipeline-correctness-before-calibration --strict` | valid |

Executable validation found and fixed three defects in the delivered
implementation, none of which weakened a contract:

- The Stage 3 legacy-row fixture seeded a bare `TextNode` with no SOURCE
  relationship, so the LanceDB adapter typed the `doc_id` column as Null and
  blocked the candidate write. Fixed in `87023bc` (realistic fixture) plus a
  defensive store guard widening null-typed adapter columns (`25ae9c3`,
  TDR-012, extracted to `LanceTableMetadataMixin` in `65695da` after the
  guard tripped the 500-line file ceiling).
- Lint debt from hook-bypassing commits: unused import and formatting drift
  (`8d0bb1d`).

**Pause Gate 3A remains OPEN.** The full fast suite — required by this ADR's
validation plan ("existing Stage 0-2 regressions") — shows 7 failures beyond
the 3 deferred Stage 4 defects. All 7 were verified to fail identically at
`9dd4514`, the remote head before this validation session, so they are
pre-existing Stage 3A implementation breakage, not regressions from the
validation-session fixes:

- `tests/test_watcher.py::TestIngestPathAllFilesFail` (2 tests) and one
  `tests/test_metadata_degradation.py` aggregation test patch
  `pipeline.embed_and_write_async`, which the Stage 3A rewrite moved out of
  `core.ingestion.pipeline` (patch-target drift, AGENTS.md gotcha 8b).
- `tests/test_metadata_degradation.py::TestPipelineDegradationAggregation`
  (2 tests): ingestion returns `status: "error"` where the tests expect
  `"ok"`.
- `tests/test_signal_handling.py::test_shutdown_flag_stops_sequential_early`:
  one file is processed where zero were expected after the shutdown flag.
- `tests/unit/test_type_aware_ingestion.py::test_binary_file_skipped`: fails
  during patch setup on `pipeline.remove_document` (also removed by Stage 3A);
  the mixed pytest summary initially suggested a chunk-count mismatch.

These 7 failures (plus the 3 deferred Stage 4 defects) must be resolved or
explicitly dispositioned before this ADR can become Accepted and before
Stage 3B begins.

#### Resolution (second validation round, same day)

All 7 were triaged against the Stage 3A contracts; one was a genuine defect,
six were stale tests:

- **Genuine defect** (`8defc05`): the aggregate `metadata_degraded` count was
  incremented only after a successful replacement, so a file whose extraction
  degraded and whose replacement then failed dropped out of the count. The
  increment now happens on observation, before `replace_source_nodes_async`,
  and the failed file detail carries the flag. Pinned by the updated
  `test_embedding_error_preserves_degradation_count`.
- Stale fixtures (`8defc05`): the two remaining aggregation tests used empty
  chunk lists, a trick that relied on the removed empty-list short-circuit;
  Stage 3A deliberately treats an empty parse as a failed replacement. They
  now feed one real node per file through a mocked replacement seam.
- Stale patch targets (`5fd97e7`): the watcher error-classification pair and
  the binary-skip test patched `pipeline.embed_and_write_async` /
  `pipeline.remove_document`, which Stage 3A moved into
  `core.ingestion.replacement` (AGENTS.md gotcha 8b). Retargeted at the new
  seams; the binary-skip logic itself was verified unchanged.
- Stale expectation (`5fd97e7`): the shutdown test asserted `chunks_created
  == 0`, an artefact of the old deferred-embedding design. Stage 3A commits
  each source fully before advancing, so a mid-run shutdown stops subsequent
  sources but cannot un-write the current one; the test now asserts
  `files_indexed == 1`.

Final gate state at `5fd97e7` (macOS aarch64, Python 3.12.10, `uv sync
--frozen`): Stage 3A group 41 passed; fast suite 1618 passed, 17 skipped,
3 failed = exactly the deferred Stage 4 Experiment 10b/13/14 defects;
`ruff check` and `ruff format --check` clean across 634 files;
`lint-imports` 8 contracts kept; strict OpenSpec validation valid. The
tested implementation SHA is `5fd97e7`; later commits on this branch are
documentation and gate bookkeeping only.

**Decision: accepted.** Every condition in the validation plan above is met
by executable evidence at a recorded SHA, with the Stage 4 defects explicitly
deferred rather than weakened. Pause Gate 3A is closed; Stage 3B (optional,
measurement-gated) may proceed under its own gate (3.GB), and Stage 4 remains
unstarted.

### Stage 5 experiment 6 confirming evidence (2026-08-19)

Stage 5 task 5.6 ran the ingestion boundedness and atomicity template
against current code at commit `c475852` (git dirty; experiment files
uncommitted; `pipeline_variant=stage3b_narrow_lock_current`). Phase A H1–H5
all PASS, so every decision in this ADR holds on the Stage 3B code:

| Gate | Result |
| --- | --- |
| H1 bounded node lifetime | PASS: max 1 live replacement batch at every corpus size (2 under 2-stream contention), max 3 nodes per batch, invariant across 25/100/400 files |
| H2 memory scaling | PASS: frozen guard 4x files → ≤2x adjusted peak RSS: 1.154 (25→100), 1.475 (100→400); descriptive 16x ratio 1.703 ≤ 4.0 |
| H3 failure safety | PASS: fault_parse, fault_embed, fault_store_write; version A rows intact after each failure; deterministic rerun identical |
| H4 successful swap | PASS: F0–F3; after recovery `stale_rows == 0` and `final_version_rows == swap_chunks` |
| H5 unchanged skip | PASS: `files_skipped_unchanged == size`, embedding seam calls 0, store write calls 0 |

Phase B re-confirms the Stage 3B lock shape against Experiment 18's Stage 3B
arm (`experiments/18-ingestion-lock-scope-ab-2026-08-19/output/results.ab.json`,
A/B reference commit `b4b01b6`):

- H6 throughput: real Ollama arm 6.744 docs/s vs Stage 3B reference 7.40 =
  0.911x, within the frozen ≥0.9x gate; lock-wait fraction 0.0 ≤ 0.10
  (Stage 3A measured 0.9668) and lock-wait wall time 0.000 s. The fake arm
  measured 0.808x, below the gate, because the exp-6 generator yields 289
  chunks per 100 files vs experiment 18's 208; chunk-normalised throughput
  shows no regression (1.13x fake, 1.26x real). Reported as found; no
  threshold was retro-fitted.
- H7 no resource regression: current max peak RSS 315,637,760 B vs Stage 3B
  reference 303,677,440 B = 1.039x ≤ 1.25.

Stage breakdown (real arm): embedding 25.911 s dominates and runs outside
the lock; lock-wait 0.000 s; store-write 1.981 s; cleanup 0.923 s. This is
the Stage 3B shape promised by decision 8. No production defects were
observed; no hotfix was needed.

## Consequences

### Positive

- Peak orchestrator node retention is bounded by one source instead of total
  corpus size.
- Re-ingestion cannot intentionally delete the last good source before a
  verified replacement exists.
- Same source bytes cannot reuse vectors produced by a different embedding
  model, parser selection, or chunk configuration.
- Interrupted writes are distinguishable without adding a backend transaction
  API.
- Legacy rows without Stage 3 attempt metadata are explicitly removable on
  both current stores.
- Timing and RSS evidence exist before any concurrency optimization is
  proposed.

### Negative

- A failed partial write may temporarily consume extra storage until a later
  successful replacement removes stale attempts.
- Changed-source replacement performs a candidate write plus one stale-ID
  deletion when stale rows exist; these are two real mutations and therefore
  two store-owned generation advances.
- Stale-row discovery currently scans collection documents in bounded pages.
  It is memory bounded, but its scan cost grows with collection size and should
  be measured before any Stage 3B optimization.
- Conservative index identity can reprocess a source when a configured parser
  or metadata selector changes even if that selector would not alter this
  particular file's output. Correctness is preferred over skip rate.
- Pre-embedding the bounded node set adds an explicit embedding phase before
  the store adapter so embedding and store-write wall time can be attributed
  separately.

### Neutral

- The 500 MiB source read ceiling is unchanged; daemon and ingestion hashing use
  the same helper.
- Existing public ingestion result keys remain, with diagnostics and
  `files_skipped_unchanged` added rather than replacing established fields.
- This decision does not select Stage 3B concurrency settings and does not run
  or claim Stage 5 retrieval-quality experiments.

## Alternatives Considered

| Option | Rejected because |
| --- | --- |
| Delete old rows before parsing | Parser/provider failure can destroy the last searchable version. |
| Hash source bytes only | Same bytes can require different vectors after model, parser, or chunk changes. |
| Reuse stable node IDs and upsert in place | Old rows can be overwritten before the complete replacement is verified. |
| Delete stale rows with `source_attempt != current` only | Missing-key inequality behavior is not a safe cross-store legacy-row contract. |
| Add backend transactions now | Current stores can implement recoverable replacement without widening the Stage 3 abstraction that far. |
| Widen embedding concurrency in Stage 3A | It mixes correctness work with an unmeasured scheduling optimization and bypasses the pause gate. |
| Treat cleanup failure as success | Old-plus-new duplicates would remain searchable without surfacing the interrupted state. |

## References

- OpenSpec change:
  `openspec/changes/harden-pipeline-correctness-before-calibration/`
- Archived change-detection design:
  `openspec/changes/archive/2026-08-15-add-ingestion-change-detection/`
- Ingestion implementation:
  `src/rag_mcp/core/ingestion/{hashing,source_state,replacement,metrics,pipeline}.py`
- Store-neutral contract and store adapters:
  `src/rag_mcp/core/vectordb/{base,paged,lance_paged,chroma,lancedb}.py`
- Deterministic Stage 3A tests:
  `tests/test_ingestion_stage3.py`, `tests/test_ingestion_stage3_legacy.py`,
  `tests/test_ingestion_parallel.py`, `tests/test_async_ingest_responsiveness.py`
- Stage 3B A/B record: `experiments/18-ingestion-lock-scope-ab-2026-08-19/`
  (commit `b4b01b6`); TDR-013 (narrow the ingestion write lock).
- Stage 5 confirming evidence: `experiments/example/experiment-6-ingestion-boundedness-and-atomicity/`
  (task 5.6, 2026-08-19).
- Related decisions: ADR-010, ADR-014, ADR-034, ADR-046, ADR-047
