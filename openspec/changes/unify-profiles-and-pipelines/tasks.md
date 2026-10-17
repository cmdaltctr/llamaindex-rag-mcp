# Tasks

Work in a feature worktree that forks from the integration branch. Start after `organise-backend-folders` has landed, because the route modules then live in `src/omrg/transports/api/routes/`. Write each failing test first, then the code. Run the named tests after each task.

## 1. Profile storage (design D1, D7, D10, D11, D12)

- [x] 1.1 Write failing tests in `tests/unit/test_workspace_migrations.py`: a version 2 database migrates to version 3, gets a backup file, and gains the `profiles` table; reserved ids, a second slot use of one pipeline, and changes to `profile_id`, `base_profile` or a slot id are refused by the database. Verify they fail.
- [x] 1.2 Add migration 3 to `SCHEMA_MIGRATIONS` in `src/omrg/integrations/workspace_sqlite/schema.py` with the table, checks and triggers from design D1. Verify the 1.1 tests pass.
- [x] 1.3 Add `ProfileRecord` to `src/omrg/core/workspace/records.py` and a `ProfileRepository` protocol (create, get, list, update title and description, archive, find by slot pipeline) to `src/omrg/core/workspace/repository.py`. Verify `tests/unit/test_workspace_contracts.py` passes with a new conformance check for the protocol.
- [x] 1.4 Move `TASK_LAYOUT_KEY` from `src/omrg/transports/api/runs_wiring.py` to `src/omrg/core/workspace/records.py`. Import it from there in `runs_wiring.py` and `src/omrg/transports/api/routes/graphs.py`. Verify `uv run pytest tests/unit -k "workspace or web_graphs" -q` passes with no other change.
- [x] 1.5 Move `default_workspace()` from `src/omrg/transports/cli/web.py` to `src/omrg/core/workspace/cleanup.py` beside `WorkspaceLayout`. Import it from there in `web.py`. Verify `uv run pytest tests/unit/test_web_launch.py tests/unit/test_web_port_selection.py -q` and `uv run lint-imports` pass.
- [x] 1.6 Move the "insert pipeline" and "insert revision" SQL out of `src/omrg/integrations/workspace_sqlite/repository.py` into a shared helper module, with no behaviour change. Verify `tests/unit/test_workspace_repository.py` passes and `repository.py` stays under 500 lines.
- [x] 1.7 Write failing tests in a new `tests/unit/test_workspace_profiles.py`: create a profile with three pipelines and their first revisions in one transaction; roll back all rows when one insert fails; make slug ids with `-2` suffixes; never reuse an archived id; list leaves out archived profiles; rename keeps the id. Verify they fail.
- [x] 1.8 Implement the SQLite profile store in a new `src/omrg/integrations/workspace_sqlite/profiles.py`, including the catalogue reads `get_profile` and `slot_document`. Verify the 1.7 tests pass and `uv run lint-imports` passes.
- [x] 1.9 Write failing tests in `tests/unit/test_workspace_profiles.py` for a read-only catalogue: it reads profiles and slot documents from a version 3 file; a write through its connection fails; the file bytes and the schema version stay the same; a version 2 file reads as no user profiles and stays version 2; a newer version or a file that is not a workspace gives an error that names the path. Verify they fail.
- [x] 1.10 Add a read-only open (`file:<path>?mode=ro` URI) to the profile store in `profiles.py`. Verify the 1.9 tests pass.

## 2. Profile catalogue and resolver (design D8, D11, D22)

