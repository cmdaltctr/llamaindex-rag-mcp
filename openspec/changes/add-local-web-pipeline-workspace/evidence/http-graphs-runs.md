# HTTP graph and run services (task 6.6)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted work tree.
Design D6, D7, D8. Specs `local-web-workspace`, `pipeline-run-records`, `pipeline-graphs`.

## Files

| File | Lines | Change |
|---|---|---|
| `src/omrg/transports/api/runs_wiring.py` | 275 | New. `RunAdmitter`, `build_executor`, `WorkspaceRuns`, `build_workspace_runs` (= `run_service_factory`), `get_runs`/`RunsDep`, `describe_operations`. |
| `src/omrg/transports/api/routes_graphs.py` | 272 | New. Catalogue, pipelines, layout, revisions, validation. |
| `src/omrg/transports/api/routes_runs.py` | 394 | New. Runs, events (polling and SSE), cancel, retry, workspace cleanup. |
| `src/omrg/transports/api/routes_jobs.py` | 186 | Rewritten. Ingestion and codebase-map jobs now run on the workspace `RunService`. `JobBook` is removed. |
| `src/omrg/transports/api/lifespan.py` | 309 | Additive. `WorkspaceLock`/`WorkspaceLocked`, `Admission.wait_closed()`, `WebRuntime.loop`, `request_shutdown(app)`; the lifespan holds the lock. Names come from `WorkspaceLayout`. |
| `src/omrg/transports/api/app.py` | | Two router lines (`graphs_router`, `runs_router`). |
| `src/omrg/transports/cli/web.py` | | Passes `run_service_factory`; probes the workspace lock before serving; a `uvicorn.Server` subclass calls `request_shutdown` in `handle_exit`. |
| `web/src/api/bootstrap.ts`, `web/src/api/bootstrap.test.ts`, `web/src/main.tsx` | | Bootstrap fragment exchange. |
| `tests/unit/test_web_graphs.py`, `test_web_runs.py`, `test_web_runs_stream.py`, `test_web_runs_service.py`, `test_web_runs_support.py` (helpers) | | New (46 tests). |
| `tests/unit/test_web_documents_jobs.py` | | Builds the app with the run-service factory. |

## Composition

- `build_workspace_runs(runtime)` builds `SqliteWorkspaceRepository(layout.records)`,
  `ArtefactStore(layout.artefacts)`, `RunService(repository, executor, admit=RunAdmitter(engine), artefacts)`
  and `WorkspaceCleanup.for_layout(repository, layout)`, with `layout = WorkspaceLayout(config.workspace)`.
  The result `WorkspaceRuns` satisfies `RunServiceHook`. The lifespan starts it after the Engine and shuts it down before `engine.close()`.
- **Admission once.** `RunAdmitter` calls `Engine.validate_pipeline(document, inputs=inputs)` and returns
  `Admission(settings, resources, payload=AdmissionSnapshot)`. Settings are recorded per collection: profile, origin and dumped settings.
  The run service redacts them. Resources hold `graph_identity`, `schema_version` and `operations` (`node -> op@version`).
  The executor calls `Engine.run_pipeline(snapshot, on_event=..., cancellation=...)` with that snapshot.
  It never re-admits the revision. Retry runs fresh admission (run-service rule).
- **Document jobs on the same service.** I chose the smaller change: no `core/workspace` edit.
  Each job kind (`ingest`, `codebase_map`) has one reserved pipeline, marked by the layout key `omrg_task`.
  Its revision is `{"task": kind}`. `WorkspaceRuns.submit_task` sets a pending `TaskWork` on the admitter for one synchronous `submit` call.
  Only the jobs routes call it. A graph submission or retry of a job revision therefore gets graph validation and fails.
  The run routes also hide job runs (404). Results are a `PipelineResult` with `outputs={"result": value}`.
  `GET /v1/jobs/{id}` reads them from the result artefact. Job statuses map `queued->queued`, `running|cancelling->running`,
  `succeeded->completed` and anything else to `failed`. The `Job` shape and error envelope do not change.
  `job_id` is the run id in UUID form. Jobs now get persisted records, interruption at the next start, and cancellation when waiting at shutdown.
  The shared 16-job queue limit applies to jobs too. A running Engine call has no safe stop point, so the executor shields it.
  When shutdown cancels the consumer, the call finishes before the Engine closes.
- **Workspace lock.** `fcntl.flock(LOCK_EX | LOCK_NB)` on `<workspace>/.lock` (mode 0600), held by the lifespan.
  The CLI probes it first. A second `omrg web` on the same workspace prints
  "Another OMRG web server is using the workspace … start this one with a different --workspace." on stderr and exits 1.
