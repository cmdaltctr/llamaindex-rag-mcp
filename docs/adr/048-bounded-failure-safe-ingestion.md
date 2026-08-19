# ADR-048: Bounded and Failure-Safe Ingestion

**Date:** 2026-08-19
**Status:** Proposed - pending Pause Gate 3A
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The pre-calibration audit identified two ingestion properties that can corrupt
or distort later calibration evidence even when retrieval itself is correct.

First, `ingest_path_async` retained every parsed node from a directory in one
`all_nodes` list and embedded/wrote only after all files had been read. Peak
memory therefore scaled with corpus size rather than a bounded ingestion unit.

Second, re-ingestion deleted the old rows for a source before parsing,
embedding, and writing its replacement. A parser, embedding provider, or store
failure could therefore remove the last durable searchable version of a source
without a replacement being available.

The archived OpenSpec change
`openspec/changes/archive/2026-08-15-add-ingestion-change-detection/` captured a
useful earlier intent: share source-content hashing with the daemon and avoid
unnecessary re-ingestion. Its old design intentionally deferred embedding,
parser, and chunking identity, however, so content hash alone is not sufficient
for the current pre-calibration correctness contract. The archived unchecked
task list is historical design input, not evidence that the current Stage 3
work was already complete.

ADR-047 also established that embedding-provider selection is process scoped.
Stage 3 must preserve that contract and must not imply that an integer
`embed_concurrency > 1` means effective embedding concurrency while the global
write lock still serializes embedding and mutation.

## Decision

1. **Process one source file at a time.** `ingest_path_async` hashes,
   parses/chunks, embeds, verifies, and commits one source before moving to the
   next. The orchestrator does not retain a directory-sized node list.

2. **Define source reuse by content plus complete index identity.** Every
   stored row carries `source_content_hash`, `source_index_identity`, and
   `source_version`. The index identity includes the effective embedding
   provider/model, parser and document-backend selectors, detected content
   type, effective chunking configuration/overrides, and metadata-shaping
   selectors that can alter embedding text. Retry and timeout budgets are
   excluded because they affect failure behavior rather than a successful
   index representation.

3. **Skip only a complete matching version.** A source is unchanged only when
   all rows currently stored for its `file_path` match the content hash and
   index identity and their declared `source_chunk_count` equals the durable
   row count. Legacy rows, partial writes, mixed attempts, and old-plus-new
   interrupted states therefore fail the skip gate and are reprocessed.

4. **Use a unique replacement attempt for each write.** New rows carry a
   `source_attempt` UUID and IDs derived from source path, attempt, chunk index,
   and original node ID. Old and new rows can coexist without accidental ID
   overwrite while durability is being established.

5. **Write and verify before stale deletion.** The replacement path embeds the
   bounded node set, writes the new attempt, then verifies the exact expected
   row count for that attempt. Only after verification does it delete rows for
   the same source whose `source_attempt` differs from the verified attempt.
   ChromaDB and LanceDB both perform this through the existing store-neutral
   `count_where` and `delete_where` contracts.

6. **Preserve the last searchable version on failure.** Parse/chunk and
   embedding failures happen before any new mutation. A store failure may leave
   a distinguishable partial candidate beside the old rows, but never deletes
   the old rows first. A stale-cleanup failure leaves verified new rows and old
   rows together; the next ingest detects the mixed state and retries rather
   than treating it as unchanged.

7. **Keep Stage 3A serialized.** Embedding, store write, verification, and
   cleanup remain inside the existing global write lock. Stage 3A instruments
   the serialized design; it does not widen effective ingestion concurrency.
   Any lock narrowing or parallel embedding belongs to Stage 3B only after the
   Pause Gate 3A evidence is recorded.

8. **Expose attribution before optimization.** Ingestion results include
   additive timings for change detection, parse/chunk, embedding, store write,
   lock wait, cleanup, and total elapsed time, plus best-effort process peak
   RSS. These diagnostics are evidence inputs, not Stage 5 calibration claims.

9. **Keep cache invalidation store owned.** Stage 3 orchestration never calls
   `bump_generation` directly. Each successful store mutation continues to
   invalidate its sparse-visible generation exactly once at the vector-store
   boundary, as required by ADR-047.

## Failure and Recovery Semantics

