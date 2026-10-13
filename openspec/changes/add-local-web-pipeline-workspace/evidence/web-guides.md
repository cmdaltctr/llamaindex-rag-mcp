# Web and notebook guides, session workspace, collection profiles (tasks 6.9, 8.7)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted work tree.
Design D8, D10, D11. Specs `local-web-workspace`, `notebook-plugins`, `transport-separation`.

Command prefix: `PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider`.

## Files

| File | Change |
|---|---|
| `src/omrg/transports/api/routes.py` | `GET /v1/session` adds `workspace` (canonical path, `null` before the runtime starts). |
| `src/omrg/transports/api/routes_documents.py` | `GET /v1/collections` items add `profile` (stored tag or `null`; a failed metadata read gives `null`). |
| `src/omrg/transports/api/openapi.yaml` | `SessionInfo.workspace` and `CollectionInfo.profile`, both required and nullable. |
| `docs/guides/web-workspace.md` | New guide (task 6.9). |
| `docs/guides/notebooks.md` | New guide (task 8.7). |
| `docs/guides/cli-reference.md`, `configuration.md`, `workspace.md`, `README.md` | Links and an `omrg web` section. `workspace.md` status line no longer says the cleanup route is missing. |
| `src/omrg/transports/api/README.md` | `--experiment-root`, templates, experiment and plugin routes, `plugins` scope, new fields. |
| `plugins/marimo/README.md` | Trust summary, starter notebook, separate-tab rule, env-variable gap. |
| `tests/unit/test_web_session_collections.py` | 3 tests for the two API gaps. |
| `tests/unit/test_web_workspace_guide.py` | 10 tests (task 6.9). |
| `tests/unit/test_notebooks_guide.py` | 8 tests (task 8.7). |
| `tests/unit/test_web_guides_support.py` | Citation helpers (no tests). |
| `tests/unit/test_web_documents.py` | One expected dict gains `"profile": None` (direct result of the new field). |

## Test-first record

| Step | Command | Result |
|---|---|---|
| API gap tests before code | `tests/unit/test_web_session_collections.py` | 3 failed |
| Code, contract not yet changed | same | 2 failed (contract rejects `workspace` and `profile`), 1 passed |
| Contract changed, wider web suites | session/collections, conformance, documents, security, files, `tests/test_openapi_conformance.py`, `tests/test_contract_coverage.py` | 1 failed (`test_collections_list_counts_and_conforms` exact dict), 185 passed; dict updated |
| Guide tests | written after the guides; covered by the mutations below | |

## Mutation checks

Script: `scratchpad/mut69/mut.sh`. Each check edits one file, runs the two guide test files, restores the file and compares SHA-256.
Control: 18 passed. Final: 18 passed.

| Id | Change | Result |
|---|---|---|
| A1 | Stored profile always `None` | 1 failed |
| A2 | Session `workspace` always `None` | 1 failed |
| A3 | `workspace` not resolved | survived: pytest `tmp_path` is already canonical |
| M1 | Fallback serves HTML for `/v1` | 4 failed |
| M2 | 500 message carries exception detail | 1 failed |
| M3 | Guide option renamed | 1 failed |
| M4 | Guide names an option that does not exist | 1 failed |
| M5 | CLI install hint drifts from the guide | 1 failed |
| M6 | `<iframe>` in a transport source | 1 failed |
| M7 | Sentence claims an embedded editor | 1 failed |
| M8 | One "never embeds the editor" removed from plugin README | survived (second statement remains); both removed: 1 failed |
| M9 | Guide port list drifts | 1 failed |
| M10 | Unknown-plugin recheck gives 500 | 1 failed |
| M11 | CLI reference link removed | 1 failed |
| M12 | Guide cites an unknown route | 1 failed |
| M13 | Guide cites a missing path | 1 failed |
| M14 | Startup launches a process | 1 failed |

## Final runs

- `-m "not slow"` over `tests/unit/test_web_*.py`, both guide tests, `test_workspace_cleanup_guide.py`, `test_pipeline_guide.py`, `test_pipeline_templates_guides.py`, `test_starter_notebook.py`, `test_plugin_marimo_manifest.py`, `tests/test_file_size_ceiling.py`, `tests/test_openapi_conformance.py`, `tests/test_contract_coverage.py`, `tests/test_cli.py`, `tests/test_no_global_settings_reads.py`, `tests/test_pipeline_import_boundaries.py`: **619 passed, 1 deselected**.
- `tests/test_docs_no_retired_env_vars.py tests/test_docs_references.py tests/test_strategy_registration_inventory.py tests/unit/test_plugin_marimo_manifest.py -m "not slow"`: **33 passed**.
- `ruff format` and `ruff check` on changed Python files: clean. `lint-imports`: **17 kept, 0 broken**.

## Findings and open points

1. **Starter notebook cannot connect in an OMRG-launched editor.** `OwnedProcessLauncher` passes only `ENV_ALLOWLIST` to the editor. `OMRG_API_URL`, `OMRG_TOKEN_FILE` and `OMRG_EXPERIMENT_CONTEXT` are not in it, and nothing else delivers them. The notebook guide states this gap. Fix options: (a) write a private connection file (mode 600) into the launch directory and let the notebook read it; (b) add a per-launch extra environment for these three names only. Belongs to task 8.6.
2. **Frontend:** `GET /v1/session` now returns `workspace`; `GET /v1/collections` items return `profile`. The Settings and Library views can show them. No `web/` file was changed.
3. Task 8.4 is not run. The notebook guide lists the unconfirmed items.

## Not run

- A real `omrg web` socket start for this task (earlier smoke runs cover it). A real marimo launch. Full suite and `local_ci.sh`.
