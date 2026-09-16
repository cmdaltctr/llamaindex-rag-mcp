# Design: Batch stale-row deletion above the store id-list cap

## Context

`replace_source_nodes_async` (Stage 3 replacement) writes and verifies
the new version, then selects stale row IDs source-scoped via
`_stale_source_ids` and deletes them in a single
`store.delete_ids(collection_name, stale_ids)` call. LanceDB builds an
`$in` filter from that list and hard-rejects lists longer than 100
entries. Any source whose previous version holds more than 100 rows
therefore fails the cleanup stage after the new version is already
durable: the operation reports `stale_cleanup`, and old rows persist
next to the new ones.

## Goals / Non-Goals

- Goal: a successful replacement removes every stale row regardless of
  row count, on every store backend.
- Goal: a mid-cleanup failure keeps the existing safety property — the
  new durable version stays searchable and a later ingest retries the
  remaining stale rows (the stale selection re-runs from scratch).
- Non-goal: changing the store contract, `delete_ids` signatures, or
  batching inside the LanceDB adapter. The call site fix protects
  every backend at once and keeps the store honest about what a single
  call accepts.
- Non-goal: performance tuning of the stale scan. Selection is already
  source-scoped.

## Decisions

### D1: batch at the replacement call site, limit 100

Slice `stale_ids` into chunks of at most 100 and issue one
`delete_ids` per slice, all inside the existing cleanup `try` block.
A module constant `STALE_DELETE_ID_BATCH_LIMIT = 100` carries the
limit with a comment naming the LanceDB `$in` cap as the binding
constraint. 100 is safe for every backend: no store rejects a shorter
ID list, and Chroma's delete path has no per-call minimum.

Alternatives rejected:
- Batching inside the LanceDB adapter: fixes one backend and hides a
  real protocol limit from callers.
- A store capability probe ("max ids per call"): speculative machinery
  for a single known constant.

### D2: fix the test stand-in, not the production signature

The partial-write test's `partial_then_fail` wrapper gains
`embed_model=None` and forwards it to the original `write_nodes`. This
restores the intended sequence: one candidate row becomes durable, the
write then raises, and the recovery path must clean both the old
version's rows and the orphan partial row.

## Risks / Trade-offs

- Partial-batch failure leaves some stale rows deleted and others not.
  This is the same recovery story as today's single-call failure: the
  next ingest re-selects stale rows for the source and retries. The
  failure-safe ordering (delete only after the new version is
  verified) is untouched.
- The regression test must produce more than 100 rows deterministically
  and independently of temp-directory path length, because row count
  feeds chunk metadata length. A fixed corpus with `chunk_size=64`
  yields roughly 150 rows; the test asserts `chunks_created > 100`
  before proceeding so the premise is checked, not assumed.

## Migration Plan

Single commit on the current feature line: tests first (red), then the
batching fix and test stand-in correction (green). No settings, env
vars, or data migrations involved.

## Open Questions

None.
