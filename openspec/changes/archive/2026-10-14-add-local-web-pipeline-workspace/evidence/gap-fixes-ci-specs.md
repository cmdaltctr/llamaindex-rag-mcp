# Gap fixes: CI, wheel check, boundaries, spec text and test-only gaps

Date: 2026-10-13. Source: `evidence/verification.md` sections A (items 9, 10, 11), B, "Spec text that does not match the deliberate design" and "Other findings".
Worktree: `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace`, branch `feat/add-local-web-pipeline-workspace`, base `879145a`, not committed.

## 1. Item A9: CI runs the web tests

Changes in `.github/workflows/ci.yml`:

- `test` job (ubuntu and macOS): `uv sync --frozen --extra web`. The web route tests and the OpenAPI runtime conformance tests now run in CI.
- `codecov` job: adds `--extra web`, so the web transport counts towards coverage.
- `floors` matrix: adds a `web` entry. The matrix comment says it covers every non-torch extra.
- New `frontend` job: `actions/checkout@9c091bb` (v7.0.0, as in the file), `actions/setup-node@820762786026740c76f36085b0efc47a31fe5020` (v7.0.0, released 2026-07-14), Node `22` (satisfies `engines: >=22.12.0`), npm cache on `web/package-lock.json`. Steps: `npm ci`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`.

Tripwire (`tests/test_clean_base_tripwire.py`): new environment adjustment after the tokenizer one.

```python
_WEB_EXTRA_CASES = -1  # PLACEHOLDER: cases that run only with fastapi
_WEB_SKIP_DELTA = -1  # PLACEHOLDER: skips added when fastapi is absent
if find_spec("fastapi") is None:
    _BASE_EXECUTED -= _WEB_EXTRA_CASES
    _BASE_SKIPPED += _WEB_SKIP_DELTA
