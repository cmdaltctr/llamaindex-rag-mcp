# Experiment transport, plugin routes, templates route and starter notebook (tasks 8.5, 8.6)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted work tree.
Design D10. Specs `notebook-plugins` and `local-web-workspace`.
Input: the "Transport wiring needed" list in `experiment-contexts.md`.
marimo is not installed. No command installed, upgraded or synced a package.

Command prefix:

```bash
PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider <files>
```

## Files

| File | Change |
|---|---|
| `src/omrg/transports/api/security.py` | `experiment_context` on `Principal`, `IssuedBearer`, `_BearerEntry`; `issue_bearer(..., experiment_context=)`; `list_bearers` shows it. `require_scope` refuses a bound bearer outside `EXPERIMENT_BEARER_PATHS`. |
| `src/omrg/transports/api/lifespan.py` | `WebConfig.experiment_roots`, `plugin_ports`, `plugin_runtime_dir`, `experiments_factory`, `plugins_factory`. `PluginHost`. `default_experiments_factory`, `default_plugins_factory`. New shutdown order. |
| `src/omrg/transports/api/runs_wiring.py` | `RunTarget`, `ExperimentJob`, `public_outputs`. Admitter runs the experiment guard. Executor takes a fresh lease. `WorkspaceRuns.targeting`. |
| `src/omrg/transports/api/routes_runs.py` | `SubmitBody.experiment_context`. 403 with `to_dict()` before any side effect. Run visibility for bound bearers. Retry keeps the source context. |
| `src/omrg/transports/api/routes.py` | `POST /v1/credentials` accepts `experiment_context` (active context only). |
| `src/omrg/transports/api/routes_experiments.py` (new) | `POST/GET /v1/experiments`, `GET/DELETE /v1/experiments/{context_id}`. Session only, scope `manage`. |
| `src/omrg/transports/api/routes_plugins.py` (new) | List, register, recheck, unregister, open editor, stop editor. Session only, scope `plugins`. |
| `src/omrg/transports/api/routes_templates.py` (new) | `GET /v1/pipeline-templates`, scope `read`. |
| `src/omrg/transports/api/app.py` | Three router lines. |
| `src/omrg/transports/api/openapi.yaml` | Eleven operations, new schemas, `ExperimentRefused` response, new fields. |
| `src/omrg/transports/cli/web.py` | `--experiment-root` (repeatable). A missing root exits with code 2. |
| `src/omrg/compose_engine.py` | `experiment_base_settings()`. |
| `src/omrg/core/workspace/repository.py`, `src/omrg/integrations/workspace_sqlite/repository.py` | `register_plugin(..., detail=None)`, `unregister_plugin(name)`. Additive. |
| `plugins/marimo/starter_notebook.py` (new, 468 lines) | marimo notebook with standard-library helpers. |
| Tests (new) | `test_web_experiments.py` (17), `test_web_experiments_runtime.py` (7), `test_web_experiments_conformance.py` (2), `test_web_plugins.py` (15), `test_web_plugins_launch.py` (2), `test_web_plugins_records.py` (4), `test_web_templates.py` (3), `test_starter_notebook.py` (10). Support module `test_web_experiments_support.py`. |
| `tests/unit/test_web_openapi_conformance_support.py` | Not owned. Additive: `FAMILIES` gains `templates`, `experiments`, `plugins`. Without it the coverage test fails for every new route. |

## Behaviour

### Credential binding and live-library isolation

- `POST /v1/credentials` with `experiment_context` checks `registry.require_active` first. Unknown or revoked context gives 400 with `to_dict()`.
- A revoked context does not revoke the credential. The next admission fails with `experiment_context_revoked`.
- A bound bearer reaches only `/v1/session`, `/v1/pipeline-operations`, `/v1/pipeline-templates`, `/v1/pipelines` and `/v1/runs`. Collections, documents, search, answer and chunks give 403 ("cannot read or change the live library").
- A bound bearer sees only runs whose `resources.experiment.context_id` is its context. Other runs read as 404.
- Stricter rule kept (lead decision): a bound credential is refused on all live-library runs, read-only ones too.

