# Workspace cleanup and guide (task 5.5)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`.

## Scope

Task 5.5: previewed cleanup of app artefacts, and the workspace guide. Design D7.
Spec `pipeline-run-records`, scenario "Cleanup is confirmed". Spec `local-web-workspace`:
cleanup needs a preview and a confirmation bound to the action and the observed state.

Files:

- `src/omrg/core/workspace/cleanup.py` (392 lines): `WorkspaceLayout`, `CleanupSelector`,
  `CleanupPreview`, `CleanupRun`, `CleanupResult`, `CleanupRejected`, `WorkspaceCleanup`.
- `src/omrg/core/workspace/cleanup_files.py` (140 lines): `CleanupFile`, `CleanupSkip`,
  `scan_run_files`, `remove_run_files`. Split from `cleanup.py` to keep it below 400 lines.
- `src/omrg/core/workspace/__init__.py`: additive eager exports. The run service names stay lazy.
- `src/omrg/core/workspace/repository.py`: new protocol method `delete_runs`.
- `src/omrg/integrations/workspace_sqlite/deletion.py` (67 lines): `delete_finished_runs`.
- `src/omrg/integrations/workspace_sqlite/repository.py`: `delete_runs` (480 lines total).
- `docs/guides/workspace.md`: the workspace guide.
- `tests/unit/test_workspace_cleanup.py`, `tests/unit/test_workspace_cleanup_safety.py`,
  `tests/unit/test_workspace_cleanup_guide.py`, `tests/unit/test_workspace_cleanup_support.py`.

## Decisions

- **Two steps.** `preview_cleanup(selector)` lists runs, event counts, artefact files,
  skipped items, warnings and totals. It issues a single-use token `wc_<random>`. The
  service keeps the selector, the fixed age cutoff, a state marker and the expiry
  (300 s) for the token. At most 64 previews wait; the oldest go first.
- **State marker.** SHA-256 of the canonical JSON of the selector, the cutoff, each
  selected run (id, status, finish time, event count) with each file (reference, size,
  `mtime_ns`), and the skipped items. `apply_cleanup(token)` repeats the plan with the
  stored selector and cutoff. A different marker gives `CleanupRejected("stale")`.
  Other reasons: `unknown` (also altered, used or evicted tokens, and tokens of another
  service instance), `expired`, `selector` (optional selector argument differs).
  Every call spends the token.
- **Selectors.** `older_than(days)` uses `finished_at <= now - days` at preview time.
  `by_status(*statuses)` accepts finished statuses only. `run(run_id)` selects one run.
  More than one criterion means all must match.
- **Active runs.** `queued`, `running` and `cancelling` are never selected. A run
  selector on an active run gives a skipped item. The SQLite deletion checks the status
  again inside the delete transaction.
- **Retry references.** A run that a kept run names as `source_run_id` stays (skipped
  with the reason). This keeps the foreign key and the provenance of the retry. The rule
  repeats until no change, so a retry chain stays whole. The adapter also refuses this
  case inside the transaction.
- **Order.** Records first, in one `BEGIN IMMEDIATE` transaction with
  `PRAGMA secure_delete = ON`; files after. If the record deletion fails, no file is
  removed. A file that cannot be removed safely stays and appears in `failed`.
- **Files.** Only regular files directly in `<workspace>/artefacts/<run_id>/`. Listing
  uses `lstat` data. Removal opens the artefact root and each run directory with
  `O_NOFOLLOW | O_DIRECTORY`, then unlinks by name relative to the directory handle. A
  link (artefact root, run directory or file) and any non-regular entry is skipped and
  reported. An empty run directory is removed with `rmdir`, which never follows a link.
  Directories with no run record are never touched.
- **Revisions are kept.** Pipelines, revisions and plugin registrations stay. Revisions
  are immutable (triggers), and a repeat of a saved revision needs them. No schema
  migration is needed. The spec does not require revision removal.
- **Interrupted runs.** The preview carries a warning: an interrupted run can have
  changed a vector store, so check source completeness first.
- **Layout names.** `WorkspaceLayout` names `workspace.db`, `.lock`, `artefacts/` and
  `uploads/`. These match the names that `transports/api/runs_wiring.py` and
  `transports/api/lifespan.py` use today. A guide test checks that they stay equal.

## Test-first record

Environment: WT `.venv`, `PYTHONPATH=src`, `PDF_READER=pypdf`, `-q -p no:cacheprovider`.

Before implementation:

    pytest tests/unit/test_workspace_cleanup.py tests/unit/test_workspace_cleanup_safety.py

Result: **2 errors during collection** (`ImportError: cannot import name 'WorkspaceLayout'
from 'omrg.core.workspace'`). FAIL as expected.

