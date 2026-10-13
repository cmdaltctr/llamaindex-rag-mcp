# Verification: add-local-web-pipeline-workspace (task 9.3)

Date: 2026-10-13.
Worktree: `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace`, branch `feat/add-local-web-pipeline-workspace`, uncommitted tree on base `489a618`.
Method: the `openspec-verify-change` workflow. Each scenario in the 10 delta specs was mapped to code (`file:line`) and to the tests that assert it. Earlier evidence files were used as leads only. Code and tests were read directly. Status rules:

- **COVERED**: the code does every THEN/AND clause, and a test asserts it.
- **PARTIAL**: one clause is missing in code or in tests. The row says which clause.
- **NOT COVERED**: no implementation or no test.

## Summary

| Capability | Scenarios | COVERED | PARTIAL | NOT COVERED |
|---|---|---|---|---|
| architecture-boundary-enforcement | 9 | 6 | 3 | 0 |
| engine-scoped-composition | 13 | 9 | 4 | 0 |
| local-web-workspace | 22 | 20 | 2 | 0 |
| modular-core-extraction | 16 | 14 | 2 | 0 |
| notebook-plugins | 14 | 12 | 2 | 0 |
| pipeline-canvas | 16 | 12 | 4 | 0 |
| pipeline-graphs | 36 | 30 | 6 | 0 |
| pipeline-run-records | 14 | 10 | 4 | 0 |
| public-library-api | 7 | 6 | 1 | 0 |
| transport-separation | 25 | 17 | 8 | 0 |
| **Total** | **172** | **136** | **36** | **0** |

The REMOVED requirement in `transport-separation` ("Versioned OpenAPI 3.1 contract for a future REST transport") has no scenario in the count. Removal check: the contract-only wording is gone from `openapi.yaml`, `transports/api/README.md` and `transports/api/__init__.py`. Stale wording stays in `src/omrg/transports/__init__.py:5` ("OpenAPI 3.1 contract for the future REST transport") and in `AGENTS.md:46` ("OpenAPI contract only"). These are docstring and documentation drift, not removed behaviour that still runs.

Design coherence (detail in the appendix): D1 to D10 and D12 are followed. D11 uses Hatch `artifacts` plus `scripts/check_web_wheel.py` in place of the named Hatch `force-include`. The intent is met, the named mechanism is not. D12 is deferred as planned (`evidence/deferred-optimisation.md`). The evidence files record 49 deviations and open points. 7 of them are already fixed in the worktree.

## Tests run for this verification

| Run | Command | Result |
|---|---|---|
| Cited pytest files (94 files, the tripwire excluded) | `PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider -m "not slow" <94 files>` | PASS: 1753 passed, 8 skipped, 1 deselected (slow), 73.6 s |
| Cited Vitest files (23 files) | `cd web && npx vitest run <23 files>` | PASS: 23 files, 171 tests passed |
| Import contracts | `PYTHONPATH=src .venv/bin/lint-imports` | PASS: 17 contracts kept, 0 broken (353 files, 1891 dependencies) |
| Sub-agent focused runs and `--collect-only` checks | various | PASS, every cited node id was collected |

The 8 skips depend on extras: 5 in `tests/test_chroma_cloud.py` and 2 in `tests/test_compose.py` need the `chroma` extra, and 1 in `tests/test_compose.py` needs `llama_index.embeddings.openai_like`. No scenario depends on a skipped test. No scenario depends on a `slow` test.

