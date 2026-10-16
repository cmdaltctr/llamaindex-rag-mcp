# HTTP transport (`omrg web`)

This package is the optional local HTTP runtime of OMRG. It serves the web
workspace and the `/v1` API from one origin. `openapi.yaml` is the versioned
OpenAPI 3.1 contract for the API. Tests compare the contract with the
running routes, so the two cannot drift apart.

## Start the server

1. Install the web extra: `uv sync --extra web` (or `pip install "omrg[web]"`).
2. Run `omrg web`.
3. Open the URL that the command writes to stderr.

Options:

| Option | Default | Use |
| --- | --- | --- |
| `--workspace PATH` | `~/.omrg/workspace` | Folder for run records, artefacts and uploads |
| `--port N` | saved port, else 8765 | Loopback port. `0` picks a free port |
| `--host ADDR` | `127.0.0.1` | Loopback address only (`127.0.0.1`, `::1`, `localhost`) |
| `--root DIR` | none | Folder that the server can read. Repeat for more folders |
| `--experiment-root DIR` | none | Folder below which experiment workspaces can be registered. Repeat for more folders |
| `--max-upload-mib MIB` | saved limit, else 50 | Per-file upload limit in whole MiB, 1 to 2048. Also read from `WEB_MAX_UPLOAD_MIB` |

The server refuses a non-loopback address. The command writes nothing to
stdout. One `omrg web` process can use a workspace at a time.

Without the web extra, `omrg web` tells you how to install it. Other `omrg`
commands, the MCP server and `import omrg` do not need the extra.

`docs/guides/web-workspace.md` is the user guide for launch, sign-in, file
grants, jobs and shutdown. `docs/guides/notebooks.md` covers the optional
notebook plugin.

## Files in this package

| File | Purpose |
| --- | --- |
| `openapi.yaml` | The HTTP contract: routes, schemas, errors, scopes and job semantics |
| `app.py` | `create_app()`: builds the application and registers every router |
| `lifespan.py` | Owns one Engine and the run service; drains them at shutdown |
| `security.py`, `middleware.py` | Session, bearer credentials, scopes, Host and Origin checks, redaction |
| `grants.py`, `uploads.py` | Approved roots and managed uploads |
| `routes/` | Route groups, one module each. They validate, delegate and format only |
| `integrations_catalogue.py` | The integration catalogue and its availability probes (`GET /v1/integrations`) |
| `connection_probe.py` | The one model-list request of a provider test (`POST /v1/connections/{provider}/test`) |
| `log_buffer.py` | The in-memory server log (last 1,000 records, redacted); `omrg web` attaches it |
| `runs_wiring.py` | Builds the workspace run service for graph runs and document jobs |
| `static.py` | Serves the built frontend; never answers a `/v1` path with HTML |

Routes contain no RAG logic. They call the Engine, core functions and the
workspace services.

## Access

The server checks every request:

- The `Host` header must be a loopback name for the bound port. Otherwise the server returns 400.
- On `/v1` paths, a foreign `Origin` or a cross-site fetch gets 403.
- A credential in the query string gets 400.

There are two credentials:

1. **Browser session.** The launch URL carries a one-time bootstrap secret in
   its `#bootstrap=` fragment. The page sends it to `POST /v1/session`. The
   server then sets the cookie `omrg_session_<port>` (HttpOnly,
   SameSite=Strict). The session holds all scopes. A `POST`, `PUT`, `PATCH`
   or `DELETE` with the cookie must carry the application Origin.
2. **Bearer credential.** A session issues it with `POST /v1/credentials`.
   Notebook clients send `Authorization: Bearer omrg_bt_<id>.<secret>`. The
   server keeps only a digest. Revoke it with
   `DELETE /v1/credentials/{credential_id}`. All credentials stop when the
   server stops.

`GET /v1/health` and `POST /v1/session` are the only public operations.

## Scopes

Each operation in `openapi.yaml` names its scope in `x-omrg-scopes`. Its
`security` list shows the credentials that can use it. When the list holds
only `sessionCookie`, the operation is session only.