After implementation, the same two files: **2 failed, 49 passed**. The two failures were a
test fault (the test made the preview and the apply on two service instances). After the
test fix, final:

    pytest tests/unit/test_workspace_cleanup*.py

Result: **61 passed**, 0 failed.

Guards and neighbours:

    pytest tests/unit/test_workspace_*.py tests/test_file_size_ceiling.py \
      tests/test_contract_coverage.py tests/test_docs_references.py \
      tests/test_docs_no_retired_env_vars.py

Result: **220 passed**, 0 failed.

## Mutation checks

Implementation mutations: each check copies `src/` to the scratchpad, makes one change,
and runs `test_workspace_cleanup.py` and `test_workspace_cleanup_safety.py` against the copy.

| Id | Change to the implementation | Result |
|---|---|---|
| M1 | Select active runs | 3 failed |
| M2 | Skip the stale-marker check | 3 failed |
| M3 | Ignore retry references in the plan | 2 failed |
| M4 | List files through links (`entry.stat()`) | 1 failed |
| M5 | Open directories without `O_NOFOLLOW` | 1 failed |
| M6 | Adapter deletes active runs | 1 failed |
| M7 | No expiry check | 1 failed |
| M8 | Adapter ignores retry references | 1 failed |
| M9 | Token can be used again | 1 failed |
| M10 | Follow a linked artefact root | 1 failed |

Guide mutations: each check edits `docs/guides/workspace.md`, runs
`test_workspace_cleanup_guide.py`, and restores the file (verified with `cmp`).

| Id | Change to the guide | Result |
|---|---|---|
| G1 | Unknown Python name | 1 failed |
| G2 | Wrong database file name | 1 failed |
| G3 | Missing `src/` path | 1 failed |
| G4 | Wrong token lifetime | 1 failed |
| G5 | Unknown CLI option | 1 failed |
| G6 | Broken code example | 1 failed |
| G7 | Broken link anchor | 1 failed |

## Survival proof

`test_workspace_cleanup_safety.py` places source files, a LanceDB directory, a Chroma
file, a marimo notebook (`*.py`), an `*.ipynb` notebook, experiment `output/` files and
`.env` inside the workspace and next to it, plus `uploads/` and a non-run directory in
`artefacts/`. After a confirmed cleanup of four runs (one per finished status), every
byte of these files is unchanged and `workspace.db` remains. Links to the outside
notebook, LanceDB directory and experiment output are skipped and stay as links. A run
directory swapped for a link after the plan is not entered (`failed` lists the file; the
decoy target is unchanged).

## Static checks

- `ruff check` and `ruff format --check`: clean on all owned files.
- `lint-imports`: 15 contracts kept, 0 broken. `omrg.core.workspace` imports no
  `sqlite3`; `test_workspace_contracts.py` confirms the import probe.
- Branch coverage of the new modules: `cleanup.py` 98%, `cleanup_files.py` 96%,
  `deletion.py` 100%. Not covered: an impossible run-id mismatch branch, and the
  "no longer a regular file" and unlink error paths in removal.

## Interface for the cleanup route (later task)

Compose once per launch, next to the run service:

```python
from omrg.core.workspace import WorkspaceCleanup, WorkspaceLayout

cleanup = WorkspaceCleanup.for_layout(repository, WorkspaceLayout(config.workspace))
```

- `cleanup.preview_cleanup(CleanupSelector(...)) -> CleanupPreview`. Use
  `preview.as_dict()` for the response: `token`, `selector`, `expires_at`, `runs`
  (`run_id`, `status`, `finished_at`, `events`, `files[{ref, bytes}]`), `skipped`
  (`item`, `reason`), `warnings`, `totals` (`runs`, `events`, `files`, `bytes`).
  `KeyError` for an unknown run id (404). `ValueError` from the selector (400 or 422).
- `cleanup.apply_cleanup(token, selector=...) -> CleanupResult` (`runs_removed`,
  `events_removed`, `files_removed`, `bytes_removed`, `failed`, `skipped`).
  `CleanupRejected.reason` in `unknown | expired | selector | stale`: return 409 with
  "preview again", like `ConfirmationRejected`.
- Both calls do blocking I/O. Run them in a worker thread from async routes.
- Protect both routes with the session scope that the other destructive actions use.

## Not covered here, and open points

- The HTTP route and OpenAPI entries (tasks 6.6, 6.7).
- `transports/api/runs_wiring.py` and `lifespan.py` repeat the layout names as their
  own constants. Suggest that they use `WorkspaceLayout`, so one module owns the names.
- Removal uses `dir_fd`, which POSIX systems support and Windows does not. The web
  lifespan already needs POSIX, because `WorkspaceLock` uses `fcntl`.
- Orphan artefact directories (no run record) are kept on purpose. A failed file
  removal therefore leaves files that a later cleanup does not list.
