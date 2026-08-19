# TDR-013: Narrow the Ingestion Write Lock to the Mutation Section

**Date:** 2026-08-19
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Tags:** ingestion | concurrency | stage3b | experiment-18

## Context

ADR-048 (bounded, failure-safe ingestion) deliberately kept Stage 3A
serialised. Its decision 8 places embedding, candidate write, durability
verification, stale scan, and cleanup inside the process-global
`threading.Lock` in `core/ingestion/_state.py`, and instruments that
serialised design rather than widening effective ingestion concurrency.
Lock narrowing or parallel embedding is a Stage 3B question only after Pause
Gate 3A evidence exists (ADR-048 decision 8).

design.md §D12
(`openspec/changes/harden-pipeline-correctness-before-calibration/design.md`)
forbids widening concurrency without measurement: only if embedding
concurrency is demonstrably constrained by the current lock scope SHALL a
follow-up commit separate embedding from the write-critical section.

The pipeline itself is a sequential per-file loop (`pipeline.py`), so
single-stream ingestion never contends with itself. Contention arises only
from concurrent ingest operations in one process: the watch daemon throttles
two concurrent ingests through `MAX_CONCURRENT_INGESTS = 2`
(`daemon/watcher.py`), and concurrent MCP tool calls can run a delete during
an ingest.

### Measured bottleneck (Experiment 18)

Phase A gates H1–H5 all passed at baseline commit `25f130f`. The two-stream
contended ingest of the same 100-file corpus with real Ollama embeddings
showed: contender lock wait 95.6% of wall time, contended speedup vs
sequential 1.002 — fully serialised, because embedding happens inside the
lock and dominates the critical section (sequential wall ~19 s, of which
embedding is the overwhelming majority; store write + verify + cleanup are
sub-second per hundred files). The store-mutation-bound fake-embedding block
showed lock wait 16.4% and speedup 1.14, confirming embedding, not store
mutation, is the constraint.

## Decision

1. **Hoist embedding and attempt stamping above the lock.** In
   `core/ingestion/replacement.py::_replace_sync`, move
   `_embed_missing_nodes` (with the embed semaphore) and
   `stamp_source_attempt` to run before `with write_lock:`.
2. **Keep mutation, verification, and cleanup inside the lock.**
   `write_nodes`, `count_where` durability verification, the bounded stale
   scan, and `delete_ids` stay inside the lock, in the tested Stage 3A order.
3. **The embed semaphore, not the write lock, now bounds concurrent
   embedding.** With `embed_concurrency` (default 2) the semaphore admits
   two simultaneous embeddings.
4. **Stored row identity is unchanged.** Row IDs are derived during
   `stamp_source_attempt` (`core/ingestion/source_state.py`), which also adds
   every source key to `excluded_embed_metadata_keys` /
   `excluded_llm_metadata_keys`, so vectors and row IDs are bit-identical to
   the in-lock ordering regardless of where stamping runs. Nodes are
   caller-private between parse and write, so stamp/embed outside the lock is
   thread-safe.
5. **ADR-048 failure ordering is unchanged.** Write → verify → stale-delete
   stays inside the lock; embedding failure still occurs before any
   mutation; each successful non-empty mutation still advances the collection
   generation exactly once.

## Evidence — Experiment 18 A/B

Arms differ ONLY in `src/rag_mcp/core/ingestion/replacement.py`: baseline
Stage 3A via explicit-path `git checkout` of commit `25f130f`, treatment
`b4b01b6`, identical harness. Timing cells ran as 3 interleaved repetitions
per arm, each in its own subprocess with a fresh isolated Chroma store.
Real block = Ollama `nomic-embed-text`; deterministic 100-file corpus.

### Real-embed contended (100 files, 2 streams)

| Rep | Baseline docs/s (Stage 3A) | Treatment docs/s (Stage 3B) | Baseline lock-wait fraction | Treatment lock-wait fraction |
| --- | --- | --- | --- | --- |
| 1 | 5.48 | 7.40 | 0.9671 | 0.0000 |
| 2 | 5.57 | 7.35 | 0.9663 | 0.0000 |
| 3 | 5.42 | 7.44 | 0.9670 | 0.0000 |
| Mean | 5.49 | 7.40 | 0.9668 | 0.0000 |

- Contended throughput +34.7%; per-rep ranges do not overlap (5.42–5.57 vs
  7.35–7.44).
- Contender lock-wait fraction 96.7% → 0.0%.
- Peak RSS ratio (treatment over baseline) 0.99 — no memory regression.

### Fake-embed contended

Baseline mean 36.48 → treatment mean 36.28 docs/s (-0.6%, noise; instant
embeddings never had an embed bottleneck).

### Gates

| Gate | Criterion | Result |
| --- | --- | --- |
| H6 | contended docs/s ≥ 20% improvement | PASS (+34.7%) |
| H7 | peak RSS ≤ 1.25× baseline and Phase A H1–H5 green on treatment | PASS (RSS ratio 0.99; correctness re-run green) |

### Treatment correctness re-run

Executed against `b4b01b6` with the same harness:

- bounded_25 / bounded_100 / bounded_400: all files indexed (54 / 212 / 836
  chunks); the unchanged second ingest skipped 100% of files with zero chunks
  created;
