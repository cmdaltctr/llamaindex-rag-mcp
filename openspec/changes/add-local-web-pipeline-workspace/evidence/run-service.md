# Local run service (tasks 5.2, 5.3, 5.4)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`.
Design D6 and D7. Spec `pipeline-run-records`.

## Files

New modules in `src/omrg/core/workspace/`:

- `jobs.py`: `RunJob` (immutable snapshot), `Admission`, `Admitter`, `RunExecutor`, `JobQueue`, typed errors.
- `service.py`: `RunService` (admission, queue, consumer, cancel, retry, start, shutdown).
- `outcomes.py`: `RunRecorder` (runner events, terminal records, completed-effect evidence).
- `events.py`: `RunEventLog` (commit, then wake; replay; async subscribe).
- `artefacts.py`: `ArtefactStore`, `to_jsonable`, `bound_preview`, `preview`, limits.
- `redaction.py`: `redact`, `redact_text`, `contains_secret`, `is_secret_key`, `REDACTED`.

Changed files:

- `core/workspace/records.py` and `integrations/workspace_sqlite/repository.py`: new
  nonterminal status `cancelling`. Transitions: `running -> cancelling`, `cancelling -> terminal`.
  `queued -> cancelling` is refused. No schema change; the status column has no CHECK.
- `core/workspace/__init__.py`: new exports. `RunService`, `ShutdownReport` and
  `RETRYABLE_STATUSES` load on first use (PEP 562). Thus `import omrg.core.workspace` still
  does not import `omrg.core.pipelines` (`test_workspace_contracts.py` checks this).

Tests: `tests/unit/test_workspace_service.py`, `test_workspace_service_outputs.py`,
`test_workspace_service_lifecycle.py`, `test_workspace_artefacts.py`, and the shared fakes in
`test_workspace_service_support.py`. All use a real `SqliteWorkspaceRepository` on `tmp_path`
and a fake executor that asyncio events control. Every wait has a time limit.

## Decisions

- **Executor contract.** `executor(job, *, on_event, cancellation) -> PipelineResult`.
  `on_event` is async, the same as the runner `EventSink`. `cancellation` is a
  `RunCancellation`, so the runner wakes when cancel is requested. Composition must pass
  `run_id=job.run_id` to `run_pipeline`. The service ignores `PipelineEvent.sequence`; the
  repository assigns the per-run sequence.
- **Admission.** An injected `admit(revision, inputs) -> Admission` runs on every submit and
  every retry. It returns settings, resource identities and an opaque payload (for example an
  `AdmissionSnapshot`). An admission error writes no record.
- **Queue.** At most 16 waiting jobs by default (`max_waiting`). The active job does not count.
  The capacity check runs before admission and before any record. Excess gives
  `QueueFullError(limit)`.
- **Snapshot.** `RunJob` is a frozen dataclass. The document, inputs, redacted settings and
  redacted resources are canonical JSON text. Properties return fresh copies.
- **Status and event.** Each change goes through `record_update` (one transaction). The log
  wakes subscribers after the commit returns. Subscribers read committed rows only.
- **Cancelling.** A queued run becomes `cancelled` at once and never executes. A running run
  records `cancelling` (reason in the event) and sets the token. A blocking call can still
  finish; the executor result then decides the terminal state.
- **Supervision.** The consumer catches each job's errors. If the terminal write fails, the
  service records `failed` with "the run service could not record the result" and continues.
- **Inputs.** Inputs that hold a credential are refused (`UnsafeInputError`). Stored inputs
  therefore stay exact, and retry can reuse them.
- **Redaction.** A credential key (for example `api_key`, `token`, `Authorization`) loses its
  value. Text loses bearer values, URL user information, credential query parameters,
  `key=value` credentials and known provider key shapes. `max_output_tokens` is kept.
- **Bounds.** Previews keep 100 rows and 4 KiB of text. An event summary is at most
  16 KiB. Vectors become `{"omitted": "vector data", "length": n}` everywhere, artefacts
  included. A cut summary gets `truncated: true` and an `artefact_ref`.
- **Artefacts.** `<workspace>/artefacts/<run_id>/<name>.json`. New directories 0o700, files
  0o600, atomic write. A reference cannot leave the root. The full redacted result is the
  `result` artefact and the run's `result_ref`.