- **Shutdown with open streams.** Uvicorn waits for open connections before the lifespan shutdown runs.
  An SSE stream that waits for lifespan shutdown would therefore block shutdown forever.
  The CLI server subclass calls `request_shutdown(app)` in `handle_exit`. That call closes admission thread-safely
  (`loop.call_soon_threadsafe`). Every stream waits on `Admission.wait_closed()` and ends with a `server.closing` frame.

## Routes (for task 6.7)

All bodies use `extra="forbid"`. Success bodies are `{"status": "ok", ...}`.
Errors use the envelope `{"status": "error", "message", "error_type"?}`.
Validation failures add `issues: [{code, message, node_id, port, edge, lever}]` with `error_type: "validation"` and status 422.
The scope dependency runs first, so 401/403 come before 503/404.

| Method | Path | Scope | Request | Success | Errors |
|---|---|---|---|---|---|
| GET | `/v1/pipeline-operations` | read | — | 200 `{operations: [catalogue entry]}`. Entry = `OperationDescriptor.to_schema()` + `available`, `unavailable_reasons[]`, `adapter_ref`. | 503 |
| POST | `/v1/pipelines` | graph | `{title (1..200), layout?: object}` | 201 `{pipeline: PipelineRecord}` | 400 reserved layout key `omrg_task` |
| GET | `/v1/pipelines` | read | — | 200 `{pipelines: [PipelineRecord]}` (job pipelines hidden) | |
| GET | `/v1/pipelines/{pipeline_id}` | read | — | 200 `{pipeline, current_revision: RevisionRecord or null}` | 404 |
| PUT | `/v1/pipelines/{pipeline_id}/layout` | graph | `{layout: object}` | 200 `{pipeline}`; no revision is created | 404, 409 job pipeline, 400 reserved key |
| POST | `/v1/pipelines/{pipeline_id}/revisions` | graph | `{document: graph or {graph, layout}}` | 201 `{revision, created: true}` or 200 `{revision, created: false}` (content-hash dedupe). Stores the normalised graph only. | 404, 409, 422 (`parse_definition` issues, for example `unsupported_schema_version`) |
| GET | `/v1/pipelines/{pipeline_id}/revisions` | read | — | 200 `{revisions: [RevisionRecord]}` | 404 |
| GET | `/v1/pipelines/{pipeline_id}/revisions/{revision_id}` | read | — | 200 `{revision}` | 404 |
| POST | `/v1/pipelines/validate` | graph | `{document, inputs?: object, collection?: str}` | 200 draft: `{valid: true, admitted: false, order, resolved_versions, collections}`. With inputs: `{valid: true, admitted: true, graph_identity, order, collections: [{name, profile, profile_origin}], nodes: [{node_id, operation, version, enabled, collection, controls: [{lever, value, source, detail}]}]}` | 422 issues |
| POST | `/v1/runs` | run | `{revision_id, inputs?: object, origin?: "submit" or "repeat"}` | 202 `{run: RunRecord}` (status `queued`) | 404 unknown or job revision, 422 issues (no record written), 429 queue full, 400 credential in inputs or non-JSON inputs, 503 |
| GET | `/v1/runs` | read | query `pipeline_id?`, `status?` (repeatable), `limit` 1..500 (100) | 200 `{runs: [RunRecord]}`, newest first, job runs hidden | 400 |
| GET | `/v1/runs/{run_id}` | read | — | 200 `{run: RunRecord}` | 404 |
| GET | `/v1/runs/{run_id}/result` | read | — | 200 `{run_id, result: redacted PipelineResult JSON + wall_time_s}` | 404 no run or no result |
| POST | `/v1/runs/{run_id}/cancel` | run | — | 200 `{run}`: queued becomes `cancelled`; active becomes `cancelling`; a terminal run is returned unchanged | 404, 409 |
| POST | `/v1/runs/{run_id}/retry` | run | — | 202 `{run}`: a new run with `origin: "retry"` and `source_run_id`; the source run does not change | 404, 409 not failed/cancelled/interrupted, 422, 429 |
| GET | `/v1/runs/{run_id}/events` | read | query `after_sequence` ≥0 (0), `limit` 1..500 (500) | 200 `{run_id, run_status, events: [RunEventRecord], last_sequence, complete}` | 404 |
| GET | `/v1/runs/{run_id}/events/stream` | read | header `Last-Event-ID` (wins), or query `after` ≥0 | 200 `text/event-stream`, `Cache-Control: no-store`. First `retry: 3000`. Then each event: `id: <sequence>`, `event: <kind>`, `data: <RunEventRecord JSON>`. Ends with `event: run.end` `data: {status, last_sequence}`, or `event: server.closing` at shutdown. | 400 bad `Last-Event-ID`, 401, 403, 404 |
| POST | `/v1/workspace/cleanup/preview` | manage (session only) | `{selector: {older_than_days?: ≥0, statuses?: [str] (≤8), run_id?: str}}` | 200 `{preview: CleanupPreview.as_dict()}` (`token`, `selector`, `expires_at`, `runs`, `skipped`, `warnings`, `totals`) | 404 unknown run, 422 invalid selector, 403 bearer |
| POST | `/v1/workspace/cleanup` | manage (session only) | `{token, selector?}` | 200 `{result: {runs_removed, events_removed, files_removed, bytes_removed, failed: [{item, reason}], skipped: [...]}}` | 409 "… (`unknown`/`expired`/`selector`/`stale`). Preview again.", 422 |
| POST | `/v1/ingestions` | files (session) | unchanged `IngestRequest` | 202 `Job` (unchanged shape) | 403, 429, 503 |
| POST | `/v1/codebase-maps` | files (session) | unchanged | 202 `Job` | 403, 429, 503 |
| GET | `/v1/jobs/{jobId}` | read | — | 200 `Job` | 404 (also for graph runs and non-UUID ids) |