- fault cells parse / embed / store_write: old version survived
  (`old_version_survived: true`) and the recovery ingest completed the swap
  (`swap_completed: true`) in all three;
- modified_25: exactly 1 of 25 files re-indexed, 24 skipped.

Raw JSON: `output/results.ab.json`, `output/cells_stage3{a,b}_rep*/`, and
`output/cells_stage3b_correctness/` under
`experiments/18-ingestion-lock-scope-ab-2026-08-19/`.

Harness note: the first A/B attempt reused per-cell store directories across
repetitions, so later rounds measured unchanged-skip paths instead of fresh
ingests; those cells were discarded. The fix scopes each store under its
cells directory (`chroma_{cells_dir().name}_{cell_id}`). All published
numbers come from the fixed harness.

## Implementation

- Commit `b4b01b6` — `feat(ingestion): narrow write lock to the mutation
  section (Stage 3B)`. Single-file production change in
  `core/ingestion/replacement.py` plus its regression test file.
- Regression tests written failing-first in
  `tests/test_ingestion_stage3b_narrow_lock.py` (embedding proceeds while
  the lock is held elsewhere; concurrent replacements overlap embedding;
  source metadata never enters embed text; write/verify/cleanup remain
  inside the lock).
- Full fast suite at implementation: 1622 passed, 17 skipped, 3 failed —
  exactly the deferred Stage 4 Experiment 10b/13/14 audit reds, untouched by
  this design.

## Consequences

### Positive

- Concurrent ingest operations in one process (daemon dual ingest, delete
  during ingest) no longer serialise on embedding: +34.7% contended docs/s
  with real embeddings on this hardware.
- No correctness or memory trade: failure table, exactly-once generation,
  bounded retention, and stored row identity are unchanged.
- The embed semaphore is now the effective concurrency limiter, matching the
  ADR-047 contract that embedding-provider concurrency is process scoped.

### Negative

- A shutdown arriving mid-embed wastes at most one bounded source's embed
  work (the mid-embed shutdown check moved out with the embed; the lock-side
  check before `write_nodes` remains).

### Neutral

- Single-stream throughput is unchanged by design; gains apply only to
  concurrent in-process callers.
- `embedding_seconds` and `lock_wait_seconds` changed meaning across arms:
  embedding time is now captured outside the lock and lock wait measures the
  narrowed section.

## Alternatives Considered

| Option | Rejected because |
| --- | --- |
| D1b — hoist embed+stamp and write via `upsert_precomputed` | `upsert_precomputed` cannot reproduce `write_nodes` row identity/layout: LanceDB fills `doc_id` with nulls and tables it creates lack the adapter's internal metadata keys; Chroma would duplicate upstream `node_to_metadata_dict` by hand. A store-contract change beyond lock scope. |
| D2 — per-collection locks | Both realistic contention sources (daemon dual ingest, delete-during-ingest) write the SAME collection, so per-collection locks buy nothing for the default workload, and complicate the per-collection `bump_generation` invariant. |
| D3 — batched writes under a short lock | Changes failure granularity to multi-source, violating ADR-048's per-source failure table and bounded retention. |
| D4 — reject outright | Rejected by measurement: contender lock wait 96.7% of wall demonstrated the lock was the constraint. |

## Known Limits

- Single-stream throughput is unchanged by design: the per-file loop is
  sequential, and overlapping embed(N+1) with write(N) is a pipeline
  restructuring outside Stage 3B scope.
- Gains apply only when concurrent ingest operations run in one process.
- Conclusions measured on ChromaDB local only; the LanceDB block is
  untested.

## Rollback

Revert commit `b4b01b6` — a single-file production change in
`core/ingestion/replacement.py` plus its test file. No store or data
migration is involved; stored row identity is unchanged, so a rollback needs
no re-ingest.

## Revisit Triggers

- A pipeline restructuring that overlaps embed(N+1) with write(N) (new
  bounded-retention analysis and its own ADR).
- LanceDB block measurement under the narrowed lock.
- Widening to per-collection locks if multi-collection write contention ever
  becomes a measured constraint.

## References

- ADR-048 (bounded, failure-safe ingestion) — decision 8 keeps Stage 3A
  serialised; this TDR records the Stage 3B follow-up it authorised.
- `openspec/changes/harden-pipeline-correctness-before-calibration/design.md`
  §D12 (measure before widening concurrency).
- `openspec/changes/harden-pipeline-correctness-before-calibration/tasks.md`
  tasks 3.6.1–3.6.4 (Stage 3B) and 3.GB.1–3.GB.2 (gate bookkeeping).
- Experiment 18 protocol and results:
  `experiments/18-ingestion-lock-scope-ab-2026-08-19/{protocol,results,design-notes,test-contract-map}.md`,
  `output/results.ab.json`, `output/cells_stage3{a,b}_rep*/`,
  `output/cells_stage3b_correctness/`.
- Implementation: commit `b4b01b6`; regression tests
  `tests/test_ingestion_stage3b_narrow_lock.py`.
- Baseline commit `25f130f` (experiment 18 gate, Stage 3A).
- test-contract-map.md §2: 0 contracts would break by design; 3 adaptable.