| Scope | Bearer can hold it | Operations |
| --- | --- | --- |
| `read` | yes | Session, collections, search, answer, chunks, jobs, operations, templates, pipelines, runs, events, integrations, connections |
| `graph` | yes | Create pipelines, save layouts and revisions, validate graphs |
| `run` | yes | Submit, cancel and retry graph runs |
| `files` | no | Roots, uploads, ingestion and codebase-map jobs |
| `credentials` | no | Issue, list and revoke bearer credentials |
| `manage` | no | Deletion, profile change, workspace cleanup, experiment folders and registration, connection tests and the server log |
| `plugins` | no | Plugin registration, recheck, removal, and editor open and stop |

`GET /v1/session` returns the credential kind, its scopes and the
`workspace` path that the server uses. Each `GET /v1/collections` item also
gives the stored `profile` name, or `null` when the collection has no profile
tag.

## Errors

Every error uses the MCP error shape: `{"status": "error", "message": "..."}`.
`error_type` is optional (`validation`, `retrieval` or `internal`).

- A body, query or header that does not match its schema gets 400 with `error_type: validation`.
- A graph document or cleanup selector that core rejects gets 422. The body adds `issues`, one per problem.
- An unknown `/v1` path gets 404 with this shape. It never gets the application HTML.
- Messages never contain stack traces or credential values.

## Destructive actions

Deletion, profile change and workspace cleanup need two requests:

1. Send a preview request. It changes nothing. It returns the effect and a
   single-use token. The token expires after 300 seconds.
2. Send the same selector again with the token.

The token is bound to the action, the selector and the store state that the
preview saw. A missing token gets 428. A used, expired, altered or stale
token gets 409, and nothing changes. Then preview again. When the vector
store has only a process-local validity token, the preview says so in
`confirmation.validity` and `confirmation.warning`.

## Jobs and graph runs

Both kinds of work use one persisted run service with one consumer and a
bounded queue. A full queue gets 429.

| Kind | Start | Response | Follow |
| --- | --- | --- | --- |
| Document job | `POST /v1/ingestions`, `POST /v1/codebase-maps` | 202 `Job` | Poll `GET /v1/jobs/{jobId}` until `completed` or `failed` |
| Graph run | `POST /v1/runs` (a saved revision and inputs) | 202 `{"run": RunRecord}` | Poll `GET /v1/runs/{run_id}`, page events, or stream events |

Job paths must be absolute and inside an approved root. A run is admitted
when you submit it. An invalid graph or input gets 422, and no run starts.
`POST /v1/runs/{run_id}/cancel` stops a run at a safe boundary.
`POST /v1/runs/{run_id}/retry` starts a new run from a failed, cancelled or
interrupted run.

Work that is not finished when the server stops does not run again. After the
next start, a graph run shows `interrupted` and a job shows `failed`.

## Run events and SSE replay

Events are stored before clients see them. Each event has a sequence number.

- **Polling.** `GET /v1/runs/{run_id}/events?after_sequence=N` returns the
  next page. Send `last_sequence` as the next `after_sequence`. `complete`
  becomes true when the run has ended and no event is left.
- **Server-sent events.** `GET /v1/runs/{run_id}/events/stream` returns
  `text/event-stream`. Each frame has `id: <sequence>`, `event: <kind>` and
  `data: <event JSON>`. After a reconnection, the browser sends
  `Last-Event-ID` and the stream replays the later events. Use `?after=N` when
  you cannot set the header. The stream ends with `run.end`, or with
  `server.closing` when the server stops.

Closing a stream does not cancel the run. Only the cancel route does.

## Upload limit

