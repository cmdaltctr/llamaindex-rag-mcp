# Design

## Context

Run output is cut in two different places today.

- **On the server.** `ArtefactStore.safe_summary` (`src/omrg/core/workspace/artefacts.py`) bounds node and status summaries to 16 KiB while a run is in progress. When a run finishes, `finish()` (`src/omrg/core/workspace/outcomes.py`) cut each stored step summary with `preview()` instead, kept no full copy and set no marker; this change routes it through `safe_summary` too. When it cuts one, it writes the full redacted value to `<artefacts>/<run_id>/<name>.json` (mode 0o600) and returns the summary with `truncated: true` and `artefact_ref: "<run_id>/<name>.json"`. `ArtefactStore.path` already refuses a reference that is not two safe segments or that leaves the store. Only `result_ref` is readable over HTTP, through `GET /v1/runs/{run_id}/result`. No route reads any other artefact.
- **In the browser.** The run detail renders the stored result and evidence through `SafeValue` and `boundText` (`web/src/runs/evidence.ts`), which cut text at 4 KiB and lists at 100 rows for display. The full value is already in memory, because `/result` returns it whole.

The upload limit is `WebConfig.max_upload_bytes` (default `DEFAULT_MAX_UPLOAD_BYTES`, 50 MiB, in `src/omrg/transports/api/uploads.py`). No CLI flag, environment variable or setting changes it today, so in practice it is always 50 MiB. `UploadStore.max_bytes` is read on every preflight and every streamed chunk. `POST /v1/uploads/preflight` already returns it as `max_bytes`. The web client keeps its own copy in `web/src/lib/uploadLimit.ts` and uses it in `UploadPanel` and in the 413 message in `web/src/lib/errors.ts`.

Settings already saves one server choice: the web port. `WorkspaceSettings` (`src/omrg/integrations/workspace_sqlite/settings.py`) stores typed keys in the `workspace_settings` table, `GET`/`PUT /v1/settings/web-port` in `routes_mcp.py` read and write it, and `WebPortPanel` edits it. A saved port applies at the next launch only, because the socket is already bound.

## Goals / Non-Goals

**Goals:**

- Every cut preview in the run detail leads to the full redacted value.
- The user sets the upload limit in Settings, and it applies without a restart.
- The limit can also be set at launch, through a flag or `.env`, for when the web workspace cannot be used.
- The server is the only source of the upload limit.

**Non-Goals:**

- Raising preview limits or changing what the server stores.
- A limit per collection or per user.
- Environment variables for the other `omrg web` options. Only the upload limit gains one here.
- Showing artefacts of other runs, or a general artefact browser.

## Decisions

### D1. One route per run artefact, addressed by name

`GET /v1/runs/{run_id}/artefacts/{name}` (read scope). The handler loads the run with the existing `_graph_run(runs, run_id, principal)` visibility check, so an invisible run answers exactly as an unknown run does. It then reads `runs.service.artefacts_for(run).read_json(f"{run_id}/{name}.json")`. `name` must pass the store's own segment check before any file access. The response is `{ "status": "ok", "run_id", "name", "value" }`. A missing file returns 404 "This run has no such output.". A refused name returns 400 with a fixed message.

Alternative considered: a `?ref=` query that takes the whole `artefact_ref`. Rejected, because it would accept a run id that differs from the path and needs a second ownership check. With the name as one path segment, the run in the path is the only run that can be read.

The client derives `name` from `artefact_ref` and checks that its run part equals the run being shown. A reference that does not match is shown as cut, with no action.

### D2. In-memory values need no route

For the stored result and evidence rows, the browser cut the text itself and already holds the full value. "Open full output" passes that value straight to the viewer. Only node and status summaries with an `artefact_ref` fetch through D1, on demand, when the user opens them. Nothing is prefetched.

### D3. One shared output viewer

A `OutputViewer` dialog on the `Dialog` primitive shows the value as `JSON.stringify(value, null, 2)` in a `<pre>` text node, after the same client-side masking `SafeValue` uses (`web/src/runs/redact.ts`), so the client masks even values that never passed the server. It shows at most 256 KiB of text and then states that the rest is not shown. "Download" builds a `Blob` from the full text, names it `run-<run_id>-<name>.json`, and revokes the object URL after the click. Load failures go through `ErrorNotice` with Retry.

### D4. The upload limit is a workspace setting that applies at once

**Storage.** `WorkspaceSettings` gains the key `upload_limit_mib` with `get_upload_limit_mib()` and `set_upload_limit_mib(mib | None)`. The range is 1 to 2048 MiB (`MIN_UPLOAD_LIMIT_MIB`, `MAX_UPLOAD_LIMIT_MIB`). A stored value that does not parse or is out of range reads as unset, as a damaged port does. Whole MiB keep the form and the stored text simple.