### Run admission and execution

1. The submit and retry routes build a `RunTarget` from the principal and the requested context.
2. `_warm_catalogue` runs `check_credential_target` first, then builds the context Engine off the event loop.
3. The admitter calls `experiments.admit(...)` for a context. For the live library it calls `check_credential_target(target_context=None)` first.
4. `ExperimentAdmissionError` and `ExperimentPathError` give 403 with `to_dict()`. No run record is written.
5. The run records `admission.provenance()` under `resources["experiment"]`: context id, graph identity, backend identity, index identity.
6. The executor takes a fresh lease, calls `experiments.execute(...)`, and sets `run_id` to the job id.

Deviation (lease timing): the admitter releases the admission lease at once. The executor takes a new lease at execution start. Reason: `RunService` drops a cancelled queued job without a callback, so a lease taken at submission could never be released. A context revoked while the run waited fails at `acquire` with `experiment_context_revoked`, before its Engine runs. A run that already started holds its lease and finishes (test `test_run_that_started_finishes_after_revocation`).

Addition: `public_outputs` stores a `ContextBundle` output as `public_rows()` for live and experiment runs. Before, the run artefact held the text form of the dataclass.

### Runtime and shutdown

- Experiment roots come only from `--experiment-root`. Without a root, `runtime.experiments` is `None`, `POST /v1/experiments` gives 409, and nothing reads settings.
- Base settings come from `compose_engine.experiment_base_settings()`.
- Contexts live in memory per launch (lead decision).
- Shutdown order: run service, `editors.stop_all()`, `experiments.close()`, `engine.close()`. A refused `experiments.close()` is logged; the live Engine still closes.

### Plugin routes

- `PluginRegistry(repo, SubprocessProbeRunner())` and `NotebookEditorSupervisor(registry, OwnedProcessLauncher(<workspace>/run/editors), ports=(2719, 2720, 2721))` are built once per launch. Startup runs no process.
- Register needs `approved: true`. The manifest must be the shipped `plugins/marimo/manifest.json` or below `<workspace>/plugins/`. The executable must be in a `PATH` directory at launch or below `<workspace>/plugins/`. Its file name must equal the manifest executable name.
- Unregister gives 409 while an editor of that plugin runs.
- Open editor needs `consent: true`, an active context and a relative `.py` notebook inside the context workspace. Response: `launch_id`, `url_without_token`, `token_delivery: {method: "response_body_once", token}`, `trust_notice`. The token appears only in that body. No route logs it. Listings omit it.

### Templates route

`GET /v1/pipeline-templates` returns `pipeline_templates(engine)` as `{name, title, description, standard_operation, document, outputs}`. `document` is the graph document. The `search` output description names `ContextBundle.public_rows()`.

### Starter notebook

- The file has the marimo layout: `app = marimo.App(...)`, `with app.setup:`, `@app.function`, `@app.class_definition`, `@app.cell`. Without marimo, a stand-in `App` keeps every decorator as identity, so tests import the helpers.
- Connection: `OMRG_API_URL` (loopback http only), `OMRG_TOKEN_FILE` (mode 600 required) or `OMRG_TOKEN`, `OMRG_EXPERIMENT_CONTEXT`. The client `repr` hides the token. No `print`.
- `ExperimentSession.run(..., run_requested=...)` returns `None` without a request. The notebook cell calls it only after `mo.stop(not run_button.value, ...)`.
- The session creates its pipeline once and saves a revision once per document digest.
- Each record holds the revision, graph hash and identity, effective settings, backend and index identity, inputs, outputs, event count and wall time.
- `checkpoint` writes `<name>.json.tmp`, flushes, `fsync`s, then `os.replace`s. A failure removes the temporary file and keeps the previous checkpoint.

