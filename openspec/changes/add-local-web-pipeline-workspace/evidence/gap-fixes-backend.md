# Gap fixes: backend (verification.md section A, items 1, 2, 4, 7 and 8)

This file records the backend fixes for the functional gaps in
`verification.md` section A. It also records one extra item from the
coordinator: stored node outcomes keep the node summary. The work is not
committed.

All commands ran in the feature worktree with this prefix:

```
PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider
```

## Summary

| Item | Gap | Status |
| ---- | --- | ------ |
| 1 | Experiment run outputs stored in workspace `artefacts/` | Fixed |
| 2 | Live-library runs record no index identity | Fixed |
| 4 | No event inspection for ingestion and codebase-map jobs | Fixed |
| 7 | Node control and source not in run result or stored run | Fixed |
| 8 | Graph runs build and close their own OCR client | Fixed |
| Extra | Stored node outcomes have no node summary | Fixed |

## Item 8: the Engine owns the OCR client

Change:

- `EnginePipelines.ocr_client(settings)` builds one OCR client on first use
  with `capabilities.build_ocr_routes`, the same builder that
  `ingest_path_async` uses. Later runs on the same Engine borrow it.
- `EnginePipelines.release()` closes the client. `Engine.close()` calls
  `release()`. A close failure is logged, not raised.
- `Engine._graph_host` passes `ocr_factory=self._pipelines.ocr_client`.
- `plan_run` no longer builds or closes a client. `RunPlan.owned` and
  `RunPlan.close()` are removed. The run closes nothing.
- An Engine composed with an OCR client lends that client. Nothing else is
  built.
- `Engine.ingest` is unchanged: without an Engine client it builds an
  operation-owned client and closes it when the batch ends.

Tests (`tests/unit/test_engine_pipelines_ingestion.py`):

- `test_graph_runs_borrow_one_engine_owned_ocr_client`: two plans and two
  real graph runs share one client; no run closes it; `Engine.close()`
  closes it once.
- `test_engine_ingest_keeps_its_operation_owned_ocr_client`: standard
  ingestion still builds and closes its own client and does not touch the
  Engine client.
- `test_injected_ocr_client_is_borrowed_and_never_rebuilt`.
- The old test `test_ingestion_run_builds_and_closes_its_own_ocr_client`
  asserted the wrong behaviour. It was replaced.

Results:

| Step | Command | Result |
| ---- | ------- | ------ |
| Before fix | `tests/unit/test_engine_pipelines_ingestion.py` | 2 failed, 3 passed |
| After fix | same | 5 passed |
| Mutation: `release()` does not close | same | 2 failed, 3 passed |
| Mutation: build a new client on each call | same | 1 failed, 4 passed |

`engine.py` is 496 lines. To keep `compose_pipelines.py` under 500 lines,
run planning moved to the new module `src/omrg/compose_pipeline_runs.py`
(`RunPlan`, `plan_run`, `with_provenance`, `SUMMARY_EVENTS`).
`compose_pipelines.py` is 474 lines.

## Item 7 and extra item: node controls, sources and summaries

Change:

- `PipelineResult.controls` (new, additive): node id to the admitted
  `EffectiveControl` tuple (`lever`, `value`, `source`, `detail`).
- `NodeOutcome.summary` (new, additive): the data of the node's
  `node_completed` or `node_bypassed` event. For a reranker switched off
  by a node parameter it is `{reranked: false, reason: "disabled by node
  parameter", rows: n}`. For a node disabled in the graph it holds the
  bypass reason.
- `EnginePipelines.run` wraps the caller's event sink. The wrapper keeps
  each node summary per `(node_id, unit_id)` and forwards every event.
  `with_provenance` then adds summaries and controls to the result. The
  runner (`runner.py`, `execution.py`) is not changed.
- `snapshot_provenance` (run record) adds `resources.controls`: node id to
  the list of admitted controls with their sources.
- `RunRecorder.finish` bounds each stored node summary with `preview()`
  before the result artefact is written. The artefact is redacted as
  before.

Tests:

- `tests/unit/test_engine_pipelines_provenance.py` (through
  `Engine.run_pipeline`): explicit node override is recorded with source
  `node`; inherited control has source `profile`; node outcomes carry the
  summary; a bypassed node keeps the bypass reason. The reranker double
  fails the test if a disabled node calls it.
- `tests/unit/test_web_runs_provenance.py`:
  `test_run_detail_records_node_controls_and_sources` (run detail and
  result routes), `test_python_run_record_keeps_index_and_controls`
  (stored record through `RunService` without HTTP) and
  `test_stored_node_summaries_are_bounded_and_redacted`.

Results:

