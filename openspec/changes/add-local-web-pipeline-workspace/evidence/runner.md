# Graph runner, events and cancellation (tasks 4.1, 4.2 and 4.4)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted work tree.

Command prefix for every run (worktree `.venv`, no installs):

    PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider <files>

## Files

New modules in `src/omrg/core/pipelines/`:

| Module | Lines | Purpose |
|---|---|---|
| `runner.py` | 300 | `run_pipeline`, `RunLimits`, `UnitSplit`; per-unit loop; result assembly |
| `execution.py` | 372 | `GraphPass` (one scheduling pass), `FatalNodeError`; value routing, joins, fan-out copies, outcomes, commit guard |
| `run_state.py` | 53 | `RunState`, shared by every pass of one run |
| `scheduler.py` | 209 | `ReadyScheduler` (pure dependency counts, bound, leases), `Lease`, `lease_for` |
| `wiring.py` | 65 | `Wiring` routing tables, `SourceKey` |
| `events.py` | 109 | `EventEmitter`: per-run sequence numbers, ordered delivery to the async sink |
| `cancellation.py` | 90 | `RunCancellation`, `PipelineCancelledError`, `run_cancellation` |

Additive edits:

- `results.py`: `EventKind` gains `NODE_QUEUED`, `NODE_CANCELLED` and `UNIT_CANCELLED`. `NodeOutcome` gains `unit_id`. New `UnitOutcome`. `PipelineResult` gains `units`.
- `__init__.py`: exports `run_pipeline`, `RunLimits`, `UnitSplit`, `RunCancellation`, `PipelineCancelledError`, `FatalNodeError` and `UnitOutcome`.

New tests: `tests/unit/test_pipeline_runner.py`, `test_pipeline_runner_contracts.py`, `test_pipeline_runner_commit_guard.py`, `test_pipeline_runner_units.py`, `test_pipeline_runner_scheduler.py`, `test_pipeline_runner_support.py` (helpers), `test_pipeline_cancellation.py`.

## Test-first record

1. The tests were written before the implementation. First run: **4 collection errors** (`ImportError: cannot import name 'PipelineCancelledError' from 'omrg.core.pipelines'`).
2. After the implementation: **45 passed** in the new files.
   Commit guard (lead decision on D3), written test-first: before the change `test_failed_unit_skips_a_commit_on_an_independent_branch` **failed** (commit `succeeded`, expected `skipped`); after it, **47 passed**.
3. Mutation checks. Each check copied `src/` to a scratch directory, made one change, and ran the named test against the copy:

| Change | Test | Result |
|---|---|---|
| Join tuple reversed | `test_join_order_is_declared_order_not_completion_order` | 2 failed |
| No fan-out copy | `test_fan_out_isolates_mutable_values` | 1 failed |
| Concurrency bound ignored | `test_ready_nodes_wait_for_the_concurrency_bound` | 1 failed |
| Lease conflicts ignored | `test_model_calls_on_one_resource_are_serialised` | 1 failed |
| No dependant skipping | `test_node_failure_skips_dependants_and_names_the_node` | 1 failed |
| Fallback not reported | `test_domain_fallback_is_an_outcome_not_a_failure` | 1 failed |
| No stop check before dispatch | `test_cancellation_before_commit_prevents_the_commit` | 1 failed |
| Running tasks cancelled on request | `test_entered_commit_completes_before_terminal_cancel` | 1 failed |
| Outer task cancellation propagates at once | `test_cancelling_the_run_task_still_finishes_the_commit` | 1 failed |
| Later units stop after one unit fails | `test_failed_file_keeps_sibling_commits` | 1 failed |
| Each unit pass kept in a module list | `test_unit_values_are_released_before_the_next_unit` | 1 failed |
| Commit guard removed | `test_failed_unit_skips_a_commit_on_an_independent_branch` | 1 failed, 1 passed |
| Commit guard skips every ready sibling, not only commits | `test_failed_unit_skips_a_commit_on_an_independent_branch` | 1 failed, 1 passed |

## Scenario coverage