## Test-first record

| Step | Command (files) | Result |
|---|---|---|
| Baseline before work | `tests/unit/test_web_*.py tests/unit/test_experiment_*.py tests/unit/test_plugin_*.py tests/unit/test_workspace_*.py -m "not slow"` | 570 passed, 1 deselected |
| Repository tests before the change | `test_web_plugins_records.py` | 3 failed, 1 passed |
| After the change | same plus workspace and plugin tests | 293 passed |
| Experiment tests before transport code | `test_web_experiments.py` | 1 failed, 15 errors |
| After security, lifespan, runs, routes | same | 16 passed |
| Template tests before router registration | `test_web_templates.py` | 3 failed |
| After registration, before contract | same | 1 failed (route not in contract), 2 passed |
| Plugin tests before routes | `test_web_plugins.py test_web_plugins_launch.py` | 15 failed, 2 passed |
| After routes, before contract | same | 1 failed (contract), 16 passed |
| CLI tests before `--experiment-root` | `test_web_experiments_runtime.py` | 2 failed, 5 passed |
| Notebook tests without the notebook file (file moved aside, SHA-256 checked after restore) | `test_starter_notebook.py` | 10 errors |

Deviation: the shutdown-order tests and the notebook tests ran after the code existed. The mutation checks below cover them.

## Mutation checks

Script `scratchpad/exp-transport/mutate.py`: one change, run the eight new test files, restore, compare SHA-256. Control: all passed. Every mutation made at least one test fail.

| Id | Change | First failing test |
|---|---|---|
| M1 | No bound-bearer path allowlist | `test_bound_bearer_cannot_touch_the_live_library` |
| M2 | No live-target credential check | `test_experiment_responses_conform`, live-library test |
| M3 | Admission lease kept | `test_run_that_started_finishes_after_revocation` |
| M4 | No fresh lease at execution | `test_run_that_started_finishes_after_revocation` |
| M5 | Provenance not recorded | `test_bound_bearer_runs_a_read_only_graph_in_its_context` |
| M6 | Bound bearer sees every run | `test_bound_bearer_sees_only_its_context_runs` |
| M7 | Retry ignores source context | `test_cancelled_queued_run_releases_and_retry_stays_in_context` |
| M8 | Credential binds without context check | `test_credentials_bind_only_to_an_active_context` |
| M9 | Experiments close before editors stop | `test_shutdown_order_is_service_editors_experiments_engine` |
| M10 | Any manifest location | `test_manifest_must_be_in_an_approved_location[outside]` |
| M11 | No executable name check | `test_executable_must_be_in_an_approved_location_and_match_the_manifest` |
| M12 | Notebook may leave the workspace | `test_open_editor_keeps_the_notebook_inside_the_workspace[../...]` |
| M13 | Token in the editor URL | `test_open_editor_gives_the_token_once_and_never_logs_it` |
| M14 | Notebook ignores `run_requested` | `test_parameter_change_without_a_request_admits_nothing` |
| M15 | Checkpoint writes in place | `test_failed_checkpoint_keeps_the_previous_file` |
| M16 | No revision cache | `test_parameter_change_runs_again_without_repeating_unrelated_steps` |
| M17 | Context bundles not made public | notebook shared-graph test, experiment run test |
| M18 | Editors not stopped at shutdown | `test_editor_runs_until_app_shutdown_...`, shutdown-order test |
| M19 | Experiments not built at startup | `test_experiment_routes_are_session_only` and others |
| M20 | Unregister keeps the record | `test_unregister_plugin_removes_only_that_record` |

Incident: the first M18 run left one fake editor group running (the mutation removed the stop). I killed it by process group. The end-to-end test now kills a leftover group in `finally`. A rerun of M18 left no process (`pgrep` empty).

## Final results