- **Timing.** The terminal event has `wall_time_s` (measured by the service),
  `runner_wall_time_s`, and `node_durations_s` per node. No field sums node durations.
- **Restart.** `start()` marks `queued`, `running` and `cancelling` runs `interrupted`. The
  event has `previous_status`. The failure lists completed effects from stored
  `effect_committed` events. The service does not run them again.
- **Shutdown.** Stop admission, cancel waiting runs, request cancellation of the active run,
  wait up to `timeout`. On timeout the consumer task is cancelled and the run is
  `interrupted`. A second call returns the same `ShutdownReport`.
- **Retry.** Only `retry(run_id)` repeats a run, and only from `failed`, `cancelled` or
  `interrupted`. It creates a new run (`origin="retry"`, `source_run_id`) from the stored
  revision and inputs, with fresh admission. The source record does not change.
  `submit(..., origin="repeat")` records an explicit repeat of a saved revision.

## Test-first record

Environment: WT `.venv`, `PYTHONPATH=src`, `PDF_READER=pypdf`.

Before implementation:

    python -m pytest -q -p no:cacheprovider tests/unit/test_workspace_service.py \
      tests/unit/test_workspace_service_outputs.py tests/unit/test_workspace_service_lifecycle.py \
      tests/unit/test_workspace_artefacts.py tests/unit/test_workspace_service_support.py

Result: **5 errors during collection** (the new names did not exist). FAIL as expected.

After implementation, all workspace tests plus guards:

    python -m pytest -q -p no:cacheprovider tests/unit/test_workspace_*.py \
      tests/test_file_size_ceiling.py tests/test_contract_coverage.py \
      tests/test_pipeline_import_boundaries.py

Result: **159 passed**, 0 failed. This includes the 37 task 5.1 tests, which stay green.

## Mutation checks

Script: copy `src/` to a scratch folder, make one change, run the four new test files.

| Id | Change | Result |
|---|---|---|
| M1 | No waiting-job limit | 1 failed |
| M2 | A job failure stops the consumer | 1 failed |
| M3 | Executor errors not caught | 1 failed |
| M4 | No key-based redaction | 12 failed |
| M5 | No text redaction | 14 failed |
| M6 | Restart does not interrupt stale runs | 2 failed |
| M7 | Artefact files 0o644 | 2 failed |
| M8 | Wall time is the sum of node durations | 1 failed |
| M9 | Cancel does not set the token | 3 failed |
| M10 | No 4 KiB text bound | 3 failed |
| M11 | No 100-row bound | 2 failed |
| M12 | Shutdown keeps queued jobs | 1 failed |
| M13 | `RunJob` not frozen | 1 failed |
| M14 | Retry records origin `submit` | 1 failed |
| M15 | Retry allowed from any state | 2 failed |
| M16 | Subscriber skips an event | 4 failed |
| M17 | Artefact path traversal allowed | 4 failed |
| M18 | Inputs with credentials accepted | 1 failed |
| M19 | Queued cancel does not remove the job | 1 failed |
| M20 | Shutdown timeout does not interrupt | 1 failed |
| M21 | Wake subscribers before the commit | 0 failed (equivalent) |

M21 cannot be seen. Subscribers read committed rows only, so an early wake makes them read
nothing new and wait again. `test_failed_commit_wakes_no_subscriber` proves that a failed
commit delivers no event.

M16 first made the subscriber spin without a pause. `subscribe` now stops when a terminal
run returns no new rows.

## Static checks

- `ruff format --check` and `ruff check` on all new and changed files: clean.
- `lint-imports`: 12 contracts kept, 0 broken.
- Largest new file: `service.py`, 392 lines.
- Branch coverage of `omrg.core.workspace` from the new tests: 95%.

## Not covered here

- Composition: build `RunService` with the SQLite repository, an `ArtefactStore` under the
  workspace, an admitter around `admit_pipeline`, and an executor around `run_pipeline`.
- The SSE route (it uses `RunService.subscribe` and `replay`).
- Cleanup of artefacts (task 5.5). Artefacts live under `<workspace>/artefacts/<run_id>/`.
- One workspace file must have one service. Two processes on the same file would mark each
  other's runs `interrupted` at start. The web lifespan must hold a workspace lock.
