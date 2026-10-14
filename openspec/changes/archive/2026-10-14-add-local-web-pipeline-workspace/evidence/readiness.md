# Readiness gate (tasks 1.0 and 1.1)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace` at `489a618`
(merge of `feat/repair-modular-core-boundaries` into `integration/core-web`).

## 1.0 Repair regressions on this base

Command (v3 `.venv`, `PYTHONPATH=src`, `PDF_READER=pypdf`):

    pytest -q tests/test_document_registry_dispatch.py \
      tests/test_metadata_store_ownership.py \
      tests/unit/test_codebase_context_repair.py \
      tests/test_no_global_settings_reads.py

Result: **119 passed**, 0 failed.

The archived evidence in
`openspec/changes/archive/2026-10-13-repair-modular-core-boundaries/evidence/`
records the same files passing (dispatch 10, metadata 38, codebase context 15,
guard set). The integration gate on `integration/core-web` gave 120 passed for
these 4 files plus the file-size ceiling test. Result: PASS.

## 1.1 Worktree

- `git rev-parse --show-toplevel`: `.../llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace`
- `git branch --show-current`: `feat/add-local-web-pipeline-workspace`
- Planning artefacts are present from the merge base (no copy needed).
- No `.env` in the worktree. `.env.example` is identical to v3.

Result: PASS.