| Failure point | Durable state after failure | Next ingest |
| --- | --- | --- |
| Source hashing | Previous searchable version unchanged | Hash again; no deletion occurred |
| Parse/chunk | Previous searchable version unchanged | Parse again |
| Embedding | Previous searchable version unchanged | Embed again |
| Store write before complete candidate | Old rows plus possible partial candidate | Incomplete count prevents skip; rewrite and clean stale attempts after verification |
| Durability verification | Old rows plus whatever candidate rows were written | Mixed/incomplete state prevents skip |
| Stale cleanup | Old rows plus a complete verified new version | Mixed attempts prevent skip; next verified attempt cleans both |

An empty parse/chunk result is treated as a failed replacement, not as a valid
empty source that is allowed to erase the old searchable version. Deleting a
source intentionally remains a separate document-deletion operation.

## Validation Plan - Pause Gate 3A

This ADR is intentionally **not Accepted yet**. Acceptance requires fresh local
or CI execution of the Stage 3A gate:

- generated-corpus bounded-node-lifetime tests;
- parse, embedding, partial store-write, and stale-cleanup fault injection;
- repeated ingest, content edit, embedding-model change, parser-selector
  change, and chunk-setting change on both ChromaDB and LanceDB where the
  contract applies;
- existing Stage 0-2 regressions, with the three known Stage 4 experiment
  runner cases still deferred rather than weakened;
- Ruff formatting/checks, import-linter contracts, file-size ceiling, and
  strict OpenSpec validation.

The working implementation currently spans the Aizat-authored branch commits
from `d81b33e` through `256723d`. The eventual gate update must replace this
working range with the tested Stage 3A implementation SHA and concrete command
results before the ADR can become Accepted or Stage 3B can begin.

## Consequences

### Positive

- Peak node retention is bounded by one source file rather than total corpus
  size.
- Re-ingestion cannot intentionally remove the last good source before a
  verified replacement exists.
- Content-only equality can no longer reuse vectors produced by a different
  embedding model, parser selection, or chunk boundary configuration.
- Interrupted writes are detectable without adding a backend-specific
  transaction API to the vector-store abstraction.
- ChromaDB and LanceDB share the same source-version and recovery protocol.
- Timing and RSS evidence are available before any concurrency optimization is
  proposed.

### Negative

- A failed partial write may temporarily consume extra storage until the next
  successful replacement cleans stale attempts.
- A normal changed-source replacement performs a write plus a stale delete,
  which are two real store mutations and therefore two store-owned generation
  advances.
- Conservative index identity can reprocess a source when a configured parser
  or metadata selector changes even if that selector would not alter this
  particular file's output. This favors correctness over skip rate.
- Pre-embedding the bounded node set adds an explicit embedding phase before
  the store adapter so embedding and store-write wall time can be measured
  separately.

### Neutral

- The 500 MiB source read ceiling is unchanged; daemon and ingestion hashing now
  call the same helper.
- Existing public ingestion result keys remain, with new diagnostics and
  `files_skipped_unchanged` added rather than replacing existing fields.
- This decision does not select Stage 3B concurrency settings and does not run
  or claim Stage 5 retrieval-quality experiments.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| Delete old rows before parsing | A parser or provider failure destroys the last searchable version. |
| Hash source bytes only | Same bytes can require different vectors after model, parser, or chunk changes. |
| Reuse stable node IDs and upsert in place | Old rows can be overwritten before the complete replacement is verified. |
| Add a backend transaction API now | Neither current store needs it for a recoverable protocol, and it would widen the Stage 3 scope. |
| Store one collection-level source manifest | Concurrent sources would contend on shared metadata and recovery would still need row-level attempt identity. |
| Widen embedding concurrency in Stage 3A | It would mix correctness changes with an unmeasured scheduling optimization and violate the existing pause gate. |
| Treat a cleanup failure as success | Old-plus-new duplicates would remain searchable without making the interrupted state explicit to the caller. |

## References

- OpenSpec change:
  `openspec/changes/harden-pipeline-correctness-before-calibration/`
- Archived change-detection design:
  `openspec/changes/archive/2026-08-15-add-ingestion-change-detection/`
- Implementation:
  `src/rag_mcp/core/ingestion/{hashing,source_state,replacement,metrics,pipeline}.py`
- Store-neutral filters and mutation contracts:
  `src/rag_mcp/core/vectordb/{base,chroma,lancedb,lance_filter}.py`
- Deterministic Stage 3A tests:
  `tests/test_ingestion_stage3.py`, `tests/test_ingestion_parallel.py`,
  `tests/test_async_ingest_responsiveness.py`
- Related decisions: ADR-010 (watcher), ADR-014 (async ingestion), ADR-034
  (VectorStore abstraction), ADR-046 (LanceDB), ADR-047 (semantic store
  swappability and process-scoped embedding provider)