| Spec scenario or task check | Test |
|---|---|
| Branches finish in different orders (4.1) | `test_join_order_is_declared_order_not_completion_order[dense,sparse]` |
| One branch has no results | `test_empty_branch_is_valid_join_input` |
| Mutable fan-out isolation (4.1) | `test_fan_out_isolates_mutable_values` |
| Resource limit is reached (4.1) | `test_ready_nodes_wait_for_the_concurrency_bound`, `test_model_calls_on_one_resource_are_serialised`, `test_lease_rules_are_configurable`, scheduler tests |
| A node fails; skipped dependants (4.2) | `test_node_failure_skips_dependants_and_names_the_node` |
| Domain fallbacks (4.2) | `test_domain_fallback_is_an_outcome_not_a_failure` |
| Failed unit starts no further source commit (lead decision on D3) | `test_failed_unit_skips_a_commit_on_an_independent_branch`, `test_entered_commit_completes_when_a_sibling_fails` |
| Directory per-file outcomes (4.2) | `test_failed_file_keeps_sibling_commits`, `test_each_source_runs_the_graph_once`, `test_fatal_error_stops_later_units` |
| Directory ingestion remains bounded | `test_unit_values_are_released_before_the_next_unit` (weak references) |
| Actual, ordered events (4.2) | `test_events_are_ordered_actual_transitions`, `test_node_events_carry_the_unit`, `test_progress_events_belong_to_their_node` |
| Durations overlap | `test_wall_time_is_measured_not_summed` |
| Queued cancellation (4.4) | `test_queued_nodes_are_cancelled` |
| Cancellation precedes commit (4.4) | `test_cancellation_before_commit_prevents_the_commit` |
| Cancellation arrives during commit (4.4) | `test_entered_commit_completes_before_terminal_cancel`, `test_cancelling_the_run_task_still_finishes_the_commit` |
| Blocking inference continues (4.4) | `test_blocking_call_finishes_at_a_safe_boundary` (real worker thread) |
| Sibling or later work sees the same cancellation | `test_adapter_stops_at_its_own_safe_boundary`, `test_cancellation_between_units_keeps_earlier_commits` |

Ordering in every test uses asyncio events or a thread event. No test sleeps to order work. `Recorder.wait_for` has a 5-second guard so a broken runner fails instead of hanging.

## Final results

| Command | Result |
|---|---|
| `tests/unit/test_pipeline_*.py`, `tests/test_pipeline_import_boundaries.py`, `tests/test_no_global_settings_reads.py` | 221 passed |
| New runner and cancellation files, three repeated runs | 47 passed each time |
| `ruff check` and `ruff format --check` on the package and the pipeline tests | clean |
| `PYTHONPATH=src lint-imports` | 12 kept, 0 broken |
| `tests/test_file_size_ceiling.py` | 1 passed. All runner modules are below 400 lines. |

## Decisions and limits

- Leases come from descriptor capabilities. Effects in `RunLimits.exclusive_effects` (default `MODEL_CALL` and `SOURCE_COMMIT`) lease every capability exclusively. Other nodes lease them as shared. Leases are per run. Serialising two concurrent runs on one Engine belongs to task 4.3.
- A node failure skips its transitive dependants. Independent read-only, pure and model-call branches in the same unit continue. A `SOURCE_COMMIT` node in that unit that has not started is skipped, even on an independent branch; the skip event names the failed node (lead decision on D3). A commit that has started finishes. `FatalNodeError` stops all further work, including later units.
- With `UnitSplit`, nodes downstream of the split port run once per unit and receive `(unit,)` on that port. All other nodes run once, before the units. Values from that first pass are copied for each unit.
- Per-unit graph outputs stay in `UnitOutcome.outputs`. Graph outputs should be summaries, because they are kept for every unit.
- A `RunCancellation` wakes the runner at once. Any other token becomes its parent and is checked at the next scheduling point.
- Event sink failures are logged and the run continues, so an entered commit is never abandoned.
- If the task that awaits `run_pipeline` is cancelled while nodes run, the runner requests cooperative cancellation, waits for started nodes, emits `run_cancelled`, then raises `CancelledError`.
