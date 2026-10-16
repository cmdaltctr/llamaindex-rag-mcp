# Web workspace

`omrg web` starts a local browser workspace for OMRG. It serves the application and the `/v1` HTTP API from one loopback address. This guide tells you how to install it, start it, sign in, give it file access, follow long work, and stop it.

The web workspace is for one user on one machine. It does not accept remote connections.

Related guides:

- [Local workspace](workspace.md): the workspace folder, its records, retention and cleanup.
- [Pipeline graphs](pipelines.md): graph documents, operations and validation.
- [Notebooks](notebooks.md): the optional marimo notebook plugin and its trust model.
- `src/omrg/transports/api/README.md`: the API package, scopes and contract checks.
- `src/omrg/transports/api/openapi.yaml`: the full HTTP contract.

## Install the web extra

The web workspace needs FastAPI and Uvicorn. They are in the optional `web` extra. The base install does not include them.

In a checkout:

```bash
uv sync --extra web
```

From a package index:

```bash
pip install "omrg[web]"
```

The wheel contains the built application files. You do not need Node or npm to run `omrg web`.

Without the extra, only `omrg web` fails. It writes this message to stderr and exits with code 1:

<!-- web-missing-extra -->
```text
The web workspace needs the optional "web" extra. Install it with: pip install "omrg[web]"  (or, in a checkout: uv sync --extra web)
```

`import omrg`, `omrg --help`, the MCP server and the other `omrg` commands work without the extra.

## Start the server

```bash
omrg web --root ~/papers
```

The command writes a link to stderr. It writes nothing to stdout. Open the link in your browser:

```text
OMRG web workspace. Open this link in your browser (it works once):
http://127.0.0.1:<port>/#bootstrap=<secret>
Press Ctrl+C to stop.
```

### Options

<!-- web-options -->
| Option | Default | Use |
|---|---|---|
| `--workspace PATH` | `~/.omrg/workspace` | Directory for application records, run artefacts and uploads. |
| `--port N` | the saved port, else `8765` | TCP port to listen on. `0` picks a free port. |
| `--host ADDR` | `127.0.0.1` | Loopback address only: `127.0.0.1`, `::1` or `localhost`. |
| `--root DIR` | none | Approve a directory for file access. Repeat the option for more directories. |
| `--experiment-root DIR` | none | Approve a directory below which you can register experiment workspaces. Repeat the option for more directories. |
| `--allow-origin ORIGIN` | none | Approve one extra loopback browser origin for this run, for example `http://name.orca.localhost:57977`. Repeat the option for more origins. |
| `--max-upload-mib MIB` | saved limit, else `50` | Per-file upload limit in whole MiB, 1 to 2048. Also read from `WEB_MAX_UPLOAD_MIB`. It locks the limit in Settings for this run. |
<!-- /web-options -->

Rules for the options:

- A non-loopback address, for example `0.0.0.0` or a LAN address, stops the command with exit code 2.
- A `--root` or `--experiment-root` that is missing, or that is not a directory, stops the command with exit code 2.
- An `--allow-origin` value that is not an exact `http` or `https` loopback origin stops the command with exit code 2 before it binds a port. The message names the rule that failed.
- A busy port (from `--port`, the saved port or the default) stops the command with exit code 1. The message names the port, `--port <n>` and Settings > MCP.
- The server runs as one process. Automatic reload is off.

### One server for each workspace

At startup the server takes a lock on the workspace. A second `omrg web` with the same `--workspace` stops with this message on stderr and exit code 1:

```text
Another OMRG web server is using the workspace <path>. Stop it, or start this one with a different --workspace.
```

`GET /v1/session` returns the workspace path that the server uses, in the `workspace` field. The Workspace section of Settings shows it.

## Sign in

The browser uses a session. A notebook or a script uses a bearer credential.

### Browser session

1. The launch link carries a one-time secret in its `#bootstrap=` fragment. The browser does not send a fragment to the server, so the secret stays out of the access log.
2. The page reads the fragment, removes it from the address bar, and sends it to `POST /v1/session`.
3. The server sets the cookie `omrg_session_<port>`. The cookie is HttpOnly and SameSite=Strict.