**Launch option.** `omrg web` gains `--max-upload-mib` (`envvar="WEB_MAX_UPLOAD_MIB"`), a text option checked by a callback that accepts only a whole number from 1 to 2048, so `1.5` is refused instead of rounded. Typer reads the flag first and the environment second. `.env` reaches the environment because `omrg.config` calls `load_dotenv(find_dotenv(usecwd=True))` on import, before options are parsed. The `usecwd` search reads the `.env` in the directory where the command starts, as the engine settings do. A bare `load_dotenv()` searches from the installed package instead. The name is flat, as cross-cutting names such as `PDF_READER` are; `Settings` ignores unknown flat names, so the engine settings do not see it. A bad value fails the launch with Typer's usage error (exit code 2), which names the option, its environment variable and the range, before any port is bound. The value goes to `WebConfig.launch_upload_limit_mib` (`int | None`).

This mirrors `--port`: a launch value beats a saved one. The difference is that the saved port waits for the next launch, while the launch upload limit locks the running limit, so Settings cannot silently fight it.

**Startup.** `_owned_runtime` picks the limit in this order: `config.launch_upload_limit_mib`, then the saved value, then `config.max_upload_bytes` (50 MiB unless a test sets it). It records the source as `launch`, `saved` or `default` on the runtime. The saved value is read from the same database `McpHttp.settings` uses. When `mcp_http` is absent (some tests), the saved step is skipped.

**Routes.** Beside the web port in `routes_mcp.py`:

- `GET /v1/settings/upload-limit` (read scope) returns `{status, max_bytes, source, saved_mib, default_mib, min_mib, max_mib}`. `max_bytes` is the limit in force. The range travels in the response, so the client holds no copy of it.
- `PUT /v1/settings/upload-limit` (session-only `manage` scope, like the web port) takes `{max_mib: int | null}` with `extra="forbid"` and `StrictInt` bounds. With `source: "launch"` it answers 409 "The upload limit was set when the server started. Remove --max-upload-mib or WEB_MAX_UPLOAD_MIB and restart to change it here." and changes nothing. Otherwise it writes the database first, then sets `runtime.uploads.max_bytes` and the source, then returns the same body as `GET`. A failed write changes nothing.

**In-flight uploads.** `UploadStore.receive` reads `self.max_bytes` once at the start and uses that value for its preflight and for every chunk. A change during an upload therefore affects only later uploads. `preflight` takes the limit as a parameter for this.

**Client.** `uploadLimitQuery` and `useSetUploadLimit` join `api/queries.ts` and `api/settingsMutations.ts`; the mutation declares `["settings", "upload-limit"]` as its invalidation. A new `UploadLimitPanel` sits in Settings › Workspace. It states the limit in force and its source. With `source: "launch"` it shows no form and says the limit was set when the server started, naming the flag and the variable. Otherwise it takes a whole number of MiB, checks it against `min_mib`/`max_mib` from the response before sending, and offers "Use the default (50 MiB)" when a value is saved. Its help line says the change applies to new uploads straight away. `UploadPanel` reads the same query, shows "Limit: <n> MiB per file", and refuses larger files locally with that number. When the query has not loaded or failed, the panel shows no number and skips the local check. The server's preflight and 413 still refuse oversized files.

`describeError` cannot know the limit, so its 413 text becomes "That file is larger than the server's per-file limit and was not uploaded." `UploadPanel` keeps its own refusal line, which names the number. `web/src/lib/uploadLimit.ts` keeps only `formatMiB`, and `MAX_UPLOAD_BYTES` and `UPLOAD_LIMIT_LABEL` are deleted. The `noLegacyResidue` guard gains a rule for those two names.

Alternatives considered:

- An environment variable or flag as the only control. Rejected: it needs a restart and a shell. It stays as the fallback for when the web workspace cannot be used.
- A launch option as a starting value that Settings may still change. Rejected: the next restart would silently undo the Settings change, and the user would not know which value wins.
- A nested name such as `WEB__MAX_UPLOAD_MIB`. Rejected: the nested delimiter belongs to `EffectiveSettings` blocks, and `omrg web` options are not engine settings.
- `max_upload_bytes` on `GET /v1/session`. Rejected: the session is cached for the whole page, so a save in Settings would not reach the upload panel without extra invalidation of an unrelated query. A dedicated query is invalidated by its own mutation.
- Calling the preflight to learn the limit. Rejected: the preflight needs a file name, and the panel should state the limit before a file is chosen.

## Risks / Trade-offs

- [An artefact can hold up to 64 MiB, which is heavy for a browser tab] → The value loads only when the user opens it, the viewer renders at most 256 KiB, and Download covers the rest.
- [A new route widens the run read surface] → It reuses the run visibility check and the store's path checks unchanged, and tests cover a bound credential reading another experiment's artefact.
- [Masking in the browser can hide a value the user wanted to see] → It masks the same keys as the existing run detail, and the server already redacted the stored value, so the result matches what the run detail shows today.
- [A large limit lets one upload fill the disk] → The ceiling is 2048 MiB, only a browser session can raise it, and the server stays loopback-only. The user owns the disk.
- [Another browser tab can hold an old limit] → The server checks every upload against the limit in force, so an old number in a tab can only refuse early or pass a file to a server that then refuses it with 413.

## Migration Plan

None. The changes are additive: two new routes, one new setting key in an existing table, no schema change. With no saved value the limit stays 50 MiB. Rollback is reverting the change; a saved `upload_limit_mib` row is then ignored, because `WorkspaceSettings` only reads known keys.