Records: `PipelineRecord {pipeline_id, title, current_revision_id, layout, created_at, updated_at}`.
`RevisionRecord {revision_id, pipeline_id, revision_number, content_hash, schema_version, document, created_at}`.
`RunRecord {run_id, pipeline_id, revision_id, graph_hash, status, origin, source_run_id, settings, resources, inputs, failure, result_ref, last_sequence, created_at, started_at, finished_at}`.
`RunEventRecord {run_id, sequence, kind, node_id, unit_id, summary, created_at}`.
Run statuses: `queued, running, cancelling, succeeded, failed, cancelled, interrupted`.
OpenAPI also needs a `422` response and an `issues` property on the error schema.
`error_type` keeps its existing enum (`validation`).

## Test-first record

Environment for all commands: WT `.venv`, `PYTHONPATH=src`, `PDF_READER=pypdf`, `-q -p no:cacheprovider`.

1. The first route drafts came before their tests, so the routes had no recorded red run.
   The 15 mutations below give the red record for each guarded rule.
2. First run of the live-stream tests: **1 failed, 7 passed**. `test_browser_disconnect_detaches_monitoring_without_cancelling` found a real defect.
   On disconnect, the stream called `aclose()` on the subscription while a pending read still ran it (`RuntimeError: aclose(): asynchronous generator is already running`).
   The fix cancels the pending read instead. After the fix: **8 passed**.
3. First run of the existing web suites after wiring: **2 failed, 158 passed**. The scope dependency came after the runtime dependency,
   so a missing credential got 503 instead of 401. Every handler now declares the scope first.
4. Final: 6.6 tests plus the jobs file and the file-size guard: **63 passed**. Frontend: `npm run lint`, `npm run typecheck` clean; `npm test` **38 passed** (5 new).

## Mutation checks

Script `scratchpad/mut66/mutate.py`. Each check copies `src/`, changes one line and runs the five 6.6 test files against the copy.

| Id | Change | Result (failing test) |
|---|---|---|
| M1 | Executor re-admits the revision document | 1 failed (`test_submitted_run_executes_the_admitted_snapshot`) |
| M2 | Stream close cancels the run | 1 failed (`test_browser_disconnect_detaches_monitoring_without_cancelling`) |
| M3 | Stream ignores admission close | 1 failed (`test_stream_ends_promptly_when_admission_closes`) |
| M4 | `Last-Event-ID` ignored | 2 failed |
| M5 | Job runs visible on run routes | 1 failed |
| M6 | Validation issues as 400 | 8 failed |
| M7 | Full queue as 503 | 1 failed |
| M8 | No workspace lock | 1 failed |
| M9 | Signal hook does not close admission | 1 failed |
| M10 | Job revision accepted by `POST /v1/runs` | 1 failed |
| M11 | Rejected cleanup token as 400 | 1 failed |
| M12 | Job error not redacted | 1 failed |
| M13 | CLI omits the run service | 1 failed |
| M14 | Revision save skips the schema check | 2 failed |
| M15 | Cleanup allowed for a `read` bearer | 1 failed |

## Real-socket smoke

Script `scratchpad/mut66/smoke.py`: real Uvicorn through `cli.web._serve`, a held graph run, an open SSE stream, then `SIGINT` from the client thread.
Result: the stream closed **0.0 s** after the signal with `event: server.closing`.
The server exited **0.2 s** after the signal. The Engine was closed. The run record was terminal.
Without the hook, Uvicorn waits for the open stream before the lifespan shutdown runs, and the stream waits for the run. Shutdown therefore hangs.

