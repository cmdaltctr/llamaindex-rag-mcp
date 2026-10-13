# Integration evidence

Worktree: `llamaindex-rag-mcp-v3-feat-repair-modular-core-boundaries`, branch `feat/repair-modular-core-boundaries`, base `v3` at `3ca82a0`. Changes are uncommitted at the time of this record.

Interpreter: the `v3` checkout's `.venv` with `PYTHONPATH=src`. No install ran in this worktree. A check confirmed that `omrg` imports from this worktree's `src/`.

Per-area before/after evidence: `dispatch.md`, `metadata.md`, `codebase-cache.md`, `guards.md`.

## 5.2 Focused gate (2026-10-13)

```bash
PYTHONPATH=src <v3>/.venv/bin/python -m pytest -m "not slow" -q -p no:cacheprovider \
  tests/test_document_registry_dispatch.py tests/test_chunking_hardening.py \
  tests/test_metadata_store_ownership.py tests/test_metadata_extractor.py \
  tests/test_metadata_degradation.py tests/test_metadata_timeout_resolution.py \
  tests/unit/test_provider_config.py tests/unit/test_codebase_context_repair.py \
  tests/unit/test_codebase_map.py tests/unit/test_codebase_map_integration.py \
  tests/test_no_global_settings_reads.py tests/test_file_size_ceiling.py \
  tests/test_engine_isolation.py tests/test_registry_contract.py
```

| Check | Result |
|---|---|
| Focused tests (dispatch, metadata, codebase/cache, isolation, boundary, size) | PASS: 385 passed, 5 skipped (Chroma extra not installed) |
| `lint-imports` | PASS: 8 contracts kept, 0 broken |
| `ruff check src tests` | PASS after fixing 2 import-order findings in `tests/test_metadata_extractor.py` |
| `ruff format --check src tests` | PASS after formatting `tests/test_no_global_settings_reads.py` |
| `openspec validate repair-modular-core-boundaries --strict` | PASS |

Known unrelated failure: `tests/test_magika_pinned_detection.py` also fails on the base commit when the venv is not activated, because `magika` is not on `PATH`.

## 5.3 Wider gate (approved by the user, 2026-10-13)

```bash
UV_PROJECT_ENVIRONMENT=<v3>/.venv PYTHONPATH=src PATH=<v3>/.venv/bin:$PATH ./scripts/local_ci.sh
```

| Check | Result |
|---|---|
| First run | FAIL at `ruff format --check`: one code example in `docs/guides/ingestion.md`. Fixed with `ruff format`. |
| ruff check, ruff format, lint-imports, OpenAPI validation | PASS |
| `pytest -m "not slow"` | 1 failed, 3412 passed, 140 skipped, 19 deselected (765 s) |
| Failure | `tests/test_clean_base_tripwire.py::test_base_skip_manifest_is_exact`: executed count 3408, expected 3306 |

Cause: the repair adds 102 tests. Collection on `v3` gives 3448 tests; collection on this branch gives 3550 (+102). The executed count rose by the same 102, so the skip count is unchanged. `_BASE_EXECUTED` is re-baselined from 3313 to 3415 with a dated comment, following the file's convention.

Tripwire rerun after the re-baseline: PASS, 5 passed in 384 s.

`openspec validate add-local-web-pipeline-workspace --strict`: PASS after reconciliation (task 5.5).

## 5.4 Tested commit

The repair commit on `feat/repair-modular-core-boundaries` holds the tested code. Its hash is in `git log` for this branch. Integration into `v3` happens when the branch merges; the web change task 1.0 checks this on its base. The user waived the Graphify refresh (`graphify-out/` is gitignored).

## 5.5 Web change reconciliation

`add-local-web-pipeline-workspace` updated:

- `specs/modular-core-extraction/spec.md`: added the repair's registered-dispatch requirement text and the "no direct helper calls" clause.
- `tasks.md`: task 1.0 names the four regression test files and the archived evidence path; new task 3.8 adds graph adapters to the accessor guard with a poisoned-default test.
- `design.md`: codebase-map facts (explicit Engine settings/store, fixed `documents` collection, cache reuse only with a durable version), D4 explicit-context rule, and named regressions in the qualification gates.
- `specs/local-web-workspace/spec.md` and `specs/engine-scoped-composition/spec.md`: matching scenarios.

Web implementation tasks stay unchecked.