| Command | Result |
|---|---|
| `tests/unit/test_web_*.py tests/unit/test_experiment_*.py tests/unit/test_plugin_*.py tests/unit/test_workspace_*.py tests/unit/test_starter_notebook.py -m "not slow"` | 631 passed, 1 deselected |
| `tests/test_file_size_ceiling.py tests/test_no_global_settings_reads.py tests/test_contract_coverage.py tests/test_pipeline_import_boundaries.py tests/test_openapi_conformance.py tests/unit/test_process_launcher*.py` | 159 passed |
| `tests/test_engine.py tests/unit/test_engine_pipelines.py tests/unit/test_pipeline_templates.py` (with `tests/test_openapi_conformance.py`) | 100 passed |
| `PYTHONPATH=src .venv/bin/lint-imports` | 17 kept, 0 broken |
| `ruff check`, `ruff format --check` on all changed files | Pass |
| Largest changed file | `integrations/workspace_sqlite/repository.py`, 498 lines |

## Open points

1. **Real marimo parse is not checked.** The notebook starts with `try: import marimo` and a stand-in. Task 8.4 must open it with a qualified marimo and run `marimo check`.
2. **The notebook needs a credential file.** The editor environment is an allowlist, so OMRG keys and tokens do not reach it. The user issues a bound credential and saves it as a mode 600 file, then sets `OMRG_TOKEN_FILE`. A later change could let "open editor" write a bound credential file into the launch directory.
3. **`GET /v1/pipeline-operations` and `POST /v1/pipelines/validate` stay open to bound bearers.** They describe or validate against the live Engine settings but read no library data.
4. **Unbound bearers can still read experiment runs.** Only bound bearers are filtered.
5. **`transports/api/README.md` and `docs/guides/` are not updated** (not owned). They should list the new routes and `--experiment-root`.
6. **Proposed check for 8.7:** the Experiments view must show `trust_notice` from `GET /v1/experiments` and `GET /v1/plugins`.

## Editor connection file (task 8.6 follow-up)

Problem: the launcher passed the editor only `ENV_ALLOWLIST`. `OMRG_API_URL`, `OMRG_TOKEN_FILE` and `OMRG_EXPERIMENT_CONTEXT` never reached an editor that OMRG started. The starter notebook could not connect. Lead decision: a private connection file, not more environment variables.

### Files

| File | Change |
|---|---|
| `src/omrg/integrations/process_launcher.py` | `LAUNCH_ENV_ALLOWLIST = ("OMRG_CONNECTION_FILE",)`. `start(..., environment=None)` accepts only those names. It refuses an empty value, a NUL byte or a secret in a value. The server's own value of the name is never inherited. |
| `src/omrg/core/plugins/editor.py` | `EditorConnection(api_url, experiment_context, token)` (token not in `repr`). `CONNECTION_FILE_NAME = "omrg_connection.json"`, `API_TOKEN_FILE_NAME = "omrg-api-token"`, `CONNECTION_ENV = "OMRG_CONNECTION_FILE"`. `build_launch_plan(..., connection=)` renders both files and the variable. `LaunchPlan.environment`. `open(..., connection=)`; the bearer joins `secrets`. Pure: `json` only. |
| `src/omrg/transports/api/routes_plugins.py` | Open issues a NEW bearer through `AccessPolicy.issue_bearer` (scopes `graph`, `read`, `run`, label `notebook editor`, bound to the context). `api_url` comes from the policy host and port. A failed open revokes it. Stop revokes it (also when stop fails). The response shape is unchanged, so `openapi.yaml` is unchanged. |
| `src/omrg/transports/api/lifespan.py` | `PluginHost.editor_cleanups` (launch id to revoke call). `shutdown_runtime` revokes every remaining editor credential after `stop_all`. |
| `plugins/marimo/starter_notebook.py` | `read_private_file` refuses any mode bit outside 0o600. `connection_from_file` reads `OMRG_CONNECTION_FILE`, then the token file it names. `ApiClient.from_environment` and `experiment_context_from_environment` prefer it, then fall back to the three variables. |
| `docs/guides/notebooks.md`, `plugins/marimo/README.md` | The gap note is gone. The guides describe the connection file, the fallback, revocation and the remaining unconfirmed items. |