| Step | Command | Result |
| ---- | ------- | ------ |
| Before fix | `tests/unit/test_engine_pipelines_provenance.py` | 4 failed |
| After fix | same | 4 passed |
| Mutation: `controls = {}` | same | 2 failed, 2 passed |
| Mutation: keep `node_completed` summaries only | same | 1 failed, 3 passed |
| Mutation: no summary bound in `finish` | `tests/unit/test_web_runs_provenance.py` | 1 failed, 4 passed |

## Item 2: live-library runs record the selected index identity

Change:

- `compose_experiments.collection_version(store, name)` reads the data
  version at admission:
  - absent collection: `{exists: false, data_version: null}`;
  - durable store: `{exists: true, data_version: <token>, version_scope:
    "durable"}` from `store.get_data_version(name)`;
  - no durable version: `{exists: true, data_version: null, version_scope:
    "process-local", generation: <n>}` from `store.get_generation(name)`.
- `compose_experiments.index_provenance(settings, store, collections,
  identity=None)` returns `backend` (store kind, location, embedding
  identity, `index_identity`, `store_class`) and `collections`.
- `RunAdmitter` records `resources.index` for live-library runs and for
  experiment runs (with the context backend identity).
- `resources.operations` (node id to `operation@version`) was already
  recorded. It now has Python and HTTP tests.

Tests (`tests/unit/test_web_runs_provenance.py`):
`test_run_detail_records_the_durable_index_identity` (LanceDB, durable
token equals `store.get_data_version`),
`test_store_without_durable_version_records_a_process_local_marker`, and
`test_python_run_record_keeps_index_and_controls`.

Results:

| Step | Command | Result |
| ---- | ------- | ------ |
| Before fix | `tests/unit/test_web_runs_provenance.py` | 5 failed |
| After fix | same | 5 passed |
| Mutation: drop the durable token branch | same | 2 failed, 3 passed |
| Mutation: do not record `resources.index` | same | 3 failed, 2 passed |

## Item 4: event inspection of ingestion and codebase-map jobs

Change:

- New route `GET /v1/jobs/{job_id}/events` (`listJobEvents`) in
  `routes_jobs.py`. It pages the committed events of the hidden job run
  with `after_sequence` and `limit` (maximum 500). It returns
  `{status, job_id, job_status, events, last_sequence, complete}`.
- Same scope as `GET /v1/jobs/{jobId}` (`read`). Graph runs, unknown ids
  and non-UUID ids return 404.
- `openapi.yaml`: new path and schema `JobEventPage`. The conformance
  family `jobs` now includes `listJobEvents`, and the jobs flow test
  checks the new response against the contract.

Tests (`tests/unit/test_web_jobs_events.py`): paging with
`after_sequence`, scope (read bearer allowed, bearer without `read` gets
403), 404 for graph runs and unknown ids.

Results:

| Step | Command | Result |
| ---- | ------- | ------ |
| Before fix | `tests/unit/test_web_jobs_events.py` | 2 failed, 1 passed (the 404 test passed already) |
| After fix | same | 3 passed |
| Contract before `openapi.yaml` edit | `tests/unit/test_web_openapi_conformance*.py` | 1 failed, 27 passed |
| Contract after | same | 28 passed |
| Mutation: ignore `after_sequence` | `tests/unit/test_web_jobs_events.py` | 1 failed, 2 passed |
| Mutation: accept graph runs as jobs | same | 1 failed, 2 passed |

Note: a job run records only `run.status` events. The job work (an
`Engine.ingest` or codebase-map call) emits no progress events.

## Item 1: experiment outputs stay below the experiment workspace

Change:

- `Admission.artefact_root` (new, optional). The run service records it as
  `resources.artefact_root` (`ARTEFACT_ROOT_KEY`).
- `RunRecorder` writes the result, overflow event artefacts and status
  artefacts of such a run below that root. Other runs use the workspace
  store as before.
- `RunService.artefacts_for(run)` returns the store of one run.
  `WorkspaceRuns.result` uses it, so `GET /v1/runs/{id}/result` still
  resolves the stored result.
- `compose_experiments.run_output_root(context)` returns
  `<experiment workspace>/output/omrg-runs`. It refuses a symbolic link or
  a path that leaves `output/` (`commit_outside_context`, HTTP 403) before
  any run record exists.
- Cleanup is unchanged. It removes run records and files below
  `<workspace>/artefacts/<run_id>/` only, so experiment outputs survive.

Tests:

- `tests/unit/test_web_experiments_outputs.py`:
  `test_ingestion_experiment_keeps_index_and_outputs_in_its_workspace`
  runs the canonical ingestion graph over HTTP with a bearer bound to an
  ingest-permitted context and real LanceDB context Engines. It checks
  that the store and `result.json` are below the experiment `output/`,
  that workspace `artefacts/` has no directory for the run, that the
  result route returns the result, that the live Engine and live library
  are untouched, and that cleanup removes the record and keeps the
  experiment outputs. `test_linked_run_output_directory_is_refused_before_any_run`
  covers the link check.