Not run here: the full suite and `tests/test_clean_base_tripwire.py`. Both belong to task 9.2 (the lead's run). The scenario "Full test suite passes" is PARTIAL for that reason only.

## OpenSpec validation

| Command | Result |
|---|---|
| `openspec validate add-local-web-pipeline-workspace --strict` | PASS: "Change 'add-local-web-pipeline-workspace' valid" (exit 0) |
| `openspec validate --all --strict` | PASS: "Totals: 62 passed, 0 failed (62 items)" (exit 0). Only INFO notes about long requirement text. |

## Graphify

Skipped by user decision. The user does not refresh Graphify during change work, and `graphify-out/` is gitignored.

## Classification of the 36 PARTIAL scenarios

### A. Behaviour differs from the spec (functional gaps, these block ADR acceptance)

1. **notebook-plugins / Approved ingestion experiment runs.** The spec says the index and outputs stay below the approved experiment workspace. The run service stores every run result, experiment runs included, in `<OMRG workspace>/artefacts` (`src/omrg/transports/api/runs_wiring.py:379`, `ArtefactStore(layout.artefacts)`). No HTTP test runs an ingestion experiment graph with a bound credential.
2. **pipeline-run-records / Runs capture sufficient provenance.** The spec asks for the selected index identities. Live-library runs record no store data version and no backend identity. Only experiment runs add one (`runs_wiring.py:194`). No Python test checks `resources.operations` versions.
3. **pipeline-run-records / Monitoring reconnects.** The spec says the client refreshes the authoritative run state on reconnect. The client re-reads the run record only at monitor start and at stream end, not on each reconnect. No Vitest test covers it.
4. **local-web-workspace / Long work is admitted.** The spec asks for event inspection of ingestion and codebase-map jobs. `routes_jobs.py:174` gives status polling only (`GET /v1/jobs/{job_id}`). The run event routes return 404 for job ids.
5. **pipeline-canvas / Reranker disabled with a click.** The run records "disabled by node parameter". The canvas node still shows "Completed", and the reason shows only in a collapsed summary in Runs.
6. **pipeline-canvas / Core reports fallback or failure.** The bypass event carries no reason (`src/omrg/core/pipelines/execution.py:185`), so a bypassed node shows "Bypassed" with no explanation. Fallback and failure are tested.
7. **pipeline-graphs / Explicit node override.** The node control and its source are kept in the admission snapshot and in the validate response. They are not in the run result or in the stored run record, as the scenario says.
8. **engine-scoped-composition (OCR client).** The requirement says runs do not construct or close their own providers. When the Engine has no OCR client, `src/omrg/compose_pipelines.py:347-351` builds one per run and closes it afterwards.
9. **transport-separation / Contract validated in CI.** CI runs `openapi-spec-validator` (`.github/workflows/ci.yml:75-77`, `scripts/local_ci.sh:33-35`). CI runs `uv sync --frozen` without `--extra web`, so every `tests/unit/test_web_*.py` test, the runtime conformance tests included, is skipped in CI.
10. **transport-separation / Release assets are absent** and **local-web-workspace / Installed package launches outside the checkout.** `scripts/check_web_wheel.py` exists, but no test, `local_ci.sh` step or CI workflow calls it. The wheel launch proof is a manual smoke test in `evidence/frontend-scaffold.md`.
11. **architecture-boundary-enforcement / Ingestion no longer reaches upward.** The spec names an injected detection seam. The code calls `core.codebase.codebase_map.detect_file_types` directly (`src/omrg/core/ingestion/sources.py:115`). `core/ingestion/pipeline.py:203` imports `omrg.capabilities` lazily (this was already on `v3`). No contract checks it.

### B. Behaviour present, test missing (test-only gaps)

- pipeline-graphs: changing a connection changes execution (no two-revision wiring test); reader `structured=True` through a graph run; ingestion parity with `metadata_degraded=true`; registered replacement splitter through a graph run; metadata store ownership through `Engine.run_pipeline`.
- engine-scoped-composition: settings default unchanged after `build_engine`; reranker model cache survives another Engine closing; Engine call after a cancelled run and `shutdown_requested` unset; one run cannot report another run's reranker failure reason.
- modular-core-extraction: code and config sources through `read.document` in a graph.
- pipeline-canvas: node selection and run identity after Canvas to Runs to Canvas (storage-level test only); theme change keeps canvas edits (viewport is manual evidence only).
- notebook-plugins: the trust notice text ("network", "not an operating-system sandbox") is not fully asserted, and the frontend copy is not tied to the server constant.
- pipeline-run-records: repeat of an older revision; vector store unchanged after a workspace upgrade; retry of an interrupted run linked to the source-completeness check.
- transport-separation: `omrg` with no arguments starts no web or editor; parameters and annotations of six MCP tools; `answer_documents` missing from `handler_names` in `tests/test_mcp_tools.py::test_all_handlers_importable_from_package_root`; no contract forbids `mcp`, `typer` or `click` in `omrg.core`; the public static frontend is not named in the auth section of the contract.
- public-library-api: `skipped_nodes` and `completed_effects` asserted at runner level only, not through `Engine.run_pipeline`.
- architecture-boundary-enforcement: no allow-list test for top-level `src/omrg/*.py`; no contract forbids `core.ingestion` and `core.retrieval` importing each other at package level.

### C. Process

- modular-core-extraction / Full test suite passes: result owned by the task 9.2 lead run.

## Spec text that does not match the deliberate design

Not edited. Each one needs a decision on the design side first. After the decision, fix the delta (and the baseline if `openspec validate --strict` then complains), as CLAUDE.md gotcha 12 says.

1. pipeline-graphs threshold scenario: the registered `select.threshold` accepts fused (RRF) scores by design. "SHALL reject" applies only to the test fixture `select.dense_threshold`.
2. pipeline-graphs / Conflicting commits: the code rejects any second commit destination. The text says only a second commit to the same source and collection.
3. pipeline-graphs / Ingestion graph changes: a node value equal to its default still counts as a change, so the source is processed again once.
4. pipeline-graphs / graph profile: the hybrid setting of a profile does not add or remove the sparse branch. The wiring decides.
5. pipeline-canvas: "Cancelling" is a run status, not a node state. "Disabled" and "bypass" are two different mechanisms.
6. notebook-plugins: an experiment credential is refused on all live-library runs, reads included. The spec only asks for mutation (lead decision).
7. pipeline-run-records / Process stops between stores: the text implies a recovery step. The completeness rules apply during the retry.
8. architecture-boundary-enforcement: the package list leaves out `core.plugins` and `core.experiments`. The top-level module scenario does not name `capabilities.py` or `pipeline_templates.py`.
9. public-library-api: `docs/guides/library-usage.md:125-126` imports `RunCancellation` and `pipeline_templates` from modules outside `__all__`.

## Other findings

- `tests/test_no_module_level_strategy_imports.py` lists `omrg.core.retrieval.policy` as forbidden. `src/omrg/core/retrieval/operations.py:22` imports it at module level, so `retrieval.pipeline` now loads `policy`. The test still passes because it does not import the adapter modules.
- `tests/unit/test_plugin_boundaries.py` docstring says no contract names `omrg.core.plugins`. The `plugin-host-starts-no-processes` contract now does.
- `tests/test_clean_base_tripwire.py` counts were re-baselined in a venv with FastAPI. In CI, where the web tests skip, the counts can drift.
- The opening sentence of `tasks.md` says every box stays unchecked. 54 of 56 boxes are now checked.

## Open risks

1. A marimo `pyproject.toml` with `auto_instantiate = true`, in the notebook folder or any parent folder, overrides OMRG's launch configuration and turns start-up cell runs on again. This is documented only.
2. A notebook header can set `on_cell_change = "autorun"`. Only the run guard in the starter notebook blocks runs the user did not request.
3. OMRG does not detect when the editor exits on its own. The editor credential and connection files stay until Stop or server shutdown.
4. The frontend bundle is 541 kB (163 kB gzip). Code splitting is deferred to task 9.4.
5. Chrome reports 10 to 40 form fields per view with no `id` or `name`. Labels exist, so this is not an accessibility failure. It is still open.
6. Experiment contexts live in memory for each launch. A restart loses them (lead decision).
7. CI does not install the `web` extra, so the web and runtime conformance tests do not run in CI (see A9).
8. `check_web_wheel.py` is not wired into any release or CI step (see A10).

## ADR-075 decision

**ADR-075 stays Proposed.** There are no NOT COVERED scenarios. The 11 functional gaps in section A are not PARTIALs with an accepted, recorded reason. Task 9.2 (full gates) is also still open.

Blocking gaps and actions:

1. Experiment artefacts: route experiment run results to the experiment workspace, or amend the spec to allow results in the OMRG workspace. Add an HTTP ingestion-experiment test with a bound credential.
2. Provenance: record the store data version and backend identity for live-library runs, then add a test.
3. Reconnect: re-read the run record on each reconnect in the event client, then add a Vitest test. Or amend the clause.
4. Job events: add `GET /v1/jobs/{job_id}/events` (read scope, OpenAPI, test). Or limit the scenario to graph runs.
5. Canvas reasons: put a reason on the core bypass event and show disabled or bypass reasons on the node, then add tests.
6. Node override: add the control and its source to `snapshot_provenance` and test it. Or reword the scenario to the admission snapshot.
7. OCR client: let the Engine own one lazy OCR client. Or amend the requirement to allow a run-owned client when the Engine has none.
8. CI web extra: add `--extra web` to the CI test job or add a `web-extra` job. Then re-measure the tripwire counts there.
9. Wheel check: call `check_web_wheel.py` after the frontend build in the release path and in `local_ci.sh`, and add a unit test.
10. Detection seam: amend the spec text to the direct call, or inject a detector. Add a contract that stops `omrg.core` importing top-level modules.
11. Finish task 9.2, then repeat this check. Change ADR-075 to Accepted only when sections A and C are closed or recorded as accepted.

---

# Appendix: per-capability detail

Each section below is the verification for one capability. It gives one row per scenario with code and tests, then gaps, spec text issues, deviations recorded in evidence, and the test files cited. Paths are relative to the worktree.

## Verification: architecture-boundary-enforcement

Change: `add-local-web-pipeline-workspace`. Worktree: `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace` (branch `feat/add-local-web-pipeline-workspace`, uncommitted tree on `489a618`).
Spec: `openspec/changes/add-local-web-pipeline-workspace/specs/architecture-boundary-enforcement/spec.md` (4 requirements, 9 scenarios).
Contracts: `pyproject.toml` `[tool.importlinter]` (no separate `.importlinter` file). `lint-imports` on the worktree: `Analyzed 353 files, 1891 dependencies. Contracts: 17 kept, 0 broken.` CI runs it at `.github/workflows/ci.yml:73` and `scripts/local_ci.sh:28`.

Result: 6 COVERED, 3 PARTIAL, 0 NOT COVERED.

| Requirement / Scenario | Status | Code | Tests |
|---|---|---|---|
| Full-package coverage / Every package is a contract source | COVERED | `pyproject.toml` contracts `core-business-avoids-providers-transports` (sources include all 13 spec packages plus `core.plugins`, `core.experiments`), `pipeline-runner-independent-of-domains`, `workspace-services-independent-of-domains-and-web`, `experiment-contexts-stay-pure`, `plugin-host-starts-no-processes`, `core-free-of-web-notebook-and-sqlite-runtimes`; `providers-constructed-only-in-compose` uses source `omrg`, so every package is a source module | `tests/test_contract_coverage.py::test_package_is_covered_by_a_contract`, `::test_contracts_are_actually_declared`; `tests/test_pipeline_import_boundaries.py::test_business_contract_covers_new_packages`, `::test_contract_is_declared_strictly`; `tests/unit/test_plugin_boundaries.py::test_core_plugins_start_no_processes`; `lint-imports` (CI). Note: `test_contract_coverage` also counts `forbidden_modules`, so it is looser than "source module". |
| Full-package coverage / Transport import from core fails | COVERED | `pyproject.toml` `core-never-imports-transports` (source `omrg.core`, forbids `omrg.transports`); `core-business-avoids-providers-transports` covers `omrg.daemon` | `tests/test_pipeline_import_boundaries.py::test_each_forbidden_import_breaks_contract[core-never-imports-transports-omrg.core.retrieval.graph_adapter]`, `::test_contract_kept_without_violation[...]`; `lint-imports` in CI. Note: no deliberate-violation test for `daemon -> transports`; the contract is older and enforced by `lint-imports`. |
| Use-case subsystems / Ingestion no longer reaches upward | PARTIAL | `src/omrg/core/ingestion/sources.py:108-123` (`detect_content_types` imports `..codebase.codebase_map.detect_file_types` lazily); `src/omrg/core/ingestion/pipeline.py:194` (calls it); `src/omrg/core/ingestion/pipeline.py:203` (lazy `from omrg.capabilities import build_ocr_routes`, pre-existing on `v3`) | None specific. No test or contract forbids `omrg.core.*` importing top-level `omrg.capabilities`, `omrg.engine` or `omrg.compose*`. Missing: (a) detection goes through the sibling `core.codebase` package, not an injected detection seam and not `omrg.integrations.magika` directly; (b) no executable check. |
| Use-case subsystems / Top-level business modules are gone | PARTIAL | `src/omrg/` top level holds `__init__.py`, `engine.py`, `compose.py`, `compose_answer.py`, `compose_engine.py`, `compose_experiments.py`, `compose_pipelines.py`, `compose_settings.py`, `capabilities.py`, `pipeline_templates.py`. By inspection these are public API or composition (module docstrings say so). Graph scheduling is in `src/omrg/core/pipelines/`, workspace services in `src/omrg/core/workspace/`. | No test enforces the allowed top-level set. `tests/unit/test_pipeline_catalogue.py::test_pipelines_package_avoids_domain_and_process_imports` covers only the runner side. Missing: an executable check of the top-level module list. `pipeline_templates.py` (graph definitions) is a judgement call. |
| Use-case subsystems / Subsystems share only settings | PARTIAL | Grep of `src/omrg/core/{codebase,documents}` finds no import of `core.ingestion` or `core.retrieval`; `core/ingestion` and `core/retrieval` do not import one another. Cross-domain graph wiring goes through `src/omrg/compose_pipelines.py` (catalogue registrars). Contracts `retrieval-graph-adapters-stay-in-domain`, `ingestion-graph-adapters-stay-in-domain`, `answer-graph-adapters-stay-in-domain` cover adapter modules only (direct imports, `allow_indirect_imports = true`). | `tests/unit/test_answer_graph_adapters.py::test_adapter_module_import_stays_inside_the_answer_domain`; `lint-imports` (adapter contracts). Missing: no contract or test forbids `core.ingestion <-> core.retrieval` or `core.codebase`/`core.documents -> core.ingestion`/`core.retrieval` for whole packages. The rule holds today by inspection only. |
| Graph scheduling independent / New operation is registered | COVERED | `src/omrg/core/pipelines/catalogue.py:198` (`register`), `:223` (`get`); `src/omrg/core/pipelines/runner.py:84` (`run_pipeline`), `:170` (`catalogue.get(node.operation, node.version)`, no name branch) | `tests/unit/test_pipeline_catalogue.py::test_register_and_lookup_latest_version`, `::test_dispatch_modules_have_no_name_branches`; `tests/unit/test_pipeline_runner_contracts.py::test_adapters_receive_explicit_settings_resources_and_params`, `::test_missing_adapter_fails_before_any_node_runs`; `tests/unit/test_pipeline_runner.py` (runs test-registered scripted adapters via `scripted_catalogue`). Note: no test adds an operation id outside the fixture set, but the fixture adapters are test-registered, which is the same path. |
| Graph scheduling independent / Runner reaches into a domain implementation | COVERED | `pyproject.toml` `pipeline-runner-independent-of-domains` (forbids ingestion, retrieval, answer, providers, transports, `subprocess`, `sqlite3`, `fastapi`, `starlette`, `uvicorn`, `marimo`; no ignores; indirect chains checked) | `tests/test_pipeline_import_boundaries.py::test_each_forbidden_import_breaks_contract[pipeline-runner-independent-of-domains-omrg.core.pipelines.violation]` (asserts `violator -> module` named for each edge), `::test_contract_kept_without_violation[...]`, `::test_contract_is_declared_strictly[...]`; `tests/unit/test_pipeline_catalogue.py::test_pipelines_package_avoids_domain_and_process_imports` |
| Injected leaves / Web runtime is unavailable | COVERED | `pyproject.toml` `core-free-of-web-notebook-and-sqlite-runtimes` (source `omrg.core`), `pipeline-runner-independent-of-domains`, `workspace-services-independent-of-domains-and-web`; `src/omrg/transports/api/__init__.py` (imports nothing); `src/omrg/__init__.py` (PEP 562 lazy exports) | `tests/unit/test_pipeline_models.py::test_importing_omrg_does_not_load_pipelines_or_settings`, `::test_top_level_exports_graph_types`; `tests/unit/test_workspace_contracts.py::test_contract_import_stays_free_of_persistence_and_domain_modules` (subprocess probe: no `fastapi`, `marimo`, `sqlite3`, transports); `tests/test_pipeline_import_boundaries.py::test_each_forbidden_import_breaks_contract[core-free-of-web-notebook-and-sqlite-runtimes-omrg.core.retrieval.graph_adapter]`; `tests/unit/test_engine_pipelines_isolation.py::test_two_engines_run_concurrently_and_stay_isolated` (validation and execution with no app). Note: proof is static plus import probes; no test sets `sys.modules["fastapi"] = None` and then validates and runs a graph. `marimo` is not installed in the venv, so execution tests already run without it. |
| Injected leaves / External process wrapper imports business logic | COVERED | `pyproject.toml` `integrations-are-leaves` (sources `omrg.integrations`, forbids `omrg.core`, `omrg.transports`, `omrg.daemon`; no ignore for `workspace_sqlite` or `process_launcher`); `plugin-host-starts-no-processes`; `src/omrg/integrations/process_launcher.py`; `src/omrg/integrations/workspace_sqlite/` (imports only its own modules) | `tests/unit/test_plugin_boundaries.py::test_process_launcher_is_an_integration_leaf` (forbids any `omrg` import), `::test_checker_detects_a_forbidden_import`; `lint-imports` in CI (`integrations-are-leaves`). Note: no deliberate-violation pytest for `workspace_sqlite`; enforcement is the CI `lint-imports` step. |

### Gaps

1. Ingestion no longer reaches upward (PARTIAL). Choose one:
   1. Change the scenario text to match the code: detection "MUST use `omrg.core.codebase` detection or the sanctioned integration" (the baseline spec said `omrg.core.codebase`).
   2. Inject a detector callable into `ingest_path_async` from composition and remove the `core.codebase` import from `core/ingestion/sources.py:115`.
   In both cases add an import-linter contract `core-avoids-top-level-modules` (source `omrg.core`, forbidden `omrg.engine`, `omrg.compose`, `omrg.compose_*`, `omrg.pipeline_templates`) and decide whether `core/ingestion/pipeline.py:203 -> omrg.capabilities` gets a PERMANENT ignore entry with a reason, or moves behind injection.
2. Top-level business modules are gone (PARTIAL). Add a pytest that lists `src/omrg/*.py` and compares it with an allow-list (`__init__`, `engine`, `compose`, `compose_*`, `capabilities`, `pipeline_templates`), so a new top-level business module fails the build.
3. Subsystems share only settings (PARTIAL). Add two forbidden contracts to `pyproject.toml`:
   1. `ingestion-and-retrieval-independent`: source `omrg.core.ingestion` forbids `omrg.core.retrieval`; a second contract (or a `independence` contract over both) for the reverse direction.
   2. `graph-subsystems-avoid-ingestion-retrieval`: sources `omrg.core.codebase`, `omrg.core.documents`, forbidden `omrg.core.ingestion`, `omrg.core.retrieval`.
   Run `lint-imports` to confirm both are kept, then extend `tests/test_pipeline_import_boundaries.py::_NEW_CONTRACTS` so a deliberate violation breaks each one.

### Spec text issues

1. "Ingestion no longer reaches upward" refers to "its injected detection seam". No such seam exists; ingestion calls `core.codebase.codebase_map.detect_file_types`, which then uses `integrations.magika`. The baseline spec (`openspec/specs/architecture-boundary-enforcement/spec.md:115-119`) required `omrg.core.codebase`. The delta wording describes a seam that was not built.
2. "Full-package import boundary coverage" lists 13 business-contract packages. The implementation also includes `core.plugins` and `core.experiments`. The list is a minimum, not wrong, but it is out of date.
3. "Every package is a contract source" says "source module". `tests/test_contract_coverage.py` accepts a package named only in `forbidden_modules`, and the `providers-constructed-only-in-compose` contract makes `omrg` a source of everything. The scenario is met, but the test would also pass for weaker configurations.
4. "Top-level business modules are gone" names `engine.py`, `compose.py` and "composition helpers". The tree also holds `capabilities.py` and `pipeline_templates.py`. Both are composition by their docstrings, but the spec does not name them.

### Deviations recorded in evidence

1. `import-boundaries.md`: `subprocess` and `sqlite3` are forbidden for `core.workspace` as well as the runner (stricter than the spec). Sibling-domain adapter contracts were deferred to task 3.8; they now exist as the three `*-graph-adapters-stay-in-domain` contracts with `allow_indirect_imports = true` (direct imports only).
2. `plugins.md`: `manifest.py` drafted before its test (not strict test-first); mutation checks cover it. Contract for `core.plugins` was proposed in evidence and is now applied (`plugin-host-starts-no-processes`). `tests/unit/test_plugin_boundaries.py` docstring still says "No import-linter contract names `omrg.core.plugins` yet", which is stale.
3. `experiment-contexts.md` and `experiment-transport.md`: `experiment-contexts-stay-pure` contract added for `core.experiments`.
4. Evidence recorded 12 kept (task 1.3) and 16 kept (lead follow-up). The current run gives 17 kept, 0 broken.

### Test files cited

- tests/test_contract_coverage.py
- tests/test_pipeline_import_boundaries.py
- tests/unit/test_plugin_boundaries.py
- tests/unit/test_pipeline_catalogue.py
- tests/unit/test_pipeline_runner_contracts.py
- tests/unit/test_pipeline_runner.py
- tests/unit/test_pipeline_models.py
- tests/unit/test_workspace_contracts.py
- tests/unit/test_engine_pipelines_isolation.py
- tests/unit/test_answer_graph_adapters.py

## Verification: engine-scoped-composition

Change: `add-local-web-pipeline-workspace`. Worktree: `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace` (branch `feat/add-local-web-pipeline-workspace`, uncommitted tree). Date: 2026-10-13.

Result: 13 scenarios. 9 COVERED, 4 PARTIAL, 0 NOT COVERED.

| Requirement / Scenario | Status | Code | Tests |
|---|---|---|---|
| Engine owns its composition / Construction from explicit settings | COVERED | `src/omrg/engine.py:65-116` (stores the given objects, constructs nothing; graph state `EnginePipelines()` is empty until first use, `src/omrg/compose_pipelines.py:362-368`) | `tests/test_engine.py::test_engine_constructs_directly_without_runtime_setup`, `tests/test_engine.py::test_direct_engine_construction_never_calls_get_settings`, `tests/unit/test_engine_pipelines.py::test_validation_has_no_side_effects` |
| Engine owns its composition / Construction from the environment | COVERED | `src/omrg/engine.py:120-129` (`from_environment` calls `compose.build_engine()`); new `src/omrg/compose_engine.py:173-182` (`experiment_base_settings`) keeps `get_settings()` inside a composition-root sibling | `tests/test_engine.py::test_engine_from_environment_delegates_to_build_engine`, `tests/test_engine.py::test_build_engine_constructs_engine_from_settings`, `tests/test_no_global_settings_reads.py::test_no_global_settings_reads_in_production_package` |
| Engine owns its composition / No process-global mutation | PARTIAL: the default effective settings object is not asserted unchanged after construction | `src/omrg/compose_engine.py:48-160` (`build_engine` returns `Engine(...)`, installs nothing); only `src/omrg/compose.py:391-392` (`ensure_runtime_setup`) calls `_install_as_process_default` | `tests/unit/test_experiment_contexts_engines.py::test_production_builder_composes_through_build_engine` (LlamaIndex `Settings.embed_model` unchanged), `tests/unit/test_experiment_contexts_engines.py::test_poisoned_process_defaults_are_untouched` (default store unchanged after build and run), `tests/test_engine.py::test_importing_omrg_constructs_nothing`, `tests/test_engine.py::test_engine_install_as_process_default_sets_globals` (installs happen only through the explicit installer) |
| Engine owns its composition / Construction failures are actionable | COVERED | `src/omrg/compose_engine.py:48-160` (validation and provider construction before `Engine(...)`) | `tests/test_engine.py::test_engine_construction_failure_leaves_no_partial_state`, `tests/test_engine.py::test_build_engine_fail_fast_on_invalid_embed_provider`, `tests/test_engine.py::test_build_engine_fail_fast_on_invalid_store`, `tests/test_compose.py::test_build_embed_model_validates_unknown_provider` (real message names `EMBED_PROVIDER='bogus'`) |
| Engine owns its composition / Graph adapters use injected composition | COVERED (see Deviations 1) | `src/omrg/engine.py:427-441` (`_graph_host` passes store, embedder, reranker, OCR, lazy `answer_llm`, `verify_llm`); `src/omrg/compose_pipelines.py:158-190` (`build_graph_host`), `:434-480` (`run` merges host and plan resources); adapters read `context.resources` only, for example `src/omrg/core/ingestion/graph_adapters.py:213,256,320,377`, `src/omrg/core/retrieval/graph_adapters.py:137` | `tests/unit/test_engine_pipelines.py::test_retrieval_graph_runs_on_the_engine_store`, `tests/unit/test_engine_pipelines_isolation.py::test_two_engines_run_concurrently_and_stay_isolated` (embedder identity `m-a`), `tests/unit/test_engine_pipelines.py::test_answer_model_is_built_once_and_shared_with_engine_answer`, `tests/unit/test_engine_pipelines_ingestion.py::test_ingestion_graph_writes_the_same_rows_as_engine_ingest`, `tests/unit/test_engine_pipelines_ingestion.py::test_ingestion_run_builds_and_closes_its_own_ocr_client`, `tests/unit/test_ingestion_graph_adapters.py::test_missing_resource_fails_before_any_work`, `tests/unit/test_retrieval_graph_adapters.py::test_missing_resource_is_reported` |
| Engine owns its composition / Graph adapters are covered by the default-accessor guard | COVERED | `tests/test_no_global_settings_reads.py:193-225` (`_GUARDED_LEAVES` gains 14 seam and adapter modules across retrieval, answer and ingestion) | `tests/test_no_global_settings_reads.py::test_repaired_leaf_has_no_default_accessor_reads` (parametrised, includes all `graph_adapters*.py`), `tests/test_no_global_settings_reads.py::test_guarded_leaves_exist`, `tests/unit/test_graph_adapters_store_forwarding.py::test_enrich_forwards_run_store_and_settings_to_metadata` (spy fails if `store` or `settings` is dropped), `tests/unit/test_retrieval_graph_adapters.py::test_poisoned_process_defaults_are_never_read`, `tests/unit/test_answer_graph_adapters.py::test_adapters_never_read_process_defaults`, `tests/unit/test_ingestion_graph_adapters.py::test_adapters_never_read_process_defaults`, `tests/unit/test_engine_pipelines_isolation.py::test_poisoned_process_defaults_are_never_read` |
| Engine owns its composition / Answering remains lazy for graphs | COVERED | `src/omrg/engine.py:429` (`answer_llm` is the bound `_get_answer_llm`, not a built model), `:443-447`; `src/omrg/compose_pipelines.py:418-432` (judge built on first call per answer block) | `tests/unit/test_engine_pipelines.py::test_retrieval_graph_never_builds_answer_models`, `tests/unit/test_engine_pipelines.py::test_empty_evidence_answer_graph_never_builds_answer_models`, `tests/unit/test_engine_pipelines.py::test_validation_has_no_side_effects`, `tests/unit/test_answer_graph_adapters.py::test_empty_evidence_returns_no_evidence_without_resolving_models` |
| Engine owns its composition / Explicit Engine lacks named-profile support | COVERED | `src/omrg/compose_pipelines.py:112-137` (`FixedProfileSource.load_profile` raises with corrective actions; `environment_keys` empty), `:287-297` (`_profile_issues` for draft checks), `:189` (resolver chosen only from the Engine) | `tests/unit/test_engine_pipelines.py::test_explicit_engine_cannot_load_named_profile` (code `profile_resolution_failed`, message names the profile and the resolver) |
| Graph resource leases / One run completes | COVERED | `src/omrg/compose_pipelines.py:462-480` (`active_runs` increment, per-Engine `asyncio.Lock`, `finally` decrement; `plan.close()` in inner `finally`) | `tests/unit/test_engine_pipelines_isolation.py::test_runs_on_one_engine_are_serialised`, `tests/unit/test_engine_pipelines_isolation.py::test_failed_run_releases_its_lease`, `tests/unit/test_engine_pipelines_isolation.py::test_close_during_a_run_fails_and_keeps_the_engine_usable` (Engine usable after the run), `tests/unit/test_engine_pipelines.py::test_caller_cancellation_is_run_scoped` (lease released after a cancelled run) |
| Graph resource leases / Close is requested while a graph is active | COVERED | `src/omrg/engine.py:353-372` (`close()` raises `RuntimeError` before `_closed` is set while `active_runs > 0`); web drain before close `src/omrg/transports/api/lifespan.py:300-332` | `tests/unit/test_engine_pipelines_isolation.py::test_close_during_a_run_fails_and_keeps_the_engine_usable`, `tests/unit/test_web_launch.py::test_shutdown_waits_for_active_work_and_rejects_new_admission`, `tests/unit/test_web_experiments_runtime.py::test_shutdown_order_is_service_editors_experiments_engine`, `tests/unit/test_workspace_service_lifecycle.py::test_shutdown_cancels_queued_and_waits_for_cooperative_run` |
| Graph resource leases / Another Engine is disposed | PARTIAL: shared immutable model artefacts surviving another Engine's close are not asserted for graphs | `src/omrg/engine.py:353-414` (closes only own store and OCR client, evicts only own BM25 namespace, never calls `reset_model_cache`); `src/omrg/compose_pipelines.py:413-416` (releases only own catalogue and judges) | `tests/unit/test_engine_pipelines_isolation.py::test_two_engines_run_concurrently_and_stay_isolated` (closes Engine B, then runs Engine A), `tests/test_engine.py::test_engine_close_evicts_only_own_bm25_entries`, `tests/test_engine_isolation.py::test_close_engine_a_leaves_engine_b_functional` |
| Graph cancellation is run scoped / One run is cancelled | PARTIAL: "explicit Engine operation" clause and the "no global shutdown flag" rule are not asserted | `src/omrg/core/pipelines/cancellation.py:34-90` (`RunCancellation`, `run_cancellation`); `src/omrg/compose_pipelines.py:462` (one token per run); no reference to `shutdown_requested` in `src/omrg/core/pipelines/`, `src/omrg/compose_pipelines.py` or any `graph_adapters*.py` | `tests/unit/test_engine_pipelines.py::test_caller_cancellation_is_run_scoped` (second graph run on the same Engine succeeds), `tests/unit/test_pipeline_cancellation.py::test_cancellation_between_units_keeps_earlier_commits`, `tests/unit/test_pipeline_cancellation.py::test_entered_commit_completes_before_terminal_cancel`, `tests/unit/test_ingestion_graph_adapters_commit.py::test_cancellation_during_commit_lets_it_finish` |
| Graph cancellation is run scoped / Shared inference state is unsafe for parallel use | PARTIAL: serialisation is proved; the outcome "one run does not report another run's diagnostic state" is not asserted | `src/omrg/core/pipelines/runner.py:47-57,146` and `src/omrg/core/pipelines/scheduler.py:40-55` (`MODEL_CALL` and `SOURCE_COMMIT` take exclusive leases); `src/omrg/compose_pipelines.py:465` (per-Engine run lock); `src/omrg/core/retrieval/_reranker_cache.py:32,47` (process failure counter under `_CACHE_LOCK`); reranker `last_failure_reason` is per instance, read in `src/omrg/core/retrieval/operations.py:236-240` | `tests/unit/test_pipeline_runner.py::test_model_calls_on_one_resource_are_serialised`, `tests/unit/test_pipeline_runner.py::test_lease_rules_are_configurable`, `tests/unit/test_pipeline_runner_scheduler.py::test_exclusive_lease_excludes_other_holders`, `tests/unit/test_engine_pipelines_isolation.py::test_runs_on_one_engine_are_serialised` |

### Gaps

1. No process-global mutation. Tests prove that construction leaves the LlamaIndex embed model and the default store unchanged. No test proves the default effective settings object is unchanged.
   Action:
   1. Add a test in `tests/test_engine.py` that installs sentinel defaults with `set_default_store`, `set_default_effective_settings` and `Settings.embed_model`.
   2. Call `compose_engine.build_engine(settings)` with patched providers, and construct `Engine(...)` directly.
   3. Assert that all three accessors still return the sentinels.
2. Another Engine is disposed. No test proves that shared, immutable model artefacts stay valid for a graph after another Engine closes.
   Action:
   1. Add a test in `tests/unit/test_engine_pipelines_isolation.py` that puts an entry in the reranker `_MODEL_CACHE` (or uses a fake reranker that records a shared artefact).
   2. Build two Engines, close Engine B, then run a graph with a `select.rerank` node on Engine A.
   3. Assert the cache entry is still present and the run reports `reranked=True`.
3. One run is cancelled. The test covers a second graph run only.
   Action:
   1. Extend `tests/unit/test_engine_pipelines.py::test_caller_cancellation_is_run_scoped`, or add a new test.
   2. After the cancelled run, call `engine.search(...)` and assert it returns rows.
   3. Assert `omrg.core.ingestion._state.shutdown_requested.is_set()` is `False` before and after the cancelled run.
4. Shared inference state is unsafe for parallel use. Serialisation is tested; diagnostic isolation is not.
   Action:
   1. Add a test with a fake reranker whose `last_failure_reason` differs per call (fail for run A, succeed for run B).
   2. Start both runs on one Engine.
   3. Assert run A's `select.rerank` summary carries its failure reason and run B's carries none.

### Spec text issues

1. Requirement "An engine owns its own composition" says "Runs SHALL borrow composed resources rather than constructing or closing their own providers". The implementation builds and closes a run-owned OCR client when the Engine has none and a node enables `ocr_fallback_enabled` (`src/omrg/compose_pipelines.py:347-351`, closed by `RunPlan.close()` at `:314-317`). This mirrors the `ingest_path_async` rule and the construction happens in composition-root code, not in an adapter. The requirement text and the design conflict. Choose one:
   1. Amend the requirement to allow a run-scoped OCR client that composition builds and closes for an Engine without one.
   2. Change composition so the Engine owns one lazily-built OCR client that runs borrow.
2. Scenario "One run is cancelled" lists "another admitted run or explicit Engine operation". On one Engine, runs are serialised by the run lock, so "another admitted run" is always sequential, never concurrent. The test matches that design. No text change needed, but readers may expect a concurrent case.

No scenario text was found to be factually wrong.

### Deviations

From `evidence/engine-wiring.md` and code reading:

1. Run-owned OCR client (see Spec text issues 1). Tested by `tests/unit/test_engine_pipelines_ingestion.py::test_ingestion_run_builds_and_closes_its_own_ocr_client`.
2. Runs on one Engine are serialised by one `asyncio.Lock` (`src/omrg/compose_pipelines.py:366,465`). Two Engines run concurrently. Evidence calls this the lease; there is no per-resource lease object at the Engine level, only the `active_runs` counter and the lock.
3. `close()` refuses while `active_runs > 0`, including runs that wait for the lock. The web runtime drains its run service and admission before it calls `engine.close()`.
4. An `AdmissionSnapshot` passed to `run_pipeline` is not checked against the Engine that admitted it (`evidence/engine-wiring.md` open point 3). Request limits are re-checked (`src/omrg/compose_pipelines.py:453-459`).
5. `request_limit_issues` imports private `_QUERY_MAX_CHARS`, `_TOP_K_MAX`, `_EXPAND_WINDOW_MAX` from `core/answer/pipeline.py` (`evidence/engine-wiring.md` open point 1).
6. The strict `xfail` defect recorded in `evidence/engine-wiring.md` (answer adapters did not accept `ContextBundle`) is fixed. No `xfail` marker remains, and `tests/unit/test_engine_pipelines.py::test_answer_chain_accepts_assembled_context_without_a_bridge` passed.
7. `src/omrg/engine.py` `ingest` keeps the pre-existing behaviour that `ingest_path_async` clears the process-global `shutdown_requested` flag at start (`src/omrg/core/ingestion/pipeline.py:127`). Graph code never sets or clears it.

### Test files cited

- tests/test_compose.py
- tests/test_engine.py
- tests/test_engine_isolation.py
- tests/test_no_global_settings_reads.py
- tests/unit/test_answer_graph_adapters.py
- tests/unit/test_engine_pipelines.py
- tests/unit/test_engine_pipelines_ingestion.py
- tests/unit/test_engine_pipelines_isolation.py
- tests/unit/test_experiment_contexts_engines.py
- tests/unit/test_graph_adapters_store_forwarding.py
- tests/unit/test_ingestion_graph_adapters.py
- tests/unit/test_ingestion_graph_adapters_commit.py
- tests/unit/test_pipeline_cancellation.py
- tests/unit/test_pipeline_runner.py
- tests/unit/test_pipeline_runner_scheduler.py
- tests/unit/test_retrieval_graph_adapters.py
- tests/unit/test_web_experiments_runtime.py
- tests/unit/test_web_launch.py
- tests/unit/test_workspace_service_lifecycle.py

## Verification: local-web-workspace

Change: `add-local-web-pipeline-workspace`. Worktree: `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace` (branch `feat/add-local-web-pipeline-workspace`, uncommitted tree on `489a618`).
Spec: `openspec/changes/add-local-web-pipeline-workspace/specs/local-web-workspace/spec.md` (7 requirements, 22 scenarios).
Method: read the code and tests directly. Evidence files were used only as leads. Code paths are relative to the worktree. Frontend code is under `web/src`.

Result: 20 COVERED, 2 PARTIAL, 0 NOT COVERED.

| Requirement / Scenario | Status | Code | Tests |
|---|---|---|---|
| Web launch optional / Installed package launches outside the checkout | PARTIAL | `pyproject.toml:153` (`artifacts = ["src/omrg/transports/api/static/**"]`); `src/omrg/transports/api/lifespan.py:44` (`PACKAGED_STATIC_DIR` from `__file__`); `src/omrg/transports/api/static.py:28` (`FrontendFallback`, `StaticFiles(follow_symlink=False)`); `scripts/check_web_wheel.py` | Automated tests cover asset serving from a static directory only: `tests/unit/test_web_launch.py::test_spa_fallback_serves_index_and_assets`, `::test_missing_static_build_gives_actionable_message`. The installed-wheel run from `/tmp` with no Node is a manual smoke in `evidence/frontend-scaffold.md:149-157`. `scripts/check_web_wheel.py` is not called by any test, `scripts/local_ci.sh`, `ci.yml` or `release.yml`. Missing: automated proof that assets load from an installed wheel without Node. |
| Web launch optional / Web dependency is missing | COVERED | `src/omrg/transports/cli/web.py:25` (`INSTALL_HINT`), `:36` (`_require_web_extra`); `src/omrg/transports/cli/__init__.py:202` (lazy `web`, installer skipped only for `web`); `src/omrg/transports/api/__init__.py` (imports nothing) | `tests/unit/test_web_launch.py::test_web_without_extra_prints_install_instruction`, `::test_help_works_when_fastapi_is_not_installed`, `::test_cli_import_and_help_do_not_load_fastapi`, `::test_no_argument_start_still_runs_mcp_server`; `tests/unit/test_web_workspace_guide.py::test_missing_extra_message_matches_the_guide`. Note: the MCP start test runs with FastAPI present; the import test proves FastAPI is never loaded on that path. |
| Local access / Remote binding is requested | COVERED | `src/omrg/transports/api/security.py:65` (`validate_bind_host`); `src/omrg/transports/cli/web.py:153-156` (exit 2); `src/omrg/transports/api/app.py` (`create_app` raises) | `tests/unit/test_web_launch.py::test_web_rejects_non_loopback_bind`; `tests/unit/test_web_security.py::test_remote_bind_is_rejected_with_explanation`, `::test_create_app_rejects_remote_bind`, `::test_loopback_hosts_are_accepted` |
| Local access / An unrelated webpage submits work | COVERED | `src/omrg/transports/api/middleware.py:33` (`GuardMiddleware`: Host, Origin, `Sec-Fetch-Site` at `:52`, query credentials); `src/omrg/transports/api/security.py:325` (`require_scope`, Origin required for cookie state changes) | `tests/unit/test_web_security.py::test_foreign_origin_cannot_submit_work_even_with_session`, `::test_cookie_post_without_origin_is_rejected`, `::test_same_site_fetch_metadata_is_rejected`, `::test_invalid_host_header_is_rejected`; `tests/unit/test_web_documents.py::test_cross_origin_search_with_session_is_rejected_before_engine` |
| Local access / Stream endpoint has no credentials | COVERED | `src/omrg/transports/api/routes_runs.py:364` (`streamRunEvents`, `ReadScope` like `:257` `getRun` and `:276` `listRunEvents`) | `tests/unit/test_web_runs_stream.py::test_stream_needs_read_credentials` (401 without credentials, 403 with a `run`-only bearer); `tests/unit/test_web_runs.py::test_run_scopes`; `tests/unit/test_web_security.py::test_stream_endpoint_rejects_missing_credentials`; `tests/unit/test_web_openapi_conformance.py::test_status_event_and_cancel_routes_are_protected` |
| Local access / Scoped notebook credential is used | COVERED | `src/omrg/transports/api/security.py:44` (`BEARER_SCOPES = graph, read, run`), `:222` (`issue_bearer` refuses other scopes), `:47` (session-only `plugins`, `files`, `credentials`, `manage`); `src/omrg/core/experiments/admission.py:67` (`check_credential_target`) | `tests/unit/test_web_security.py::test_bearer_scopes_exclude_plugin_admin_and_file_grants`, `::test_bearer_scope_is_enforced`; `tests/unit/test_web_plugins.py::test_plugin_routes_are_session_only` (asserts `launcher.started == []`); `tests/unit/test_web_experiments.py::test_bound_bearer_cannot_touch_the_live_library`, `::test_bound_bearer_cannot_select_another_context` (asserts no Engine built), `::test_unbound_bearer_cannot_select_a_context` |
| File access / Path escapes an approved root | COVERED | `src/omrg/transports/api/grants.py:94` (`resolve`), `:114` (`check`, symlinks followed then containment); `src/omrg/transports/api/routes_jobs.py:76` (`_granted` before admission) | `tests/unit/test_web_files.py::test_traversal_is_denied`, `::test_symlink_escape_is_denied`, `::test_root_prefix_sibling_is_not_inside`; `tests/unit/test_web_documents_jobs.py::test_ingestion_outside_grants_is_denied_before_admission` |
| File access / Indexed source is outside grants | COVERED | `src/omrg/transports/api/grants.py:114` (`check` ignores indexed metadata as a grant); `src/omrg/transports/api/routes_inspect.py:86` (`getChunk` reads stored chunks and lineage neighbours, never the source file). No original-file route exists, so original access is denied by construction. | `tests/unit/test_web_files.py::test_indexed_metadata_path_outside_roots_is_denied`; `tests/unit/test_web_documents_jobs.py::test_chunk_inspection_returns_text_and_neighbours` (source `/elsewhere/report.md` is outside every root) |
| File access / Upload exceeds its limit | COVERED | `src/omrg/transports/api/uploads.py:30` (`DEFAULT_MAX_UPLOAD_BYTES` 50 MiB), `:93` (`preflight`), `:127` (`receive`, streaming limit, partial removed), `:83` (`purge_partials`) | `tests/unit/test_web_files.py::test_upload_route_rejects_oversize_without_residue`, `::test_stream_over_limit_is_removed`, `::test_preflight_rejects_declared_size_over_limit`, `::test_failed_stream_is_removed`, `::test_cancelled_stream_is_removed`, `::test_upload_route_rejects_archives_and_url_names` |
| Document workflows / Library lists sources | COVERED | `src/omrg/transports/api/routes_documents.py:87` (`listCollections`), `:96` (`listDocuments`, machine-local orphan status); `web/src/views/shared/labels.ts` (availability labels) | `tests/unit/test_web_documents.py::test_sources_list_keeps_machine_local_orphan_semantics` (unknown is `null`), `::test_collections_list_counts_and_conforms`; vitest `web/src/views/library/LibraryView.test.tsx` "shows sources with chunk counts, stable ids and machine-local availability" (asserts unknown row has no "missing/lost/deleted") |
| Document workflows / Search and answer execute | COVERED | `src/omrg/transports/api/routes_documents.py:110` (`searchCollection` calls `engine.search` with omitted controls as `None`), `:161` (`answerCollection` calls `engine.answer`, MCP error shape) | `tests/unit/test_web_documents.py::test_search_passes_profile_resolved_controls_as_none`, `::test_search_forwards_explicit_controls`, `::test_search_result_shape_conforms_with_lineage_and_score_kind`, `::test_answer_shape_conforms_with_deterministic_citations`, `::test_answer_forwards_controls_and_validates_bounds`, `::test_answer_engine_failure_keeps_answer_error_shape`; vitest `web/src/views/search/SearchView.test.tsx` "sends null for every control left to the profile", `web/src/views/ask/AskView.test.tsx` "sends the question with profile-resolved controls" |
| Document workflows / Citation is opened | COVERED | `src/omrg/transports/api/routes_inspect.py:57-87` (stored chunk plus `lineage.neighbours`) | `tests/unit/test_web_documents_jobs.py::test_chunk_inspection_returns_text_and_neighbours`, `::test_chunk_text_is_served_as_json_data_not_html`, `::test_chunk_inspection_needs_read_scope`; vitest `web/src/views/search/SearchView.test.tsx` "opens the stored chunk and navigates to its neighbours", `web/src/runs/EvidenceInspector.test.tsx` "opens the full chunk through the protected chunk route", `web/src/views/ask/AskView.test.tsx` (citation links) |
| Document workflows / Codebase mapping retains workspace context | COVERED | `src/omrg/transports/api/routes_jobs.py:146-171` (passes `engine.resolve_settings()` and `engine_store(engine)` explicitly); `src/omrg/core/codebase/cache.py` (owner context, durable data version) | `tests/unit/test_web_documents_jobs.py::test_codebase_map_job_passes_engine_settings_and_store`; `tests/unit/test_codebase_context_repair.py::test_build_uses_supplied_context_without_defaults`, `::test_both_document_graph_calls_receive_supplied_threshold`, `::test_same_directory_different_store_is_a_miss`, `::test_same_directory_different_map_settings_is_a_miss`, `::test_unprovable_store_context_never_reuses`, `::test_store_data_change_invalidates` |
| Destructive actions / User requests deletion without confirmation | COVERED | `src/omrg/transports/api/routes_admin.py:128` (`deleteDocuments`, preview then 428/409); `src/omrg/transports/api/confirmations.py:104` (`ConfirmationBook`); `web/src/views/library/DeletePanel.tsx` | `tests/unit/test_web_destructive.py::test_preview_reports_scope_and_mutates_nothing`, `::test_delete_without_confirmation_never_mutates`, `::test_confirmed_preview_deletes_exactly_the_selection`; `tests/unit/test_workspace_cleanup.py::test_preview_changes_nothing`; vitest `web/src/views/library/LibraryConfirm.test.tsx` "previews first and deletes nothing until the user confirms with the token" |
| Destructive actions / Store changes after preview | COVERED | `src/omrg/transports/api/confirmations.py:44` (`ObservedState`, `durable` or `process_local`), `:146` (`PROCESS_LOCAL_WARNING`); `src/omrg/transports/api/routes_admin.py:86` (observe first) | `tests/unit/test_web_destructive.py::test_store_change_after_preview_makes_confirmation_stale`, `::test_backend_guarantee_is_disclosed` (both store kinds), `::test_altered_selector_is_rejected_and_needs_new_preview`, `::test_expired_confirmation_is_rejected`; `tests/unit/test_workspace_cleanup.py::test_new_matching_run_makes_the_preview_stale`; vitest `web/src/views/library/LibraryConfirm.test.tsx` "offers a fresh preview when the confirmation is stale (409)" |
| Destructive actions / Profile change is confirmed | COVERED | `src/omrg/transports/api/routes_admin.py:183` (`changeCollectionProfile`, preview and confirm branches) | `tests/unit/test_web_destructive.py::test_profile_preview_then_confirm_changes_query_defaults_only` (chunk count unchanged, hybrid default flips), `::test_profile_confirm_needs_matching_fresh_preview`; vitest `web/src/views/library/LibraryConfirm.test.tsx` "shows exactly what will change, then confirms with the token", `web/src/views/library/LibraryProfile.test.tsx` |
| HTTP graph and run services / Graph is submitted directly to the API | COVERED | `src/omrg/transports/api/routes_graphs.py:168` (`savePipelineRevision`), `:253` (`validatePipeline`, core validation, 422 with `issues`); `src/omrg/transports/api/routes_runs.py:181` (`submitRun` re-validates the saved revision) | `tests/unit/test_web_graphs.py::test_invalid_graph_gets_structured_issues_and_never_runs`, `::test_cycle_is_rejected_with_node_names`, `::test_revision_save_rejects_unsupported_schema_before_storage`, `::test_invalid_saved_revision_is_refused_at_submission` |
| HTTP graph and run services / Long work is admitted | PARTIAL | `src/omrg/transports/api/routes_jobs.py:132` (`ingestPath` 202), `:146` (`generateCodebaseMap` 202), `:174` (`getJobStatus`); `src/omrg/transports/api/routes_runs.py:181` (`submitRun` 202), `:276`/`:364` (run events); `src/omrg/transports/api/routes_runs.py:97-106` (`_graph_run` hides job runs) | `tests/unit/test_web_documents_jobs.py::test_ingestion_inside_root_runs_as_polled_job`, `::test_job_polling_accepts_read_bearer`; `tests/unit/test_web_runs.py::test_run_scopes`, `::test_polling_returns_ordered_events_after_a_sequence`; `tests/unit/test_web_openapi_conformance.py::test_long_running_operations_declare_202_with_an_identifier`; `tests/unit/test_web_runs_service.py::test_jobs_are_persisted_and_hidden_from_graph_listings`. Missing: event inspection for ingestion and codebase-map jobs. Jobs expose status polling only; `/v1/runs/{id}` and its event routes return 404 for job runs. |
| HTTP graph and run services / Frontend fallback receives an API path | COVERED | `src/omrg/transports/api/static.py:4,45` (never answers `/v1` with HTML); `src/omrg/transports/api/errors.py` (envelope) | `tests/unit/test_web_launch.py::test_unknown_api_path_returns_json_envelope_not_html`, `::test_api_errors_use_envelope_for_method_not_allowed`; `tests/unit/test_web_security.py::test_unknown_api_path_with_session_is_json_404`; `tests/unit/test_web_openapi_conformance.py::test_unknown_api_path_never_serves_html`; `tests/unit/test_web_workspace_guide.py::test_unknown_api_paths_return_the_envelope_with_assets_built` |
| Application lifecycle / Web and explicit library Engine coexist | COVERED | `src/omrg/transports/api/lifespan.py:253-257` (one Engine through `compose.build_engine`), `:347` (`build_lifespan`); `src/omrg/transports/cli/__init__.py:202` (legacy installer skipped for `web`); `src/omrg/compose_experiments.py` (separate Engines per context) | `tests/unit/test_web_launch.py::test_web_bypasses_legacy_installer_and_prints_bootstrap_url_to_stderr`, `::test_lifespan_builds_one_engine_and_closes_it`; `tests/test_engine_isolation.py::test_two_engine_full_path_isolation`, `::test_close_engine_a_leaves_engine_b_functional`; `tests/unit/test_engine_pipelines_isolation.py::test_two_engines_run_concurrently_and_stay_isolated`, `::test_poisoned_process_defaults_are_never_read`; `tests/unit/test_web_experiments.py::test_session_can_run_live_and_experiment_graphs`. Note: no single test builds the web app next to an unrelated library Engine; the parts are proved separately. |
| Application lifecycle / Shutdown has active work | COVERED | `src/omrg/transports/api/lifespan.py:300-333` (`shutdown_runtime`: close admission, run-service shutdown, wait idle, then close); `src/omrg/core/workspace/service.py:181` (`shutdown` cancels queued, cancels active, waits) | `tests/unit/test_web_launch.py::test_shutdown_waits_for_active_work_and_rejects_new_admission`, `::test_run_service_hook_starts_and_shuts_down_before_engine_close`; `tests/unit/test_workspace_service_lifecycle.py::test_shutdown_cancels_queued_and_waits_for_cooperative_run` (queued run never executes), `::test_shutdown_timeout_interrupts_a_stuck_run`; `tests/unit/test_pipeline_cancellation.py::test_entered_commit_completes_before_terminal_cancel`, `::test_blocking_call_finishes_at_a_safe_boundary`; `tests/unit/test_web_runs_service.py::test_signal_closes_admission_before_the_server_drains`; `tests/unit/test_web_experiments_runtime.py::test_shutdown_order_is_service_editors_experiments_engine` |
| Application lifecycle / Optional plugin is absent | COVERED | `src/omrg/transports/api/routes_plugins.py:65` (`INSTALL_HINT`), `:159-168` (`listPlugins` with `install_hint`); `web/src/experiments/NotebookPanel.tsx:19-20` | `tests/unit/test_web_plugins.py::test_list_starts_with_no_plugin_and_explains_installation`, `::test_incompatible_plugin_cannot_open`; `tests/unit/test_web_plugins_launch.py::test_editor_runs_until_app_shutdown_and_starts_nothing_at_startup`; vitest `web/src/experiments/NotebookPanel.test.tsx` "explains how to install the plugin when none is registered, without an install button", `web/src/views/settings/PluginSection.test.tsx` "states that the workspace works without a plugin and offers no install button" |

### Gaps

1. Installed package launches outside the checkout (PARTIAL). The wheel-from-`/tmp`, no-Node proof is manual only. Action: add a `web-wheel` job to `.github/workflows/ci.yml` (or `scripts/local_ci.sh`) that runs `npm ci && npm run build`, `uv build --wheel`, then `python scripts/check_web_wheel.py dist/*.whl`, then installs the wheel in a clean venv, runs from a temp directory with `node` removed from `PATH`, and requests `/` and one `/assets/` file. This is part of open task 9.2.
2. Long work is admitted (PARTIAL). Ingestion and codebase-map jobs have no event inspection. Choose one:
   1. Add `GET /v1/jobs/{job_id}/events` (read scope) that returns the run events the service already records under the job's run id, declare it in `openapi.yaml`, and add a test next to `test_job_polling_accepts_read_bearer`.
   2. Amend the scenario text to say event inspection applies to graph runs, and jobs offer protected status polling only (matches design.md section on jobs).

### Spec text issues

1. "Long work is admitted" groups ingestion, graph execution and codebase mapping, then requires event inspection for all three. The implementation and `evidence/http-graphs-runs.md` deviation 7 and 8 treat jobs as polled only (`src/omrg/transports/api/README.md` says the same). Either the spec overstates the design or the code is short. See gap 2.
2. "Indexed source is outside grants" implies an original-file route exists. None exists in this release, so the denial is structural. The text is not wrong, but a reader may look for a route that is not there.
3. "Upload exceeds its limit ... without admitting ingestion": uploads never admit ingestion in this design (ingestion is a separate `POST /v1/ingestions`), so that clause is satisfied trivially.

### Deviations recorded in evidence

1. `http-foundation.md`: `--host` option added (loopback only); default workspace `~/.omrg/workspace`; upload extension set comes from `WebConfig.upload_extensions` (default `DEFAULT_INGEST_EXTENSIONS`) because `Engine` had no settings accessor.
2. `http-documents.md`: Engine accessor fallback to private attributes (later resolved by public `Engine.describe_operations` per `http-graphs-runs.md` lead follow-up); `JobBook` placeholder (since replaced: jobs now run on the shared run service, see `routes_jobs.py`); destructive scope (since resolved: session-only `manage` scope at `security.py:46-47`); check-then-act window between token observation and delete is not detected for another process; legacy rows without `chunk_id` cannot be inspected; Engine failures return the exception type only.
3. `http-graphs-runs.md`: jobs have no retry route; SIGINT re-raised by Uvicorn after graceful shutdown; earlier failing tests fixed in lead follow-up.
4. `openapi.md`: framework request validation stays 400 (core graph validation 422); `{jobId}` path name kept; foundation routes have no runtime `operation_id`; five em dashes remain in reviewed descriptions; 501 from `getChunk` and 400 for credentials in run inputs are declared but not exercised. Deviation 4 (vacuous scope test) is fixed: `test_every_protected_route_declares_a_scope` now uses `iter_api_routes` and asserts `checked > 0`.
5. `frontend-scaffold.md`: networked clean install of `omrg[web]` from the lock not run (local uv cache incomplete); wheel smoke was manual.
6. `end-to-end.md`: comparison used polled run events, not SSE; launcher used a fake embedder and fake LLM.
7. `experiment-transport.md`: admission lease released at once and re-acquired at execution start.
8. `browser.md`: browser walk-through is manual (Chrome DevTools). Defects D1 to D6 fixed with vitest or browser checks. Open design choice: canvas node cards are small at fit-view.

### Test files cited

- tests/unit/test_web_launch.py
- tests/unit/test_web_security.py
- tests/unit/test_web_files.py
- tests/unit/test_web_documents.py
- tests/unit/test_web_documents_jobs.py
- tests/unit/test_web_destructive.py
- tests/unit/test_web_graphs.py
- tests/unit/test_web_runs.py
- tests/unit/test_web_runs_stream.py
- tests/unit/test_web_runs_service.py
- tests/unit/test_web_openapi_conformance.py
- tests/unit/test_web_plugins.py
- tests/unit/test_web_plugins_launch.py
- tests/unit/test_web_experiments.py
- tests/unit/test_web_experiments_runtime.py
- tests/unit/test_web_workspace_guide.py
- tests/unit/test_workspace_cleanup.py
- tests/unit/test_workspace_service_lifecycle.py
- tests/unit/test_pipeline_cancellation.py
- tests/unit/test_codebase_context_repair.py
- tests/unit/test_engine_pipelines_isolation.py
- tests/test_engine_isolation.py
- web/src/views/library/LibraryView.test.tsx
- web/src/views/library/LibraryConfirm.test.tsx
- web/src/views/library/LibraryProfile.test.tsx
- web/src/views/search/SearchView.test.tsx
- web/src/views/ask/AskView.test.tsx
- web/src/runs/EvidenceInspector.test.tsx
- web/src/experiments/NotebookPanel.test.tsx
- web/src/views/settings/PluginSection.test.tsx

## Verification: modular-core-extraction

Change: `add-local-web-pipeline-workspace`. Worktree: `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace` (branch `feat/add-local-web-pipeline-workspace`, uncommitted tree). Date: 2026-10-13.

Result: 16 scenarios. 14 COVERED, 2 PARTIAL, 0 NOT COVERED.

| Requirement / Scenario | Status | Code | Tests |
|---|---|---|---|
| Ingestion and chunking / Content-type dispatch preserved | PARTIAL: standard path proved; graph path not tested with a code or config source | `src/omrg/core/ingestion/chunker.py:69-122` (`chunk_specialised_source`, content type before extension); graph `src/omrg/core/ingestion/graph_adapters.py:192-211` (`read_adapter` calls the same seam with `unit.content_type`) | `tests/unit/test_type_aware_ingestion.py::TestContentTypeDispatch::test_content_type_takes_precedence`, `tests/unit/test_type_aware_ingestion.py::TestContentTypeDispatch::test_none_content_type_uses_extension`, `tests/unit/test_ingestion_seams.py::test_chunk_specialised_source_returns_none_for_document_reads`, `tests/unit/test_ingestion_seams.py::test_read_and_chunk_composes_the_seams` |
| Ingestion and chunking / Strategy resolved through the registry | COVERED | `src/omrg/core/ingestion/chunker.py:16` (only `chunking.registry` imported), `:49` (`_chunking_get("sentence")`), `:108` (`"code"`), `:120` (`"config"`) | `tests/test_no_module_level_strategy_imports.py::test_no_module_level_strategy_import[core/ingestion/chunker.py]`, `tests/test_document_registry_dispatch.py::test_both_document_branches_invoke_registered_sentence_strategy`, `tests/unit/test_ingestion_seams.py::test_split_documents_uses_registry_and_stamps_metadata` |
| Ingestion and chunking / Only existing strategies extracted | COVERED | `src/omrg/core/chunking/registry.py:61-63` unchanged (no file under `core/chunking/` modified); graph `prepare.chunk` calls `split_documents` at `src/omrg/core/ingestion/graph_adapters.py:262-293` | `tests/test_strategy_registration_inventory.py::test_registry_names_blocks_match_live_registries`, `tests/unit/test_ingestion_graph_adapters.py::test_register_publishes_every_ingestion_operation`, `tests/unit/test_ingestion_graph_adapters.py::test_graph_chain_matches_ingest_path_async` |
| Ingestion and chunking / Async ingestion entry point preserved | COVERED | `src/omrg/core/ingestion/pipeline.py:88-99` signature identical to HEAD (diffed); adapters are `async def` in `src/omrg/core/ingestion/graph_adapters.py`; catalogue enforces async at `src/omrg/core/pipelines/catalogue.py:176-217`; frozen settings via `NodeContext.settings` (`src/omrg/core/pipelines/adapters.py:66-81`) | `tests/unit/test_ingestion_seams_parity.py::test_seam_composition_matches_ingest_path_async`, `tests/test_document_registry_dispatch.py::test_ordinary_ingestion_invokes_registered_strategy_and_forwards_store`, `tests/unit/test_pipeline_catalogue.py::test_registration_requires_async_adapter`, `tests/unit/test_pipeline_admission.py::test_snapshot_is_immutable_and_detached`, `tests/test_profile_isolation.py::TestPerCollectionIsolation::test_settings_are_frozen_so_operations_cannot_leak` |
| Ingestion and chunking / Protected replacement is reused | COVERED | `src/omrg/core/ingestion/replacement.py:90` (`prepare_source_embeddings`), `:184-282` (standard composite); `src/omrg/core/ingestion/commit.py:158-282` (write, verify, stale cleanup under one `write_lock`); graph `src/omrg/core/ingestion/graph_adapters.py:299-325` (embed) and `:350-402` (commit calls `commit_prepared_source` at `:373`) | `tests/unit/test_ingestion_seams_replacement.py::test_replace_source_nodes_composes_prepare_and_commit`, `tests/unit/test_ingestion_seams_replacement.py::test_commit_holds_the_write_lock_for_write_verify_and_cleanup`, `tests/unit/test_ingestion_seams_replacement.py::test_failed_verification_keeps_previous_version`, `tests/unit/test_ingestion_graph_adapters_commit.py::test_failed_verification_keeps_previous_version_and_retry_cleans`, `tests/unit/test_ingestion_graph_adapters.py::test_only_the_commit_operation_mutates_the_store`, `tests/unit/test_ingestion_graph_adapters.py::test_embedding_cannot_be_bypassed_into_the_commit`, `tests/unit/test_ingestion_graph_adapters.py::test_graph_chain_matches_ingest_path_async` |
| Ingestion and chunking / Registered replacement reaches production dispatch | COVERED (graph side proved indirectly) | `src/omrg/core/ingestion/chunker.py:34-58`, `:203-249` (`split_documents`, both branches), `:320-334`; graph `src/omrg/core/ingestion/graph_adapters.py:279-290` calls the same `split_documents` with `structured=read.structured` | `tests/test_document_registry_dispatch.py::test_both_document_branches_invoke_registered_sentence_strategy` (5 branches, structured and unstructured), `tests/unit/test_ingestion_seams.py::test_split_documents_uses_registry_and_stamps_metadata` (both `structured` values), `tests/unit/test_ingestion_graph_adapters.py::test_reader_markdown_declaration_reaches_the_splitter` (spy proves the graph adapter calls `split_documents`) |
| Ingestion and chunking / Reader-produced Markdown remains intact | COVERED | `src/omrg/core/ingestion/chunker.py:148-157` (`declares_markdown`), `:222-229` (model-token resolution, `markdown_chunk_size`); graph `src/omrg/core/ingestion/graph_adapters.py:275-288` | `tests/test_document_registry_dispatch.py::test_both_document_branches_invoke_registered_sentence_strategy[scan.pdf-False-markdown-True]`, `tests/test_document_registry_dispatch.py::test_markdown_postprocessing_runs_exactly_once`, `tests/unit/test_ingestion_seams.py::test_declares_markdown_follows_reader_declaration`, `tests/unit/test_ingestion_graph_adapters.py::test_reader_markdown_declaration_reaches_the_splitter`, `tests/unit/test_ingestion_graph_adapters.py::test_read_keeps_reader_declarations_on_its_port` |
| Ingestion and chunking / Metadata degradation survives dispatch | COVERED | `src/omrg/core/ingestion/chunker.py:26-31` (`_ChunkResult`), `:323-334`; graph carries it on `SourceWork` at `src/omrg/core/ingestion/graph_adapters.py:258` and reports it at `:385` | `tests/test_document_registry_dispatch.py::test_both_document_branches_invoke_registered_sentence_strategy` (asserts `nodes.metadata_degraded is True` on unstructured branches), `tests/unit/test_ingestion_seams.py::test_enrich_documents_forwards_store_settings_and_taxonomy`, `tests/unit/test_ingestion_seams.py::test_read_and_chunk_composes_the_seams` |
| Retrieval grouping / End-to-end search dispatch | COVERED | `src/omrg/core/retrieval/pipeline.py:134` (`search`) delegating to `src/omrg/core/retrieval/operations.py:61-323` | `tests/unit/test_retrieval_seams_parity.py::test_search_reproduces_recorded_parity_case` (15 recorded cases), `tests/unit/test_retrieval_seams_parity.py::test_parity_cases_cover_the_required_rules`, `tests/unit/test_retrieval_seams.py::test_search_delegates_to_the_shared_seams` |
| Retrieval grouping / Stages resolved through the registry | COVERED (see Deviations 3) | `src/omrg/core/retrieval/pipeline.py:23,67,108,286` (`_retrieval_get`); `src/omrg/core/retrieval/graph_adapters.py:60,86` (fusion); `src/omrg/core/retrieval/graph_adapters_retrieve.py:33,170` (dense), `:199` (`sparse_policy_runner` through the sparse registry); reranker is the injected host resource | `tests/test_no_module_level_strategy_imports.py::test_no_module_level_strategy_import[core/retrieval/pipeline.py]`, `tests/unit/test_retrieval_graph_adapters.py::test_importing_adapters_loads_no_concrete_strategy`, `tests/unit/test_retrieval_seams.py::test_importing_seams_loads_no_concrete_strategy_module` |
| Retrieval grouping / Threshold policy relocated intact | COVERED | `src/omrg/core/retrieval/policy.py` unchanged against HEAD (÷30 at `_effective_threshold`); applied once through `src/omrg/core/retrieval/operations.py:22,283-311`; no settings or config file modified | `tests/unit/test_retrieval_seams.py::test_successful_rerank_divides_threshold_by_thirty`, `tests/unit/test_retrieval_seams.py::test_failed_rerank_uses_the_undivided_dense_threshold`, `tests/unit/test_retrieval_seams.py::test_pipeline_holds_no_private_threshold_transform`, `tests/unit/test_retrieval_seams_parity.py::test_search_reproduces_recorded_parity_case[dense_rerank_success_div30]`, `tests/unit/test_retrieval_graph_adapters_parity.py::test_graph_chain_matches_search[hybrid_rerank_success_div30]` |
| Retrieval grouping / Reranker model cache reset preserved | COVERED | `src/omrg/core/retrieval/_reranker_cache.py:78-92` (unchanged) | `tests/test_reranker.py::TestCrossEncoderRerankerSingleton::test_reset_model_cache_forces_reload`, `tests/test_reranker.py::TestFailureEscalation::test_reset_model_cache_clears_failure_counter` |
| Retrieval grouping / Graph and search share filtering | COVERED | `src/omrg/core/retrieval/operations.py:153-311` (first-stage threshold, dense eligibility, rerank success, fallback, score threshold, truncate); graph `src/omrg/core/retrieval/graph_adapters.py:74-86,127-213` | `tests/unit/test_retrieval_graph_adapters_parity.py::test_graph_chain_matches_search` (15 cases, compares `score_kind`, `dense_score_kind`, threshold kind, rerank reason and backend), `tests/unit/test_retrieval_graph_adapters_parity.py::test_reranker_failure_is_a_fallback_outcome`, `tests/unit/test_retrieval_graph_adapters_parity.py::test_reranker_success_labels_reranker_scores`, `tests/unit/test_retrieval_graph_adapters.py::test_threshold_refuses_rank_only_evidence`, `tests/unit/test_retrieval_seams.py::test_dense_eligibility_drops_low_dense_and_sparse_only_rows` |
| Behaviour preservation / Full test suite passes | PARTIAL: full-suite result owned by task 9.2 lead run | Coverage floors in `pyproject.toml` and `CLAUDE.md` coverage table | Not run here. Infrastructure: `uv run pytest -m "not slow" --cov=omrg`, `scripts/local_ci.sh`, `tests/test_clean_base_tripwire.py` (not run by rule) |
| Behaviour preservation / File size ceiling across the package | COVERED | Largest files are exactly 500 lines (`src/omrg/integrations/ocr_worker/protocol.py`, `src/omrg/core/vectordb/lancedb.py`, `src/omrg/config/__init__.py`); new `src/omrg/compose_pipelines.py` 493, `src/omrg/engine.py` 488 | `tests/test_file_size_ceiling.py::test_no_file_exceeds_500_lines` (scans all of `src/omrg/` with `rglob`) |
| Behaviour preservation / MCP and CLI surfaces unchanged | COVERED | `src/omrg/transports/mcp/` not modified; `src/omrg/transports/cli/__init__.py:202-208` (skip legacy installer only for `web`; `None` subcommand still starts MCP), `:236` adds `web` | `tests/unit/test_web_launch.py::test_no_argument_start_still_runs_mcp_server`, `tests/test_mcp_tools.py::test_list_tools_discovers_all_eight`, `tests/test_cli.py` (existing command and help tests), `tests/unit/test_web_launch.py::test_web_bypasses_legacy_installer_and_prints_bootstrap_url_to_stderr` |

### Gaps

1. Content-type dispatch preserved (graph clause). No graph test feeds a code or config source through `read.document`. The parity fixtures hold only `.md` and `.txt` files.
   Action:
   1. Add a test in `tests/unit/test_ingestion_graph_adapters.py` that runs `read.document` on a `.txt` source whose unit has `content_type="code/python"`.
   2. Assert that the work item is `specialised`, the nodes come from the registered `code` strategy, and every node has `metadata["content_type"] == "code/python"`.
   3. Add a second case for a `config/yaml` source through the `config` strategy.
2. Full test suite passes. This agent did not run the full suite by rule.
   Action:
   1. Read the task 9.2 lead run result for `uv run pytest -m "not slow" --cov=omrg`.
   2. Confirm the three coverage floors (Core + MCP 95%, Orchestration 85%, Overall 90%) in that run.
   3. Mark this scenario COVERED only when both are green.

Optional hardening (scenario already COVERED):

1. Registered replacement reaches production dispatch, graph side. The proof is indirect: a spy shows `chunk_adapter` calls `split_documents`, and a sentinel shows `split_documents` uses the registry. Add one graph test that registers the sentinel `sentence` strategy and runs `prepare.chunk` for a structured and an unstructured `BackendRead`. This makes the regression fail directly if the adapter gains a private splitter.
2. Metadata degradation through a graph. No test asserts `metadata_degraded` in the `commit.source` summary. Add an assertion to an enrich test that forces a degraded extraction.

### Spec text issues

1. Strategy resolved through the registry: the scenario names only `core/ingestion/chunker.py`. The new graph dispatch module `core/ingestion/graph_adapters.py` has no equivalent module-level import guard. A manual check found that importing it loads only `chunking.registry` and `chunking.model_token`. Consider naming the adapter modules in the scenario, or add them to the parametrisation of `tests/test_no_module_level_strategy_imports.py`.
2. `tests/test_no_module_level_strategy_imports.py` lists `omrg.core.retrieval.policy` in `_FORBIDDEN_STRATEGY_MODULES`. The new `src/omrg/core/retrieval/operations.py:22` imports `.policy` at module level, and `pipeline.py` and `graph_adapters.py` import `operations` at module level. At HEAD, `pipeline.py` imported `policy` lazily inside a function. The scenario text ("concrete implementation modules") and the repository's own forbidden list now disagree about whether `policy` is a concrete strategy. `policy` is not a registered retrieval strategy and loads only `logging`. Decide one of:
   1. Remove `omrg.core.retrieval.policy` from the forbidden list, with a comment that it is a pure rule module.
   2. Make the `operations.py` import of `policy` lazy and add `core/retrieval/operations.py` and the four `graph_adapters*.py` modules to the AST parametrisation.

No scenario text was found to be factually wrong.

### Deviations

From evidence files and code reading:

1. Code and configuration sources are split inside `read.document`, not `prepare.chunk` (`evidence/ingestion-adapters.md` item 1). `prepare.chunk` levers therefore do not change code/config sources. This keeps one content-type dispatch rule.
2. A node-level lever equal to the default changes the ingestion fingerprint and reprocesses once (`evidence/ingestion-adapters.md` item 2). Conservative.
3. `operations.py` imports `policy` at module level, so importing the retrieval `pipeline` now loads `policy` (it did not at HEAD). See Spec text issues 2.
4. New score kind `sparse_rank_v1` for rank-only sparse rows; new operation ids `retrieve.prepare_query` and `select.threshold` (score-kind-aware) in place of the guide's provisional `select.dense_threshold` (`evidence/retrieval-adapters.md` items 1 and 2).
5. RRF takes at most one dense and one other ranking; more inputs raise `ValueError` (`evidence/retrieval-adapters.md` item 4).
6. The rerank decision lives in `retrieve.prepare_query`; `select.rerank enabled=false` skips inference and `select.threshold` restores the dense gate as for a failed rerank (`evidence/retrieval-adapters.md` item 6).
7. The graph commit uses `commit_prepared_source`, which still returns a zero-write outcome when the process-global `shutdown_requested` flag is set (`src/omrg/core/ingestion/commit.py:196`). Graph code never sets or clears that flag. This is unchanged standard behaviour, recorded here for completeness.
8. `evidence/engine-wiring.md` recorded a strict `xfail` (`test_answer_chain_accepts_assembled_context_without_a_bridge`). No `xfail` marker remains in the engine pipeline tests, and that test passed in the focused run.

### Test files cited

- tests/test_cli.py
- tests/test_document_registry_dispatch.py
- tests/test_file_size_ceiling.py
- tests/test_mcp_tools.py
- tests/test_no_module_level_strategy_imports.py
- tests/test_profile_isolation.py
- tests/test_reranker.py
- tests/test_strategy_registration_inventory.py
- tests/unit/test_ingestion_graph_adapters.py
- tests/unit/test_ingestion_graph_adapters_commit.py
- tests/unit/test_ingestion_seams.py
- tests/unit/test_ingestion_seams_parity.py
- tests/unit/test_ingestion_seams_replacement.py
- tests/unit/test_pipeline_admission.py
- tests/unit/test_pipeline_catalogue.py
- tests/unit/test_retrieval_graph_adapters.py
- tests/unit/test_retrieval_graph_adapters_parity.py
- tests/unit/test_retrieval_seams.py
- tests/unit/test_retrieval_seams_parity.py
- tests/unit/test_type_aware_ingestion.py
- tests/unit/test_web_launch.py

## Verification: `notebook-plugins` (change `add-local-web-pipeline-workspace`)

Date: 2026-10-13. Worktree: `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace` (uncommitted tree). Read-only check. Paths are relative to the worktree. Vitest paths are relative to `web/src/`.

Result: 14 scenarios. 12 COVERED, 2 PARTIAL, 0 NOT COVERED.

| Requirement / Scenario | Status | Code | Tests |
|---|---|---|---|
| Notebook integration is separately managed / marimo is absent | COVERED | `src/omrg/transports/api/routes_plugins.py:65` (`INSTALL_HINT`), `:159-171` (`GET /v1/plugins`); `web/src/experiments/NotebookPanel.tsx:33,47` (install hint, "works without the plugin"); `plugins/marimo/README.md` | `tests/unit/test_web_plugins.py::test_list_starts_with_no_plugin_and_explains_installation`; `tests/unit/test_notebooks_guide.py::test_workspace_serves_documents_and_graphs_without_a_plugin`; `experiments/NotebookPanel.test.tsx` > notebook editor > "explains how to install the plugin when none is registered, without an install button", "keeps the rest of the view working when the plugin routes fail"; `views/settings/PluginSection.test.tsx` > Settings plugin panel > "states that the workspace works without a plugin and offers no install button" |
| Notebook integration is separately managed / Editor is updated independently | COVERED | `src/omrg/core/plugins/registration.py:99` (`inspect_executable`: path, size, mtime, SHA-256), `:170` (`state`: changed executable gives `unchecked`), `:197` (`recheck`); `pyproject.toml` (no marimo dependency, wheel `packages = ["src/omrg"]`) | `tests/unit/test_plugin_marimo_manifest.py::test_external_version_change_triggers_recheck`, `::test_plugin_payload_lives_outside_the_package`, `::test_built_wheel_excludes_plugins` (slow); `tests/unit/test_plugin_registration.py::test_changed_executable_invalidates_until_recheck`, `::test_probe_argv_never_contains_install_actions`, `::test_missing_executable_never_installs`. Manual: `marimo-qualification.md` section 5 (`uv.lock`, `pyproject.toml` SHA-256 unchanged across a real 0.25.1 to 0.25.0 to 0.25.1 cycle) |
| Plugin manifests are constrained data / Manifest attempts executable hooks | COVERED | `src/omrg/core/plugins/manifest.py:50` (`_SHELL_CHARS`), `:59` (`_FORBIDDEN_TOKENS`), `:65` (`_FORBIDDEN_PREFIXES`), `:192` (`parse_manifest`, closed schema), `:402-405` | `tests/unit/test_plugin_manifest.py::test_rejects_unsafe_or_malformed_manifests` (parametrised: shell syntax, unknown substitution, import hook, installer), `::test_duplicate_keys_and_bad_json_are_rejected`; `tests/unit/test_plugin_registration.py::test_invalid_manifest_is_rejected_without_launch`; `tests/unit/test_web_plugins.py::test_invalid_manifest_is_rejected_without_a_process` |
| Plugin manifests are constrained data / Manifest is approved | COVERED | `registration.py:148` (`register(..., approved=True)` stores manifest SHA-256 and executable identity), `:170` (`needs_approval` on manifest change), `:282-293`; `routes_plugins.py:174-208` (location and name checks) | `tests/unit/test_plugin_registration.py::test_registration_requires_explicit_trust`, `::test_registration_stores_hash_and_executable_without_probing`, `::test_changed_manifest_requires_new_approval`, `::test_deleted_manifest_requires_new_approval`, `::test_changed_executable_invalidates_until_recheck`; `tests/unit/test_plugin_marimo_manifest.py::test_edited_shipped_manifest_needs_new_approval`; `tests/unit/test_web_plugins.py::test_register_needs_explicit_approval_and_runs_nothing`; `views/settings/PluginSection.test.tsx` > "registers only after the approval box is ticked" |
| Compatibility is checked before launch / Editor loses a required capability | COVERED | `registration.py:226` (`_probe`), `:249` (`_check_help`: every argument-backed capability flag must appear in help text); `manifest.py` required capabilities `loopback_bind`, `token_auth`, `startup_execution_disabled`, `auto_install_disabled`, `update_check_disabled`; `editor.py:204` (`open` rechecks first) | `tests/unit/test_plugin_registration.py::test_missing_help_flag_names_the_capability`, `::test_undeclared_required_capability_blocks_launch`, `::test_probe_failures_are_incompatible`; `tests/unit/test_plugin_manifest.py::test_missing_required_capability_is_recorded_not_hidden`; `tests/unit/test_plugin_editor.py::test_incompatible_plugin_is_not_launched`; `tests/unit/test_web_plugins.py::test_incompatible_plugin_cannot_open`; `experiments/NotebookPanel.test.tsx` > "shows the server's actionable message for an incompatible plugin" |
| Compatibility is checked before launch / Independently updated version is supported | COVERED | `registration.py:197` (`recheck` compares the probed version with the manifest range); `editor.py:204` | `tests/unit/test_plugin_marimo_manifest.py::test_external_version_change_triggers_recheck` (0.25.9 passes, `launchable`), `::test_independent_registration_with_shipped_manifest`; `tests/unit/test_plugin_registration.py::test_recheck_records_compatible_version`; `tests/unit/test_plugin_editor.py::test_open_rechecks_then_launches_loopback_with_token_file`. Manual: `marimo-qualification.md` section 5 (real upgrade, recheck, start) |
| Editor lifecycle is explicit and locally protected / Notebook is opened | COVERED | `editor.py:132` (`build_launch_plan`, loopback only), `:204` (`open` needs consent); `plugins/marimo/manifest.json` (`.marimo.toml` with `auto_instantiate = false`, `on_cell_change = "lazy"`, `--headless`, `--skip-update-check`, `--no-sandbox`, `--token-password-file`); `web/src/experiments/OpenEditorForm.tsx:47-51` (`window.open(url, "_blank", "noopener,noreferrer")`) | `tests/unit/test_plugin_editor.py::test_open_requires_consent`; `tests/unit/test_web_plugins.py::test_open_editor_needs_consent_and_an_active_context`, `::test_open_editor_gives_the_token_once_and_never_logs_it`; `tests/unit/test_process_launcher_editor.py::test_open_and_stop_owned_editor` (asserts `auto_instantiate = false` and `on_cell_change = "lazy"` in the written config); `tests/unit/test_plugin_marimo_manifest.py::test_shipped_manifest_is_valid_and_complete`; `tests/unit/test_web_plugins_launch.py::test_editor_runs_until_app_shutdown_and_starts_nothing_at_startup`; `experiments/NotebookPanel.test.tsx` > "needs explicit consent before it calls the open route", "opens the editor in a new tab with noopener and keeps the token out of the address and storage"; `experiments/ExperimentsView.test.tsx` > "never embeds an editor frame". Real marimo no-startup-run: manual only (`marimo-qualification.md` 2a, marker test) |
| Editor lifecycle is explicit and locally protected / An unrelated editor owns the port | COVERED | `editor.py:245` (`_try_port`); `src/omrg/integrations/process_launcher.py` (port check before start, `PortInUseError`) | `tests/unit/test_plugin_editor.py::test_unrelated_port_is_skipped_not_adopted`, `::test_all_ports_busy_fails_clearly`; `tests/unit/test_process_launcher_editor.py::test_unrelated_editor_on_port_is_not_adopted`, `::test_only_busy_ports_fail_clearly`; `tests/unit/test_process_launcher.py::test_unrelated_listener_is_refused_and_left_running` |
| Editor lifecycle is explicit and locally protected / Stop is approved | COVERED | `editor.py:294` (`stop`), `:306` (`stop_all`); `process_launcher.py:336-356` (`killpg` SIGTERM, bounded wait, SIGKILL at `:143`); `src/omrg/transports/api/lifespan.py` (shutdown order: run service, `editors.stop_all()`, experiments, engine); `routes_plugins.py:329` | `tests/unit/test_process_launcher_editor.py::test_open_and_stop_owned_editor` (group gone, token file gone, notebook digest unchanged); `tests/unit/test_process_launcher.py::test_stop_escalates_after_bounded_wait`, `::test_stop_cleans_the_whole_owned_group`, `::test_stop_unknown_id_touches_nothing`; `tests/unit/test_plugin_editor.py::test_stop_only_targets_owned_sessions`, `::test_stop_all_stops_owned_sessions`; `tests/unit/test_web_experiments_runtime.py::test_shutdown_order_is_service_editors_experiments_engine`; `experiments/NotebookPanel.test.tsx` > "lists running editors and stops one after confirmation" |
| Notebook runs share the graph contract / A parameter cell changes | COVERED | `plugins/marimo/starter_notebook.py:386-397` (`ExperimentSession.run` returns `None` without `run_requested`), notebook cell guarded by `mo.stop(not run_button.value, ...)`; manifest `on_cell_change = "lazy"` | `tests/unit/test_starter_notebook.py::test_parameter_change_without_a_request_admits_nothing`, `::test_notebook_imports_without_marimo_and_keeps_explicit_run_controls`, `::test_checkpoint_is_written_atomically`. Manual: `marimo-qualification.md` section 4 (parameter change gave 0 runs) |
| Notebook runs share the graph contract / Canvas and notebook select the same revision | COVERED | `starter_notebook.py:302` (`ExperimentSession` uses `POST /v1/pipelines`, revisions, `POST /v1/runs`); run snapshot per run (`src/omrg/transports/api/runs_wiring.py`) | `tests/unit/test_starter_notebook.py::test_notebook_and_canvas_share_the_graph_and_record_identities` (same `graph_hash`, same `graph_identity`, different `run_id`, backend identity recorded). Manual: `end-to-end.md` (browser and notebook runs of one revision match) |
| Experiment writes stay in approved experiment workspaces / Notebook targets the live library for mutation | COVERED | `src/omrg/core/experiments/admission.py:67-95` (`check_credential_target`, `live_library_target`); `src/omrg/transports/api/security.py` (bound-bearer path allowlist); `routes_runs.py` (403 before side effects) | `tests/unit/test_experiment_contexts_engines.py::test_experiment_credential_cannot_target_the_live_library`; `tests/unit/test_experiment_contexts.py::test_credential_target_rejections`; `tests/unit/test_web_experiments.py::test_bound_bearer_cannot_touch_the_live_library`, `::test_unbound_bearer_cannot_select_a_context`; `api/experiments.test.ts` > experiments client > "refuses a credential without a context, so it can never reach the live library" |
| Experiment writes stay in approved experiment workspaces / An approved ingestion experiment runs | PARTIAL | `src/omrg/compose_experiments.py:183-269` (Engine per context, store at `<workspace>/output/<backend>`, provenance); `core/experiments/contexts.py` (LanceDB default, `declared_factors=["store"]`); `starter_notebook.py:282` (`checkpoint` into `output/`) | `tests/unit/test_experiment_contexts_engines.py::test_ingestion_experiment_writes_only_below_its_workspace`, `::test_experiment_identity_differs_from_live_and_between_contexts`, `::test_declared_store_factor_moves_the_store_backend`; `tests/unit/test_experiment_contexts.py::test_non_default_store_needs_a_declared_factor`; `tests/unit/test_web_experiments.py::test_bound_bearer_runs_a_read_only_graph_in_its_context`; `tests/unit/test_starter_notebook.py::test_checkpoint_is_written_atomically`. Missing: (a) no HTTP test runs an ingestion graph through `POST /v1/runs` with a bound credential (ingestion is tested at composition level, HTTP with a read-only graph); (b) the server also stores every experiment run's result in `<OMRG workspace>/artefacts` (`runs_wiring.py:379`), so outputs do not stay only below the experiment workspace |
| Experiment writes stay in approved experiment workspaces / Trust warning is displayed | PARTIAL | `src/omrg/transports/api/routes_experiments.py:33-37` (`TRUST_NOTICE`: filesystem and network permissions, "not an operating-system sandbox"), returned by register, list and open routes (`routes_plugins.py:169,208,323`); `web/src/experiments/ExperimentsView.tsx:36-37` (warning region), `NotebookPanel.tsx:33`, `views/settings/PluginSection.tsx:49` | `experiments/ExperimentsView.test.tsx` > Experiments view > "shows the server's trust notice verbatim and prominently"; `views/settings/PluginSection.test.tsx` > "lists every plugin state with the server's detail" (shows `TRUST`); `tests/unit/test_web_plugins.py::test_list_starts_with_no_plugin_and_explains_installation`; `tests/unit/test_web_experiments.py::test_register_list_get_and_revoke`. Missing: Python tests assert only the word "filesystem"; nothing asserts "network" or the no-containment sentence, and the vitest `TRUST` fixture is a copy not tied to the server constant |

### Gaps

1. Approved ingestion experiment over HTTP is not tested. Action: add a test in `tests/unit/test_web_experiments.py` that registers a context with `actions=["read", "ingest"]`, issues a bound bearer, submits an ingestion revision with `experiment_context`, and asserts `resources.experiment.backend.store_path` is below `<context>/output`, the live store is untouched, and `revision_id` plus outputs are recorded.
2. Server run artefacts for experiment runs live in `<OMRG workspace>/artefacts`, outside the experiment workspace. Choose one:
   1. Amend the spec scenario: "its index and its exported outputs SHALL remain below the experiment workspace; OMRG keeps its own run record in the app workspace".
   2. Route experiment run artefacts to `<context>/output/runs` in `runs_wiring.py` and add a test.
3. Trust notice wording is weakly asserted. Actions:
   1. In `tests/unit/test_web_plugins.py` and `tests/unit/test_web_experiments.py`, assert `body["trust_notice"] == TRUST_NOTICE` and that it contains "network" and "not an operating-system sandbox".
   2. Add a Python test that the vitest fixture `web/src/experiments/test/experimentsServer.ts` `TRUST` equals `routes_experiments.TRUST_NOTICE`, or import the server text into the fixture.

### Spec text issues

1. "Notebook targets the live library for mutation" asks for refusal of mutation only. The code refuses every live-library run and read for a bound credential (`live_library_target`, 403 on `/v1/collections`). This is a stricter lead decision, not a spec error. Consider rewording to "any live-library request".
2. "Manifest is approved: a changed manifest or executable reference SHALL require revalidation and approval". The code requires new approval for a changed or deleted manifest, and for a different executable path (new registration). A changed executable at the same path needs a recheck only, not new approval. If "executable reference" means the path, the text is correct; if it means the file content, the text is wrong. Clarify.
3. "An approved ingestion experiment runs ... outputs SHALL remain below that approved experiment workspace" conflicts with the shared run store (see Gap 2).

### Deviations

1. Tested range changed from `>=0.25.0,<0.26.0` to `>=0.25.1,<0.26.0`; only 0.25.1 had the full behaviour check (`marimo-qualification.md` item 11).
2. Starter notebook header changed to the canonical marimo layout after `marimo check` failed; the test loader injects a stand-in module (`marimo-qualification.md` section 3).
3. Stricter credential rule: a bound credential is refused on all live-library runs, read-only ones too (`experiment-transport.md`, `experiment-contexts.md` open point 1).
4. Lease timing: the admitter releases the admission lease at once; the executor takes a fresh lease at execution start (`experiment-transport.md`).
5. Contexts live in memory per launch; approval records do not survive a restart (lead decision; `experiment-transport.md` "Runtime and shutdown", `experiment-contexts.md` open point 2).
6. Editor connection through a private connection file (`OMRG_CONNECTION_FILE`) instead of more environment variables (lead decision; `experiment-transport.md` follow-up).
7. Test-first not strict: `manifest.py` drafted before its tests; shutdown-order and notebook tests written after code. Mutation checks cover them (`plugins.md`, `experiment-transport.md`).

### Risks noted in evidence

1. **`pyproject.toml` re-enables startup runs.** A `pyproject.toml` with `[tool.marimo.runtime] auto_instantiate = true` in the notebook directory or any parent wins over the launch-directory `.marimo.toml` and re-enables startup execution; OMRG cannot block it with a flag. Options listed: (a) document only (done); (b) refuse to open when such a file exists between the notebook and the filesystem root; (c) record the nearest `pyproject.toml` path in the open response (`marimo-qualification.md` 2b and open point 1).
2. **Notebook header `on_cell_change = "autorun"`.** A PEP 723 header can set `runtime.on_cell_change = "autorun"` (only `auto_instantiate` is stripped). The starter notebook's `mo.stop(not run_button.value, ...)` still blocks unrequested runs; other notebooks have no such guard (`marimo-qualification.md` 2b and open point 2).
3. **Editor exiting on its own is not detected.** OMRG keeps the connection files and the editor credential until Stop or application shutdown (`marimo-qualification.md` open point 3, `experiment-transport.md` follow-up open point 2).
4. **Contexts in memory per launch.** Registry state is lost on restart, like bearer credentials (`experiment-contexts.md` open point 2, `experiment-transport.md`).
5. Ready detection uses a loopback connect; a race with an unrelated program between check and bind can give a false ready signal (`plugins.md` open point 3).
6. A process that leaves its group with `setsid` is not tracked (`plugins.md` open point 4).
7. `GET /v1/pipeline-operations` and `POST /v1/pipelines/validate` stay open to bound bearers; unbound bearers can still read experiment runs (`experiment-transport.md` open points 3 and 4).
8. Chroma as a declared store factor is composed but never built in a test (`experiment-contexts.md` open point 3).
9. Bundle size 541 kB and form-field id/name console notes are frontend-wide risks; see `pipeline-canvas.md` (`browser.md` open findings 1 and 3).

### Test files cited

- tests/unit/test_web_plugins.py
- tests/unit/test_web_plugins_launch.py
- tests/unit/test_notebooks_guide.py
- tests/unit/test_plugin_marimo_manifest.py
- tests/unit/test_plugin_registration.py
- tests/unit/test_plugin_manifest.py
- tests/unit/test_plugin_editor.py
- tests/unit/test_process_launcher.py
- tests/unit/test_process_launcher_editor.py
- tests/unit/test_web_experiments.py
- tests/unit/test_web_experiments_runtime.py
- tests/unit/test_starter_notebook.py
- tests/unit/test_experiment_contexts.py
- tests/unit/test_experiment_contexts_engines.py
- web/src/experiments/NotebookPanel.test.tsx
- web/src/experiments/ExperimentsView.test.tsx
- web/src/views/settings/PluginSection.test.tsx
- web/src/api/experiments.test.ts

### Focused runs (this verification)

- `pytest -m "not slow"` on test_plugin_registration, test_plugin_editor, test_plugin_marimo_manifest, test_starter_notebook, test_pipeline_admission: 80 passed, 1 deselected.
- `cd web && npx vitest run` on NotebookPanel, ExperimentsView, PluginSection (with seven canvas and runs files): 10 files, 72 passed.
- `pytest --collect-only` on test_web_plugins, test_web_plugins_launch, test_process_launcher, test_process_launcher_editor, test_notebooks_guide, test_experiment_contexts, test_experiment_contexts_engines, test_web_experiments, test_web_experiments_runtime and others: 326 collected, no errors.

## Verification: `pipeline-canvas` (change `add-local-web-pipeline-workspace`)

Date: 2026-10-13. Worktree: `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace` (uncommitted tree). Read-only check. Paths are relative to the worktree. Vitest paths are relative to `web/src/`.

Result: 16 scenarios. 12 COVERED, 4 PARTIAL, 0 NOT COVERED.

| Requirement / Scenario | Status | Code | Tests |
|---|---|---|---|
| Canvas edits executable graphs / Template is rewired | COVERED | `web/src/canvas/graph.ts:101` (`toDocument`, execution graph only), `web/src/canvas/useCanvasSession.ts:171` (Run submits the saved `revision_id`), `web/src/canvas/TemplatePicker.tsx`, `web/src/canvas/templates.ts`; runner follows saved edges (`src/omrg/core/pipelines/execution.py`) | `canvas/CanvasView.edit.test.tsx` > canvas catalogue and editing > "rewires a saved template and saves the new connections, with layout kept apart"; `canvas/graph.test.ts` > graph draft > "rewires the saved document when edges change"; `canvas/CanvasView.template.test.tsx` > start from template > "loads the template document into a new unsaved draft that the user can edit and save"; `tests/unit/test_pipeline_templates.py::test_template_copy_without_reranker_validates_and_runs` (rewired copy runs on the new edges; rerank absent from node results) |
| Canvas edits executable graphs / Incompatible connection is attempted | COVERED | `web/src/canvas/connections.ts:12` (`portCompatibility`), `:63` (`checkConnection`: kind, score kind, cardinality, loop, self, duplicate), `:100` (`connectionGuard`); `web/src/canvas/ConnectionMenu.tsx:46` and `FlowSurface.tsx:140` ("Cannot connect: ..."); server: `src/omrg/transports/api/routes_graphs.py` validate route | `canvas/CanvasView.edit.test.tsx` > "explains an incompatible connection and does not add it"; `canvas/connections.test.ts` > connection checks > "refuses a connection that closes a loop", "refuses a different value kind and names both ports", "guards drag connections from the flow surface"; `canvas/CanvasView.edit.test.tsx` > "shows server validation issues on the matching node and port"; `tests/unit/test_web_graphs.py::test_invalid_graph_gets_structured_issues_and_never_runs`, `tests/unit/test_web_graphs.py::test_cycle_is_rejected_with_node_names` |
| Canvas edits executable graphs / Draft differs from saved revision | COVERED | `web/src/canvas/RunPanel.tsx:22-27` ("Save a revision before you run", "The draft differs from revision N. Run uses revision N ..."); `useCanvasSession.ts:171-177` (submits saved revision, JSON clone snapshot) | `canvas/CanvasView.run.test.tsx` > revision, run and cancellation > "runs the saved revision and keeps the admitted snapshot after later draft edits"; `tests/unit/test_web_graphs.py::test_invalid_saved_revision_is_refused_at_submission`; `tests/unit/test_pipeline_admission.py::test_snapshot_is_immutable_and_detached` |
| Node controls show effective behaviour / Reranker is disabled with a click | PARTIAL | `web/src/canvas/ParamField.tsx:38` (Inherit/On/Off), `NodeInspector.tsx:55-67` (bypass toggle); `src/omrg/core/retrieval/graph_adapters.py:127-135` (`enabled=False` skips inference, summary reason "disabled by node parameter"); `web/src/runs/NodeRunInspector.tsx` (reason only inside the collapsed "Output summary") | `canvas/CanvasView.run.test.tsx` > node controls > "writes Inherit, On and Off for a lever and shows the effective inherited value" (saved `params: {enabled: false}`); `tests/unit/test_pipeline_admission.py::test_node_disables_reranker_regardless_of_profile`; `tests/unit/test_retrieval_graph_adapters.py::test_disabled_reranker_bypasses_inference`. Missing: no test asserts that the inspector shows the bypass and its reason after the run |
| Node controls show effective behaviour / Profile default is restored | COVERED | `ParamField.tsx:18-31` (Inherit removes the key; effective value and source after validation); `src/omrg/core/pipelines/admission.py` (control source `profile`) | `canvas/CanvasView.run.test.tsx` > "writes Inherit, On and Off ..." (Inherit drops `params`; "Effective value: Off (profile: documents profile)"); `canvas/graph.test.ts` > "drops inherited parameters and default enablement from the document"; `tests/unit/test_pipeline_admission.py::test_inherited_control_reports_profile_source`, `::test_omitted_profile_inherits_collection_profile` |
| Node controls show effective behaviour / Active run has an edited toggle | COVERED | `useCanvasSession.ts:177` (`JSON.parse(JSON.stringify(revision.document))` snapshot) | `canvas/CanvasView.run.test.tsx` > "runs the saved revision and keeps the admitted snapshot after later draft edits" (Off before submit, Inherit after; snapshot keeps `"enabled": true`); `tests/unit/test_web_runs.py::test_editing_after_submission_keeps_the_admitted_revision` |
| Execution display follows real events / A node has not started | COVERED | `web/src/runs/runState.ts:50-68,120,151` ("Not started" without events; no computed progress) | `canvas/CanvasView.live.test.tsx` > canvas live run state > "shows only states that events report and no progress figures"; `runs/runState.test.ts` > run state from events > "reports only what events report: a node without events has no state" |
| Execution display follows real events / Core reports fallback or failure | PARTIAL | `runState.ts:56-57,135-151` (fallback, failed, skipped, bypassed labels); `web/src/runs/NodeRunBadge.tsx:11` (detail text for fallback, failed, skipped only); core emits `node_bypassed` with no reason (`src/omrg/core/pipelines/execution.py:185`) | `canvas/CanvasView.live.test.tsx` > "labels a fallback with its reason and a failure with its error"; `runs/runState.test.ts` > "records a fallback with its reason and a failure with its error". Missing: no test for the "bypasses" case; a bypassed node shows "Bypassed" with no explanation |
| Execution display follows real events / Motion is reduced | COVERED | `web/src/runs/useReducedMotion.ts:3`, `runState.ts:155` (`edgeRunStyle`), `canvas/FlowSurface.tsx:78-87`, `web/src/styles/app.css:387` | `canvas/CanvasView.live.test.tsx` > "keeps a static highlight when reduced motion is requested" (not animated, "Running" text kept); `runs/runState.test.ts` > edge highlighting > "uses a static highlight when motion is reduced". Note: browser.md "Not verified" item 6: reduced motion never observed in a real browser |
| Execution display follows real events / Replay is opened | COVERED | `web/src/runs/ReplayPanel.tsx:10-61` (GET events only, "Replay of recorded events. Nothing runs again."), `runs/LiveRunSummary.tsx:28` ("Recorded run, not live") | `runs/RunsView.test.tsx` > Runs view > "replays a finished run as labelled historical playback". No-execution clause holds by construction (panel calls only `listRunEvents`); the test does not assert absence of POST calls |
| Inspectors expose useful bounded evidence / Ranked rows are inspected | COVERED | `web/src/runs/EvidenceRows.tsx` (rank, `dense_rank`/`sparse_rank`/`fused_rank`), `runs/evidence.ts` (`scoreText`), `EvidenceInspector.tsx:39` ("not probabilities of correctness") | `runs/EvidenceInspector.test.tsx` > evidence inspector > "labels rank and score by score kind"; `runs/evidence.test.ts` > score kinds > "keeps an unknown kind visible and never calls a score a probability", "shows no number for a rank-only kind, even when a value is present" |
| Inspectors expose useful bounded evidence / Large or sensitive payload is inspected | COVERED | `runs/evidence.ts:8,28,55` (100 rows, 4 KiB), `runs/redact.ts:11-27`; server: `src/omrg/core/workspace/artefacts.py` (`to_jsonable` omits vectors, redaction) | `runs/EvidenceInspector.test.tsx` > "bounds previews at 100 rows and 4 KiB and says so"; `runs/RunsView.test.tsx` > "never renders a secret, only the server's redacted marker"; `runs/evidence.test.ts` > secret exclusion > "masks credential keys whatever their value"; `tests/unit/test_workspace_artefacts.py::test_to_jsonable_omits_vectors_and_converts_objects`, `::test_secret_keys_are_redacted`, `::test_long_text_is_truncated_to_four_kib`, `::test_rows_are_limited_to_one_hundred` |
| Application navigation preserves working state / User opens evidence and returns | PARTIAL | `web/src/canvas/storage.ts:91-100` (`readSession`/`writeSession`), `useCanvasSession.ts:19,102`, `useDraft.ts`, `graph.ts:37` (selection in the stored layout) | `canvas/CanvasView.edit.test.tsx` > "restores the unsaved draft after the view is closed and opened again"; `canvas/storage.test.ts` > draft storage > "remembers the open pipeline and the submitted run"; `canvas/useDraft.test.ts` > useDraft (3 tests). Missing: no component test navigates Canvas to Runs (evidence) and back and asserts that the selection and the submitted run identity are restored |
| Application navigation preserves working state / Graph preset is saved | COVERED | Revision save touches workspace records only (`routes_graphs.py`); profile change only through `PATCH /v1/collections/{c}/profile` preview and token (`web/src/views/library/ProfilePanel.tsx`, `usePreviewConfirm.ts`) | `tests/unit/test_pipeline_admission.py::test_explicit_profile_uses_bundle_and_keeps_collection_metadata` (no mutation, metadata unchanged); `tests/unit/test_web_destructive.py::test_profile_preview_then_confirm_changes_query_defaults_only`, `::test_profile_confirm_needs_matching_fresh_preview`; `views/library/LibraryConfirm.test.tsx` > confirmed profile change > "shows exactly what will change, then confirms with the token" |
| Controls are accessible and theme-aware / Graph is edited using a keyboard | COVERED | `web/src/canvas/GraphOutline.tsx:26,61,87,94` (Enter/Space select, Delete/Backspace remove, Remove buttons), `ConnectionMenu.tsx:34-51` ("Connect ports" form), `FlowSurface.tsx:146` | `canvas/CanvasView.edit.test.tsx` > "adds and connects nodes with the keyboard and saves the wiring", "deletes a selected node with Delete and a connection with Backspace". Note: Validate is pressed by click in tests, not by key; the manual keyboard walk in `browser.md` reaches Validate and node settings |
| Controls are accessible and theme-aware / Theme or viewport changes | PARTIAL (manual evidence only for viewport) | `web/src/lib/preferences.ts:69` (`applyTheme`), `web/src/styles/tokens.css`, `app.css`, `canvas/canvas.css`, `runs/runs.css` (D4 and D5 fixes) | `theme.test.tsx` > theme preference > "keeps the current draft view when the theme changes" (checks the view only, not canvas edits). Viewport narrowing, readable focus and reachable inspector actions: manual only (`browser.md` 1280/768/390/320 px, 200% zoom, focus walk) |

### Gaps

1. Reranker disabled with a click: the reason "disabled by node parameter" reaches the run summary but the canvas node shows "Completed" and the reason sits only in a collapsed "Output summary". Actions:
   1. Add a vitest case in `canvas/CanvasView.live.test.tsx` or `runs/RunsView.test.tsx` that sends a `node_completed` event with `summary: {reranked: false, reason: "disabled by node parameter"}` and asserts the visible reason.
   2. If the assertion fails, show `summary.reason` in `NodeRunBadge.tsx` or `NodeRunInspector.tsx` when `reranked` is false.
   3. Add an assertion on `summary["reason"] == "disabled by node parameter"` to `tests/unit/test_retrieval_graph_adapters.py::test_disabled_reranker_bypasses_inference`.
2. Bypass outcome has no explanation and no test. Actions:
   1. Add a test that sends `node_bypassed` and asserts "Bypassed" on the node card.
   2. Choose one: (a) emit a summary message with the bypass reason from `execution.py:_bypass` and show it in `NodeRunBadge.tsx`; (b) show a fixed text such as "Bypassed: passes its input through unchanged" for every bypass.
3. Navigation state: run identity and selection restoration after navigation is not tested at component level. Action: add an `App`-level vitest case: select a node, submit a run, open Runs, return to Canvas, assert the selected node (`aria-pressed="true"`) and the "Submitted run" region with the same run id.
4. Theme or viewport: no automated check that canvas edits survive a theme change, and viewport behaviour is manual only. Actions:
   1. Extend `theme.test.tsx` to add a canvas node, change the theme, and assert the node is still in the outline.
   2. Accept the manual browser evidence for viewport width, or add a Playwright check later (not available now).
5. Replay no-execution clause: optional hardening. Action: assert in "replays a finished run as labelled historical playback" that `server.calls` holds no POST.

### Spec text issues

1. "Reranker is disabled with a click ... the inspector SHALL show the bypass and its reason". The code has two different things: the `enabled` lever set to Off (node runs, passes evidence through, summary reason) and the node bypass toggle (`enabled: false` on the node, `node_bypassed` event, no reason). The scenario word "bypass" fits neither cleanly. Decide which one the scenario means and reword it.
2. The requirement lists "cancelling" among node states. In the code "cancelling" is a run status (`core/workspace/records.py`); node states end in "cancelled". Reword to "run cancelling and node cancelled".
3. "Templates SHALL be editable" was first blocked by a missing templates route (`canvas-editor.md`); `experiments-view.md` later added `GET /v1/pipeline-templates` and the picker. No text change needed; the earlier OPEN note in `canvas-editor.md` is stale.

### Deviations

1. Validation route is `POST /v1/pipelines/validate` with `{document, inputs?, collection?}`, not `/v1/pipelines/{id}/validate`; issues use `node_id` and `edge` (`canvas-editor.md`).
2. Draft validation without `inputs` returns no effective values; the canvas sends inputs only when every required input has a value (`canvas-editor.md`).
3. Graph-wide `overrides` are kept but not editable; `metadata_filter` (object) shows "cannot be edited on the canvas yet" (`canvas-editor.md` PARTIAL).
4. Node times come from the stored result only; a running node shows "recorded when the run ends" (`canvas-runs.md` open point 3).
5. Retrieval outputs were first stored as text; fixed by `to_jsonable` dataclass branch and `public_outputs` (`canvas-runs.md` lead follow-up, `experiment-transport.md`).
6. Reload showed an empty graph; fixed in `useDraft.ts` (`canvas-runs.md` lead follow-up).
7. Browser defects D1 to D6 found and fixed in task 7.7 (`browser.md`).

### Risks noted in evidence

1. Bundle size: single script 541 kB (163 kB gzip); Vite chunk-size warning; code splitting deferred to task 9.4 (`browser.md` open finding 3).
2. Form fields without `id` or `name`: Chrome issue "A form field element should have an id or name attribute", 10 to 40 per view; labels exist, so not an accessibility failure; left open (`browser.md` open finding 1).
3. Node cards render at 0.35 to 0.45 zoom at 1280 px with a six-node graph (`browser.md` open finding 2).
4. Effective-value text is not shown after reload until the next Validate (`browser.md` open finding 5).
5. Reduced-motion rendering of an active run never observed in a real browser; Safari and Firefox not tested (`browser.md` "Not verified" 6 and 7).
6. Real `omrg web` console-script start with `compose.build_engine()` not exercised by the browser walk (`browser.md` "Not verified" 5).
7. `describe_operations` reads private Engine attributes; the client depends only on the JSON shape (`canvas-editor.md`).
8. Control borders below 3:1 contrast against fill (`frontend-scaffold.md` open finding).

### Test files cited

- web/src/canvas/CanvasView.edit.test.tsx
- web/src/canvas/CanvasView.run.test.tsx
- web/src/canvas/CanvasView.live.test.tsx
- web/src/canvas/CanvasView.template.test.tsx
- web/src/canvas/graph.test.ts
- web/src/canvas/connections.test.ts
- web/src/canvas/storage.test.ts
- web/src/canvas/useDraft.test.ts
- web/src/runs/runState.test.ts
- web/src/runs/RunsView.test.tsx
- web/src/runs/EvidenceInspector.test.tsx
- web/src/runs/evidence.test.ts
- web/src/views/library/LibraryConfirm.test.tsx
- web/src/theme.test.tsx
- tests/unit/test_pipeline_templates.py
- tests/unit/test_web_graphs.py
- tests/unit/test_web_runs.py
- tests/unit/test_pipeline_admission.py
- tests/unit/test_retrieval_graph_adapters.py
- tests/unit/test_workspace_artefacts.py
- tests/unit/test_web_destructive.py

### Focused runs (this verification)

- `cd web && npx vitest run` on CanvasView.edit, CanvasView.run, CanvasView.live, RunsView, EvidenceInspector, evidence, NotebookPanel, ExperimentsView, PluginSection, theme: 10 files, 72 passed.
- `pytest -m "not slow"` on test_plugin_registration, test_plugin_editor, test_plugin_marimo_manifest, test_starter_notebook, test_pipeline_admission: 80 passed, 1 deselected.
- `pytest --collect-only` on the other 16 cited Python files: 326 collected, no errors.

## Verification: `pipeline-graphs` capability

Change: `add-local-web-pipeline-workspace`. Worktree: `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace` (WT). Paths below are relative to WT. Date: 2026-10-13.

Method: read every scenario in `openspec/changes/add-local-web-pipeline-workspace/specs/pipeline-graphs/spec.md` (36 scenarios), then read the implementing code and the test bodies. Evidence files were used only as leads. Test node ids were confirmed with `pytest --collect-only` (546 tests collected over the pipeline, adapter, seam, engine and web graph files).

Focused runs (`PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider -m "not slow"`):

- `tests/unit/test_pipeline_preflight.py`, `test_pipeline_runner.py`, `test_pipeline_admission.py`, `test_pipeline_cancellation.py`: **73 passed**.
- `tests/unit/test_engine_pipelines.py`, `test_pipeline_models.py`: **39 passed** (the former strict `xfail` `test_answer_chain_accepts_assembled_context_without_a_bridge` is now a plain passing test).

Result: **30 COVERED, 6 PARTIAL, 0 NOT COVERED.**

| Requirement / Scenario | Status | Code | Tests |
|---|---|---|---|
| Saved connections / Changing a connection changes execution | PARTIAL | `src/omrg/core/pipelines/models.py:139` (`execution_identity`), `src/omrg/core/pipelines/execution.py:93` (`_inputs` routes by edges), `src/omrg/core/pipelines/runner.py:84` (runs the admitted snapshot graph only) | `tests/unit/test_pipeline_models.py::test_connection_change_changes_execution_identity`, `tests/unit/test_pipeline_templates.py::test_template_copy_without_reranker_validates_and_runs`, `tests/unit/test_pipeline_runner.py::test_join_order_is_declared_order_not_completion_order` |
| Saved connections / Moving a node changes presentation only | COVERED | `src/omrg/core/pipelines/models.py:101-141` (layout lives in `GraphLayout`, outside `GraphDocument`), `src/omrg/core/ingestion/graph_fingerprint.py:196` (`graph_shape` ignores ids and layout) | `tests/unit/test_pipeline_models.py::test_layout_change_keeps_execution_identity`, `tests/unit/test_ingestion_graph_fingerprint.py::test_presentation_and_query_changes_keep_the_shape`, `tests/unit/test_ingestion_graph_fingerprint_reuse.py::test_layout_and_id_changes_reuse_standard_sources`, `tests/unit/test_web_graphs.py::test_pipeline_lifecycle_keeps_layout_out_of_revisions`, `web/src/canvas/graph.test.ts` ("changes only layout when a node moves, the viewport changes or the selection changes") |
| Saved connections / Unsupported graph version | COVERED | `src/omrg/core/pipelines/models.py:130`, `:187` (`_version_issue`), `:209` (`parse_definition`) | `tests/unit/test_pipeline_models.py::test_unsupported_schema_version_is_rejected`, `tests/unit/test_pipeline_models.py::test_missing_schema_version_is_rejected`, `tests/unit/test_web_graphs.py::test_revision_save_rejects_unsupported_schema_before_storage` |
| Operation contracts / Catalogue drives node configuration | COVERED | `src/omrg/core/pipelines/catalogue.py:148` (`to_schema`), `:239` (`describe`), `:261` (`capability_reasons`) | `tests/unit/test_pipeline_catalogue.py::test_descriptor_schema_lists_ports_params_and_effects`, `tests/unit/test_pipeline_catalogue.py::test_catalogue_reports_unavailable_operations_with_reasons`, `tests/unit/test_web_graphs.py::test_catalogue_lists_operations_with_unavailable_reasons`, `web/src/canvas/CanvasView.edit.test.tsx` ("lists the catalogue and disables unavailable operations with reasons") |
| Operation contracts / A strategy is reused | COVERED | `src/omrg/core/retrieval/graph_adapters_retrieve.py` (dense via `registry.get("dense")`, sparse via `sparse_policy_runner`), `src/omrg/core/ingestion/graph_adapters.py:192` (`read_document`), `:262` (`split_documents`, registry dispatch at `src/omrg/core/ingestion/chunker.py:203`) | `tests/unit/test_pipeline_templates.py::test_search_template_matches_engine_search` (patches `registry._cache["dense"]`), `tests/unit/test_retrieval_graph_adapters_parity.py::test_graph_chain_matches_search`, `tests/unit/test_ingestion_graph_adapters.py::test_graph_chain_matches_ingest_path_async`, `tests/unit/test_pipeline_catalogue.py::test_dispatch_modules_have_no_name_branches` |
| Operation contracts / Invalid bypass | COVERED | `src/omrg/core/pipelines/validation.py:179` (no declared bypass), `src/omrg/core/pipelines/topology.py:193` (bypassed type flows downstream), `src/omrg/core/pipelines/catalogue.py:124` (`_check_bypass`) | `tests/unit/test_pipeline_preflight.py::test_disabled_node_without_bypass_rejected`, `tests/unit/test_pipeline_preflight.py::test_bypass_type_flows_from_upstream`, `tests/unit/test_pipeline_catalogue.py::test_bypass_cannot_change_port_kind`, `tests/unit/test_ingestion_graph_adapters.py::test_embedding_cannot_be_bypassed_into_the_commit` |
| Preflight / Invalid graph does not execute | COVERED | `src/omrg/core/pipelines/validation.py:291` (`preflight`, no adapter call), `:185` (`_resolve`), `src/omrg/core/pipelines/topology.py:99`, `:125`, `:171` | `tests/unit/test_pipeline_preflight.py::test_preflight_runs_no_adapter`, `::test_unknown_operation_names_node`, `::test_missing_required_input`, `::test_incompatible_connection_names_edge`, `::test_cycle_is_rejected`, `tests/unit/test_engine_pipelines.py::test_validation_has_no_side_effects`, `tests/unit/test_engine_pipelines.py::test_invalid_run_input_raises_before_side_effects`, `tests/unit/test_web_graphs.py::test_invalid_graph_gets_structured_issues_and_never_runs` |
| Preflight / Identity conflict | COVERED | `src/omrg/core/pipelines/validation.py:227` (`_check_identity`, `same_space`), `src/omrg/compose_pipelines.py:79` (`StoreCollectionView`) | `tests/unit/test_pipeline_preflight.py::test_embedding_identity_mismatch_with_equal_dimensions`, `::test_embedding_identity_mismatch_for_commit`, `tests/unit/test_engine_pipelines.py::test_embedding_identity_mismatch_is_rejected` |
| Preflight / Executable text is submitted | COVERED | `src/omrg/core/pipelines/executable.py:32`, `src/omrg/core/pipelines/validation.py:129` (`_check_text`), `:185` (`_resolve`) | `tests/unit/test_pipeline_preflight.py::test_executable_parameter_text_rejected`, `::test_executable_operation_text_rejected`, `tests/unit/test_pipeline_catalogue.py::test_operation_id_rejects_expressions` |
| Preflight / Conflicting commits | COVERED | `src/omrg/core/pipelines/validation.py:246` (`check_commits`), `src/omrg/core/ingestion/graph_fingerprint.py:102` | `tests/unit/test_pipeline_preflight.py::test_conflicting_commits_same_collection`, `::test_multiple_commit_destinations_rejected_initially`, `tests/unit/test_ingestion_graph_fingerprint.py::test_two_commit_destinations_are_refused` |
| Branches and joins / Branches finish in different orders | COVERED | `src/omrg/core/pipelines/execution.py:93` (inputs in declared edge order) | `tests/unit/test_pipeline_runner.py::test_join_order_is_declared_order_not_completion_order`, `::test_fan_out_isolates_mutable_values` |
| Branches and joins / One branch has no results | COVERED | `src/omrg/core/pipelines/execution.py:93`, `src/omrg/core/retrieval/graph_adapters.py:103` (`rrf_adapter`) | `tests/unit/test_pipeline_runner.py::test_empty_branch_is_valid_join_input`, `tests/unit/test_retrieval_graph_adapters.py::test_empty_dense_branch_joins_sparse_branch` |
| Branches and joins / Resource limit is reached | COVERED | `src/omrg/core/pipelines/scheduler.py:40` (`lease_for`), `:120` (`dispatchable`), `:195` (`_fits`), `src/omrg/core/pipelines/runner.py:47` (`RunLimits`), `src/omrg/compose_pipelines.py:355` (per-Engine run lock) | `tests/unit/test_pipeline_runner.py::test_ready_nodes_wait_for_the_concurrency_bound`, `::test_model_calls_on_one_resource_are_serialised`, `tests/unit/test_pipeline_runner_scheduler.py::test_exclusive_lease_excludes_other_holders`, `tests/unit/test_engine_pipelines_isolation.py::test_runs_on_one_engine_are_serialised`, `tests/unit/test_web_runs_service.py::test_jobs_and_graph_runs_share_one_bounded_queue` |
| Run settings / Inherited profile | COVERED | `src/omrg/core/pipelines/admission.py:115` (`resolve_collections`), `:142` (`node_snapshot`) | `tests/unit/test_pipeline_admission.py::test_omitted_profile_inherits_collection_profile`, `::test_inherited_control_reports_profile_source` |
| Run settings / Explicit graph profile | COVERED | `src/omrg/core/pipelines/admission.py:82` (`load_profile`), `:115` | `tests/unit/test_pipeline_admission.py::test_explicit_profile_uses_bundle_and_keeps_collection_metadata` |
| Run settings / Explicit node override | PARTIAL | `src/omrg/core/pipelines/snapshot.py:25-91` (`ControlSource`, `EffectiveControl`, `NodeSnapshot.controls`), `src/omrg/core/retrieval/graph_adapters.py:127` (`rerank_adapter` skips inference when disabled), `src/omrg/transports/api/routes_graphs.py:237` (controls in the admission view only) | `tests/unit/test_pipeline_admission.py::test_node_disables_reranker_regardless_of_profile`, `::test_node_override_beats_graph_override_beats_profile`, `tests/unit/test_retrieval_graph_adapters.py::test_disabled_reranker_bypasses_inference` |
| Run settings / Settings change during execution | COVERED | `src/omrg/core/pipelines/snapshot.py:94` (frozen `AdmissionSnapshot`), `src/omrg/core/pipelines/admission.py:198` | `tests/unit/test_pipeline_admission.py::test_snapshot_is_immutable_and_detached`, `tests/unit/test_web_runs.py::test_editing_after_submission_keeps_the_admitted_revision`, `tests/unit/test_web_runs.py::test_submitted_run_executes_the_admitted_snapshot` |
| Run settings / Unsupported composition override | COVERED | `src/omrg/core/pipelines/levers.py:111` (`is_host_owned`), `:118` (`lever_error`), `src/omrg/core/pipelines/validation.py:102` (`check_document`, hybrid hint) | `tests/unit/test_pipeline_preflight.py::test_graph_overrides_outside_allowed_levers`, `::test_unsupported_graph_profile`, `tests/unit/test_pipeline_admission.py::test_hybrid_graph_profile_rejected_before_resolution`, `tests/unit/test_engine_pipelines.py::test_explicit_engine_cannot_load_named_profile` |
| Retrieval and answering / Threshold sees an incompatible score | COVERED | `src/omrg/core/pipelines/ports.py:184` (`check_port_compatibility`), `src/omrg/core/retrieval/graph_adapters.py:168-177` (runtime score-kind guard), `src/omrg/core/retrieval/operations.py:283` (`apply_score_threshold`) | `tests/unit/test_pipeline_catalogue.py::test_fusion_score_cannot_feed_dense_threshold`, `tests/unit/test_pipeline_preflight.py::test_incompatible_connection_names_edge`, `tests/unit/test_retrieval_graph_adapters.py::test_threshold_refuses_rank_only_evidence`, `::test_reranker_declares_bypass_and_threshold_rejects_rank_only_scores` |
| Retrieval and answering / Reranker degrades | COVERED | `src/omrg/core/retrieval/graph_adapters.py:127` (`run_reranker`, `NodeOutput.fallback`), `:181-197` (dense gate re-applied) | `tests/unit/test_retrieval_graph_adapters.py::test_reranker_failure_returns_fallback_not_exception`, `tests/unit/test_retrieval_graph_adapters_parity.py::test_reranker_failure_is_a_fallback_outcome`, `tests/unit/test_pipeline_templates.py::test_search_template_matches_engine_search`, `tests/unit/test_pipeline_runner.py::test_domain_fallback_is_an_outcome_not_a_failure` |
| Retrieval and answering / Answer has no evidence | COVERED | `src/omrg/core/answer/graph_adapters.py:206-226` (`synthesise_adapter` returns `no_evidence_result` before model lookup) | `tests/unit/test_answer_graph_adapters.py::test_empty_evidence_returns_no_evidence_without_resolving_models`, `::test_no_evidence_never_looks_up_the_answer_resource`, `tests/unit/test_engine_pipelines.py::test_empty_evidence_answer_graph_never_builds_answer_models`, `tests/unit/test_answer_graph_adapters_parity.py::test_graph_chain_matches_standard_answer_path` |
| Retrieval and answering / Citation is inspected | COVERED | `src/omrg/core/answer/graph_adapters.py:268` (`cite_adapter` calls shared `resolve_citations`), `:313` (`verify_claims_adapter`, separate verification label) | `tests/unit/test_answer_seams.py::test_seam_citations_resolve_to_stored_chunks`, `tests/unit/test_answer_graph_adapters.py::test_port_contracts_keep_citations_before_verification`, `::test_synthesis_output_is_unresolved_until_citations_run`, `tests/unit/test_pipeline_templates_parity.py::test_answer_template_matches_engine_answer`, `web/src/views/ask/AskView.test.tsx`, `web/src/runs/EvidenceInspector.test.tsx` |
| Graph ingestion / Same complete source is reused | COVERED | `src/omrg/core/ingestion/graph_adapters.py:155-186` (`identify_adapter`, `check_source_state`), `:192-196` (non-pending passes through) | `tests/unit/test_ingestion_graph_adapters.py::test_unchanged_sources_skip_expensive_work`, `tests/unit/test_ingestion_graph_fingerprint_reuse.py::test_changed_shaping_operation_reprocesses_then_reuses` |
| Graph ingestion / Ingestion graph changes | COVERED | `src/omrg/core/ingestion/graph_fingerprint.py:196`, `:206`, `src/omrg/core/ingestion/source_state.py:128` (`build_index_identity(..., graph_shape=)`) | `tests/unit/test_ingestion_graph_fingerprint.py::test_shaping_changes_change_the_shape`, `tests/unit/test_ingestion_graph_fingerprint_reuse.py::test_changed_shaping_operation_reprocesses_then_reuses`, `::test_admitting_a_changed_graph_does_not_change_vectors`, `::test_shape_change_without_parameter_effect_still_reprocesses` |
| Graph ingestion / Existing lineage is invalid | COVERED | `src/omrg/core/ingestion/graph_adapters.py:155-186` (guard in `prepare_source` / `check_source_state` before any read) | `tests/unit/test_ingestion_graph_adapters_commit.py::test_legacy_lineage_is_rejected_before_parsing`, `::test_invalid_lineage_fails_before_mutation` |
| Graph ingestion / Replacement reaches commit | COVERED | `src/omrg/core/ingestion/graph_adapters_values.py:164` (`run_protected`, `asyncio.shield`), `src/omrg/core/ingestion/graph_adapters.py:350-415` (`commit_adapter`, sole mutator) | `tests/unit/test_ingestion_graph_adapters_commit.py::test_failed_verification_keeps_previous_version_and_retry_cleans`, `::test_task_cancellation_waits_for_an_entered_commit`, `tests/unit/test_ingestion_graph_adapters.py::test_only_the_commit_operation_mutates_the_store`, `::test_non_commit_nodes_never_mutate_the_store`, `tests/unit/test_ingestion_seams_replacement.py::test_commit_holds_the_write_lock_for_write_verify_and_cleanup` |
| Graph ingestion / Reader declares Markdown or structured output | PARTIAL | `src/omrg/core/ingestion/graph_adapters.py:192-221` (`BackendRead` kept), `:262-292` (`declares_markdown`, `structured=read.structured`) | `tests/unit/test_ingestion_graph_adapters.py::test_reader_markdown_declaration_reaches_the_splitter`, `::test_read_keeps_reader_declarations_on_its_port`, `tests/unit/test_ingestion_seams.py::test_split_documents_uses_registry_and_stamps_metadata` |
| Graph ingestion / Directory ingestion remains bounded | COVERED | `src/omrg/core/pipelines/runner.py:193` (`_run_units`), `src/omrg/core/ingestion/graph_adapters_values.py:87` (`single_unit`), `src/omrg/core/ingestion/graph_adapters.py:115` (`ingestion_unit_split`) | `tests/unit/test_pipeline_runner_units.py::test_unit_values_are_released_before_the_next_unit`, `::test_failed_file_keeps_sibling_commits`, `::test_each_source_runs_the_graph_once`, `tests/unit/test_ingestion_graph_adapters.py::test_identify_refuses_more_than_one_source` |
| Outcomes and cancellation / A node fails | COVERED | `src/omrg/core/pipelines/execution.py:326` (`_fail`), `:347` (`_mark_dependants`), `:188` (`_skip_commits_after_failure`) | `tests/unit/test_pipeline_runner.py::test_node_failure_skips_dependants_and_names_the_node`, `tests/unit/test_pipeline_runner_units.py::test_failed_file_keeps_sibling_commits`, `tests/unit/test_pipeline_runner_commit_guard.py::test_entered_commit_completes_when_a_sibling_fails`, `::test_failed_unit_skips_a_commit_on_an_independent_branch` |
| Outcomes and cancellation / Cancellation precedes commit | COVERED | `src/omrg/core/pipelines/cancellation.py:34` (`RunCancellation`), `src/omrg/core/pipelines/execution.py:199` (`_stop_pending`), `src/omrg/core/ingestion/graph_adapters.py:350-371` (check before `run_protected`) | `tests/unit/test_pipeline_cancellation.py::test_cancellation_before_commit_prevents_the_commit`, `::test_cancellation_between_units_keeps_earlier_commits`, `::test_adapter_stops_at_its_own_safe_boundary`, `tests/unit/test_ingestion_graph_adapters_commit.py::test_cancellation_before_commit_starts_nothing`, `tests/unit/test_engine_pipelines.py::test_caller_cancellation_is_run_scoped` |
| Outcomes and cancellation / Cancellation arrives during commit | COVERED | `src/omrg/core/ingestion/graph_adapters_values.py:164`, `src/omrg/core/pipelines/runner.py:265` (`_conclude`, completed effects) | `tests/unit/test_pipeline_cancellation.py::test_entered_commit_completes_before_terminal_cancel`, `::test_cancelling_the_run_task_still_finishes_the_commit`, `tests/unit/test_ingestion_graph_adapters_commit.py::test_cancellation_during_commit_lets_it_finish` |
| Outcomes and cancellation / Blocking inference continues | COVERED | `src/omrg/core/pipelines/execution.py:109-160` (waits for started nodes, emits `run_cancelling` before `run_cancelled`) | `tests/unit/test_pipeline_cancellation.py::test_blocking_call_finishes_at_a_safe_boundary` |
| Shared algorithms / Canonical retrieval parity | COVERED | `src/omrg/pipeline_templates.py:147` (`search_template`), `src/omrg/core/retrieval/graph_adapters.py` (calls `operations.py`, `assembly.py`) | `tests/unit/test_pipeline_templates.py::test_search_template_matches_engine_search`, `tests/unit/test_retrieval_graph_adapters_parity.py::test_graph_chain_matches_search`, `::test_graph_chain_matches_recorded_expectation` |
| Shared algorithms / Canonical ingestion and answer parity | PARTIAL | `src/omrg/pipeline_templates.py:133`, `:167`, `src/omrg/core/ingestion/graph_adapters.py:385` (commit summary carries `metadata_degraded`) | `tests/unit/test_pipeline_templates_parity.py::test_ingestion_template_writes_the_same_rows_as_engine_ingest`, `::test_answer_template_matches_engine_answer`, `tests/unit/test_engine_pipelines_ingestion.py::test_ingestion_graph_writes_the_same_rows_as_engine_ingest`, `tests/unit/test_ingestion_graph_adapters.py::test_graph_chain_matches_ingest_path_async`, `tests/unit/test_answer_graph_adapters_parity.py::test_graph_chain_matches_standard_answer_path` |
| Shared algorithms / Repaired document strategy is reused | PARTIAL | `src/omrg/core/ingestion/graph_adapters.py:262-292` (graph calls `split_documents`), `src/omrg/core/ingestion/chunker.py:203` (registry `sentence` dispatch) | `tests/test_document_registry_dispatch.py::test_both_document_branches_invoke_registered_sentence_strategy` (standard path only), `tests/unit/test_ingestion_seams.py::test_split_documents_uses_registry_and_stamps_metadata`, `tests/unit/test_ingestion_graph_adapters.py::test_reader_markdown_declaration_reaches_the_splitter` |
| Shared algorithms / Metadata enrichment retains the owning store | PARTIAL | `src/omrg/core/ingestion/graph_adapters.py:241-259` (`enrich_adapter` passes `store=required(context, STORE_RESOURCE)` and node settings) | `tests/unit/test_graph_adapters_store_forwarding.py::test_enrich_forwards_run_store_and_settings_to_metadata`, `tests/unit/test_ingestion_graph_adapters.py::test_adapters_never_read_process_defaults`, `tests/test_metadata_store_ownership.py::test_two_engines_interleaved_ingestion_prompts` (standard `Engine.ingest` path only) |

### Gaps

1. **Changing a connection changes execution (PARTIAL).** Tests prove that a rewire changes execution identity, and that one rewired template copy runs. No test runs two revisions that differ only in connections against one fixture and asserts that the invoked node set and the output differ. Action: add a test in `tests/unit/test_engine_pipelines.py` that runs two revisions of one search graph (for example `dense -> select` and `sparse -> fuse -> select`) on one `FakeStore`. Assert the `NodeOutcome` ids and the output rows differ, and that each run's `graph_identity` equals its own revision.
2. **Explicit node override (PARTIAL).** The effective control and its source live in `AdmissionSnapshot.NodeSnapshot.controls` and in the admission view of `POST .../validate`. `PipelineResult` and the persisted run record (`snapshot_provenance` in `src/omrg/transports/api/runs_wiring.py:116`) store only collection-level settings, so a finished run does not record the node control or its source. Choose one:
   1. Add node controls to `snapshot_provenance` and assert them in `tests/unit/test_web_runs.py::test_submitted_run_executes_the_admitted_snapshot`.
   2. Reword the scenario to "the admission snapshot SHALL record the effective control and its source".
3. **Reader declares Markdown or structured output (PARTIAL).** The Markdown declaration is checked through a real graph run. The `structured` declaration is checked only on the port type and in the `split_documents` seam test. No graph run exercises `structured=True` (the parity fixtures are `.md` and `.txt`). Action: add a graph test that patches `graph_adapters.read_document` to return `BackendRead(..., structured=True, ...)` and spies `split_documents` for `structured is True` and no enrichment call.
4. **Canonical ingestion and answer parity (PARTIAL).** Answer degradation markers are compared on 18 cases. Ingestion parity runs with extraction disabled, so `metadata_degraded` is always false on both paths and is never compared under a degrading condition. Action: add an ingestion parity case where metadata extraction degrades (fake extractor returns degraded), then compare `metadata_degraded` in `file_details` with the graph commit summaries and the stored chunk metadata.
5. **Repaired document strategy is reused (PARTIAL).** The registered `sentence` replacement is proven on the standard path (`tests/test_document_registry_dispatch.py`) and on the `split_documents` seam. No test runs a graph with a registered sentinel strategy, and no test checks the degradation marker through the graph. Action: reuse the `sentinel_strategy` fixture from `tests/test_document_registry_dispatch.py` in a graph test that runs the canonical ingestion graph and asserts the sentinel was called with `is_markdown` from the reader and that the degradation marker reaches the commit summary.
6. **Metadata enrichment retains the owning store (PARTIAL).** `test_enrich_forwards_run_store_and_settings_to_metadata` proves that one run forwards its own store object and settings. The two-Engine prompt capture test exists only for `Engine.ingest`. Action: add a graph variant of `test_two_engines_interleaved_ingestion_prompts` that calls `Engine.run_pipeline(canonical_ingestion_definition(...))` on two Engines with disjoint stores and checks each captured classification prompt holds only its own labels plus seeds.

### Spec text issues

1. **Threshold sees an incompatible score.** The real catalogue's `select.threshold` accepts `rrf_v1` evidence by design. It never thresholds the fused score; it applies the dense gate before fusion, as `search()` does. Only the test fixture operation `select.dense_threshold` is rejected by port typing, and the runtime guard rejects rank-only sparse evidence. The scenario's "SHALL reject" therefore never triggers for a registered operation. Suggest: "SHALL either reject the connection or apply the threshold only on the score kind it was calibrated for, and SHALL NOT label that score as dense similarity."
2. **Explicit node override.** "The result SHALL record the effective control" does not match the design: controls are recorded in the admission snapshot, not in `PipelineResult` (see Gap 2).
3. **Conflicting commits.** The implementation is stricter than the text. It rejects any second enabled commit destination (`multiple_commit_destinations`), not only commits to the same source and collection. Suggest the scenario names the one-destination rule.
4. **Explicit graph profile.** A profile's `hybrid_enabled` value does not add or remove a sparse branch. The graph shape decides the stages (end-to-end run shows `hybrid_enabled false` while the graph fuses). The scenario does not say this; a reader could expect the bundle to change the stages.
5. **Ingestion graph changes.** An explicit node-level lever equal to its default counts as index shaping and reprocesses once. The scenario does not mention this conservative choice.

### Deviations (from evidence files, relevant to this capability)

1. `retrieval-adapters.md`: new score kind `sparse_rank_v1` for sparse rows (rank only, no score), not `native_fts_v1`.
2. `retrieval-adapters.md`, `templates-and-guides.md`: the provisional `select.dense_threshold` is not registered; `select.threshold` is score-kind-aware and `retrieve.prepare_query` is new.
3. `retrieval-adapters.md`: the hybrid lever is resolved into `PreparedQuery.hybrid`, but the graph shape decides whether a sparse branch runs.
4. `retrieval-adapters.md`: `combine.rrf` takes at most one dense and one other ranking; more raise `ValueError`.
5. `retrieval-adapters.md`: with a dense threshold above 0 and no rerank, a sparse-only fusion returns no rows (keeps the `search()` dense eligibility rule).
6. `retrieval-adapters.md`: the rerank decision lives in `retrieve.prepare_query`; `select.rerank enabled=false` skips inference and `select.threshold` restores the dense gate.
7. `ingestion-adapters.md`: `_INDEX_IDENTITY_SCHEMA` stays at 6; the standard shape adds nothing, so existing collections do not reprocess. Only non-standard graphs get a new identity.
8. `ingestion-adapters.md`: explicit node lever equal to the default counts in the fingerprint (reprocesses once).
9. `ingestion-adapters.md`: `source.discover` reports unsupported files only as a count in the event summary.
10. `runner.md` (lead decision on D3): after a unit failure, a not-started `SOURCE_COMMIT` node in that unit is skipped even on an independent branch; a started commit finishes.
11. `runner.md`: leases are per run; per-Engine serialisation of runs is an `asyncio.Lock` in `compose_pipelines.EnginePipelines` (task 4.3). Event sink failures are logged and the run continues.
12. `engine-wiring.md`: the answer-chain defect (`ContextBundle` not iterable) is fixed: `src/omrg/core/answer/graph_adapters.py:187` (`_context_rows`) accepts `public_rows()`. The strict `xfail` is gone and the test passes.
13. `engine-wiring.md`, `answer-seams.md`: `answer()` request limits (query 4096 characters, `top_k` 1 to 100, `expand_window` 0 to 10) apply to graphs with an answer output through `compose_pipelines.request_limit_issues`, not inside the answer adapters.
14. `templates-and-guides.md`: templates are Python builders in `src/omrg/pipeline_templates.py`, not JSON files; the search output is a `ContextBundle` (HTTP serialises with `public_rows()`); `verify.claims` is always wired; `canonical_templates(rerank=True)` is the default.
15. `adapter-guards.md`: `core/ingestion/pipeline.py` and `replacement.py` stay off `_GUARDED_LEAVES` because they still fall back to `get_default_store` when a caller passes no store.

### Test files cited

tests/unit/test_pipeline_models.py
tests/unit/test_pipeline_catalogue.py
tests/unit/test_pipeline_preflight.py
tests/unit/test_pipeline_admission.py
tests/unit/test_pipeline_runner.py
tests/unit/test_pipeline_runner_scheduler.py
tests/unit/test_pipeline_runner_units.py
tests/unit/test_pipeline_runner_commit_guard.py
tests/unit/test_pipeline_cancellation.py
tests/unit/test_pipeline_templates.py
tests/unit/test_pipeline_templates_parity.py
tests/unit/test_engine_pipelines.py
tests/unit/test_engine_pipelines_isolation.py
tests/unit/test_engine_pipelines_ingestion.py
tests/unit/test_retrieval_graph_adapters.py
tests/unit/test_retrieval_graph_adapters_parity.py
tests/unit/test_answer_graph_adapters.py
tests/unit/test_answer_graph_adapters_parity.py
tests/unit/test_answer_seams.py
tests/unit/test_ingestion_graph_adapters.py
tests/unit/test_ingestion_graph_adapters_commit.py
tests/unit/test_ingestion_graph_fingerprint.py
tests/unit/test_ingestion_graph_fingerprint_reuse.py
tests/unit/test_ingestion_seams.py
tests/unit/test_ingestion_seams_replacement.py
tests/unit/test_graph_adapters_store_forwarding.py
tests/unit/test_web_graphs.py
tests/unit/test_web_runs.py
tests/unit/test_web_runs_service.py
tests/test_document_registry_dispatch.py
tests/test_metadata_store_ownership.py
web/src/canvas/graph.test.ts
web/src/canvas/CanvasView.edit.test.tsx
web/src/views/ask/AskView.test.tsx
web/src/runs/EvidenceInspector.test.tsx

## Verification: capability `pipeline-run-records`

Change: `add-local-web-pipeline-workspace`. Worktree `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace`, branch `feat/add-local-web-pipeline-workspace`, uncommitted tree on base `489a618`.
Spec: `openspec/changes/add-local-web-pipeline-workspace/specs/pipeline-run-records/spec.md` (6 requirements, 14 scenarios).
Method: read the code and the tests. Evidence files were used as leads only. Paths are relative to the worktree.

Counts: **10 COVERED, 4 PARTIAL, 0 NOT COVERED** (14 scenarios).

Focused runs (`PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider`):

- Collect-only on 15 cited Python files: 236 tests collected, no errors.
- `test_workspace_repository.py test_workspace_service.py test_workspace_service_outputs.py test_workspace_service_lifecycle.py test_web_runs.py`: **71 passed**.
- `test_web_runs_stream.py test_workspace_migrations.py test_workspace_cleanup_safety.py`: **26 passed**.
- Vitest not run (instruction). Vitest names below come from reading the files.

### Scenario table

| Requirement / Scenario | Status | Code | Tests |
|---|---|---|---|
| R1 Execution revisions are immutable (requirement text: layout stored separately) | COVERED | `src/omrg/integrations/workspace_sqlite/schema.py:45-48` (no-update and no-delete triggers on `pipeline_revisions`); `repository.py:148` `save_layout` writes `pipelines.layout_json` only; `repository.py:160` `save_revision` (SHA-256 content hash, dedupe per pipeline) | `tests/unit/test_workspace_repository.py::test_stored_revisions_cannot_be_updated_or_deleted`, `::test_layout_save_never_creates_a_revision`, `::test_semantic_change_creates_new_revision_and_moves_current`, `::test_revision_identity_is_sha256_of_canonical_json`; `tests/unit/test_web_graphs.py::test_pipeline_lifecycle_keeps_layout_out_of_revisions`; vitest `web/src/canvas/CanvasView.run.test.tsx` "saves the layout without creating a revision" |
| R1 / Editing after submission | COVERED | `src/omrg/core/workspace/service.py:275-316` `_enqueue` freezes document, inputs, settings and resources as canonical JSON in `RunJob`; `src/omrg/core/workspace/jobs.py:85-86` frozen `RunJob`; run row keeps `revision_id` | `tests/unit/test_workspace_repository.py::test_editing_after_submission_keeps_the_admitted_revision`; `tests/unit/test_workspace_service.py::test_job_snapshot_is_immutable_and_survives_later_edits`; `tests/unit/test_web_runs.py::test_editing_after_submission_keeps_the_admitted_revision`; vitest `web/src/canvas/CanvasView.run.test.tsx` "runs the saved revision and keeps the admitted snapshot after later draft edits" |
| R1 / Old revision is selected | PARTIAL | `service.py:233-256` `submit(..., origin="repeat")` runs fresh admission (`service.py:290`); `src/omrg/transports/api/routes_runs.py:81,202` accepts `origin: "repeat"`; `runs_wiring.py:115-133` `snapshot_provenance` | `tests/unit/test_workspace_service_lifecycle.py::test_explicit_repeat_records_its_origin`; `tests/unit/test_web_runs.py::test_explicit_repeat_and_input_refusals`; `tests/unit/test_workspace_repository.py::test_repeat_and_retry_runs_identify_their_origin`. Gaps: no test repeats an older, non-current revision and checks that the executed document equals that old revision; for live-library runs no index identity is captured (see R2). The web UI has no repeat control (only `RunDetail.tsx:39` labels the origin); the HTTP route is the only user path. |
| R2 Runs capture sufficient provenance (requirement text) | PARTIAL | `runs_wiring.py:115-133` records per-collection profile, profile origin and full `EffectiveSettings` dump (includes `vector_store`, `lancedb_uri`, `embed_provider`, `embed_model`), plus `graph_identity`, `schema_version`, `operations` (`node -> op@version`); `outcomes.py:84-118` records `failed_node`, `completed_effects`, `result_ref` | `tests/unit/test_web_runs.py::test_submitted_run_executes_the_admitted_snapshot` (asserts `graph_identity`, profile, result ref); `tests/unit/test_workspace_service.py::test_failed_result_records_failing_node_and_completed_effects`. Gaps: no durable index identity (for example `get_data_version`) is recorded for live-library runs; only experiment runs record `index_identity` (`runs_wiring.py:194`, `core/experiments/admission.py:51`). No Python test asserts the `operations` versions field. |
| R2 / A run is inspected | COVERED | `routes_runs.py:257-275` `GET /v1/runs/{id}` and `/result` read the stored record and result artefact only; `web/src/runs/RunSnapshot.tsx:15-47` renders from the run record, never the draft | `tests/unit/test_web_runs.py::test_submitted_run_executes_the_admitted_snapshot`, `::test_failed_run_can_be_retried_as_a_new_run`; `tests/unit/test_workspace_service.py::test_failed_result_records_failing_node_and_completed_effects`; vitest `web/src/runs/RunsView.test.tsx` "shows the immutable snapshot of a failed run and its completed effects" |
| R2 / Secrets occur in runtime configuration | COVERED | `src/omrg/core/workspace/redaction.py:60-103` key and text redaction; `outcomes.py:37-39` `plain()`; `service.py:286-288` refuses inputs that hold credentials; `artefacts.py:37-47` vectors become `{"omitted": "vector data"}`; `artefacts.py:26-28,230` 100 rows, 4 KiB text, 16 KiB summaries | `tests/unit/test_workspace_service_outputs.py::test_secrets_never_reach_records_events_or_artefacts`, `::test_large_event_payloads_are_bounded`; `tests/unit/test_workspace_service.py::test_inputs_with_credentials_are_refused`, `::test_job_snapshot_is_immutable_and_survives_later_edits` (`openrouter_api_key` redacted); `tests/unit/test_workspace_artefacts.py::test_secret_keys_are_redacted`, `::test_secret_values_are_redacted_in_text`, `::test_to_jsonable_omits_vectors_and_converts_objects`; `tests/unit/test_web_runs.py::test_explicit_repeat_and_input_refusals`; vitest `RunsView.test.tsx` "never renders a secret, only the server's redacted marker", `web/src/runs/evidence.test.ts` "secret exclusion" |
| R3 Local admission and supervision are bounded (requirement text) | COVERED | `jobs.py:24` `DEFAULT_MAX_WAITING = 16`; `service.py:364-375` single consumer; `src/omrg/transports/api/lifespan.py:145` `WorkspaceLock` (one service per workspace file); `src/omrg/core/pipelines/runner.py:56` `max_concurrency = 2` and leases in `scheduler.py` | `tests/unit/test_workspace_service.py::test_default_waiting_limit_is_sixteen`; `tests/unit/test_web_runs_service.py::test_second_server_on_the_same_workspace_does_not_start`, `::test_jobs_and_graph_runs_share_one_bounded_queue`; `tests/unit/test_pipeline_runner_scheduler.py` and `test_pipeline_runner.py::test_ready_nodes_wait_for_the_concurrency_bound` (named in `evidence/runner.md`) |
| R3 / Queue is full | COVERED | `jobs.py:181` `check_capacity` before admission and record (`service.py:285`); `routes_runs.py:124-125` maps `QueueFullError` to 429 | `tests/unit/test_workspace_service.py::test_queue_overflow_is_rejected_visibly_without_starting_work`; `tests/unit/test_web_runs.py::test_full_queue_returns_429_without_a_record` |
| R3 / One job fails | COVERED | `service.py:364-392` catches executor errors and records `failed`; `outcomes.py:59-65` `fail_safely` if the terminal write fails | `tests/unit/test_workspace_service.py::test_failed_job_does_not_stop_the_consumer`, `::test_consumer_survives_a_recording_failure` |
| R4 Events can be replayed consistently (requirement text) | COVERED | `repository.py:321` `record_update` updates the run row and inserts the event in one `BEGIN IMMEDIATE` transaction with `last_sequence + 1`; `events.py:33-62` commits, then wakes subscribers; `web/src/runs/eventClient.ts:111` drops `sequence <= last` | `tests/unit/test_workspace_repository.py::test_status_update_and_event_commit_together`, `::test_failed_event_write_rolls_back_the_status_update`, `::test_sequences_are_independent_per_run`; `tests/unit/test_workspace_service.py::test_subscribers_see_events_only_after_commit`, `::test_failed_commit_wakes_no_subscriber`, `::test_status_and_runner_events_are_committed_in_order` |
| R4 / Monitoring reconnects | PARTIAL | `events.py:69-111` replay and subscribe after a sequence; `routes_runs.py:310-321` `Last-Event-ID` wins over `after`; `routes_runs.py:351-352` final `run.end` frame carries the stored status; `web/src/runs/eventClient.ts` dedupe; `web/src/runs/useRunMonitor.ts:46-63` reads the run record at start and again on stream end | `tests/unit/test_workspace_service_outputs.py::test_reconnect_replays_later_events_in_order`; `tests/unit/test_web_runs_stream.py::test_reconnect_replays_after_last_event_id`, `::test_stream_replays_every_event_with_sequence_ids`; `tests/unit/test_web_runs.py::test_polling_returns_ordered_events_after_a_sequence`; vitest `eventClient.test.ts` "drops events that a reconnect replays again", "resumes a new stream after the last seen sequence", "deduplicates repeated polling pages..."; `CanvasView.live.test.tsx` "deduplicates events replayed after a reconnect". Gap: clause "client SHALL refresh the authoritative run state" after a reconnect. The client re-reads the record only at mount and at stream end, not on reconnect, and no vitest asserts the `getRunRecord` refresh (`refreshedStatus` has no test). |
| R4 / Subscriber disconnects | COVERED | `events.py:79-111` closing the iterator only removes the waiter; `routes_runs.py:323-361` stream close cancels only the pending read; `useRunMonitor.ts:67-70` unmount only closes the follower | `tests/unit/test_workspace_service_outputs.py::test_subscriber_disconnect_does_not_cancel_the_run`; `tests/unit/test_web_runs_stream.py::test_browser_disconnect_detaches_monitoring_without_cancelling` |
| R4 / Durations overlap | COVERED | `outcomes.py:84-118` stores `wall_time_s` (service clock), `runner_wall_time_s` and per-node `node_durations_s`, never a sum; `runner.py:138` measured wall time | `tests/unit/test_workspace_service_outputs.py::test_overlapping_node_durations_are_never_summed`; `tests/unit/test_pipeline_runner.py::test_wall_time_is_measured_not_summed`; vitest `RunsView.test.tsx` "shows node timings separately from the run wall time and never adds them up" |
| R5 / Process stops between stores | PARTIAL | `service.py:157-175` `start()` marks `queued`, `running`, `cancelling` runs `interrupted` and never re-runs them; `outcomes.py:157-177` lists completed effects from stored `effect_committed` events; `src/omrg/core/pipelines/execution.py:298-306` emits `effect_committed` with `data.effect`; `cleanup.py:43` warns that interrupted runs need a completeness check | `tests/unit/test_workspace_service_lifecycle.py::test_restart_marks_unfinished_runs_interrupted_without_rerun`, `::test_shutdown_timeout_interrupts_a_stuck_run`; `tests/unit/test_web_runs.py::test_restart_reports_unfinished_runs_as_interrupted`; `tests/unit/test_web_openapi_conformance_runs.py::test_unfinished_work_reads_interrupted_after_restart`. Gap: clause "recovery SHALL use existing source completeness rules before an explicit retry". The retry path re-admits and runs the ingestion commit adapter, which keeps lineage/complete-version checks (`tests/unit/test_ingestion_graph_adapters_commit.py::test_failed_verification_keeps_previous_version_and_retry_cleans`), but no test links an interrupted run's retry to a source-completeness check. Also `effect_committed` is emitted only after the commit node returns, so a crash inside the commit leaves no effect evidence (the run still reads `interrupted`). |
| R5 / User requests retry | COVERED | `service.py:258-273` `retry()` only from `failed`, `cancelled`, `interrupted`; new run with `origin="retry"`, `source_run_id`, fresh admission; `routes_runs.py:217-230` | `tests/unit/test_workspace_service_lifecycle.py::test_explicit_retry_creates_a_new_run_from_the_stored_snapshot` (source events unchanged, new index identity from fresh admission), `::test_interrupted_run_can_be_retried_explicitly`, `::test_retry_is_refused_for_succeeded_or_active_runs`; `tests/unit/test_web_runs.py::test_failed_run_can_be_retried_as_a_new_run`; vitest `RunsView.test.tsx` "retries only on an explicit click and opens the new run" |
| R6 Application artefacts separate and bounded (requirement text) | COVERED | `src/omrg/integrations/workspace_sqlite/schema.py:114-141` dirs 0o700, files 0o600; `src/omrg/core/workspace/artefacts.py:145-241` artefacts under `<workspace>/artefacts/<run_id>/`, atomic, 0o600, no escape | `tests/unit/test_workspace_migrations.py::test_new_workspace_directory_and_files_are_owner_only`, `::test_existing_database_permissions_are_tightened`; `tests/unit/test_workspace_artefacts.py::test_artefacts_are_owner_only`, `::test_artefact_references_cannot_escape_the_root` |
| R6 / Workspace schema changes | PARTIAL | `schema.py:161-171` SQLite backup API copy (0o600) before mutation; `schema.py:174-223` all migrations in one transaction, rollback names the backup; refuses foreign or newer files | `tests/unit/test_workspace_migrations.py::test_upgrade_backs_up_previous_records_before_mutation`, `::test_failed_migration_rolls_back_and_keeps_original_intact`, `::test_newer_schema_is_refused_without_mutation`, `::test_foreign_database_is_refused`. Gap: clause "SHALL NOT migrate or rebuild vector stores" is proved only structurally (the adapter imports no vector store; `tests/unit/test_workspace_contracts.py::test_contract_import_stays_free_of_persistence_and_domain_modules`, import-linter contracts in `pyproject.toml:279-405`). No behavioural test opens a workspace next to a real vector store and checks it is unchanged after an upgrade. |
| R6 / Large output is inspected | COVERED | `outcomes.py:95-118` full redacted result goes to the `result` artefact; previews cut at 12 KiB with `outputs_truncated`; `artefacts.py:230-241` `safe_summary` adds `truncated: true` and `artefact_ref`; `routes_runs.py:264` result route needs read scope | `tests/unit/test_workspace_service_outputs.py::test_large_output_is_previewed_with_a_private_reference`, `::test_large_event_payloads_are_bounded`; `tests/unit/test_workspace_artefacts.py::test_safe_summary_truncates_with_a_protected_reference`, `::test_long_text_is_truncated_to_four_kib`, `::test_rows_are_limited_to_one_hundred`; vitest `EvidenceInspector.test.tsx` "bounds previews at 100 rows and 4 KiB and says so", "opens the full chunk through the protected chunk route" |
| R6 / Cleanup is confirmed | COVERED | `src/omrg/core/workspace/cleanup.py:261-311` preview with single-use token, stale and selector checks; `cleanup_files.py:41-140` `O_NOFOLLOW` removal of run files only; `integrations/workspace_sqlite/deletion.py`; `routes_runs.py:424-460` | `tests/unit/test_workspace_cleanup.py::test_apply_removes_exactly_the_previewed_items`, `::test_preview_changes_nothing`, `::test_apply_keeps_pipelines_and_revisions`, `::test_new_matching_run_makes_the_preview_stale`, `::test_token_is_single_use`; `tests/unit/test_workspace_cleanup_safety.py::test_protected_files_inside_and_next_to_workspace_survive` (sources, LanceDB, Chroma, `.py` and `.ipynb` notebooks, experiment `output/`, `.env`), `::test_symlinked_run_directory_is_not_followed`, `::test_failed_record_deletion_removes_no_files`; `tests/unit/test_web_runs_service.py::test_cleanup_removes_exactly_the_previewed_runs`, `::test_cleanup_token_is_single_use_and_bound_to_the_selector`; `tests/unit/test_web_openapi_conformance_runs.py::test_cleanup_responses_conform` |

Note: the table has 19 rows. 5 rows are requirement-text rows. The 14 scenario rows give the counts above.

### Gaps

1. **Index identity not captured for live-library runs (R2, R1 "Old revision").** Action: in `runs_wiring.snapshot_provenance`, add per-collection `store.get_data_version(name)` (or the experiment `BackendIdentity` shape via `compose_experiments.live_backend_identity`) to `resources`; add a test in `tests/unit/test_web_runs.py` that asserts it and that a repeat after a data change records the new value.
2. **No test that a repeat of an older revision runs that older document (R1 "Old revision").** Action: add a service test that saves revisions A then B, calls `submit(A, origin="repeat")`, and asserts `executor.calls[-1].document == A`.
3. **No test of operation versions in provenance (R2).** Action: assert `run["resources"]["operations"]` (`op@version` per node) in `test_submitted_run_executes_the_admitted_snapshot`.
4. **Authoritative refresh after reconnect untested and only at stream end (R4 "Monitoring reconnects").** Action: choose one. (a) Call `getRunRecord` on each `onopen` after a reconnect in `useRunMonitor.ts`, and add a vitest that asserts the second fetch. (b) Keep the end-only refresh, add a vitest for `refreshedStatus`, and change the spec clause to "refresh on stream end or terminal event".
5. **Interrupted run to source-completeness link untested (R5 "Process stops between stores").** Action: add an integration test that marks an ingestion run interrupted after a partial commit, retries it, and asserts the commit adapter's completeness check decides reuse or replacement. Optionally emit `effect_started` before the commit so a crash inside the commit still leaves evidence.
6. **No behavioural "vector store untouched by schema upgrade" test (R6 "Workspace schema changes").** Action: extend `test_upgrade_backs_up_previous_records_before_mutation` with a LanceDB directory next to the workspace and compare its bytes before and after the upgrade (same pattern as `test_workspace_cleanup_safety.py`).

### Spec text issues

1. **R5 "Process stops between stores"** says recovery "SHALL use existing source completeness rules before an explicit retry". The design (D7) and code do not run a recovery step. The retry re-runs the graph and the commit adapter applies the completeness rules during that retry. Suggest wording: "an explicit retry SHALL rely on existing source completeness rules".
2. **R4 "Monitoring reconnects"** says the client refreshes authoritative state on reconnect. Built behaviour refreshes at monitor start and stream end, and the server's `run.end` frame carries the stored status. Either change the code (gap 4a) or the spec (gap 4b).
3. **R3 requirement text** lists "queued/running/terminal states". The built status set adds a nonterminal `cancelling` state (`evidence/run-service.md`; `records.py`). The spec does not forbid it, but it does not name it. Suggest naming `cancelling` in the requirement.
4. **R2 requirement text** says "operation versions". The record stores them under `resources.operations`, not as a separate field. This is acceptable but the spec could name the location.

### Test files cited

Python:

- `tests/unit/test_workspace_repository.py`
- `tests/unit/test_workspace_migrations.py`
- `tests/unit/test_workspace_contracts.py`
- `tests/unit/test_workspace_service.py`
- `tests/unit/test_workspace_service_outputs.py`
- `tests/unit/test_workspace_service_lifecycle.py`
- `tests/unit/test_workspace_artefacts.py`
- `tests/unit/test_workspace_cleanup.py`
- `tests/unit/test_workspace_cleanup_safety.py`
- `tests/unit/test_web_runs.py`
- `tests/unit/test_web_runs_service.py`
- `tests/unit/test_web_runs_stream.py`
- `tests/unit/test_web_graphs.py`
- `tests/unit/test_web_openapi_conformance_runs.py`
- `tests/unit/test_pipeline_runner.py`
- `tests/unit/test_pipeline_runner_scheduler.py`
- `tests/unit/test_ingestion_graph_adapters_commit.py`

Vitest (`web/src`):

- `web/src/canvas/CanvasView.run.test.tsx`
- `web/src/canvas/CanvasView.live.test.tsx`
- `web/src/runs/RunsView.test.tsx`
- `web/src/runs/eventClient.test.ts`
- `web/src/runs/EvidenceInspector.test.tsx`
- `web/src/runs/evidence.test.ts`

## Verification: public-library-api

Change: `add-local-web-pipeline-workspace`. Worktree: `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace` (branch `feat/add-local-web-pipeline-workspace`, uncommitted tree).
Spec: `openspec/changes/add-local-web-pipeline-workspace/specs/public-library-api/spec.md` (one MODIFIED requirement, 7 scenarios).
Paths are relative to the worktree.

Counts: 7 scenarios. COVERED 6, PARTIAL 1, NOT COVERED 0.

| Requirement / Scenario | Status | Code | Tests |
|---|---|---|---|
| Public API / Core operations are importable from the top level | COVERED | `src/omrg/__init__.py:17-51` (`__all__` and PEP 562 lazy exports of `Engine`, `EffectiveSettings`, the four graph types, `__version__`); `src/omrg/engine.py:133` (`async def ingest`), `:159` (`search`), `:198` (`async def answer`), `:298` (`validate_pipeline`), `:318` (`async def run_pipeline`); documented in `docs/guides/library-usage.md:95-165` | `tests/test_engine.py::test_public_api_exports_engine_effective_settings_version`, `tests/unit/test_pipeline_models.py::test_top_level_exports_graph_types`, `tests/test_engine.py::test_engine_public_method_surface_is_exactly_documented`, `tests/unit/test_pipeline_guide.py::test_guides_have_execution_and_cancellation_examples`, `tests/unit/test_pipeline_guide.py::test_python_examples_run_without_web_or_notebook`. Validation and execution accept a plain mapping, so no internal import is needed for them (see Spec text issue 1 for cancellation and templates). |
| Public API / The exported surface is declared | COVERED | `src/omrg/__init__.py:3-6` (docstring: names absent from `__all__` are internal), `:17-25` (`__all__`), `:54-56` (`__dir__`) | `tests/test_engine.py::test_public_api_exports_engine_effective_settings_version` (exact `__all__` list), `tests/unit/test_pipeline_models.py::test_top_level_exports_graph_types` (names in `__all__` and `dir(omrg)`) |
| Public API / Importing the package has no side effects | COVERED | `src/omrg/__init__.py:13-15` (module body imports only `importlib.metadata`; all exports lazy) | `tests/unit/test_pipeline_models.py::test_importing_omrg_does_not_load_pipelines_or_settings` (fresh interpreter: `omrg.config` and `omrg.core.pipelines` not loaded after import; graph-type access does not load `omrg.config` or `networkx`), `tests/test_engine.py::test_importing_omrg_constructs_nothing`, `tests/test_engine.py::test_direct_engine_construction_never_calls_get_settings`. Note: provider, store and network-client absence is shown indirectly (their modules are never imported). |
| Public API / Optional dependencies do not break import | COVERED | `src/omrg/__init__.py` (lazy); `src/omrg/transports/api/__init__.py` (imports nothing); `src/omrg/transports/cli/web.py:25-43` (install hint names the `web` extra) | `tests/unit/test_web_launch.py::test_help_works_when_fastapi_is_not_installed`, `tests/unit/test_web_launch.py::test_cli_import_and_help_do_not_load_fastapi`, `tests/unit/test_web_launch.py::test_web_without_extra_prints_install_instruction`, `tests/unit/test_web_workspace_guide.py::test_missing_extra_message_matches_the_guide`, `tests/test_vectordb_registry_availability.py::test_explicit_chroma_without_extra_fails_startup`, `tests/test_clean_base_tripwire.py::test_default_runtime_loads_no_chroma_modules`. Caveat: the web tests carry module-level `pytest.importorskip("fastapi")`, so they skip where the extra is absent (CI). |
| Public API / Invalid graph is validated through the public API | COVERED | `src/omrg/engine.py:298-316` (`validate_pipeline` raises `PipelineValidationError`), `:318-346` (`run_pipeline` validates before running); issues carry `node_id`, `port`, `edge` | `tests/unit/test_engine_pipelines.py::test_invalid_graph_names_the_node`, `tests/unit/test_engine_pipelines.py::test_invalid_run_input_raises_before_side_effects` (no store reads or writes), `tests/unit/test_engine_pipelines.py::test_validation_has_no_side_effects`, `tests/unit/test_pipeline_preflight.py::test_edge_to_unknown_node_or_port`, `tests/unit/test_pipeline_preflight.py::test_missing_required_input` (asserts `node_id` and `port`). Port diagnostics are asserted at the core validation seam that `Engine.validate_pipeline` calls, not through the Engine itself. |
| Public API / Valid graph is executed through the public API | COVERED | `src/omrg/engine.py:318-346` (`on_event` sink, returns `PipelineResult`); graph determines execution through the runner in `omrg.core.pipelines` | `tests/unit/test_engine_pipelines.py::test_retrieval_graph_runs_on_the_engine_store` (`PipelineResult`, events end with `run_completed`), `tests/unit/test_engine_pipelines.py::test_retrieval_graph_never_builds_answer_models`, `tests/unit/test_pipeline_guide.py::test_python_examples_run_without_web_or_notebook` (blocks `fastapi`, `starlette`, `uvicorn`, `marimo`), `tests/unit/test_pipeline_guide.py::test_example_modules_import_without_web_or_notebook` |
| Public API / Runtime node failure has a stable result | PARTIAL | `src/omrg/core/pipelines/results.py:149-180` (`PipelineResult.status`, `failed_node`, `error`, `completed_effects`, `skipped_nodes`); Engine returns it, `engine.py:318-346` | Runner level: `tests/unit/test_pipeline_runner.py::test_node_failure_skips_dependants_and_names_the_node` (failed node, error, `skipped_nodes`), `tests/unit/test_pipeline_runner_commit_guard.py::test_entered_commit_completes_when_a_sibling_fails` (`completed_effects`), `tests/unit/test_pipeline_runner_units.py::test_failed_file_keeps_sibling_commits`. Engine level: `tests/unit/test_engine_pipelines_isolation.py::test_failed_run_releases_its_lease` (status and `failed_node` only). Shapes unchanged: `tests/unit/test_pipeline_templates.py::test_search_template_matches_engine_search`, `tests/unit/test_pipeline_templates_parity.py::test_answer_template_matches_engine_answer`, `tests/unit/test_pipeline_templates_parity.py::test_ingestion_template_writes_the_same_rows_as_engine_ingest`, `tests/unit/test_retrieval_seams_parity.py::test_search_reproduces_recorded_parity_case`. Missing: no test through `Engine.run_pipeline` asserts `skipped_nodes` and `completed_effects` together on a node failure. |

### Gaps

1. **Runtime node failure has a stable result (PARTIAL).** The three failure fields are proved at the runner level, but the public Engine path asserts only `status` and `failed_node`. Action: add one test in `tests/unit/test_engine_pipelines.py` that runs an ingestion-plus-retrieval graph through `Engine.run_pipeline` with a failing node and asserts `result.status`, `result.failed_node`, `result.error`, `result.skipped_nodes` (dependants) and `result.completed_effects` (an effect that finished first).

### Spec text issues

1. **Documented usage needs internal modules.** `docs/guides/library-usage.md:125-126` tells consumers to import `pipeline_templates` from `omrg.compose_pipelines` and `RunCancellation` from `omrg.core.pipelines`. Neither is in `__all__`, so both are internal under this requirement. Validation and execution work without them, but the documented cancellation path does not. `evidence/engine-wiring.md` open point 2 records the same. Action, choose one: (a) export `RunCancellation` (and optionally `pipeline_templates`) from `omrg.__init__` and add them to the spec's export list and the `__all__` test; or (b) state in the spec that cancellation tokens follow the `CancellationToken` protocol (`omrg.core.pipelines.adapters`) and that a consumer may supply any object with a `cancelled` property, then change the guide to show that.
2. Scenario "Importing the package has no side effects" cannot be proved directly for "no network client constructed". The tests prove it by module absence. This is acceptable; no change needed.
3. The requirement's export list drops the baseline phrase "stable public result/error types" and names concrete graph types. The baseline exported no such types, so nothing was removed.

### Deviations

From `evidence/engine-wiring.md` (open points), status rechecked:

1. `request_limit_issues` imports private `_QUERY_MAX_CHARS`, `_TOP_K_MAX` and `_EXPAND_WINDOW_MAX` from `core/answer/pipeline.py`. Internal only; does not affect the public surface. Still open.
2. `RunCancellation` is not exported at the package top level (see Spec text issue 1). Still open.
3. An `AdmissionSnapshot` passed to `run_pipeline` is not checked against the Engine that admitted it. Callers must pass snapshots from the same Engine. Still open, and not stated in `docs/guides/library-usage.md`.

From `evidence/http-graphs-runs.md` and `evidence/http-documents.md`: the requested public Engine additions now exist (`Engine.describe_operations`, `Engine.resolve_settings`, `Engine.store`, `Engine.profile_resolver`, `run_pipeline(run_id=...)`). `tests/test_engine.py::test_engine_public_method_surface_is_exactly_documented` pins the method set. The two read-only properties are not callables, so that test does not pin them.

### Test files cited

- tests/test_engine.py
- tests/test_vectordb_registry_availability.py
- tests/test_clean_base_tripwire.py (read only; not run)
- tests/unit/test_pipeline_models.py
- tests/unit/test_engine_pipelines.py
- tests/unit/test_engine_pipelines_isolation.py
- tests/unit/test_pipeline_guide.py
- tests/unit/test_pipeline_preflight.py
- tests/unit/test_pipeline_runner.py
- tests/unit/test_pipeline_runner_commit_guard.py
- tests/unit/test_pipeline_runner_units.py
- tests/unit/test_pipeline_templates.py
- tests/unit/test_pipeline_templates_parity.py
- tests/unit/test_retrieval_seams_parity.py
- tests/unit/test_web_launch.py
- tests/unit/test_web_workspace_guide.py

### Focused runs (this verification)

Environment: worktree `.venv`, `PYTHONPATH=src PDF_READER=pypdf -p no:cacheprovider -m "not slow"`.

- `tests/unit/test_pipeline_models.py tests/unit/test_engine_pipelines.py tests/unit/test_web_launch.py` with `tests/test_engine.py::test_public_api_exports_engine_effective_settings_version` and `::test_engine_public_method_surface_is_exactly_documented` (part of a 104-test run that also held the OpenAPI conformance files): **104 passed**.
- Extra check: in a fresh interpreter, `import omrg; omrg.Engine; import omrg.engine` loads none of `fastapi`, `starlette`, `marimo`, `omrg.transports`.

## Verification: transport-separation

Change: `add-local-web-pipeline-workspace`. Worktree: `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace` (branch `feat/add-local-web-pipeline-workspace`, uncommitted tree).
Spec: `openspec/changes/add-local-web-pipeline-workspace/specs/transport-separation/spec.md`.
Paths are relative to the worktree. The REMOVED requirement is excluded from the counts.

Counts: 25 scenarios. COVERED 17, PARTIAL 8, NOT COVERED 0.

| Requirement / Scenario | Status | Code | Tests |
|---|---|---|---|
| Thin transports / CLI split by command group | COVERED | `src/omrg/transports/cli/__init__.py:224-237` (one import per command module, `web` added); `src/omrg/transports/cli/web.py:132-195` (own module, validates options, calls `api.app.create_app`, no domain logic) | `tests/test_cli.py::TestEntryPoint::test_help_flag`, `tests/test_cli.py::TestEntryPoint::test_unknown_subcommand`, `tests/test_cli.py::TestIngestCLI::test_ingest_help`, `tests/test_cli.py::TestSearchCLI::test_search_help`, `tests/test_cli.py::TestDeleteCLI::test_delete_help`, `tests/unit/test_web_launch.py::test_web_bypasses_legacy_installer_and_prints_bootstrap_url_to_stderr` (patches `omrg.transports.cli.web._serve`). Note: module separation is shown by per-module import and patch targets, not by a dedicated structure test. |
| Thin transports / MCP split by tool | COVERED | `src/omrg/transports/mcp/__init__.py:119` (owns `mcp = MCPServer(...)`), `:161-167` (imports every tool module) | `tests/test_mcp_tools.py::test_list_tools_discovers_all_eight`, `tests/test_mcp_tools.py::test_all_handlers_importable_from_package_root` |
| Thin transports / MCP server entry unchanged | PARTIAL | `src/omrg/transports/cli/__init__.py:190-208` (no subcommand calls `mcp_main()`; only `web` skips the legacy installer; nothing else starts web or marimo) | `tests/unit/test_web_launch.py::test_no_argument_start_still_runs_mcp_server`, `tests/test_mcp_tools.py::test_main_calls_mcp_run`. Missing: no assertion that the web server or notebook editor does NOT start on the no-argument path; tool signatures only partly asserted (see next row). |
| Thin transports / Tool set stays complete after a transport split | PARTIAL | `src/omrg/transports/mcp/*.py` (unchanged by this change apart from `codebase.py`, which came from the merged `repair-modular-core-boundaries` change) | `tests/test_mcp_tools.py::test_list_tools_discovers_all_eight` (names only), `tests/test_mcp_tools.py::test_search_documents_annotations_remain_read_only`, `tests/test_answer_transport_mcp.py` (answer annotations), `tests/test_mcp_tools.py::test_search_documents_defaults_follow_policy_resolver`. Missing: parameters, defaults and annotations for the other six tools are not asserted. |
| Thin transports / Handlers stay importable from the package root | PARTIAL | `src/omrg/transports/mcp/__init__.py:161-167` (all eight names bound, including `answer_documents`) | `tests/test_mcp_tools.py::test_all_handlers_importable_from_package_root`. Missing: the test lists seven handlers; `answer_documents` is not checked. |
| Thin transports / Core stays transport-agnostic | PARTIAL | `pyproject.toml` import-linter contracts `core-never-imports-transports` (source `omrg.core`, forbids `omrg.transports`) and `core-free-of-web-notebook-and-sqlite-runtimes` (forbids `fastapi`, `starlette`, `uvicorn`, `marimo`, `sqlite3`); `src/omrg/engine.py:298-346` (graph validation and execution on Engine) | `tests/test_pipeline_import_boundaries.py::test_contract_is_declared_strictly`, `tests/test_pipeline_import_boundaries.py::test_each_forbidden_import_breaks_contract`, `tests/test_pipeline_import_boundaries.py::test_contract_kept_without_violation`, `tests/test_contract_coverage.py::test_package_is_covered_by_a_contract`, `tests/unit/test_engine_pipelines.py::test_retrieval_graph_runs_on_the_engine_store`; CI step `lint-imports`. Missing: no contract forbids the MCP SDK (`mcp`, the source of MCP `Context`) or the CLI framework (`typer`, `click`) in `omrg.core`. A grep found no such import today. |
| Thin transports / Optional HTTP runtime is launched | COVERED | `src/omrg/transports/api/app.py:72-93` (registers every router in `API_ROUTERS`); delegation in `routes_documents.py:96-180` (core `list_documents`, `Engine.search`, `Engine.answer`), `routes_jobs.py:132-171` (`Engine.ingest`, core codebase map with Engine settings and store), `routes_admin.py:83-123,164-223` (core delete and profile functions), `routes_graphs.py:253-272` and `runs_wiring.py:151-170,251-271` (`Engine.validate_pipeline`, `Engine.run_pipeline`) | `tests/unit/test_web_openapi_conformance.py::test_every_runtime_route_is_declared`, `tests/unit/test_web_openapi_conformance.py::test_every_declared_operation_is_implemented`, `tests/unit/test_web_documents.py::test_search_forwards_explicit_controls`, `tests/unit/test_web_documents_jobs.py::test_codebase_map_job_passes_engine_settings_and_store`, `tests/unit/test_web_graphs.py::test_valid_draft_and_admission_checks`, `tests/unit/test_web_runs.py::test_submitted_run_executes_the_admitted_snapshot` |
| OpenAPI runtime / Contract covers the core operations | COVERED | `src/omrg/transports/api/openapi.yaml:386-790` (`ingestPath`, `generateCodebaseMap`, `getJobStatus`, `listCollections`, `listDocuments`, `deleteDocuments`, `searchCollection`, `answerCollection`, `changeCollectionProfile`). All nine v3 reviewed paths and operation ids are unchanged (checked against `git show v3:.../openapi.yaml`). | `tests/unit/test_web_openapi_conformance.py::test_every_declared_operation_is_implemented`, `tests/unit/test_web_openapi_conformance.py::test_response_flows_cover_every_operation`, `tests/unit/test_web_openapi_conformance_documents.py::test_foundation_and_job_responses_conform`, `tests/unit/test_web_openapi_conformance_documents.py::test_document_and_destructive_responses_conform`, `tests/test_openapi_conformance.py::TestAnswerCollectionConformance::test_answer_path_and_operation_are_declared` |
| OpenAPI runtime / Graph and workspace routes are declared | COVERED | `openapi.yaml:106-385` (health, session, credentials, roots, uploads), `:691` (chunk inspection), `:793-1543` (catalogue, pipelines, revisions, validate, runs, result, cancel, retry, events, SSE stream, cleanup), `:1544-1903` (templates, experiments, plugins) | `tests/unit/test_web_openapi_conformance.py::test_every_runtime_route_is_declared`, `tests/unit/test_web_openapi_conformance.py::test_declared_scopes_match_route_dependencies`, `tests/unit/test_web_openapi_conformance_runs.py::test_graph_responses_conform`, `tests/unit/test_web_openapi_conformance_runs.py::test_run_and_event_responses_conform`, `tests/unit/test_web_openapi_conformance_runs.py::test_cleanup_responses_conform`, `tests/unit/test_web_plugins.py::test_plugin_responses_conform`, `tests/unit/test_web_experiments_conformance.py::test_experiment_responses_conform`, `tests/unit/test_web_templates.py::test_templates_match_the_composition_root` |
| OpenAPI runtime / Profile change endpoint carries preview/confirm | COVERED | `src/omrg/transports/api/routes_admin.py:183-223` (no `confirm` gives `status: preview`, contract and confirmation; mutation only after `book.redeem`); `openapi.yaml:742` and `ProfilePreview` at `:3168` | `tests/unit/test_web_destructive.py::test_profile_preview_then_confirm_changes_query_defaults_only`, `tests/unit/test_web_destructive.py::test_profile_confirm_needs_matching_fresh_preview`, `tests/unit/test_web_destructive.py::test_profile_change_on_missing_collection_is_rejected`, `tests/unit/test_web_openapi_conformance.py::test_profile_change_branches_are_mutually_exclusive` |
| OpenAPI runtime / Deletion endpoint requires a confirmed preview | COVERED | `routes_admin.py:128-158` (dry run issues a confirmation; apply redeems it against observed store state first); `openapi.yaml:532` (`deleteDocuments` with 409/428), `DeleteResult` `:3105`, `Confirmation` `:3050` | `tests/unit/test_web_destructive.py::test_delete_without_confirmation_never_mutates`, `tests/unit/test_web_destructive.py::test_preview_reports_scope_and_mutates_nothing`, `tests/unit/test_web_destructive.py::test_confirmed_preview_deletes_exactly_the_selection`, `tests/unit/test_web_destructive.py::test_store_change_after_preview_makes_confirmation_stale`, `tests/unit/test_web_openapi_conformance.py::test_destructive_operations_are_session_only_with_confirmation` |
| OpenAPI runtime / Explicit success and error schemas | COVERED | `src/omrg/transports/api/errors.py:30-83` (envelope; generic 500 without detail); `openapi.yaml:2088` (`Error`: `status`, `message`, `error_type`, optional `issues`) and shared responses | `tests/unit/test_web_openapi_conformance.py::test_access_and_failure_statuses_are_declared`, all `ContractChecker` flow tests (fail on an undeclared status or media type), `tests/unit/test_web_security.py::test_internal_errors_do_not_leak_details`, `tests/unit/test_web_security.py::test_validation_errors_use_envelope_without_echoing_input`, `tests/unit/test_web_documents_jobs.py::test_failed_ingestion_reports_redacted_error`, `tests/unit/test_web_documents.py::test_search_profile_error_is_validation_and_failure_is_not_leaked` |
| OpenAPI runtime / Authentication schemes declared | PARTIAL | `openapi.yaml:1904` (`sessionCookie`, `bearerToken`), `:79` (`x-omrg-scope-catalogue`), per-operation `security` and `x-omrg-scopes`; `security.py:325` (`require_scope`); `middleware.py:46-60` (Host guard on every path) | `tests/unit/test_web_openapi_conformance.py::test_scope_catalogue_matches_the_access_policy`, `tests/unit/test_web_openapi_conformance.py::test_declared_scopes_match_route_dependencies`, `tests/unit/test_web_openapi_conformance.py::test_public_operations_are_only_health_and_bootstrap`, `tests/unit/test_web_security.py::test_every_protected_route_declares_a_scope`, `tests/unit/test_web_security.py::test_bootstrap_requires_matching_origin`. Missing: the unauthenticated static frontend (`static.py`, served for every non-`/v1` path) is not identified in the contract, and `src/omrg/transports/api/README.md:71` says health and session are the only public operations. |
| OpenAPI runtime / Long-running operations declared | COVERED | `routes_jobs.py:132,146` (202 jobs), `routes_runs.py:181,217` (202 runs), `:206,276,364` (cancel, events, SSE); `openapi.yaml` `Job` `:3233`, `RunEnvelope` `:3733` | `tests/unit/test_web_openapi_conformance.py::test_long_running_operations_declare_202_with_an_identifier` (4 cases), `tests/unit/test_web_openapi_conformance.py::test_status_event_and_cancel_routes_are_protected`, `tests/unit/test_web_openapi_conformance_runs.py::test_run_and_event_responses_conform`, `tests/unit/test_web_openapi_conformance_runs.py::test_unfinished_work_reads_interrupted_after_restart`, `tests/unit/test_web_documents_jobs.py::test_ingestion_inside_root_runs_as_polled_job` |
| OpenAPI runtime / Runtime routes conform | COVERED | `src/omrg/transports/api/routes*.py`, `openapi.yaml` | `tests/unit/test_web_openapi_conformance.py::test_every_runtime_route_is_declared`, `::test_every_declared_operation_is_implemented`, `::test_operation_ids_agree_where_the_runtime_names_them`, `::test_request_bodies_match_runtime_models`, `::test_parameters_match_runtime`, `::test_unknown_api_path_never_serves_html`, plus the seven family flow tests |
| OpenAPI runtime / Contract validated in CI | PARTIAL | `.github/workflows/ci.yml:75-77` and `scripts/local_ci.sh:33-35` run `openapi-spec-validator` on `openapi.yaml` | `tests/test_openapi_conformance.py` (runs in the CI fast suite). Missing: CI installs with `uv sync --frozen` and no `--extra web`; `uv export --frozen` confirms FastAPI is absent from the default set, so every `tests/unit/test_web_*.py` module (all have module-level `pytest.importorskip("fastapi")`), including the runtime conformance tests, is skipped in CI. `ci.yml` never mentions `web`. |
| OpenAPI runtime / Search request schema covers every optional search parameter | COVERED | `openapi.yaml:2382` (`SearchRequest`: `diagnostics`, `expand_window`, `hybrid`, `metadata_filter`, `rerank`, `similarity_threshold`, `top_k`; profile-resolved ones have no default); `routes_documents.py:31` (`SearchBody`) | `tests/test_openapi_conformance.py::TestSearchRequestConformance::test_every_search_parameter_is_declared`, `tests/test_openapi_conformance.py::TestSearchRequestDefaults::test_rule3a_profile_resolved_params_have_no_default`, `::test_rule3a_descriptions_mention_profile_resolution`, `tests/unit/test_web_openapi_conformance.py::test_request_bodies_match_runtime_models`, `tests/unit/test_web_documents.py::test_search_passes_profile_resolved_controls_as_none` |
| OpenAPI runtime / Document listing schema covers every listing result key | COVERED | `openapi.yaml:2942` (`DocumentInfo`: `source_id` nullable, `orphaned` `boolean|null`) | `tests/test_openapi_conformance.py::TestDocumentInfoConformance::test_every_listing_key_is_declared`, `tests/unit/test_web_documents.py::test_sources_list_keeps_machine_local_orphan_semantics` (asserts true, false and null against the schema) |
| OpenAPI runtime / Search result schema covers every default result key | COVERED | `openapi.yaml:2444` (`SearchResult`) | `tests/test_openapi_conformance.py::TestSearchResultConformance::test_every_default_result_key_is_declared_and_required`, `tests/unit/test_web_documents.py::test_search_result_shape_conforms_with_lineage_and_score_kind` |
| OpenAPI runtime / Search result schema covers diagnostic keys as optional | COVERED | `openapi.yaml:2444` | `tests/test_openapi_conformance.py::TestSearchResultConformance::test_every_diagnostic_key_is_declared_and_not_required` |
| OpenAPI runtime / A parameter default disagrees with the implementation | COVERED | conformance helpers in `tests/unit/test_web_openapi_conformance.py` and `tests/test_openapi_conformance.py` | `tests/test_openapi_conformance.py::TestSearchRequestDefaults::test_rule2_concrete_default_matches` (names the parameter), `::test_rule1_required_parameter_has_no_default`, `::test_rule4_explicit_null_default_rejected`, `tests/unit/test_web_openapi_conformance.py::test_request_bodies_match_runtime_models`, `::test_parameters_match_runtime` (mutations M4 and M10 in `evidence/openapi.md` fail naming the field) |
| OpenAPI runtime / An implemented field is missing from the contract | COVERED | as above | `tests/test_openapi_conformance.py::TestFailureMessagesAreActionable::test_missing_search_parameter_message_names_field_and_schema`, `::test_missing_listing_key_message_names_field_and_schema`, `::test_missing_result_key_message_names_field_and_schema`, `tests/unit/test_web_openapi_conformance.py::test_request_bodies_match_runtime_models` |
| OpenAPI runtime / A new field is added to an implemented surface | COVERED | request fields derived from runtime models; response schemas closed with `additionalProperties: false` | `tests/unit/test_web_openapi_conformance.py::test_request_bodies_match_runtime_models` (mutation M5), flow tests through `ContractChecker` (mutation M11), `tests/test_openapi_conformance.py` derivation tests. No field allow-list is consulted (see Spec text issues for the empty `PENDING_CONTRACT_KEYS`). |
| Web packaging / Base installation has no HTTP extra | COVERED | `pyproject.toml` extra `web = ["fastapi>=0.143.0", "uvicorn>=0.52.0"]`; `src/omrg/transports/api/__init__.py` imports nothing; `cli/web.py:25-43` (`_require_web_extra`, install hint names the extra) | `tests/unit/test_web_launch.py::test_cli_import_and_help_do_not_load_fastapi`, `::test_help_works_when_fastapi_is_not_installed`, `::test_web_without_extra_prints_install_instruction`. Caveat: these run only where FastAPI is installed (module-level `importorskip`), so they skip in CI. |
| Web packaging / Release assets are absent | PARTIAL | `scripts/check_web_wheel.py:22-55` (fails when `static/index.html` or a referenced asset is missing); `pyproject.toml` hatch `artifacts = ["src/omrg/transports/api/static/**"]`; `lifespan.py:44` (`PACKAGED_STATIC_DIR` from `__file__`) | None automated. Manual both-ways check recorded in `evidence/frontend-scaffold.md:152`. Missing: no test for the checker, and neither `.github/workflows/release.yml`, `ci.yml`, `local_ci.sh` nor `[tool.semantic_release] build_command` runs it, so release preparation is not gated. |

### Gaps

1. **MCP server entry unchanged (PARTIAL).** The no-argument test does not prove that web or the notebook editor stay off. Action: in `tests/unit/test_web_launch.py::test_no_argument_start_still_runs_mcp_server`, patch `omrg.transports.cli.web._serve` and assert it is not called. Also assert `fastapi`, `uvicorn.server` and `marimo` are absent from `sys.modules` in a subprocess run of `omrg` with `mcp.run` patched.
2. **Tool set complete (PARTIAL).** Only names, plus search and answer annotations, are pinned. Action: add one test that lists tools and compares each tool's `inputSchema` (names, required, defaults) and `annotations` to a committed snapshot taken from `v3`.
3. **Handlers importable (PARTIAL).** `answer_documents` is missing from the handler list. Action: add `"answer_documents"` to `handler_names` in `tests/test_mcp_tools.py::test_all_handlers_importable_from_package_root`.
4. **Core transport-agnostic (PARTIAL).** The MCP SDK and the CLI framework are not forbidden in core. Action: add `mcp`, `typer` and `click` to `forbidden_modules` of `core-free-of-web-notebook-and-sqlite-runtimes` in `pyproject.toml`, and extend `tests/test_pipeline_import_boundaries.py` to inject one of them.
5. **Authentication schemes declared (PARTIAL).** The public static frontend is not identified in the contract. Action, choose one: (a) add an `x-omrg-unauthenticated-static` note to `openapi.yaml` `info` stating that non-`/v1` paths serve the built frontend without credentials, under the Host guard, and never answer `/v1` with HTML; or (b) add the statement to the contract description. In both cases correct `README.md:71` and add a test that a wrong Host on `/` gets 400.
6. **Contract validated in CI (PARTIAL).** Runtime conformance tests skip in CI because the `web` extra is not installed. Action, choose one: (a) change the CI `test` job to `uv sync --frozen --extra web`; or (b) add a `web-extra` CI job that runs `uv sync --frozen --extra web` and `pytest tests/unit/test_web_*.py tests/test_openapi_conformance.py -m "not slow"`, and add `web` to the floors matrix. Then re-measure the `tests/test_clean_base_tripwire.py` counts in the CI environment (see Related risk).
7. **Release assets absent (PARTIAL).** The wheel checker exists but nothing runs it or tests it. Action: (a) add a unit test that builds two small zip files (with and without `static/index.html` and a referenced asset) and asserts `check_wheel` results; (b) wire `uv build && python scripts/check_web_wheel.py dist/*.whl` into the release path (for example `build_command` in `[tool.semantic_release]` after an `npm ci && npm run build` step, or a pre-publish job in `release.yml`).

**Related risk (not a scenario, not run here).** `tests/test_clean_base_tripwire.py` pins `_BASE_EXECUTED = 4689` and `_BASE_SKIPPED = 133`, re-baselined in a venv that has FastAPI. In the CI base environment the 24 `tests/unit/test_web_*.py` modules skip, so the pinned counts will probably drift and that test will probably fail in CI. Action: run the base suite in a `uv sync --frozen` venv without the web extra, or follow Gap 6 option (a) so CI and the baseline share one environment.

### Removed requirement check

Requirement removed: "Versioned OpenAPI 3.1 contract for the future REST transport" (contract-only, "folder SHALL contain NO runtime HTTP code").

- Gone from the contract: `openapi.yaml` is version `2.0.0`, server `http://127.0.0.1:{port}/v1`, the JWT `bearerAuth` scheme is removed, and no "no runtime" or "future" wording remains (grep).
- Gone from `src/omrg/transports/api/README.md` and `src/omrg/transports/api/__init__.py` (now "Optional local HTTP transport (`omrg web`)").
- The runtime now exists (`transports/api/*.py`), as the replacement requirement needs.
- **Stale wording still present:**
  1. `src/omrg/transports/__init__.py:5` says "`api/` (OpenAPI 3.1 contract for the future REST transport)". Action: change it to "`api/` (optional local HTTP runtime for `omrg web`, with its OpenAPI 3.1 contract)".
  2. `AGENTS.md:46` (and `CLAUDE.md`, a symlink to it) says "`transports/api/` (OpenAPI contract only)". Action: update Architecture Invariant 3 to name the optional HTTP runtime.
- The baseline `openspec/specs/transport-separation/spec.md:176` still holds the old requirement. This is expected until archive applies the REMOVED delta.

### Spec text issues

1. Scenario "Explicit success and error schemas" says errors keep the "existing status/message envelope". The contract adds `error_type` (already present in v3) and optional `issues`. This matches the intent; no change needed.
2. Scenario "A new field is added to an implemented surface" forbids a maintained allow-list. `tests/unit/test_web_documents_support.py:49` keeps `PENDING_CONTRACT_KEYS` with empty entries, used by `test_web_destructive.py:96,285`. It is empty, so the scenario holds, but it is an allow-list mechanism. Action: delete it and the two `<=` assertions, since `assert_conforms` already fails on undeclared keys.
3. Requirement text "No transport file SHALL contain ... domain mutation policy" is ambiguous for the preview/confirm token book (`transports/api/confirmations.py`) and run admission wiring (`transports/api/runs_wiring.py`, 405 lines). Both are transport-side composition and access control, not RAG or scheduling logic. Action: state in the spec or design that confirmation tokens and run-service composition are transport concerns.
4. Scenario "Authentication schemes declared" says "bootstrap/static operation". The design serves static assets outside `/v1` and outside the contract. Either the scenario or the contract needs to change (Gap 5).

### Deviations

From `evidence/openapi.md` (task 6.7):

1. Framework request validation stays 400 `validation`; only graph and cleanup-selector validation give 422 with `issues`. Both are declared. Still true.
2. Path parameter `{jobId}` kept in the contract while the runtime uses `job_id`. The parameter test compares counts, not names. Still true.
3. Foundation routes in `routes.py:62-203` have no `operation_id`; the id test checks only routes that set one. Still open.
4. Vacuous `test_every_protected_route_declares_a_scope`: **fixed** (`tests/unit/test_web_security.py:287-302` now uses `iter_api_routes` and asserts `checked > 0`).
5. `plugins` scope without routes: **resolved** (plugin operations are declared and covered by `test_plugin_responses_conform`).
6. Five em dashes remain in kept search and answer descriptions in `openapi.yaml` (count confirmed: 5).
7. 501 from `getChunk` and 400 for credentials in run inputs are declared but not exercised.

From `evidence/http-foundation.md`, `evidence/http-documents.md`, `evidence/http-graphs-runs.md` (status rechecked):

- `--host` option added to `omrg web` beyond the task list (loopback only). Still true.
- Default workspace `~/.omrg/workspace`. Still true.
- Engine store and resolver fallbacks to private attributes: **resolved** (`engine_access.py` now reads public `Engine.store` and `Engine.profile_resolver`).
- Destructive routes on `run` scope: **resolved** (`routes_admin.py:36` uses session-only `manage`).
- `JobBook` placeholder: **resolved** (jobs run on the shared run service; no `JobBook` in `src/`).
- `Engine.run_pipeline` without `run_id` and no public catalogue accessor: **resolved** (`engine.py:318-352`).
- Check-then-act window on destructive actions (a write by another process between observation and the writer) remains, as recorded.
- Jobs have no retry route; `retryRun` refuses job runs (404). Still true.

### Test files cited

- tests/test_cli.py
- tests/test_mcp_tools.py
- tests/test_answer_transport_mcp.py
- tests/test_pipeline_import_boundaries.py
- tests/test_contract_coverage.py
- tests/test_openapi_conformance.py
- tests/test_clean_base_tripwire.py (read only, risk note)
- tests/unit/test_engine_pipelines.py
- tests/unit/test_web_launch.py
- tests/unit/test_web_security.py
- tests/unit/test_web_openapi_conformance.py
- tests/unit/test_web_openapi_conformance_documents.py
- tests/unit/test_web_openapi_conformance_runs.py
- tests/unit/test_web_openapi_conformance_support.py
- tests/unit/test_web_documents.py
- tests/unit/test_web_documents_jobs.py
- tests/unit/test_web_documents_support.py
- tests/unit/test_web_destructive.py
- tests/unit/test_web_graphs.py
- tests/unit/test_web_runs.py
- tests/unit/test_web_plugins.py
- tests/unit/test_web_experiments_conformance.py
- tests/unit/test_web_templates.py

### Focused runs (this verification)

Environment: worktree `.venv`, `PYTHONPATH=src PDF_READER=pypdf -p no:cacheprovider -m "not slow"`.

1. `tests/unit/test_web_openapi_conformance.py tests/test_openapi_conformance.py tests/unit/test_web_launch.py tests/unit/test_pipeline_models.py tests/unit/test_engine_pipelines.py` plus four named node ids from `tests/test_mcp_tools.py` and `tests/test_engine.py`: **104 passed**.
2. `tests/unit/test_web_openapi_conformance_documents.py tests/unit/test_web_openapi_conformance_runs.py tests/unit/test_web_destructive.py`: **40 passed**.

## Design coherence: `add-local-web-pipeline-workspace`

Source: `openspec/changes/add-local-web-pipeline-workspace/design.md` (D1 to D12, Qualification Gates), `tasks.md`, and every file in `evidence/`.
Paths are relative to the worktree `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace`. Read-only check; no tests beyond the focused runs in `pipeline-run-records.md`.

Result: **10 decisions followed, 2 followed with recorded deviations (D5 detail, D11 packaging mechanism), 0 not followed.** D12 is deferred and the deferral is clean.

### Decision table

| Decision | Followed? | Evidence |
|---|---|---|
| D1 Optional web transport (FastAPI, React Flow, SQLite; algorithms and runner under `core/`) | Yes | `pyproject.toml:135-137` `web` extra (`fastapi`, `uvicorn`); `web/package.json:19` `@xyflow/react`; `src/omrg/integrations/workspace_sqlite/`; runner in `src/omrg/core/pipelines/runner.py`, `execution.py`, `scheduler.py`. |
| D2 Versioned graph documents and typed catalogue; layout separate | Yes | `src/omrg/core/pipelines/models.py`, `catalogue.py`, `ports.py`; layout in `pipelines.layout_json` only (`integrations/workspace_sqlite/repository.py:148`); domain adapters register through `graph_adapters_catalogue.py` modules. Recorded detail: new operation ids `retrieve.prepare_query`, `select.threshold` and score kind `sparse_rank_v1` (`retrieval-adapters.md`). |
| D3 Validate before admission; bounded finite scheduling | Yes, with one stricter rule | `core/pipelines/validation.py`, `topology.py:114` (NetworkX), `scheduler.py` (dependency counts, bound, leases), `runner.py:56` `max_concurrency = 2`. Lead decision: a failed unit also skips a not-yet-started `SOURCE_COMMIT` on an independent branch (`runner.md`). |
| D4 Share algorithms; adapters pass store/settings; guard leaf list | Yes | Adapters in `core/retrieval/graph_adapters*.py`, `core/ingestion/graph_adapters*.py`, `core/answer/graph_adapters.py`; all listed in `_GUARDED_LEAVES` (`tests/test_no_global_settings_reads.py:212-223`); parity tests `tests/unit/test_*_graph_adapters_parity.py`; `pipeline_templates.py` canonical graphs. |
| D5 Freeze configuration, preserve index safety, shaping fingerprint | Yes, with recorded detail | `core/pipelines/snapshot.py:50-120` (`CollectionSnapshot`, `EffectiveControl` with node/graph/profile source); `core/ingestion/graph_fingerprint.py`, `source_state.py` `build_index_identity(..., graph_shape=None)`; `tests/unit/test_ingestion_graph_fingerprint_reuse.py`. Detail: code/config sources keep content-type split inside `read.document`, so `prepare.chunk` levers do not reach them; an explicit lever equal to default reprocesses once (`ingestion-adapters.md`). |
| D6 Engine owns resources; jobs borrow; close during run refused | Yes | `engine.py:298,318` `validate_pipeline`, `run_pipeline`; `engine.py:62` close refused during active run, test `tests/unit/test_engine_pipelines_isolation.py::test_close_during_a_run_fails_and_keeps_the_engine_usable`; lazy exports in `src/omrg/__init__.py:17-32`; `Engine.describe_operations`, `Engine.store`, `Engine.profile_resolver` added (`engine.py:280,286,348`). |
| D7 One consumer, 16 waiting jobs, SQLite app store, commit-then-notify, SSE with replay, bounded previews | Yes | `core/workspace/jobs.py:24`, `service.py:364-392`, `events.py:33-62`, `integrations/workspace_sqlite/repository.py:321`, `schema.py:161-223` (backup, one-transaction migration), `core/workspace/artefacts.py:26-29`, `routes_runs.py:304-364`; `transports/cli/web.py:76` `workers=1`; `lifespan.py:145` `WorkspaceLock`. Additions: nonterminal `cancelling` status; artefact preview cap 12 KiB for outputs (`outcomes.py:27`) alongside the 100-row and 4 KiB limits. |
| D8 Protected local HTTP and explicit grants | Yes, with one addition | `transports/api/security.py` (session cookie, bearer scopes, `SESSION_SCOPES` with `manage`), `middleware.py` (Host/Origin), `grants.py`, `uploads.py:29-30` (50 MiB), `confirmations.py` (preview-bound tokens with store validity). Addition: `--host` option (loopback only) and default workspace `~/.omrg/workspace` (`http-foundation.md`). |
| D9 Compact application and evidence-first canvas | Yes | Navigation Canvas, Library, Search, Ask, Runs, Experiments, Settings (`deferred-optimisation.md`, `web/src/App.tsx`); vitest files under `web/src/canvas`, `web/src/runs`, `web/src/views`; `browser.md` lists five open UI findings (form field names, small nodes at fit-view, 541 kB bundle, narrow nav scroll, validation text after reload). |
| D10 Optional marimo manifest plugin, independent updates | Yes, with recorded limits | `plugins/marimo/manifest.json`, `README.md`, `starter_notebook.py` outside the wheel; `core/plugins/`; import contract `plugin-host-starts-no-processes`; `lifespan.py:321` `stop_all` at shutdown; qualified marimo 0.25.1, range `>=0.25.1,<0.26.0` (`marimo-qualification.md`). Limits: a parent `pyproject.toml` with `auto_instantiate = true` overrides the launch config; notebook header `on_cell_change = "autorun"` is not blocked. |
| D11 Package once; optional deps optional | Partly: mechanism differs | Design says "force-include built assets in Hatchling wheel". Code uses Hatch `artifacts = ["src/omrg/transports/api/static/**"]` (`pyproject.toml:150-153`) plus `scripts/check_web_wheel.py` to fail release preparation when assets are missing. Intent (wheel carries assets, release check fails without them) is met; the named mechanism is not. `web-dependency.md` records torch-free and lazy import checks PASS. |
| D12 Later device-aware optimisation (deferred) | Yes (deferred cleanly) | `evidence/deferred-optimisation.md`: 0 matches for optimiser terms in changed `src/`, `web/src/`, `plugins/`; no dependency, route, view or button; D12, `proposal.md` and ADR-075 keep Quick/Standard/Full. Result PASS; the evidence says to re-run the search in task 9.2. |
| Qualification Gates | Partly met | Gate 1 (repair regressions): `readiness.md` PASS. Gate 2 (marimo/uv): `marimo-qualification.md` PASS for 0.25.1. Gate 3 (model/backend concurrency): serial leases are the default (`runner.md` "Leases come from descriptor capabilities"); no evidence of a concurrency qualification that would relax them, so serial access stays, as the gate allows. Gate 4 (floors, packaged assets, torch-free): `web-dependency.md` PASS for floors and torch-free; wheel asset check in task 6.8 evidence; full gate set belongs to unchecked task 9.2. Gate 5 (baseline conflicts, lineage rejection kept): not separately evidenced; part of unchecked task 9.3. ADR-075 is still **Proposed** (`docs/adr/075-...md:4`), as task 9.3 requires before acceptance. |

### Deviations recorded in evidence

Each item names the evidence file. "Resolved" means a later lead follow-up or code check in this worktree shows the fix.

1. Lease timing: experiment admitter releases its lease at once; the executor takes a new lease at start, because a cancelled queued job has no release callback. `experiment-transport.md`
2. Test-first not strict for shutdown-order and notebook tests; mutation checks used instead. `experiment-transport.md`
3. Test-first not strict for `manifest.py`; mutation checks used instead. `plugins.md`
4. Stricter rule: experiment-bound credentials are refused on all live-library runs, read-only ones too (spec requires refusal only for mutation). `experiment-contexts.md`, `experiment-transport.md`
5. Experiment context registry lives in memory per launch; approvals do not survive restart. `experiment-contexts.md`, `experiment-transport.md`
6. Chroma as a declared experiment factor is composed but never built in a test. `experiment-contexts.md`
7. `GET /v1/pipeline-operations` and `POST /v1/pipelines/validate` stay open to bound bearers; unbound bearers can read experiment runs. `experiment-transport.md`
8. Commit guard: a failed unit skips not-yet-started source commits on independent branches (lead decision on D3). `runner.md`
9. Code/config sources split inside `read.document`; `prepare.chunk` levers do not reach them. `ingestion-adapters.md`
10. Lever equal to default counts in the fingerprint and reprocesses once. `ingestion-adapters.md`
11. New score kind `sparse_rank_v1`; new op ids `retrieve.prepare_query`, `select.threshold` (guide's `select.dense_threshold` not registered). `retrieval-adapters.md`
12. RRF accepts at most two rankings. `retrieval-adapters.md`
13. Templates are Python builders in `src/omrg/pipeline_templates.py`, not JSON files; `compose_pipelines.pipeline_templates` uses private `engine._graph_host` (still present at `compose_pipelines.py:212`). `templates-and-guides.md`
14. `--host` option added and default workspace `~/.omrg/workspace` chosen. `http-foundation.md`
15. Upload extensions come from `WebConfig.upload_extensions`, not profile-resolved sets. `http-foundation.md`
16. Request validation stays 400; only core graph and cleanup-selector validation give 422. `openapi.md`
17. Path name `{jobId}` kept in the contract while runtime uses `job_id`. `openapi.md`
18. Foundation routes have no runtime `operation_id`; runtime serves no generated OpenAPI document. `openapi.md`
19. Vacuous scope test `test_every_protected_route_declares_a_scope` (checks no route under FastAPI 0.143). `openapi.md`
20. Five em dashes kept in reviewed OpenAPI descriptions. `openapi.md`
21. 501 from `getChunk` and 400 for credentials in run inputs declared but not exercised in conformance tests. `openapi.md`
22. Check-then-act window between validity-token read and destructive write. `http-documents.md`
23. Legacy rows without `chunk_id` cannot be inspected. `http-documents.md`
24. Job error text redaction does not cover configured provider secrets. `http-documents.md`
25. Destructive routes used `run` scope; recommendation for a `manage` scope. Resolved: `security.py:47` and `routes_admin.py:36` use `manage`. `http-documents.md`
26. `JobBook` in-memory job placeholder. Resolved: jobs moved to the shared run service (`test_web_runs_service.py::test_jobs_and_graph_runs_share_one_bounded_queue`). `http-documents.md`, `http-foundation.md`
27. No public Engine store/resolver/catalogue accessor. Resolved: `engine.py:280,286,348`. `http-documents.md`, `http-graphs-runs.md`
28. `Engine.run_pipeline` had no `run_id`. Resolved in lead follow-up. `http-graphs-runs.md`
29. Synchronous admission on the event loop; catalogue warmed in a worker thread first. `http-graphs-runs.md`
30. SIGINT re-raised by Uvicorn after graceful shutdown. `http-graphs-runs.md`
31. Jobs have no retry route. `http-graphs-runs.md`
32. Two failing tests (`test_web_security.py::test_bearer_scope_is_enforced`, `test_workspace_cleanup_guide.py::test_layout_names_match_the_web_wiring`). Resolved in lead follow-up. `http-graphs-runs.md`
33. Retrieval outputs stored as text; restored pipeline showed empty draft. Both resolved in lead follow-up. `canvas-runs.md`
34. Node times shown only from the stored result while a node runs. `canvas-runs.md`
35. Browser walk at 1280/768/390 px not run in `canvas-runs.md`; later covered in `browser.md`. `canvas-runs.md`
36. Five open browser findings (form field names, small nodes, bundle size 541 kB, narrow nav scroll, validation text after reload). `browser.md`
37. Runs view has no deep link to one run; marimo sign-in page format; `window.open` may be blocked. `experiments-view.md`
38. `web/src/lib/views.ts` Experiments summary text outdated. `experiments-view.md`
39. Marimo: parent `pyproject.toml` can re-enable startup execution; notebook header `autorun` not blocked; editor exit not noticed. `marimo-qualification.md`, `experiment-transport.md`
40. Version range narrowed to `>=0.25.1,<0.26.0` (0.25.0 probe only). `marimo-qualification.md`
41. `register_plugin` resets `detail`; `checked_at` set at registration. `plugins.md`
42. Processes leaving the group with `setsid` are not tracked; port race between check and bind. `plugins.md`
43. `request_limit_issues` imports private answer limits; `run_cancellation` not exported; admitted snapshot not bound to its Engine. `engine-wiring.md`
44. Graph answers do not apply `answer()` request limits at adapter level (applied at admission instead via `compose_pipelines.request_limit_issues`). `answer-seams.md`
45. Removal uses `dir_fd` (POSIX only); orphan artefact directories are kept; layout names duplicated (later resolved through `WorkspaceLayout`). `workspace-cleanup.md`
46. Revisions are kept by cleanup (spec does not require removal). `workspace-cleanup.md`
47. End-to-end: experiment identity shows `llamacpp` with an empty model (launcher artefact); comparison used polling, not SSE; Chroma not tried; real marimo not started in that run. `end-to-end.md`
48. Starter notebook is 529 lines (outside the `src/omrg` ceiling). `experiment-transport.md`
49. Packaging uses Hatch `artifacts` plus `scripts/check_web_wheel.py` instead of the `force-include` named in D11. `frontend-scaffold.md`

Total: **49 recorded deviations or open points** (7 shown as resolved in this worktree).

### Unchecked tasks

From `tasks.md` (54 of 56 checked):

- [ ] **9.2** Run approved fast/coverage, frontend, OpenAPI, import, floor, wheel, and torch-free gates; record exact PASS/FAIL/NOT RUN results.
- [ ] **9.3** Verify the implementation against all delta scenarios; validate OpenSpec strictly, update Graphify, and accept the ADR only after evidence passes.

Note: `tasks.md` line 3 still says "Every checkbox ... remains unchecked until approval, implementation, and verification". That planning sentence is stale now that 54 tasks are checked.