File locations: the launch directory is `<workspace>/run/editors/launch-*` (0o700). The connection file and the token file are 0o600 (`O_EXCL | O_NOFOLLOW`), written by the launcher. They are never in the experiment workspace. The launcher removes the launch directory at stop, so both files go. No route or launcher logs either value; the output buffer redacts the bearer.

### Test-first record

Command prefix: `PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider`.

| Step | Tests | Result |
|---|---|---|
| Before code | `test_process_launcher_connection.py test_web_plugins_connection.py test_web_plugins.py test_starter_notebook.py` | 26 failed, 25 passed |
| Before code | `test_plugin_editor_connection.py` | collection error (`ImportError: API_TOKEN_FILE_NAME`) |
| After code | same five files plus `test_plugin_editor.py` | all passed (41 backend, 25 notebook) |
| Guide test before doc and test update | `test_notebooks_guide.py` | 1 failed, 7 passed (pinned the four old variables) |
| After update | `test_notebooks_guide.py test_starter_notebook.py` | 33 passed |

The fake editor (`tests/unit/test_process_launcher_support.py`) now reads `OMRG_CONNECTION_FILE` and records the connection, both file modes and the API token. `test_web_plugins_connection.py` uses the production plugin host. It checks: both files 0o600, in `<workspace>/run/editors`, not in the experiment; the credential is new, bound, has the three scopes and runs a graph in its context; the bearer is not in argv, the editor environment, the response or the log. After stop, both files are gone and the bearer gets 401. After application shutdown, both files are gone and `authenticate_bearer` returns `None`.

### Mutation checks

Each mutation was applied, the named tests run, and the file restored.

| Mutation | Result |
|---|---|
| Launcher drops the per-launch environment | 1 failed |
| Launcher skips the secret check on values | 1 failed |
| Token written into the connection JSON | 3 failed |
| Bearer missing from `secrets` | 2 failed |
| Stop does not revoke | 2 failed |
| Failed open keeps the credential | 1 failed |
| Shutdown does not revoke | 1 failed |
| Notebook accepts mode 0o700 | 2 failed |
| Notebook prefers the variables over the file | 1 failed |
| Route passes no connection | 3 failed |

### Final results

| Command | Result |
|---|---|
| `tests/unit/test_plugin_*.py tests/unit/test_process_launcher*.py tests/unit/test_web_*.py tests/unit/test_starter_notebook.py tests/unit/test_notebooks_guide.py` | 483 passed |
| `tests/test_file_size_ceiling.py tests/test_pipeline_import_boundaries.py tests/test_contract_coverage.py tests/test_no_global_settings_reads.py tests/test_openapi_conformance.py tests/test_docs_references.py tests/test_docs_no_retired_env_vars.py` | 146 passed |
| `PYTHONPATH=src .venv/bin/lint-imports` | 17 kept, 0 broken |
| `ruff check`, `ruff format` on changed files | Pass |

### Open points

1. No real marimo launch confirmed that marimo passes `OMRG_CONNECTION_FILE` to the notebook kernel. Task 8.4 must check it.
2. OMRG does not notice when an editor process ends by itself. The files and the credential stay until stop or shutdown.
3. `web/src/experiments/CredentialPanel.tsx` still tells the user to set `OMRG_TOKEN_FILE` and `OMRG_EXPERIMENT_CONTEXT`. That stays correct for an editor that the user starts. The frontend owner can add that an OMRG-opened editor needs no manual step.
4. The starter notebook is 529 lines. The 500-line ceiling covers `src/omrg/` only, so no guard fails.