- `tests/unit/test_workspace_service_outputs.py`: run with and without an
  artefact root.
- `tests/unit/test_workspace_cleanup_safety.py`:
  `test_experiment_run_outputs_survive_cleanup_of_their_record`. This is a
  regression guard: it passed before and after, because cleanup never read
  the run resources.

Results:

| Step | Command | Result |
| ---- | ------- | ------ |
| Before fix | `tests/unit/test_web_experiments_outputs.py` | 2 failed |
| Before fix | `tests/unit/test_workspace_service_outputs.py` | new tests failed (`Admission` had no `artefact_root`) |
| After fix | both files | 2 passed; 9 passed |
| Mutation: `artefact_root=None` in experiment admission | `tests/unit/test_web_experiments_outputs.py` | 1 failed, 1 passed |
| Mutation: result route reads the workspace store | same | 1 failed, 1 passed |
| Mutation: no link check | same | 1 failed, 1 passed |
| Mutation: `run_artefacts` ignores the root | `tests/unit/test_workspace_service_outputs.py` | 1 failed, 8 passed |
| Mutation: root not recorded | same | 1 failed, 8 passed |

## Final runs

| Command | Result |
| ------- | ------ |
| `tests/unit/test_web_*.py tests/unit/test_engine_*.py tests/test_engine.py tests/unit/test_workspace_*.py tests/unit/test_experiment_*.py tests/unit/test_pipeline_*.py tests/unit/test_ingestion_*.py` | 919 passed, 2 skipped |
| Guards: `tests/test_file_size_ceiling.py tests/test_default_store_accessor.py tests/test_pipeline_import_boundaries.py tests/test_core_import_contracts.py tests/test_contract_coverage.py tests/unit/test_plugin_boundaries.py tests/unit/test_verification_gaps_*.py tests/test_ocr_worker_import_boundary.py tests/test_mcp_tools.py` | 152 passed, 5 skipped |
| `tests/test_compose.py tests/test_engine_isolation.py tests/test_engine.py tests/test_ocr_*.py tests/unit/test_ocr_route_dispatch.py` | 536 passed, 4 skipped |
| `PYTHONPATH=src .venv/bin/lint-imports` | 21 kept, 0 broken |
| `.venv/bin/openapi-spec-validator src/omrg/transports/api/openapi.yaml` | OK |
| `.venv/bin/ruff check` and `ruff format` on changed files | clean |

## Files

Changed: `src/omrg/engine.py`, `src/omrg/compose_pipelines.py`,
`src/omrg/compose_experiments.py`, `src/omrg/core/pipelines/results.py`,
`src/omrg/core/workspace/{__init__.py,jobs.py,outcomes.py,service.py}`,
`src/omrg/transports/api/{runs_wiring.py,routes_jobs.py,openapi.yaml}`,
`tests/unit/test_engine_pipelines_ingestion.py`,
`tests/unit/test_engine_pipelines_support.py` (`rerank_graph` helper),
`tests/unit/test_workspace_service_support.py`,
`tests/unit/test_workspace_service_outputs.py`,
`tests/unit/test_workspace_cleanup_safety.py`,
`tests/unit/test_web_openapi_conformance_support.py`,
`tests/unit/test_web_openapi_conformance_documents.py`.

New: `src/omrg/compose_pipeline_runs.py`,
`tests/unit/test_engine_pipelines_provenance.py`,
`tests/unit/test_web_runs_provenance.py`,
`tests/unit/test_web_jobs_events.py`,
`tests/unit/test_web_experiments_outputs.py`.

## Deviations and open points

1. New top-level module `src/omrg/compose_pipeline_runs.py`. It was not in
   the owned file list. It was needed to keep `compose_pipelines.py`
   under 500 lines. `tests/test_core_import_contracts.py` picks it up
   automatically and passes.
2. `core/pipelines/results.py` gained `PipelineResult.controls` as well as
   `NodeOutcome.summary`. Both are additive with empty defaults.
3. Summaries and controls are added in `EnginePipelines.run`. A caller of
   the core `run_pipeline` without the Engine gets empty values.
4. Node outcomes live in the stored result (`GET /v1/runs/{id}/result`),
   not in the run record. The run record carries `resources.controls`.
   The web type `NodeOutcomeRecord` in `web/src/api/runs.ts` has no
   `summary` field yet. The web owner must add it and show it.
5. The index data version is read at admission. An ingestion run changes
   it later. The record does not hold the version after the run.
6. The Engine-owned OCR client is built from the settings of the first
   node that enables the OCR fallback. Later runs on the same Engine reuse
   it, even when their OCR route settings differ. This matches an Engine
   composed with a client. Decide whether per-route clients are needed.
7. The experiment HTTP test replaces the private `ExperimentEngines._build`
   with a real LanceDB builder after startup.
