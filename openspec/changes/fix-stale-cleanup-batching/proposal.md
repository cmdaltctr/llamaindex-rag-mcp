# Proposal: Batch stale-row deletion above the store id-list cap

## Why

Replacing a document whose current version holds more than 100 chunk
rows never completes its cleanup. The replacement path collects every
stale row ID for the source and passes the whole list to one
`delete_ids` call. LanceDB rejects a filter whose `$in` list exceeds
100 entries, so the cleanup stage raises, the ingest reports an
error, and the old version's rows stay in the store beside the new
version. Searches can then return both old and new text for the same
file. The failure was observed live during the exp 32 review run:
`$in list exceeds the maximum of 100 entries (got 356)`.

A second, related defect hides the first in the regression suite.
`test_partial_store_write_preserves_old_version_and_recovers` wraps
`store.write_nodes` with a stand-in that does not accept the
`embed_model` keyword. The stand-in raises `TypeError` before it
writes any partial row, so the test never performs the partial write
it claims to exercise. With short temp directories the test passes
by accident; with long ones it surfaces the batching bug.

## What Changes

- `src/omrg/core/ingestion/replacement.py`: delete stale row IDs in
  batches of 100 or fewer per `delete_ids` call, inside the existing
  cleanup stage and failure handling.
- `tests/test_ingestion_stage3.py`: fix the partial-write stand-in to
  accept and forward `embed_model`, and add a regression that
  replaces a source with more than 100 rows and asserts the old
  version is fully removed.

## Impact

- Affected specs: `async-ingestion` (one requirement amended with a
  batching scenario).
- Affected code: the stale-cleanup section of
  `replace_source_nodes_async` only. No public API, settings, store
  contract, or transport changes.
- Risk: low. Smaller delete requests are strictly weaker demands on
  every backend; Chroma is unaffected either way.