## Static checks

- `ruff check` and `ruff format --check` on all owned files: clean.
- `lint-imports`: **15 kept, 0 broken**.
- Wider command: all `tests/unit/test_web_*.py`, `test_file_size_ceiling.py`, `test_pipeline_import_boundaries.py`,
  `test_workspace_cleanup_guide.py`, `test_cli*.py`, `test_no_global_settings_reads.py`, `test_contract_coverage.py`,
  `test_openapi_conformance.py`, `test_workspace_service*.py` and `test_engine_accessors.py`.
  Result: **528 passed, 2 failed**. Both failures are in files this task does not own (see open points 1 and 2).
- Branch coverage (6.6 tests, jobs and launch tests): `routes_jobs.py` 98%, `routes_runs.py` 95%, `lifespan.py` 94%,
  `routes_graphs.py` 93%, `runs_wiring.py` 93%, `cli/web.py` 87%.

## Deviations and open points

1. **`tests/unit/test_web_security.py::test_bearer_scope_is_enforced` fails.** The test adds a placeholder route
   `GET /v1/runs/{run_id}/events` after `create_app`. The real route now matches first and has no run service in that app,
   so a `read` bearer gets 503 instead of the placeholder's 200. The 401 and 403 checks still pass.
   Fix (test owner): move the placeholder to a path no real route uses (for example `/v1/probe/{run_id}/events`),
   or build the app with `run_service_factory=run_service_factory` and a real run id.
2. **`tests/unit/test_workspace_cleanup_guide.py::test_layout_names_match_the_web_wiring` fails.** As asked, `runs_wiring.py` and
   `lifespan.py` now take every name from `WorkspaceLayout`. The test still looks for the literal strings `"workspace.db"`, `".lock"`,
   `"artefacts"` and `"uploads"` in the API source. Fix (test owner): assert that the API source uses `WorkspaceLayout(`
   and does not repeat the literals.
3. **No public catalogue accessor on `Engine`.** `describe_operations` reads `engine._pipelines.catalogue()` and
   `engine._graph_host(None).host.capabilities`. Fix (owner of `engine.py`): add `Engine.describe_operations()`
   and update the method-set test. Then replace the body of `runs_wiring.describe_operations`.
4. **`Engine.run_pipeline` takes no `run_id`.** The runner creates its own id. The executor rewrites `PipelineResult.run_id`
   to `job.run_id`, so the stored result names the workspace run. The service records events under `job.run_id`.
   The runner's `PipelineEvent.run_id` is not stored. Fix (owner of `engine.py`): add `run_id: str | None = None`, pass it to
   `EnginePipelines.run` and `run_pipeline`, then remove the `model_copy`.
5. **Synchronous admission on the event loop.** `RunService.submit` is synchronous and calls `validate_pipeline`.
   The routes build the catalogue in a worker thread first, so the slow first import never blocks the loop.
6. **The SIGINT is re-raised.** Uvicorn re-raises the captured signal after a graceful shutdown, so `omrg web` still ends with
   `KeyboardInterrupt` on Ctrl+C. This behaviour has not changed.
7. **Job retry.** Jobs have no retry route. `POST /v1/runs/{id}/retry` refuses job runs (404). A retry of a job uses the files scope,
   so it belongs on a jobs route if one is wanted.
8. `src/omrg/transports/api/README.md` still describes jobs as polled only. Task 6.7 can update it with the OpenAPI changes.

## Not run

- A browser walk-through of the bootstrap link (task 7.x). The Vitest test covers the client steps with a mocked `fetch`.
- A real `compose.build_engine()` start (needs the configured embedding model).
- Full test suite and `local_ci.sh` (not permitted for this agent).

## Lead follow-up (2026-10-13)

- `Engine.run_pipeline(..., run_id=None)` forwards the caller's run id to the runner; the executor no longer patches the result.
- New public `Engine.describe_operations(collection=None)`; `runs_wiring.describe_operations` uses it. Method-set test updated.
- `engine.py` stayed under 500 lines by moving error redaction to `compose_pipelines.redact_engine_error` (492 lines).
- `test_web_security.py` stand-in stream route moved to `/v1/probe/{run_id}/events` (the real run events route now owns the old path).
- `test_workspace_cleanup_guide.py` now asserts the web wiring uses `WorkspaceLayout(` and holds no duplicate file-name literals.
- Change-related set (web, workspace, engine, pipeline, domain adapters, plugins, guards): 1223 passed, 1 skipped. `lint-imports`: 16 kept, 0 broken.
