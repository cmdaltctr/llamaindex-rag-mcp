# Tasks: Batch stale-row deletion above the store id-list cap

## 1. Regression tests (red first)

- [x] 1.1 Fix `test_partial_store_write_preserves_old_version_and_recovers`: the `partial_then_fail` stand-in accepts `embed_model=None` and forwards it to the original `write_nodes`, so the partial row is actually written before the injected failure. Confirm the test still exercises failure and recovery.
- [x] 1.2 Add `test_replacement_over_one_hundred_rows_removes_all_stale_rows`: ingest a source that asserts `chunks_created > 100`, replace its content, and assert the second ingest reports `status == "ok"`, `chunks_removed` equals the first version's row count, and no old-version text remains in the store. Run both tests and confirm they FAIL on the current code, recording the failure output as evidence. (Evidence: batching test failed with the production error `$in list exceeds the maximum of 100 entries (got 268)`; the partial-write test failed on long temp paths for the same reason, and its premise defect was confirmed by inspection.)

## 2. Implementation

- [x] 2.1 In `src/omrg/core/ingestion/replacement.py`, add module constant `STALE_DELETE_ID_BATCH_LIMIT = 100` with a comment naming the LanceDB `$in` cap. Replace the single `delete_ids` call in the cleanup stage with a loop issuing one call per slice of at most 100 IDs, inside the existing try/except so a batch failure still raises `stale_cleanup` with the current message shape.

## 3. Verification

- [x] 3.1 Run the two tests from task 1 and confirm both PASS. Run the full `tests/test_ingestion_stage3.py` suite and confirm no regression. (2 targeted tests pass; whole file 20 passed on short temp paths; both tests also pass on the long temp paths that originally failed; `tests/test_lineage_store_contract.py` 34 passed; ruff check and format clean.)
- [x] 3.2 Run `openspec validate fix-stale-cleanup-batching --strict` and confirm it passes.
- [x] 3.3 Defer the full local CI gate to the operator's chosen time; record that it was not run in this session.

## 4. Close-out

- [x] 4.1 Commit the tests and fix with a Conventional Commit message on the current feature line. (`ba338b0`)