- [x] 2.1 Write failing tests in `tests/test_profiles.py`: with a fake catalogue, a collection tagged `my-notes` resolves to its base settings with `profile_name == "my-notes"`; an unknown tag lists built-in and ready user profiles; a deleted profile gives the "was deleted" error; with no catalogue, a non-built-in tag gives the D11 message with the profile id and the database path. Verify they fail.
- [x] 2.2 Add `src/omrg/core/profiles/catalogue.py` with the `ProfileCatalogue` protocol, `ProfileBinding` and the slot contracts as plain data. Verify `uv run lint-imports` passes.
- [x] 2.3 Add the `catalogue` argument and a `binding(collection)` method to `ProfileResolver` in `src/omrg/core/profiles/resolver.py`, and accept the catalogue in `compose.build_profile_resolver`. Verify the 2.1 tests and `tests/unit/test_profile_resolver_injection.py` pass.
- [x] 2.4 Write failing tests in `tests/test_profiles.py` for the safety contract: a user target names its three pipelines with revision numbers and the Ingest note; `apply_profile_change` accepts a ready user id from the catalogue and refuses others. Verify they fail.
- [x] 2.5 Change `generate_safety_contract` and `apply_profile_change` in `src/omrg/core/profiles/contract.py` to use the catalogue. Verify the 2.4 tests pass and the existing profile tests still pass.
- [x] 2.6 Update `docs/guides/configuration.md` (Profiles section): user profiles, base profile, the tag, where each process reads the workspace, and the no-workspace error with its fix. Verify every path the section names exists.

## 3. Engine concurrency (design D3)

- [x] 3.1 Write a failing test in `tests/unit/test_engine_pipelines.py`: two runs of a read-only graph, built on a catalogue whose fake operation waits on a two-party barrier, are both in progress before either ends. Verify it fails today because of the Engine lock.
- [x] 3.2 Write tests in the same file that two graphs with an enabled `SOURCE_COMMIT` fake step never overlap, and that a read-only run starts while a writing run holds the lock. Verify the first passes today.
- [x] 3.3 Change `EnginePipelines.run` in `src/omrg/compose_pipelines.py` to take the lock only for snapshots with an enabled write step, and guard `active_runs` with a thread lock. Verify the 3.1 and 3.2 tests and `tests/unit/test_engine_pipelines_isolation.py` pass, and the file stays under 500 lines.

## 4. Profile service (design D4, D6, D7, D9, D10, D12, D18, D21, D23)

- [x] 4.1 Write failing tests for `profile_templates(engine, base_profile)`: a `codebase` duplicate has sparse and fusion steps on a host whose default profile turns hybrid off, every graph names its base profile and no collection, and each template passes `Engine.validate_pipeline`. Verify they fail.
- [x] 4.2 Add `profile_templates` to `src/omrg/compose_pipelines.py`, reusing `canonical_templates`. Verify the 4.1 tests and `tests/unit/test_pipeline_templates.py` pass.
- [x] 4.3 Write failing tests in a new `tests/unit/test_profile_service.py` for readiness: no saved graph, a missing `results` output, a write step in Search, a write step in Answer, no write step in Ingest, two write steps in Ingest, and a draft issue each give one plain-English reason that names the pipeline and contains no bare issue code; an `embedding_identity_mismatch` issue alone does not. Verify they fail.
- [x] 4.4 Write failing tests in the same file for create (from a built-in, from a user profile, empty), rename, refused built-in rename, delete, refused delete with `used_by`, and `used_by` from collection tags. Verify they fail.
- [x] 4.5 Write failing tests in the same file for `standard_graphs`: a built-in returns three graphs equal to revision 1 of a fresh duplicate's pipelines; `codebase` graphs follow `codebase` settings on a `documents` host; a user profile returns `null`. Verify they fail.
- [x] 4.6 Implement `ProfileService` in a new `src/omrg/compose_profiles.py` with the built-in titles and descriptions, the readiness check, `standard_graphs`, the bind check against a collection, and a process lock around delete and bind. Verify the 4.3, 4.4 and 4.5 tests pass.
- [x] 4.7 Write failing tests for the upgrade step (design D10): a search graph fills the Search slot and keeps its runs; a non-empty `layout.title` becomes the profile title; an empty or blank `layout.title` gives the pipeline title; a graph with `profile: codebase` gets base `codebase` and standard `codebase` graphs in the other slots; a graph with no `graph.profile` gets base `documents` and one new revision that names `documents`, with the earlier revision kept; a pipeline whose layout holds `omrg_task` is skipped and keeps its runs; a pipeline titled "Workspace job: ingest" without that key is migrated; a pipeline with no revision gives a not-ready profile; a second call adds nothing. Verify they fail.
- [x] 4.8 Implement the upgrade step in `src/omrg/compose_profiles.py`, using `TASK_LAYOUT_KEY` from `core/workspace/records.py`. Verify the 4.7 tests pass.
- [x] 4.9 Add `omrg.compose_profiles` to the forbidden list of `core-never-imports-top-level-modules` in `pyproject.toml`. Verify `uv run lint-imports` passes.