The link works once. After 20 wrong guesses, the secret stops working. To get a new link, restart `omrg web`.

The session holds every scope. A `POST`, `PUT`, `PATCH` or `DELETE` request with the cookie must also carry the application `Origin`.

### Bearer credentials for notebooks and scripts

A browser session issues bearer credentials:

```http
POST /v1/credentials
{"scopes": ["read", "graph", "run"], "label": "notebook"}
```

The response shows the token once, in the form `omrg_bt_<id>.<secret>`. Send it as `Authorization: Bearer <token>`. The server keeps only a digest of the secret.

- List credentials with `GET /v1/credentials`.
- Revoke one with `DELETE /v1/credentials/{credential_id}`. The revocation applies to the next request.
- All credentials stop when the server stops.

A bearer credential can hold only these scopes:

| Scope | Allows |
|---|---|
| `read` | Collections, search, answer, chunks, jobs, pipelines, runs and events. |
| `graph` | Create pipelines, save layouts and revisions, validate graphs. |
| `run` | Submit, cancel and retry graph runs. |

These scopes are session only. A bearer credential cannot hold them:

| Scope | Allows |
|---|---|
| `files` | Roots, uploads, ingestion jobs and codebase-map jobs. |
| `credentials` | Issue, list and revoke bearer credentials. |
| `manage` | Deletion, profile change, workspace cleanup, experiment folders and registration, connection tests and the server log. |
| `plugins` | Notebook plugin registration, recheck and editor launch. |

A credential that you issue with `experiment_context` is bound to that experiment. It runs graphs only in that experiment and cannot read or change the live library. See [Notebooks](notebooks.md).

### Request checks

The server checks every request before any route runs:

- The `Host` header must be a loopback name with the bound port. Otherwise the server returns 400.
- On `/v1` paths, a foreign `Origin` or a cross-site fetch gets 403. An origin is not foreign when it is the server's own loopback address or one that you approved with `--allow-origin`.
- A credential in the query string gets 400. Put credentials in a header or the cookie.

`GET /v1/health` and `POST /v1/session` are the only public `/v1` operations.

#### Use an embedded preview

Some preview panes, for example the Orca browser preview, serve the workspace page from their own address. The server then refuses the sign-in with 403, and the page shows "The workspace session was not accepted".

1. Copy the origin from the address bar of the preview. It has the form `http://<name>.orca.localhost:<port>`.
2. Start the server with `omrg web --allow-origin <origin>`.
3. Open the link that the command prints, in the preview.

The option approves that one origin for this run only. The host must be `localhost`, a `.localhost` name, `127.0.0.1` or `[::1]`. A wildcard, a path or any other host stops the command. The option does not change the `Host` check or the cookie rules. The preview can change its port, or the number at the end of its host name, when it reopens. If the sign-in fails again with 403, copy the new origin and start the server again. You can repeat `--allow-origin` to approve several host names in one launch.

## Give file access

The server reads files only below approved roots. It never accepts an arbitrary server path from the browser.

1. Start the server with one `--root` for each directory that it can read.
2. `GET /v1/roots` lists the approved roots and the managed upload root.
3. Give an absolute path inside an approved root to an ingestion job.

The server resolves each path, including symbolic links, before it reads it. A path that escapes its root gets 403 before any work starts. A source path in the index does not grant access to the original file. You can still inspect the stored chunks of that source.

### Upload files

Uploads go into the managed `uploads/` directory of the workspace.

1. Send `POST /v1/uploads/preflight` with `{"name": "report.pdf", "size": 1048576}`. Nothing is stored.
2. Send `POST /v1/uploads` with the raw file body. Put the percent-encoded file name in the `X-Upload-Name` header.
3. Ingest the upload by its path below the managed root.

Upload rules:

- The limit is 50 MiB for each file by default. The server also counts bytes while it receives them. To change the limit, see [Set the upload limit](#set-the-upload-limit).
- The file name must be a plain name. Separators, control characters, hidden names and URL schemes get 400.
- The extension must be one that OMRG can ingest. Archives and other types get 415. A file over the limit gets 413.
- The server writes to a private partial file first. A failed or cancelled upload leaves no partial file.
- The response gives the upload `id`, `name`, `size` and `sha256`. It never gives the server path.

The initial release does not ingest from URLs.

### Set the upload limit

The per-file limit is a workspace setting, from 1 to 2048 MiB. The server uses the first value in this order:

1. `omrg web --max-upload-mib <n>`.
2. `WEB_MAX_UPLOAD_MIB` in the environment or `.env`.
3. The value saved in Settings > Workspace.
4. 50 MiB.

`GET /v1/settings/upload-limit` (`read`) returns the limit in force:

```json
{"status": "ok", "max_bytes": 52428800, "source": "default", "saved_mib": null,
 "default_mib": 50, "min_mib": 1, "max_mib": 2048}
```

`source` is `launch`, `saved` or `default`. To change the limit, send `PUT /v1/settings/upload-limit` with `{"max_mib": 200}`. To return to the default, send `{"max_mib": null}`. This request needs the browser session.

- The server saves the value first. Then it applies the value to new uploads at once, with no restart.
- An upload in progress keeps the limit it started with.
- A value that is not a whole number from 1 to 2048, or an extra field, gets 422. Nothing changes.
- When a launch option set the limit, the request gets 409 and nothing changes. Remove the option and restart to change the limit in Settings.

## Jobs and graph runs

Long work is admitted as a job or a graph run. Both use one persisted run service with one consumer. At most 16 items can wait. A full queue gets 429.

| Work | Start | Response | Follow |
|---|---|---|---|
| Ingestion job | `POST /v1/ingestions` | 202 with a job | Poll `GET /v1/jobs/{jobId}` |
| Codebase-map job | `POST /v1/codebase-maps` | 202 with a job | Poll `GET /v1/jobs/{jobId}` |
| Graph run | `POST /v1/runs` | 202 with a run record | Poll `GET /v1/runs/{run_id}`, or read its events |

A job status is `queued`, `running`, `completed` or `failed`. A graph run status is `queued`, `running`, `cancelling`, `succeeded`, `failed`, `cancelled` or `interrupted`.

The server validates a graph run before it admits it. An invalid graph or input gets 422 with one issue for each problem, and no run starts. To stop a run, send `POST /v1/runs/{run_id}/cancel`. To run a failed, cancelled or interrupted run again, send `POST /v1/runs/{run_id}/retry`.

### Read run events

The server stores each event before a client sees it. Each event has a sequence number.

- **Polling.** `GET /v1/runs/{run_id}/events?after_sequence=N` returns the next page. Use `last_sequence` from the response as the next `after_sequence`. `complete` is true when the run has ended and no event is left.
- **Server-sent events.** `GET /v1/runs/{run_id}/events/stream` returns `text/event-stream`. After a reconnection, the browser sends `Last-Event-ID`, and the stream replays the later events. If you cannot set the header, use `?after=N`. The stream ends with `run.end`, or with `server.closing` when the server stops.

The browser removes duplicate events by sequence number. If the stream fails, the browser polls.

Closing a stream does not cancel the run. Only the cancel route cancels a run.

### Read full run output

An event, status or node summary larger than 16 KiB is cut. The server keeps the full value, with credentials and raw vectors removed, in a private artefact. The cut summary has `truncated: true` and `artefact_ref: "<run_id>/<name>.json"`.

1. Take `<name>` from `artefact_ref`. Remove the run id and `.json`.
2. Send `GET /v1/runs/{run_id}/artefacts/{name}`.
3. Read the full value in `value`.

The route has the same access rule as `GET /v1/runs/{run_id}`. A run that you cannot read gets 404 `Unknown run.`. An unknown name gets 404 `This run has no such output.`. A name that is not one plain path segment gets 400, and the server reads no file.

## Confirm destructive actions

Deletion, collection profile change and workspace cleanup use two requests:

1. Send a preview. It changes nothing. It returns the effect and a single-use token.
2. Send the same selector again with the token.

The token is bound to the action, the selector and the store state that the preview saw. It expires after 300 seconds. A missing token gets 428. A used, expired, altered or stale token gets 409, and nothing changes. Then make a new preview.

Some vector stores give only a process-local validity token. Then the preview says so in `confirmation.validity` and `confirmation.warning`: a change from another process can go undetected.

A confirmed profile change applies to new queries. Existing chunks stay as they are until you ingest again.

| Action | Preview | Confirm |
|---|---|---|
| Delete documents or a collection | `DELETE /v1/collections/{collection}/documents` with `dry_run: true` | The same request with `confirmation_token` |
| Change a collection profile | `PATCH /v1/collections/{collection}/profile` with `confirm: false` | The same request with `confirm: true` and `confirmation_token` |
| Clean up old run records | `POST /v1/workspace/cleanup/preview` | `POST /v1/workspace/cleanup` with the token |

Cleanup removes run records and run artefacts only. It never removes vector data, source files, uploads, notebooks or experiment outputs. See [Clean up old runs](workspace.md#clean-up-old-runs).

Changing a display name needs the browser session but no preview and no token. It changes only a label, loses no data and can be undone by saving the old value.

## Errors never return HTML

Every `/v1` error uses the JSON envelope `{"status": "error", "message": "..."}`. Some errors add `error_type` (`validation`, `retrieval` or `internal`) or `issues`.

- An unknown `/v1` path gets 404 with the envelope. The application page never answers a `/v1` path.
- An unexpected server error gets 500 with the message `Internal server error.` and no detail.
- Messages never contain stack traces or credential values. The server log removes credentials and configured provider secrets.

Paths outside `/v1` belong to the application. A missing asset file gets a plain 404. When the application files are not built, `/` returns a message that names `npm ci && npm run build`. The API still works.

## MCP over HTTP

The server can serve MCP at `/mcp`. It is off by default. Turn it on with `PUT /v1/mcp` (Settings > MCP). `POST /v1/mcp/token` creates or rotates the one token. `DELETE /v1/mcp/token` revokes it. `PUT /v1/settings/web-port` saves the port for the next launch. These changes need the browser session. Client set-up and the request checks: [MCP tools](mcp-tools.md#connect-a-client).

## Integrations, connections and the server log

These routes show the state of the running server. They change no setting and install no package.

| Route | Scope | Returns |
|---|---|---|
| `GET /v1/integrations` | `read` | One entry for each installable extra and for Magika. `availability` is `available`, `not-installed` or `unknown` (a probe failed). Each entry has copy-ready `install_command` and `pip_command` values. |
| `GET /v1/connections` | `read` | `config_dir` (the server working directory, where the settings read `.env`) and one entry each for `ollama`, `llamacpp` and `openrouter`: endpoint URLs, model names, `key_set` and the roles that use the provider. The key value is never returned. A change to `.env` needs a server restart. |
| `POST /v1/connections/{provider}/test` | `manage` | `{reachable, reason}` after one model-list request with a 5-second timeout. `reason` is `refused`, `timeout`, `unauthorised`, `http-<status>` or `not-configured`. No response body or error text is returned. |
| `GET /v1/logs?after=<seq>` | `manage` | The buffered log records after a sequence. |
| `GET /v1/logs/stream` | `manage` | The same records as server-sent events, with replay after `Last-Event-ID` or `?after=`. The stream ends with `server.closing`. |

The server keeps the last 1,000 log records in memory and writes no log file. The filter that removes provider keys and credentials runs before a record is stored.

`POST /v1/experiment-folders` (scope `manage`) creates a directory below an approved experiment root. `GET /v1/experiments` returns the folder tree of each root in `folders`.

## Stop the server

Press Ctrl+C in the terminal that runs `omrg web`. The server then:

1. stops new admission and ends open event streams with `server.closing`. An open MCP stream is closed after 5 seconds,
2. cancels queued work,
3. asks active runs to stop at a safe point and waits for active writes to finish,
4. stops notebook editors that it started,
5. closes the experiment engines and the Engine.

Closing the browser does not stop the server or cancel runs.

If the process stops without this sequence, for example after a crash, unfinished runs show `interrupted` at the next start. The server does not retry them. Check source completeness before you run the work again.

## Screens

The workspace has seven areas. Use the navigation on the left to open an area. The OMRG logo and name sit at the top of the navigation. Use the button next to them to collapse the navigation to a column of icons. In the collapsed column, the button sits under the logo. The browser remembers the choice. Under 768 px the navigation becomes one row of icons under the top bar. The top bar shows the collection count and one button that switches between Light and Dark. Choose System, Light or Dark in Settings.

Every area has its own address. Back and forward move between them. An address that the app does not know opens Home.

| Area | Address | What you can do |
|---|---|---|
| Home | `#/home` | See every project as a card with its title, profile, counts and database. Open a project. |
| Chat | `#/chat/<collection>` | Pick a knowledge base by its title and ask it a question. Read the answer, its citations and the evidence. Each question answers on its own. |
| Knowledge Base | `#/knowledge-base/<collection>` | Rename the project title with the pencil. See the database that holds the project (logo and name in the header, name in the project list and in the Sources table). List sources, upload and ingest files, ingest from an approved folder, search, preview and confirm a deletion or a profile change. The upload panel shows the server's per-file limit and refuses a larger file before it is sent. Change the limit in Settings › Workspace. |
| Studio | `#/studio`, `#/studio/<pipeline-id>` | Start a pipeline from a template, a profile preset or an empty graph. Add operations, connect ports, save a revision, validate, run and cancel. |
| Experiments | `#/experiments`, `#/experiments/runs/<run-id>` | Create experiment folders and sub-experiments, issue a bound credential, register and open the notebook editor, and read pipeline runs. A preview that is cut offers Open full output, which shows the redacted value as text and downloads it. |
| Integrations | `#/integrations` | See which optional parts are installed and copy the command that installs the rest. The page never installs anything. |
| Settings | `#/settings` | Read the provider connections and test them, read the server log, copy the MCP client configuration, manage MCP access over HTTP, and set the per-file upload limit. |

The screenshots show a local server with small Markdown sources. The run output screenshot shows a search result passage that is longer than the 4 KiB preview.

| Area | Light | Dark |
|---|---|---|
| Home | [image](images/web-workspace/home-light-1280.png) | [image](images/web-workspace/home-dark-1280.png) |
| Chat | [image](images/web-workspace/chat-light-1280.png) | [image](images/web-workspace/chat-dark-1280.png) |
| Studio gallery | [image](images/web-workspace/studio-gallery-light-1280.png) | [image](images/web-workspace/studio-gallery-dark-1280.png) |
| Studio canvas | [image](images/web-workspace/studio-canvas-light-1280.png) | [image](images/web-workspace/studio-canvas-dark-1280.png) |
| Experiments | [image](images/web-workspace/experiments-light-1280.png) | [image](images/web-workspace/experiments-dark-1280.png) |
| Integrations | [image](images/web-workspace/integrations-light-1280.png) | [image](images/web-workspace/integrations-dark-1280.png) |
| Run output | [image](images/web-workspace/run-output-light-1280.png) | [image](images/web-workspace/run-output-dark-1280.png) |
| Settings › Workspace | [image](images/web-workspace/settings-light-1280.png) | [image](images/web-workspace/settings-dark-1280.png) |

![Studio canvas with the Search template](images/web-workspace/studio-canvas-light-1280.png)

On a phone, the areas use one column. Two examples at 390 px: [Home](images/web-workspace/home-light-390.png) and the [Studio canvas](images/web-workspace/studio-canvas-light-390.png).

### Studio canvas layout

On a pipeline canvas (`#/studio/<pipeline-id>`), the flow surface fills the whole main area. The workspace navigation shows as an icon column. Select "Expand navigation" to open it for this visit only. The stored navigation choice does not change, and the next canvas visit starts collapsed again.

One panel floats over the right side of the canvas. It holds six sections. Each section has its own icon.

1. Pipeline settings (Title, Profile and Collection).
2. Operations.
3. Nodes and connections.
4. Connect ports.
5. Revision and run.
6. Node settings.

You can open several sections at the same time. At first, only Operations is open. When you select a node, Node settings opens. When you start a run from the panel, Revision and run opens. Closing a section does not change the draft.

Select "Collapse panel" to shrink the panel to a narrow icon rail. Each rail button shows a tooltip with its section name. A highlighted button means that its section is open. Select a rail button to expand the panel with that section open. Collapsing the panel does not change the draft, the selection or the open sections.

![Studio canvas with the panel collapsed to the icon rail](images/web-workspace/studio-canvas-rail-light-1280.png)

On a window narrower than 1024 px, the panel sits under the flow surface and shows its sections. The icon rail is not available.

### Database and profile in the Knowledge Base

Each collection lives in one vector database. The workspace shows it in four places:

1. The project header and the Home card show the logo and the name, for example LanceDB.
2. The project list shows the name only.
3. The Sources table has a Database column with the name only.
4. `GET /v1/collections` returns `store` for each collection, with `name` (for example `lancedb`) and `label` (for example `LanceDB`). It never returns a path, a tenant or a key.

The label comes from the vector-store registry (`register(..., label=...)`). A backend without a label shows its registered name. The logo is a PNG in `web/public/integrations/vector-stores/`, named after the registered backend, for example `web/public/integrations/vector-stores/lancedb.png`. When the file is missing, the workspace shows the name only. To add a database, add its module, one `register()` call and one PNG.

The Profile tab shows the stored profile as a badge. When a collection has no stored profile, the badge reads "No profile". The "New profile" list starts on the stored profile. When none is stored, it starts empty and "Preview profile change" stays disabled until you choose a profile.

### Display name and collection name

A project has two names. The collection name is the storage address. MCP tools, the CLI, the API and the address bar use it, so it never changes. The display name is a label for the workspace.

1. Click the pencil next to the project title in the Knowledge Base. Type a name and press Enter to save. Press Escape to cancel. Save an empty value to remove the display name.
2. The Home card, the project list in the Knowledge Base and in Chat, and the project title show the display name. Without one, they show the collection name.
3. The line `Collection name: <name>` always shows the real name. It sits under the project title and under the counts on each Home card. Use it in MCP, CLI and API calls.
4. "Sources in <name>", the Chat question box and the delete dialog keep the collection name, because you may need to type or match it.
5. A display name has at most 80 characters, counted as Unicode code points, and no control characters. The server removes spaces at both ends.
6. The route is `PATCH /v1/collections/{collection}/display-name` with `{"display_name": "..."}`. It returns `{"collection", "display_name"}`, and `display_name` is `null` after a clear. It needs the browser session. A bearer credential gets 403. An unknown collection gets 404 and nothing is created.

The name is stored in the collection metadata, next to the profile. On LanceDB a change creates a new table version. The next keyword search rebuilds its index, and an open delete or profile preview must be made again.

Keyboard use on the Studio canvas:

1. Press Tab to move through the panel section headers and the controls in each open section. Press Enter or Space on a header to open or close its section.
2. On a node, press Enter to select it. Use the arrow keys to move it. Press Delete to remove it.
3. Use the Nodes and connections section and the Connect ports section to edit the graph without a pointer.

Third-party notices for the bundled application are in `web/THIRD_PARTY_NOTICES.md`.

## Optional parts

| Part | Needed for | Install |
|---|---|---|
| `web` extra | `omrg web` | `uv sync --extra web` or `pip install "omrg[web]"` |
| Experiment roots | Experiment workspaces and notebook runs | `omrg web --experiment-root DIR` |
| marimo | The notebook editor | Outside OMRG. See [Notebooks](notebooks.md). |

The workspace works without marimo. The Notebooks section of the Experiments area then shows how to install and register it.
