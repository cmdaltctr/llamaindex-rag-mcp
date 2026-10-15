# ADR-078: Upload Limit as a Workspace Setting, and a Run Artefact Route

- **Date:** 2026-10-15
- **Status:** Accepted (2026-10-15; evidence: `tests/unit/test_web_upload_limit.py` (22) and `tests/unit/test_web_run_artefacts.py` (14) pass; live server: bad launch values exit 2, `.env` value 300 locks Settings and PUT returns 409, a saved 200 MiB applies without restart and survives one, "Open full output" opens an 8,306-character step summary)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-075](075-omrg-owned-pipeline-runner-local-web-packaging-and-external-tool-plugins.md) (local web runtime), [ADR-077](077-web-workspace-client-foundation.md) (web client foundation)
- **Change:** `openspec/changes/archive/2026-10-15-add-run-output-inspection-and-upload-limit/` (design D1 to D4)

## Context

The per-file upload limit was fixed at 50 MiB. No flag, environment variable
or setting changed it, and the web client kept its own copy of the number.

The run detail cut long outputs for display. For node and status summaries
the server saved the full value as an artefact, but no route read it. When a
run finished, the server also cut each stored step summary and kept no full
copy. The `pipeline-run-records` spec requires every cut preview to be
marked and to open in full.

## Decision

1. **The upload limit is a saved workspace setting.** `WorkspaceSettings`
   stores `upload_limit_mib`, a whole number from 1 to 2048. A damaged value
   reads as unset. `GET /v1/settings/upload-limit` returns the limit in
   force, its source (`launch`, `saved` or `default`) and the range.
   `PUT` (browser session only) writes the database first, then changes the
   running limit. New uploads use the new limit at once. An upload in
   progress keeps the limit it started with.
2. **A launch value is the fallback and locks the limit.** For when the
   browser cannot be used, `omrg web --max-upload-mib <n>` or
   `WEB_MAX_UPLOAD_MIB` (from the environment or `.env`) sets the limit. The
   order is flag, then environment, then saved value, then 50 MiB. A launch
   value locks the limit for that run: `PUT` returns 409 with the way to
   unlock it, and the Settings panel shows no form. A bad launch value stops
   the command with exit code 2 before a port is bound.
3. **The server is the only source of the number.** The client reads the
   limit from the query and holds no copy. The 413 message names no number.
4. **Each stored run artefact has one route.**
   `GET /v1/runs/{run_id}/artefacts/{name}` (read scope) reads one artefact
   of the run in the path. It uses the existing run visibility check, so an
   invisible run answers as an unknown run. A name that fails the store's
   segment check gets 400 before any file access.
5. **A finished run keeps full step summaries.** When `finish()` cuts a step
   summary, it saves the full redacted value through
   `ArtefactStore.safe_summary`, and the stored summary carries
   `truncated: true` and `artefact_ref`.
6. **`.env` is read from the working directory.** `omrg.config` and
   `omrg.transports.mcp` call `load_dotenv(find_dotenv(usecwd=True))`. A bare
   `load_dotenv()` searched from the installed package, so an installed
   `omrg` ignored the user's `.env` for settings read straight from the
   environment.

## Consequences

### Positive

- The user changes the limit in Settings without a shell or a restart.
- The launch fallback works when the web workspace does not.
- The launch lock means a restart never undoes a Settings change in silence.
- Every cut preview, including finished step summaries, opens in full.

### Negative

- To change a limit set at launch, the user must remove the flag or
  variable and restart.
- One more read route on run data. It reuses the run visibility and store
  path checks.
- A limit of 2048 MiB lets one upload use a large part of the disk.

### Neutral

- `WEB_MAX_UPLOAD_MIB` is flat. The engine settings ignore unknown flat
  names, so they do not see it.
- The other `omrg web` options gain no environment variables.
- Rollback leaves a saved `upload_limit_mib` row that nothing reads.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Flag or environment variable only** | It needs a restart and a shell. It stays as the fallback. |
| **A launch value as a start value that Settings can change** | The next restart would undo the Settings change without telling the user. |
| **`WEB__MAX_UPLOAD_MIB`** | The nested delimiter belongs to `EffectiveSettings` blocks. `omrg web` options are not engine settings. |
| **`max_upload_bytes` on `GET /v1/session`** | The session is cached for the whole page, so a save would not reach the upload panel. |
| **Read the limit from the upload preflight** | The preflight needs a file name, and the panel states the limit before a file is chosen. |
| **`?ref=` query with the whole `artefact_ref`** | It would accept a run id different from the path and need a second ownership check. |
| **Narrow the spec to exclude finished step summaries** | The spec requires every cut preview to open in full. Saving the full value costs one artefact write. |

## References

- `src/omrg/integrations/workspace_sqlite/settings.py`, `src/omrg/transports/api/routes_mcp.py`, `src/omrg/transports/api/lifespan.py`, `src/omrg/transports/api/uploads.py`
- `src/omrg/transports/cli/web.py`, `src/omrg/config/__init__.py`, `src/omrg/transports/mcp/__init__.py`
- `src/omrg/transports/api/routes_runs.py`, `src/omrg/core/workspace/outcomes.py`
- `web/src/settings/UploadLimitPanel.tsx`, `web/src/experiments/runs/OutputViewer.tsx`
- `.env.example`, `docs/guides/cli-reference.md`, `docs/guides/configuration.md`, `docs/guides/web-workspace.md`