## 5. Engine dispatch (design D2, D13 to D17)

- [x] 5.1 Move the resource release body of `Engine.close` into a new `src/omrg/engine_lifecycle.py` with no behaviour change. Verify `tests/test_engine.py` and `tests/test_engine_isolation.py` pass and `engine.py` has fewer than 480 lines.
- [x] 5.2 Write failing tests in a new `tests/unit/test_engine_profiles.py`: `Engine.search` on a collection tagged with a duplicate of `documents` returns the same rows as the built-in for the recorded retrieval cases; a request `top_k` replaces the graph's step setting; `hybrid` has no effect; diagnostics list the unused request values. Verify they fail.
- [x] 5.3 Write failing tests in the same file: a user-profile search works when called from a worker thread and from a thread that runs an event loop; a run failure raises an error that names the step; a validation failure raises `ValueError`. Verify they fail.
- [x] 5.4 Write failing tests in the same file: `Engine.answer` on a user profile equals the built-in answer for the recorded answer cases; `client_completion` or `rows` with a user profile raise `ValueError` with the D17 message. Verify they fail.
- [x] 5.5 Write failing tests in the same file: `Engine.ingest` on a user profile returns the built-in summary keys, writes the same rows as the built-in, calls `progress_callback` once per file, and reprocesses a source after an Ingest change. Verify they fail.
- [x] 5.6 Write a guard test that `search`, `answer` and `ingest` on a built-in collection never call `run_pipeline`. Verify it passes before and after 5.7, and fails when the guard is pointed at a user-profile collection.
- [x] 5.7 Implement `src/omrg/engine_profiles.py` (request values, private event loop runner, result mapping, `ProfileRunError`) and the three dispatch branches in `src/omrg/engine.py`; pass the catalogue through `compose.build_engine` in `src/omrg/compose_engine.py`. Verify the 5.2 to 5.6 tests pass and `engine.py` stays under 500 lines.
- [x] 5.8 Add `omrg.engine_profiles` and `omrg.engine_lifecycle` to `core-never-imports-top-level-modules` in `pyproject.toml`. Verify `uv run lint-imports` passes.
- [x] 5.9 Update `docs/guides/pipelines.md` with a "Profiles own pipelines" section: slots, contracts, readiness, request values, result mapping, concurrency rule, server model for answers. Verify `tests/unit/test_pipeline_templates_guides.py` passes.

## 6. Draft check values (design D24)

- [x] 6.1 Write failing tests in `tests/unit/test_pipeline_admission.py` for a new draft controls helper: with no inputs it returns the controls of each valid node; `graph.profile` wins over the collection profile; node parameters win over graph overrides; a node with invalid parameters gets none; the controls equal those of `admit_pipeline` for the same graph and inputs. Verify they fail.
- [x] 6.2 Move the controls loop of `_Admission.node_snapshot` into the helper in `src/omrg/core/pipelines/admission.py` and call it from admission. Verify the 6.1 tests and `uv run pytest tests/unit -k "admission or pipeline" -q` pass, and the file stays under 500 lines.
- [x] 6.3 Write failing tests in `tests/unit/test_web_graphs.py` for `validatePipeline` with no inputs: a valid draft returns `nodes` with controls; the collection comes from a node parameter, then `graph.collection`, then the request `collection`, then the host default; a draft with an unconnected port returns 422 with `issues` and with `nodes` for the valid nodes; a collection whose profile does not resolve gives that node no controls. Verify they fail.
- [x] 6.4 Return the draft controls from `EnginePipelines.validate` in `src/omrg/compose_pipelines.py`, also on a failure, and add `nodes` to the draft view and to the validation failure body in `src/omrg/transports/api/routes/graphs.py`. Verify the 6.3 tests pass and `compose_pipelines.py` stays under 500 lines.

## 7. HTTP API (design D7, D9, D10, D19, D20, D23, D24)

