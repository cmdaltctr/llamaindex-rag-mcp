# Integrated gates (task 9.2)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, base `489a618`, uncommitted tree.
Approved by the user in this session (full suite and local CI).

| Gate | Command | Result |
|---|---|---|
| Lint, whole repo | `ruff check .` | PASS |
| Format, whole repo | `ruff format --check .` | PASS, after formatting three Markdown code blocks (`docs/guides/pipelines.md`, `evidence/plugins.md`, `evidence/workspace-cleanup.md`) |
| Import contracts | `lint-imports` | PASS, 17 kept, 0 broken (8 before this change) |
| OpenSpec | `openspec validate --all --strict` | PASS, 62/62 |
| OpenAPI | `openapi_spec_validator` on `openapi.yaml` (v2.0.0, 38 operations) | PASS |
| OpenAPI runtime conformance | `tests/unit/test_web_openapi_conformance*.py` | PASS (in fast suite) |
| Torch-free default install | `local_ci.sh` step | PASS |
| Torch-free web extra | `uv pip compile --extra web` (see `web-dependency.md`) | PASS, no torch |
| Dependency floors | `tests/test_dependency_floors.py`; `uv pip compile --extra web --resolution lowest-direct` | PASS |
| File size ceiling | `tests/test_file_size_ceiling.py` | PASS |
| Fast suite, first run | `./scripts/local_ci.sh` (13 min 41 s) | 4661 passed, 1 failed, 25 errors. The failure was the expected tripwire drift. The 25 errors were `tests/unit/test_starter_notebook.py` while task 8.4 edited the notebook during the run (traceback lines did not match the file); the file passes alone (25 passed) |
| Base suite, final tree | tripwire command: `pytest -m "not slow" -q -rs --ignore=tests/test_clean_base_tripwire.py` | PASS, 4682 passed, 140 skipped, 20 deselected, exit 0 (6 min 59 s) |
| Tripwire after re-baseline | `pytest tests/test_clean_base_tripwire.py` | PASS, 5 passed. `_BASE_EXECUTED` 3415 -> 4689 (+1274), `_BASE_DESELECTED` 19 -> 20 (slow marimo wheel test); skips unchanged |
| Frontend | `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` in `web/` | PASS, 32 files / 271 tests; build warns the script chunk is 541 kB |
| Wheel packaging | `scripts/check_web_wheel.py`; installed-wheel smoke outside the checkout without Node (`frontend-scaffold.md`) | PASS |
| marimo qualification | `marimo-qualification.md` | PASS for marimo 0.25.1 with uv 0.12.18 |

## Coverage

NOT RUN as a separate gate. `local_ci.sh` runs the fast suite without `--cov`, the same as CI's
blocking job. CI's coverage job measures it on the pull request (Codecov project checks are
informational; the patch check blocks).

## NOT RUN

- Coverage percentages (see above).
- Chroma-extra suites (extra not installed; 140 base skips include the Chroma-gated files).
- `-m slow` suites, except the marimo wheel check run by task 8.2.
- A fully clean offline `pip install "omrg[web]"` from the lock (uv cache lacks some locked wheels; see `frontend-scaffold.md`).
- Browsers other than Chrome.