The per-file upload limit comes from the first source in this order:
`--max-upload-mib`, `WEB_MAX_UPLOAD_MIB`, the value saved in Settings, then
50 MiB. `GET /v1/settings/upload-limit` (`read`) returns `max_bytes`,
`source` (`launch`, `saved` or `default`), `saved_mib`, `default_mib`,
`min_mib` and `max_mib`. `PUT /v1/settings/upload-limit` (`manage`, session
only) takes `{"max_mib": n}` or `{"max_mib": null}`. The server saves the
value, then applies it to new uploads at once. An upload in progress keeps
its start limit. An invalid body gets 422. When a launch option set the
limit, the request gets 409 and nothing changes.

## Full run output

An event, status or node summary larger than 16 KiB is cut. It then has `truncated: true` and
`artefact_ref: "<run_id>/<name>.json"`. The server keeps the full value, with
credentials and raw vectors removed, in a private artefact.
`GET /v1/runs/{run_id}/artefacts/{name}` (`read`) returns it as
`{"status": "ok", "run_id", "name", "value"}`. `name` is the file name of the
reference without `.json`.

The route uses the same access rule as `GET /v1/runs/{run_id}`. A run that
the caller cannot read gets 404, as an unknown run does. An unknown name gets
404. A name that is not one plain path segment gets 400, and no file is read.

## Templates, experiments and plugins

| Method | Path | Scope | Use |
| --- | --- | --- | --- |
| GET | `/v1/pipeline-templates` | `read` | Canonical graph templates (search, answer, ingestion) with their graph documents |
| POST | `/v1/experiments` | `manage` | Register an experiment workspace below an `--experiment-root`. 409 when the server has no experiment root |
| GET | `/v1/experiments` | `manage` | Approved roots and the experiment contexts of this launch |
| GET | `/v1/experiments/{context_id}` | `manage` | One context with its backend and index identity |
| DELETE | `/v1/experiments/{context_id}` | `manage` | Revoke a context. New runs in it are refused |
| GET | `/v1/plugins` | `plugins` | Plugin states, running editors, install hint and trust notice. Runs no process |
| POST | `/v1/plugins` | `plugins` | Register a manifest and an executable. Needs `approved: true` |
| POST | `/v1/plugins/{name}/recheck` | `plugins` | Probe the registered executable (`--version`, `edit --help`) |
| DELETE | `/v1/plugins/{name}` | `plugins` | Remove a registration. 409 while its editor runs |
| POST | `/v1/plugins/{name}/editors` | `plugins` | Recheck, then open a notebook in a separate local editor. Needs `consent: true` |
| DELETE | `/v1/plugin-editors/{launch_id}` | `plugins` | Stop an owned editor. Notebook files stay |

A bearer credential issued with `experiment_context` is bound to that
context. It reaches only `/v1/session`, `/v1/pipeline-operations`,
`/v1/pipeline-templates`, `/v1/pipelines` and `/v1/runs`, and sees only the
runs of its context. Live-library routes give 403.

The editor access token appears once, in the body of the open response. The
editor URL never holds it. The workspace opens the editor in a separate
browser tab and never embeds it. Startup registers and launches nothing.

## Contract checks

- `scripts/local_ci.sh` validates `openapi.yaml` with `openapi-spec-validator`.
- `tests/test_openapi_conformance.py` compares the search, listing and answer
  schemas with the core and MCP code.
- `tests/unit/test_web_openapi_conformance.py` compares the running routes with
  the contract: route set, scopes, session-only access, declared statuses,
  request fields, defaults, bounds and parameters.
- `tests/unit/test_web_openapi_conformance_documents.py` and
  `tests/unit/test_web_openapi_conformance_runs.py` send real requests and
  validate each response against the declared schema for its status.

When you add or change a route, change `openapi.yaml` in the same change.

## More information

- `docs/guides/web-workspace.md`: launch, sign-in, file grants, jobs, events and shutdown.
- `docs/guides/notebooks.md`: notebook trust, the marimo plugin and the starter notebook.
- `docs/guides/workspace.md`: workspace folders, retention, interruption and cleanup.
- `docs/guides/pipelines.md`: graph documents, operations and validation.
- `docs/guides/mcp-tools.md`: the MCP tools that call the same core operations.
- `docs/guides/configuration.md`: settings and environment variables.