- [x] 7.1 Write failing tests in a new `tests/unit/test_web_profiles.py` for `GET /v1/profiles`, `POST /v1/profiles` (built-in, user, empty source), `GET`, `PATCH` and `DELETE /v1/profiles/{profile_id}`, with 403 for built-ins, 404 for unknown or deleted ids, and 409 with `used_by`. Include `standard_graphs` on `GET` of each built-in, `null` on a user profile, and its absence from list items. Verify they fail.
- [x] 7.2 Implement `src/omrg/transports/api/routes/profiles.py` and register it in `src/omrg/transports/api/app.py`. Verify the 7.1 tests pass.
- [x] 7.3 Write failing tests in `tests/unit/test_web_destructive.py`: `changeCollectionProfile` previews and confirms a ready user profile, refuses a not-ready one with 400 and reasons, and refuses a confirmation after a slot save with 409. Verify they fail.
- [x] 7.4 Change `ProfileBody` and the confirmation state in `src/omrg/transports/api/routes/admin.py` to accept profile ids and to include the profile's revision ids. Verify the 7.3 tests and the existing destructive tests pass.
- [x] 7.5 Write failing tests in `tests/unit/test_web_graphs.py`: `savePipelineRevision` returns `affected_collections`, refuses a breaking save on an in-use profile with 409, refuses a `graph.profile` that differs from the base, and refuses a save on a deleted profile; `createPipeline` answers 410; `getPipeline` shows `profile_slot`. Verify they fail.
- [x] 7.6 Change `src/omrg/transports/api/routes/graphs.py` to meet the 7.5 tests. Verify they pass.
- [x] 7.7 Write a failing test that a web start builds the Engine with the workspace catalogue and runs the upgrade step once. Verify it fails.
- [x] 7.8 Wire the catalogue and the upgrade step into `src/omrg/transports/api/lifespan.py`. Verify the 7.7 test passes.
- [x] 7.9 Write a failing test that a Chat answer and a Knowledge Base search on a user-profile collection add no run record. Verify it fails, then passes after 7.8.
- [x] 7.10 Update `src/omrg/transports/api/openapi.yaml`: the profile operations and schemas, `standard_graphs` on the profile detail schema only, the `ProfileChangeRequest.profile` pattern, `nodes` on the draft check response and on its 422 body, `affected_collections`, `profile_slot`, and `createPipeline` as deprecated with 410 only. Verify the `tests/unit/test_web_openapi_conformance*.py` tests pass.
- [x] 7.11 Update the route table in `src/omrg/transports/api/README.md`. Verify it lists every new operation id.

## 8. MCP, CLI and watcher (design D11, D14, D17)

