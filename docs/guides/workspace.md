# Local workspace

The local web workspace keeps application records for `omrs web`. This guide tells you where the workspace is, what it stores, how long it keeps records, and how to remove old run records safely.

Status: the record store, the run service and the cleanup service are available as library code in `omrs.core.workspace`. The running web server also offers cleanup through `POST /v1/workspace/cleanup/preview` and `POST /v1/workspace/cleanup` (see [Web workspace](web-workspace.md#confirm-destructive-actions)). The library interface in [Clean up old runs](#clean-up-old-runs) needs a stopped server.

## Workspace location

The default workspace is `~/.omrs/workspace`. To use a different directory, start the server with `--workspace`:

```bash
omrs web --workspace ~/projects/demo-workspace
```

Use one workspace for one web server. At startup the server takes an advisory lock on the `.lock` file (`WorkspaceLock` in `src/omrs/transports/api/lifespan.py`). A second server on the same workspace stops with an error. Stop the first server, or give the second server a different `--workspace`. The operating system releases the lock when the process stops, so a crash does not leave a stale lock.

## Workspace layout

<!-- workspace-layout -->
| Name | Contents |
|---|---|
| `workspace.db` | SQLite file with the application records. |
| `.lock` | Advisory lock file. It holds no data. |
| `artefacts/` | Private run artefacts, one directory for each run: `artefacts/<run_id>/<name>.json`. |
| `uploads/` | Files that you uploaded through the web workspace. |
| `workspace.db.v<old>-to-v<new>.<time>.bak` | Backup of the records before a schema upgrade. |
<!-- /workspace-layout -->

The Python names for these paths are in `omrs.core.workspace.WorkspaceLayout`.

SQLite also uses its own lock on `workspace.db`. Each write is one `BEGIN IMMEDIATE` transaction. While a write runs, SQLite can create the temporary file `workspace.db-journal` next to the database.

## What the workspace stores

The file `workspace.db` has these tables:

| Table | Contents |
|---|---|
| `pipelines` | Pipeline identity, title, current revision and the presentation layout. |
| `pipeline_revisions` | Immutable execution documents with a content hash and a schema version. |
| `runs` | Status, revision, redacted settings, resource identities, inputs, failure, result reference and times. |
| `run_events` | Events of each run, with a sequence number for each run. |
| `plugin_registrations` | Approved external tools and their compatibility status. |
| `workspace_settings` | Empty. Older builds kept web-server settings here. The first launch of this build copies each row into the settings file (omrs.jsonc) and deletes it (ADR-087). The table stays so an older build still opens the file. |
| `mcp_tokens` | The one MCP token, as a SHA-256 hash with its creation time. The token value is never stored. |
| `profiles` | User profiles: id, title, description, base profile and the three pipelines (Ingest, Search, Answer) that each profile owns. Deleting a profile sets `archived_at`; the row stays. |
| `chat_folders` | Folders for stored chats. One level. Deleting a folder deletes its chats. |
| `chats` | Stored chats: title, folder and times. Deleting a chat deletes its turns. |
| `chat_turns` | The turns of each chat: collection, question and the finished answer as JSON, with the evidence text. |

A layout change does not create a revision. A semantic graph change creates a new revision. Database triggers stop all updates and deletes of revisions.

Run artefacts are bounded and redacted:

- A text preview keeps the first 4 KiB. A list or mapping preview keeps the first 100 entries.
- An event summary is 16 KiB or less. A larger summary moves to an artefact, and the event gets `truncated: true` and an `artefact_ref`.
- One artefact file is 64 MiB or less. A larger value becomes an omission marker.
- Raw vectors become `{"omitted": "vector data", "length": n}`.

## What the workspace never stores

- The contents of `.env` and provider credentials. Credential keys and credential text are redacted. The run service refuses inputs that hold a credential (`UnsafeInputError`).
- Vector data. Vectors stay in the configured vector store, for example a LanceDB directory.
- Your source documents. The records hold paths and identities, not full text. The exception is a file that you upload: it goes to `uploads/`.

A schema upgrade changes `workspace.db` only. It never migrates or rebuilds a vector store.

## Private permissions

On systems with POSIX permissions:

- The server creates missing workspace directories with mode `0700`.
- `workspace.db`, backups and artefact files get mode `0600`.
- Run artefact directories get mode `0700`.
- An existing directory keeps its mode, because you can choose a shared parent directory.

## Retention

The workspace keeps runs, events and artefacts until you remove them with an explicit cleanup. It has no automatic expiry.

## Interruption and retry

When the server starts, the run service marks each `queued`, `running` or `cancelling` run as `interrupted`. The event records the `previous_status`. The failure lists the effects that the run completed before it stopped. The service never repeats model calls, source replacement or deletion automatically.

To repeat a run:

1. Check the affected collection. An interrupted run can have changed the vector store before it stopped. Each source replacement is failure-safe, and the next ingestion processes an incomplete source again. See [Interrupted re-ingests resume](ingestion.md#interrupted-re-ingests-resume).
2. Call `omrs.core.workspace.RunService.retry` with the run identifier. Only `failed`, `cancelled` and `interrupted` runs accept a retry.
3. Read the new run. It has `origin` `retry` and the `source_run_id` of the original run. The original record does not change.

## Clean up old runs

Cleanup removes finished runs, their events and their artefact files. It has two steps:

1. Preview. Call `omrs.core.workspace.WorkspaceCleanup.preview_cleanup` with a selector. The preview lists each run, its event count and its artefact files, with totals. Nothing changes.
2. Confirm. Call `omrs.core.workspace.WorkspaceCleanup.apply_cleanup` with the preview token. The service removes only the listed items.

Use one of these selectors from `omrs.core.workspace.CleanupSelector`:

| Selector | Selects |
|---|---|
| `CleanupSelector.older_than(days)` | Finished runs that finished `days` days ago or earlier. |
| `CleanupSelector.by_status(*statuses)` | Finished runs with one of the statuses. |
| `CleanupSelector.run(run_id)` | One run. |

When you give more than one criterion, a run must match all of them.

<!-- cleanup-example -->
```python
from pathlib import Path

from omrs.core.workspace import CleanupSelector, WorkspaceCleanup, WorkspaceLayout
from omrs.integrations.workspace_sqlite import SqliteWorkspaceRepository

layout = WorkspaceLayout(Path.home() / ".omrs" / "workspace")
cleanup = WorkspaceCleanup.for_layout(SqliteWorkspaceRepository(layout.records), layout)

preview = cleanup.preview_cleanup(CleanupSelector.older_than(30))
print(preview.totals)
result = cleanup.apply_cleanup(preview.token)
print(result.runs_removed, result.files_removed, result.failed)
```

Stop the web server before you run this example. The server holds the workspace lock, and the cleanup service must use the same records as the server.

### Rules that keep cleanup safe

- Cleanup never selects an active run (`queued`, `running` or `cancelling`).
- Cleanup keeps a run when a kept run names it as its retry source. The preview lists the run under `skipped` with the reason.
- A token is single-use. It expires after 300 seconds.
- `apply_cleanup` repeats the preview. When a run, an event count or an artefact file changed, it rejects the token with the reason `stale` and removes nothing. Other reasons are `unknown`, `expired` and `selector`. After a rejection, make a new preview.
- The service removes the records first, in one transaction, then the files. A file that it cannot remove safely stays in place and appears in `failed`.
- The preview warns when it includes `interrupted` runs. Check source completeness before you remove their records.

### What cleanup never touches

Cleanup deletes rows in `workspace.db` and regular files in `artefacts/<run_id>/`. It never removes:

- pipelines, revisions or plugin registrations,
- uploads, source documents or `.env`,
- vector store directories, for example LanceDB or Chroma data,
- notebooks (`*.py` marimo notebooks and `*.ipynb` files),
- experiment `output/` directories.

Cleanup never follows a symbolic link. A link in `artefacts/`, or a link in place of `artefacts/` or a run directory, appears under `skipped` and stays. Cleanup also keeps files that are not regular files, and directories that have no run record.

Revisions stay after cleanup. They are immutable, and an explicit repeat of a saved revision needs them. Removing revisions needs a versioned schema migration with a backup; this release does not do that.
