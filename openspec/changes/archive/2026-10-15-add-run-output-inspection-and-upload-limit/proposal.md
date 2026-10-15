# Proposal

## Why

The redesign review found two places where the web workspace shows less than the server knows.

First, run output that is larger than a preview is cut, and nothing lets the user open the rest. The main spec `pipeline-run-records` ("Large output is inspected") requires a protected inspection reference. The server already writes the full, redacted value to a private artefact and puts its `artefact_ref` in the summary, but no route serves it and the run detail shows only "preview cut at 4 KiB".

Second, the upload limit is fixed at 50 MiB and nobody can change it. The server holds it in code, and the web client keeps its own copy. A user with larger files has no way to raise it, and if the two copies ever differ, the client refuses files the server would accept or passes files the server then refuses.

## Changes

- **Run artefact route**: `GET /v1/runs/{run_id}/artefacts/{name}` returns one stored, redacted artefact of a run with the same access policy as `GET /v1/runs/{run_id}`. A bearer credential bound to an experiment reads only artefacts of that experiment's runs. An unknown run, an unknown artefact, or a name that is not one path segment returns 404 or 400 without file system detail.
- **Open full output in the run detail**: every truncated preview in the Experiments run detail (node summaries, the stored result and evidence rows) offers "Open full output". It opens a dialog that shows the redacted value as plain text, with a stated display limit and a "Download" action for the whole artefact.
- **Upload limit in Settings**: the per-file limit becomes a workspace setting, saved in the workspace database, from 1 to 2048 MiB, default 50 MiB. `GET` and `PUT /v1/settings/upload-limit` read and change it; a change applies to new uploads at once, with no restart. Settings › Workspace gains an "Upload limit" panel to change it or return to the default.
- **Upload limit at launch**: `omrg web --max-upload-mib <n>`, or `WEB_MAX_UPLOAD_MIB` in the environment or `.env`, sets the limit when the web workspace cannot be used. A launch value wins over the saved one and locks the Settings panel for that run. `.env.example` and the CLI reference document it, and the CLI reference is brought up to date with every `omrg web` option.
- **Server is the only source of the limit**: the Knowledge Base reads the limit from that route, refuses larger files locally with a message that names it, and keeps no limit of its own. The client-side `MAX_UPLOAD_BYTES` constant is deleted.
- **OpenAPI** contract and guides updated for all of the above.

No behaviour is removed. With no saved value the limit stays 50 MiB.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `pipeline-run-records`: adds a requirement that truncated run output is readable in full through a protected route.
- `local-web-workspace`: adds requirements that the workspace opens truncated run output, that the upload limit is set in Settings, and that the workspace enforces the server's limit.

## Impact

- **Backend**: `src/omrg/transports/api/routes_runs.py` (new route reusing the run visibility check and `ArtefactStore.read_json`), `src/omrg/integrations/workspace_sqlite/settings.py` (new `upload_limit_mib` key), `src/omrg/transports/api/routes_mcp.py` (upload-limit routes beside the web port), `src/omrg/transports/api/uploads.py` and `lifespan.py` (saved limit at startup, one limit per upload), `openapi.yaml`, conformance tests.
- **Frontend**: `web/src/api/runs.ts`, `web/src/api/settings.ts`, `web/src/api/queries.ts`, `web/src/api/settingsMutations.ts`, the run detail components under `web/src/experiments/runs/`, a shared output dialog, a new `web/src/settings/UploadLimitPanel.tsx` in `WorkspaceSection`, `web/src/knowledge-base/UploadPanel.tsx`, `web/src/lib/uploadLimit.ts`, `web/src/lib/errors.ts`.
- **CLI**: `src/omrg/transports/cli/web.py` (`--max-upload-mib`, `WEB_MAX_UPLOAD_MIB`).
- **Docs**: `docs/guides/web-workspace.md`, `docs/guides/cli-reference.md`, `docs/guides/configuration.md`, `.env.example`, `src/omrg/transports/api/README.md`.
- **Dependencies**: none.
- **Order**: builds on `redesign-web-workspace` in the same worktree: its views and its `noLegacyResidue` and friendly-error rules.
