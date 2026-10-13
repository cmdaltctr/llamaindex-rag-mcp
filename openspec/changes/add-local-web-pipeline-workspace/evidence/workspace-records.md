# Workspace records (task 5.1)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`.

## Scope

Task 5.1: repository contracts and the standard-library SQLite adapter.
Design D7. Spec `pipeline-run-records`.

Files:

- `src/omrg/core/workspace/__init__.py`: public contract exports.
- `src/omrg/core/workspace/records.py`: TypedDict records, status sets, `canonical_json`, `content_hash`.
- `src/omrg/core/workspace/repository.py`: `WorkspaceRepository` protocol (runtime checkable).
- `src/omrg/integrations/workspace_sqlite/__init__.py`: adapter exports.
- `src/omrg/integrations/workspace_sqlite/schema.py`: versioned migrations, backup, rollback, owner-only files.
- `src/omrg/integrations/workspace_sqlite/rows.py`: JSON helpers and row-to-record conversion.
- `src/omrg/integrations/workspace_sqlite/repository.py`: `SqliteWorkspaceRepository`.
- `tests/unit/test_workspace_repository.py`, `tests/unit/test_workspace_migrations.py`, `tests/unit/test_workspace_contracts.py`.

## Decisions

- The adapter imports no `omrg.core` module. The `integrations-are-leaves` contract
  forbids `omrg.core` and needs no new ignore entry. The adapter repeats the status
  sets and the canonical JSON form. Parity tests compare them with the core contract.
- Content hash: SHA-256 of JSON with sorted keys, no whitespace, `ensure_ascii=False`,
  NaN and infinity rejected.
- Revisions are unique per `(pipeline_id, content_hash)`. Identical content returns the
  existing revision and moves the current-revision pointer to it. Identical content
  under another schema version raises `ValueError`.
- SQLite triggers abort any `UPDATE` or `DELETE` on `pipeline_revisions`.
- `save_layout` updates `pipelines.layout_json` only.
- `record_update` updates the run row and inserts the event in one `BEGIN IMMEDIATE`
  transaction. The sequence is `runs.last_sequence + 1`. `create_run` writes event 1.
- Run statuses: `queued`, `running`, `succeeded`, `failed`, `cancelled`, `interrupted`.
  `queued` can go to `running` or a terminal state. `running` can go to a terminal
  state. A terminal run accepts no further update or event.
- `PRAGMA application_id` marks a workspace file. A file with tables and another
  application id is refused without change. A newer `user_version` is refused.
- An upgrade of an existing file first copies it with the SQLite backup API to
  `<name>.v<old>-to-v<new>.<time>.bak` (mode 0o600). All pending migrations run in
  one transaction. On failure the transaction rolls back and the error names the backup.
- New directories get mode 0o700. Existing directories keep their mode. The database
  and backup files get mode 0o600.

## Test-first record

Environment for all commands: v3 `.venv` on `PATH`, `PYTHONPATH=src`, `PDF_READER=pypdf`.

Before implementation:

    python -m pytest -q -p no:cacheprovider tests/unit/test_workspace_repository.py \
      tests/unit/test_workspace_migrations.py tests/unit/test_workspace_contracts.py

Result: **3 errors during collection** (`ModuleNotFoundError: No module named
'omrg.core.workspace'`). FAIL as expected.

After implementation, same command plus guards:

    python -m pytest -q -p no:cacheprovider tests/unit/test_workspace_repository.py \
      tests/unit/test_workspace_migrations.py tests/unit/test_workspace_contracts.py \
      tests/test_contract_coverage.py tests/test_file_size_ceiling.py

Result: **66 passed**, 0 failed (37 new workspace tests, 29 guard tests).

## Mutation checks

Each check copies `src/` to a scratch directory, makes one change, and runs the three
workspace test files against the copy. Every mutation made at least one test fail.

| Id | Change to the implementation | Result |
|---|---|---|
| M1 | Remove revision immutability triggers | 1 failed |
| M2 | Always insert a new revision for identical content | 2 failed |
| M3 | Skip the pre-migration backup | 3 failed |
| M4 | Commit after each migration statement | 1 failed |
| M5 | Commit the run update before the event insert | 1 failed |
| M6 | Do not chmod the database file | 1 failed |
| M7 | Accept updates on terminal runs | 3 failed |
| M8 | Use one global event sequence | 1 failed |
| M9 | Layout save changes the current revision | 1 failed |

## Static checks

- `ruff format` and `ruff check` on all new files: clean.
- `lint-imports`: 8 contracts kept, 0 broken.
- Branch coverage of the new modules: 100% except one line, then covered by the
  schema-version conflict assertion.
- Largest file: `integrations/workspace_sqlite/repository.py`, 465 lines.

## Not covered here

- Contract entries for `omrg.core.workspace` in `pyproject.toml` (task 1.3).
- Payload size bounds, redaction and artefact storage (task 5.3).
- Restart interruption flow (task 5.4) and cleanup (task 5.5). The revision triggers
  block revision deletion; task 5.5 must decide if pipeline cleanup removes revisions.