```

`_BASE_EXECUTED`, `_BASE_SKIPPED` and `_BASE_DESELECTED` are unchanged. The `-1` sentinels make the manifest fail if nobody sets them.

Measurement script: `scratchpad/measure_web_cases.sh` (session scratchpad). It hides `fastapi` with a shim package on `PYTHONPATH` that raises `ModuleNotFoundError` (the same error as an absent package, so `pytest.importorskip` skips). `uvicorn` stays visible, because the base install already has it through `mcp`. Default mode runs only the files whose collected-case count changes. `--full` runs the whole fast suite twice.

**Blocker found (not fixed, not my files).** Two support modules fail collection without FastAPI, because pytest collects them (`test_*.py` names) and they import FastAPI with no `importorskip`:

- `tests/unit/test_web_runs_support.py:18`
- `tests/unit/test_web_experiments_support.py:18`

The base floors job (no `web` extra) fails at collection today, before any count is compared. The script stops and names these files.

What to do:

1. Add `pytest.importorskip("fastapi")` before the FastAPI import in both modules (the owner of `tests/unit/test_web_*` does this).
2. Run `scratchpad/measure_web_cases.sh` and paste the two printed values into the tripwire.
3. Optional: run `scratchpad/measure_web_cases.sh --full` once to confirm against the full suite.

Trial result (both support modules ignored, current tree): `_WEB_EXTRA_CASES = 330`, `_WEB_SKIP_DELTA = 24` (one skip per web module). After step 1, expect the skip delta to be 26 (two more modules skip at import). Other agents add web tests now, so measure at the end.

## 2. Item A10: wheel check wired

- `.github/workflows/release.yml`: new steps before `Semantic Release` (so before tagging and publishing): set up Node (pinned SHA as above), `npm ci && npm run build` in `web/`, set up uv (pinned SHA from `ci.yml`), `uv build --wheel --out-dir wheel-check`, `python3 scripts/check_web_wheel.py wheel-check/*.whl`, then delete `wheel-check/`.
  - Decision: the wheel goes to `wheel-check/`, not `dist/`. Semantic Release runs with `build: "false"` and its publish uploads `dist/*`, so building into `dist/` would add a wheel to the GitHub Release. If the lead wants the checked wheel published, change `--out-dir wheel-check` to `--out-dir dist` and remove the `rm -rf`.
  - The existing release steps use unpinned tags (`actions/checkout@v5`). They are unchanged.
- `scripts/local_ci.sh`: new step "frontend gates and web wheel assets". It runs the same npm gates as the CI `frontend` job, builds a wheel into `mktemp -d`, and runs the check. Without `npm` it prints `SKIPPED: npm not found. Install Node 22 or later ...` and continues.
- New test `tests/unit/test_check_web_wheel.py` (6 tests): complete wheel passes; missing `index.html` fails with the `npm run build` instruction; a missing referenced asset fails and names it; an index without assets fails; no arguments gives exit 2; the command line exits 0 or 1.

Verification:

| Check | Result |
|---|---|
| `pytest tests/unit/test_check_web_wheel.py` | 6 passed |
| Break: missing-asset comparison set to `if False` | 1 failed (`test_wheel_missing_a_referenced_asset_fails_and_names_it`), restored |
| Break: index check set to `if False` | 2 failed, restored |
| `uv build --wheel` to scratchpad + `check_web_wheel.py` on the real wheel | exit 0 (static assets present in this worktree) |
| `bash -n scripts/local_ci.sh` | OK. The script itself was not run (agent rules). |
| Frontend job steps | Not run here: other agents edit `web/src` now. |

## 3. Item A11: detection seam and top-level imports

The scenario "Ingestion no longer reaches upward" is about top-level imports, so both fixes apply.

Spec text (`specs/architecture-boundary-enforcement/spec.md`): ingestion calls the core codebase detector through `core.codebase` (core-to-core) or the `integrations.magika` leaf. No `core/` module imports a top-level `omrg` module, except the sanctioned lazy `omrg.capabilities` import in `core/ingestion/pipeline.py`. `lint-imports` fails on any other such import.

New import-linter contracts (`pyproject.toml`, `[tool.importlinter]` only):

| Contract | Rule |
|---|---|
| `core-never-imports-top-level-modules` | `omrg.core` must not import any top-level `src/omrg/*.py` module. One commented ignore: `omrg.core.ingestion.pipeline -> omrg.capabilities`. |
| `ingestion-and-retrieval-stay-independent` | `omrg.core.ingestion` must not import `omrg.core.retrieval` (direct imports only). |
| `retrieval-stays-independent-of-ingestion` | The reverse direction. |
| `core-free-of-transport-frameworks` | `omrg.core` must not import `mcp`, `typer` or `click` (closes the transport-separation section-B gap). |

Why direct-only for ingestion and retrieval: an `independence` contract (and indirect checking) is broken by legitimate shared layers. Example chain: `core.retrieval.* -> core.vectordb.base -> core.vectordb.identity -> omrg.config -> core.ingestion.settings`. Direct imports are what architecture invariant 2 forbids.

New test `tests/test_core_import_contracts.py` (11 tests). It copies the real `src/omrg` tree into `tmp_path` and runs `lint-imports` with one contract:

- Each contract is kept on the real tree.
- The top-level contract forbids exactly the current top-level modules, so a new top-level module fails the test until it is added.
- Violations break the contract and the output names the edge: `core.ingestion.sources -> omrg.engine`; `core.codebase.codebase_map -> omrg.capabilities` (the ignore excuses only `pipeline.py`); `core.ingestion.sources -> core.retrieval.policy`; `core.retrieval.policy -> core.ingestion.sources`; `core.pipelines -> typer`.
- Red first: all 9 tests failed (KeyError) before the contracts existed.
- Ignore is needed: without the ignore, the contract is BROKEN on the real tree and names `omrg.core.ingestion.pipeline -> omrg.capabilities`.

`PYTHONPATH=src .venv/bin/lint-imports`: **21 kept, 0 broken** (was 17).

## 4. Spec text that did not match the deliberate design

The code is the deliberate design (lead decision). Each delta scenario now states the implemented behaviour (CLAUDE.md gotcha 12).

| # | Spec file and scenario | Change |
|---|---|---|
| 1 | pipeline-graphs / Threshold sees an incompatible score | Port validation or the score-kind guard rejects the connection, or the operation applies the threshold only to the dense score it was calibrated for (dense gate before fusion, as `search()`). It never compares a fusion score with a dense threshold or labels it dense. |
| 2 | pipeline-graphs / Conflicting commits | Preflight rejects any recipe with more than one enabled commit destination (`multiple_commit_destinations`), same target or not. |
| 3 | pipeline-graphs / new scenario "Explicit parameter equals its default" | An explicit index-shaping value equal to the inherited value counts as a change: the source is processed again once, then reused. |
| 4 | pipeline-graphs / Explicit graph profile | Added: the bundle's hybrid setting does not add or remove a sparse branch; the graph wiring decides. |
| 5 | pipeline-canvas / requirement text and "Reranker is disabled with a click" | States are node states (queued, running, completed, skipped, bypassed, failed, cancelled) plus the cancelling **run** status. The reranker scenario now describes the `enabled` control (node runs, no inference, reason in summary, inspector shows it). New scenario "Node is disabled in the graph" covers the bypass toggle. The requirement says the two are separate mechanisms. |
| 6 | notebook-plugins / "Notebook targets the live library" | A bound experiment credential is refused for any live-library run or read, not only mutation. |
| 7 | pipeline-run-records / Process stops between stores | No separate recovery step at start. An explicit retry applies the source completeness rules during its own ingestion. |
| 8 | architecture-boundary-enforcement | Package list adds `core.plugins` and `core.experiments`. "Top-level business modules are gone" names `compose_*.py`, `capabilities.py` and `pipeline_templates.py`. |
| 9 | public-library-api (`docs/guides/library-usage.md`) | Guide keeps its runnable example. A new "Advanced imports" note says `pipeline_templates` (`omrg.compose_pipelines`) and `RunCancellation` (`omrg.core.pipelines`) are not in `omrg.__all__`, are internal, and are optional. The spec text needs no change: it asks that non-`__all__` names be documented as internal. |

Not changed (functional gaps owned by other agents): A7 "Explicit node override" (result vs admission snapshot) and A1 experiment artefact location.

Validation:

| Command | Result |
|---|---|
| `openspec validate add-local-web-pipeline-workspace --strict` | valid (3 INFO notes on long requirement text) |
| `openspec validate --all --strict` | 62 passed, 0 failed |

No baseline spec in `openspec/specs/` needed a change.

## 5. Other findings

- `tests/test_no_module_level_strategy_imports.py`:
  - Decision: `omrg.core.retrieval.policy` is a pure helper (threshold scaling, `fetch_k`, rerank-policy resolution), not a registered strategy. It is removed from the forbidden list with a comment. `operations.py` is unchanged.
  - The AST check now also covers `core/retrieval/operations.py`, the four retrieval `graph_adapters*` modules, the three ingestion `graph_adapters*` modules and `core/answer/graph_adapters.py`.
  - New test `test_importing_module_loads_no_strategy` imports each module (and the backend orchestrator) in a fresh interpreter and checks `sys.modules`. This catches a load through a helper.
  - Proof: with `policy` put back in the list, 5 tests fail (the AST check on `operations.py`, and the runtime check on `retrieval.pipeline`, `operations`, `graph_adapters`, `graph_adapters_retrieve`). Restored: 30 passed.
- `tests/unit/test_plugin_boundaries.py`: the docstring now names the `plugin-host-starts-no-processes` contract.
- Stale REST wording: `src/omrg/transports/__init__.py` and `AGENTS.md` line 46 now describe `transports/api/` as the optional local HTTP transport for `omrg web` (`web` extra) with its OpenAPI 3.1 contract. `CLAUDE.md` is a symlink to `AGENTS.md`, so it changes too.
- `tests/test_mcp_tools.py::test_all_handlers_importable_from_package_root`: adds `answer_documents` and asserts that `handler_names` equals the set of registered tools, so a new tool cannot be left out. Proof: with `answer_documents` removed from the list, the test fails.

## 6. Section B test-only gaps

New test files only, in `tests/unit/` (written by a helper agent, checked here). No existing file was edited for these. 26 tests, all pass. No product bug found, so no `xfail`.

| Capability | Gap | Test (`tests/unit/...::`) |
|---|---|---|
| pipeline-graphs | Changing a connection changes execution | `test_verification_gaps_pipeline_graphs.py::test_two_revisions_differing_only_in_wiring_run_differently` |
| pipeline-graphs | Reader `structured=True` through a graph run | `...pipeline_graphs.py::test_structured_reader_declaration_through_a_graph_run[True|False]` |
| pipeline-graphs | Ingestion parity with `metadata_degraded=true` | `...pipeline_graphs.py::test_ingestion_parity_keeps_metadata_degraded_true` |
| pipeline-graphs | Registered replacement splitter through a graph run | `...pipeline_graphs.py::test_registered_replacement_splitter_runs_in_a_graph` |
| pipeline-graphs | Metadata store ownership through `Engine.run_pipeline` | `...pipeline_graphs.py::test_two_engines_graph_ingestion_prompts_hold_only_own_labels[a|b]` |
| engine-scoped-composition | Process defaults unchanged after `build_engine` | `test_verification_gaps_engine.py::test_build_engine_leaves_process_defaults_unchanged` |
| engine-scoped-composition | Reranker model cache survives another Engine closing | `...engine.py::test_model_cache_survives_another_engine_close` |
| engine-scoped-composition | Engine call after a cancelled run; `shutdown_requested` unset | `...engine.py::test_engine_call_after_cancelled_run_and_flag_stays_unset` |
| engine-scoped-composition | One run cannot report another run's rerank failure | `...engine.py::test_one_run_cannot_report_another_runs_rerank_failure` |
| modular-core-extraction | Code and config sources through `read.document` | `test_verification_gaps_modular_core.py::test_code_and_config_sources_route_through_read_document` (both files end in `.txt`, so only the detected content type routes them) |
| notebook-plugins | Trust notice text; frontend copy tied to the server constant | `test_verification_gaps_notebook_plugins.py` (4 tests; reads `web/src/experiments/test/experimentsServer.ts` as text) |
| pipeline-run-records | Repeat of an older revision | `test_verification_gaps_run_records.py::test_repeat_of_an_older_revision_runs_that_document` |
| pipeline-run-records | Vector store unchanged after a workspace upgrade | `...run_records.py::test_workspace_upgrade_leaves_vector_store_bytes_unchanged` (byte compare) |
| pipeline-run-records | Retry of an interrupted run uses source completeness | `...run_records.py::test_retry_of_interrupted_ingestion_uses_source_completeness` |
| transport-separation | `omrg` with no arguments starts no web or editor | `test_verification_gaps_transport.py::test_no_argument_start_never_calls_the_web_server`, `::test_no_argument_entry_point_loads_no_web_or_editor_modules` |
| transport-separation | Parameters and annotations of the MCP tools | `...transport.py::test_every_mcp_tool_keeps_its_v3_parameters_and_annotations` (all eight tools; snapshot equals `v3` at `3ca82a0`) |
| transport-separation | `answer_documents` missing from `handler_names` | `tests/test_mcp_tools.py::test_all_handlers_importable_from_package_root` (section 5) |
| transport-separation | No contract forbids `mcp`, `typer`, `click` in core | contract `core-free-of-transport-frameworks` (section 3) |
| public-library-api | Skipped nodes and completed effects through `Engine.run_pipeline` | `test_verification_gaps_public_api.py::test_failed_run_reports_skipped_nodes_and_completed_effects`, `::test_cancelled_run_keeps_the_effect_that_finished_first` |
| architecture-boundary-enforcement | Allow-list of top-level `src/omrg/*.py` | `test_verification_gaps_boundaries.py::test_top_level_modules_match_the_allow_list`, `::test_no_top_level_business_package_appears` |
| architecture-boundary-enforcement | Ingestion and retrieval at package level | contracts `ingestion-and-retrieval-stay-independent` and `retrieval-stays-independent-of-ingestion` (section 3) |

Not done here (other owners): all pipeline-canvas items, and "public static frontend not named in the auth section" (`openapi.yaml`).

Proof the tests can fail: about 20 deliberate product breaks were injected through a scratch pytest plugin (not by editing product files). Each failed its test. Examples: `build_engine` installs process defaults; `close()` clears the model cache; cancellation sets the global shutdown flag; enrich ignores `structured`; `metadata_degraded` dropped; completeness check forced true and forced false; repeat runs the current revision; the upgrade touches the store directory; a weaker trust notice; a changed tool annotation. The wiring test was checked by reasoning only: it asserts a different node order, graph identity and rows. The allow-list test failed for real once, when another agent added `src/omrg/compose_pipeline_runs.py`.

Notes:

1. `_ALLOWED_TOP_LEVEL` (gap test) and the `core-never-imports-top-level-modules` forbidden list now include `compose_pipeline_runs`. Both tests fail if a top-level module is added, renamed or deleted without an update. That is intended.
2. `test_build_engine_leaves_process_defaults_unchanged` reads `get_default_effective_settings()` and `get_default_store()`. The agent rules forbid this in new code, but the gap is about those defaults, so the test must read them. It writes nothing. Lead decision: keep or delete.


## Tests run

All commands run in the worktree with `PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider`.

| Run | Result |
|---|---|
| All new and touched test files (8 gap files, `test_core_import_contracts.py`, `test_check_web_wheel.py`, `test_no_module_level_strategy_imports.py`, `test_mcp_tools.py`, `test_plugin_boundaries.py`, `test_contract_coverage.py`, `test_pipeline_import_boundaries.py`, `test_pipeline_guide.py`) | 191 passed, 5 skipped (after adding `compose_pipeline_runs` to the contract; before that, 1 failed as designed) |
| `test_verification_gaps_*.py` alone | 26 passed |
| `PYTHONPATH=src .venv/bin/lint-imports` | 21 kept, 0 broken |
| `.venv/bin/ruff check` and `ruff format --check` on every changed or new Python file | clean |
| `openspec validate add-local-web-pipeline-workspace --strict`; `openspec validate --all --strict` | valid; 62 passed, 0 failed |
| `tests/test_file_size_ceiling.py` | 1 failed: `src/omrg/compose_pipelines.py` 513 lines (another agent's file) |

Not run (agent rules): the full suite, `tests/test_clean_base_tripwire.py`, `scripts/local_ci.sh`, the npm gates.

Tripwire effect of the new tests (base counts are not changed here):

- New tests in this change: 26 gap tests, 11 contract tests, 6 wheel-check tests, 24 more in `test_no_module_level_strategy_imports.py` (6 before, 30 now: 9 more AST cases and 15 runtime cases), and the `test_mcp_tools.py` change adds none. Re-baseline `_BASE_EXECUTED` from the full run in task 9.2.
- Without FastAPI, `test_verification_gaps_notebook_plugins.py` skips as one module. The measurement script picks this up.


## Open items for the lead

1. Fix the two support modules (section 1), then run `measure_web_cases.sh` and set `_WEB_EXTRA_CASES` and `_WEB_SKIP_DELTA`.
2. `tests/test_file_size_ceiling.py` fails now: `src/omrg/compose_pipelines.py` has 513 lines. Another agent edits that file.
3. Decide whether the release wheel goes to `dist/` (published) or stays in `wheel-check/` (checked only).
4. The `frontend` CI job and the `local_ci.sh` frontend step were not run here. Run `local_ci.sh` once the web agents finish.