- [x] 8.1 Write failing tests in `tests/unit/test_compose_profiles_catalogue.py` for `workspace_profile_catalogue()`: it returns a read-only catalogue when `~/.omrg/workspace/workspace.db` exists (use a temporary `HOME`), `None` when it does not, and never creates the folder or the file. Verify they fail.
- [x] 8.2 Implement `workspace_profile_catalogue()` in `src/omrg/compose_profiles.py`. Pass its result from `compose.ensure_runtime_setup()` and add `compose.runtime_engine()` in `src/omrg/compose.py`. Verify the 8.1 tests pass and `compose.py` stays under 500 lines.
- [x] 8.3 Write failing tests in `tests/test_mcp_tools.py`: `list_profiles` returns built-ins only without a catalogue and built-ins plus user profiles with one; it carries read-only annotations. Verify they fail.
- [x] 8.4 Add `list_profiles` to `src/omrg/transports/mcp/profile.py` and register it in `src/omrg/transports/mcp/server.py`. Verify the 8.3 tests pass.
- [x] 8.5 Write failing tests in `tests/test_e2e_stdio.py` (or a new `tests/unit/test_mcp_stdio_profiles.py`): with a default workspace that holds `my-notes` bound to collection `notes`, the stdio server's `search_documents` and `answer_documents` run the `my-notes` pipelines and the database file stays unchanged; with no workspace file the tool returns the D11 error with the profile id and the path. Verify they fail.
- [x] 8.6 Pass `workspace_profile_catalogue()` to `compose.build_engine()` in `src/omrg/transports/mcp/__init__.py`. Verify the 8.5 tests pass.
- [x] 8.7 Write failing tests: `change_collection_profile` accepts a ready user id on an Engine with a read-write catalogue, and refuses a user id on the stdio server with the D11 binding message. Verify they fail, then change the tool and verify they pass.
- [x] 8.8 Write a failing test that `search_documents` passes `None` values through to `Engine.search`; keep the existing built-in search tests as the proof of unchanged results. Verify it fails, then remove the pre-fill in `src/omrg/transports/mcp/search.py` and verify all MCP search tests pass.
- [x] 8.9 Write failing tests in `tests/test_answer_transport_mcp.py`: on a user-profile collection, `answer_documents` and its MRTR resolvers send no sampling request and answer with the server model. Verify they fail, then change `answer.py` and `answer_mrtr.py` and verify they pass.
- [x] 8.10 Write failing tests in `tests/test_cli.py` (or a new `tests/unit/test_cli_user_profiles.py`): with a default workspace that holds `my-notes` bound to `notes`, `omrg search`, `omrg answer` and `omrg ingest` on `notes` run the `my-notes` pipelines; on a built-in collection they call the direct core functions as before; with no workspace file each prints the D11 error and exits with code 1. Verify they fail.
- [x] 8.11 Change `src/omrg/transports/cli/search.py`, `answer.py` and `ingest.py` to ask the resolver for the binding and to call `compose.runtime_engine()` for a user binding. Verify the 8.10 tests and the existing CLI tests pass.
- [x] 8.12 Write failing tests in `tests/test_watcher.py` and `tests/test_install_login_watcher.py`: the watcher and the catch-up ingest on a collection bound to `my-notes` run its Ingest pipeline; with no workspace file the watcher logs the D11 error for that file and keeps running, and the install stops with the D11 error. Verify they fail.
- [x] 8.13 Change `_dispatch_ingest` in `src/omrg/daemon/watcher.py` and `_run_catchup_ingest` in `src/omrg/transports/cli/install_login_watcher.py` in the same way as 8.11. Verify the 8.12 tests and the existing watcher tests pass.
- [x] 8.14 Write a failing test in `tests/test_cli_profile.py` that `omrg set-profile` with a non-built-in name prints the D11 binding message and leaves the tag unchanged. Verify it fails, then change `src/omrg/transports/cli/profile.py` and verify it passes.
- [x] 8.15 Update `docs/guides/mcp-tools.md` (`list_profiles`, `change_collection_profile`, user profiles on the stdio server, the server-model rule for user-profile answers) and `docs/guides/cli-reference.md` (user profiles in `search`, `answer`, `ingest` and `watch`, and the `set-profile` message). Verify every tool and option named exists.

## 9. Latency check and decision record

- [x] 9.1 Write the `slow`-marked latency test from design "Latency check" in a new `tests/unit/test_profile_dispatch_latency.py`. Verify it passes with `uv run pytest -m slow tests/unit/test_profile_dispatch_latency.py -s` and prints the medians.
- [x] 9.2 Record the measured median and 95th-percentile overhead in `docs/guides/pipelines.md`. Verify the numbers match the 9.1 output.
- [x] 9.3 Write `docs/adr/080-profiles-own-pipelines.md` with the decisions D1 to D25 in short form and the measured overhead. Verify it follows the format in `docs/adr/ADR_README.md`.
- [x] 9.4 Add the ADR-080 row to the index table in `docs/adr/ADR_README.md`. Verify the link opens the new file.
- [x] 9.5 Add a gotcha to `AGENTS.md`: the web server owns the workspace; other processes read the default workspace read-only and bind no user profile; built-ins keep the direct path. Verify the text names real paths.

## 10. Release coordination and final verification

- [ ] 10.1 Confirm with the owner of `studio-profiles-gallery` that both changes merge into the integration branch before the next release. Record the planned release in the pull request description. Verify no release tag falls between the two merges.
- [x] 10.2 Run `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`. Verify no failures.
- [x] 10.3 Run `uv run lint-imports`, `uv run ruff check .` and `uv run ruff format --check .`. Verify all three pass.
- [x] 10.4 Run `uv run pytest tests/test_file_size_ceiling.py`. Verify every file stays under 500 lines.
- [x] 10.5 Run `npm run lint`, `npm run typecheck` and `npm test` in `web/`. Verify the web still builds against the changed API.
- [x] 10.6 Run `openspec validate unify-profiles-and-pipelines --strict`. Verify it passes.
- [x] 10.7 Run `./scripts/local_ci.sh`. Verify every step passes before the push.
