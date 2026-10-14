# Browser evidence, guide screenshots and attribution (task 7.7)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted work tree. Design D9, D11. Specs `pipeline-canvas`, `local-web-workspace`.

Tool: Chrome through the Chrome DevTools MCP server, isolated browser context. Viewport emulation with device pixel ratio 1 unless stated. No Playwright, no installs.

Server: the offline launcher described in [end-to-end.md](end-to-end.md) (real `Engine`, LanceDB in a scratch directory, hashed fake embedder, fake answer LLM, no reranker, `--root` on synthetic sources, one `--experiment-root`, built assets, real run service). Sources include Arabic prose with English identifiers.

## Screenshots

All files are in `docs/guides/images/web-workspace/` and are cited in the "Screens" section of `docs/guides/web-workspace.md`. `tests/unit/test_web_workspace_guide.py` checks that each cited path exists.

| View | 1280 px light | 1280 px dark | 768 px | 390 px | Other |
|---|---|---|---|---|---|
| Canvas (Search template, rewired, finished run node states) | `canvas-light-1280.png` | `canvas-dark-1280.png` | `canvas-light-768.png` | `canvas-light-390.png` | `canvas-focus-light-1280.png` (keyboard focus on a node) |
| Runs detail (admitted snapshot, replay, node outcomes) | `runs-detail-light-1280.png` | `runs-detail-dark-1280.png` | `runs-light-768.png` | `runs-light-390.png` | |
| Runs evidence inspector (ranked rows, score kind, full chunk, Arabic chunk) | `runs-evidence-light-1280.png` | `runs-evidence-dark-1280.png` | | | |
| Library | `library-light-1280.png` | `library-dark-1280.png` | `library-light-768.png` | `library-light-390.png` | |
| Search (hybrid on, chunk viewer with neighbours) | `search-light-1280.png` | `search-dark-1280.png` | | | |
| Ask (cited answer, evidence supplied to the model) | `ask-light-1280.png` | `ask-dark-1280.png` | | | |
| Experiments (context, bound credential form, experiment runs) | `experiments-light-1280.png` | `experiments-dark-1280.png` | | | |
| Settings | `settings-light-1280.png` | `settings-dark-1280.png` | | | `settings-light-320.png` |

24 PNG files, 5.3 MB in total. Full-page captures at 1280 px; viewport captures at 768 px and 390 px. The narrow captures use the light theme.

## Defects found and fixed

| # | Defect (plain English) | Where | Fix | Test |
|---|---|---|---|---|
| D1 | A node added after a node was removed landed on top of an existing node. The slot came from the node count, so a gap made the count point at a taken slot. Seen when the sparse node covered the context node. | `web/src/canvas/graph.ts` `addNode` | New `freeSlot()` picks the first grid slot that no node covers. | `graph.test.ts` "places an added node on a free grid slot": **1 failed, 8 passed** before the fix; **56 passed** (canvas folder) after. |
| D2 | In the Runs evidence table, the chunk button did not wrap. It took most of the row, the Source column shrank to about 60 px, and each row grew to about 555 px tall. | `web/src/runs/runs.css` | `.evidence-table__source` min 8rem; buttons in the table are 10rem wide and wrap. | Browser measurement: rows 555 px to 179-197 px; table no longer wider than its panel (scrollWidth 982 to 720). CSS only, no jsdom test. |
| D3 | The Experiments "Experiment runs" table showed "Not recorded" for the index identity. The UI read `resources.experiment.index_identity`; the server records it at `resources.experiment.backend.index_identity`. The test fixture had the wrong shape too, so tests passed. | `web/src/experiments/ExperimentRuns.tsx`, `test/experimentsServer.ts` | Fixture changed to the server shape (from `compose_experiments.ExperimentEngine.resources()`); the component reads `backend.index_identity`. | Fixture change alone: **1 failed, 16 passed**; after the fix **17 passed**. Browser shows `67ea325ad7b203fb`. |
| D4 | The Runs view overflowed sideways at 768 px (page 998 px wide) and at 390 px (420 px). Between 768 and 1023 px the run list kept its own column beside the navigation, and nested settings rows kept a fixed 6rem key column at every depth. | `web/src/runs/runs.css` | Run list stacks above the detail below 1024 px; the key column may shrink; nested settings rows stack key above value below 1024 px. | Browser: page width 768 at 768 px and 390 at 390 px; no element outside the viewport except inside scroll containers. |
| D5 | Keyboard focus on a canvas node was invisible. React Flow's own `.react-flow__node.selectable:focus-visible { outline: none }` loads later and has higher specificity than our rule. Connections were also affected. | `web/src/canvas/canvas.css` | Our focus rule adds the `.selectable` selector. | Browser: node and edge outline `2px solid` accent with `:focus-visible`; was `none`. See `canvas-focus-light-1280.png`. |
| D6 | `web/THIRD_PARTY_NOTICES.md` named only OpenChamber. The built bundle contains 17 npm packages (MIT, ISC, BSD-3-Clause) and the build strips their licence comments. | `web/THIRD_PARTY_NOTICES.md` | Added a "Bundled runtime packages" table (versions from `package-lock.json`), the MIT, ISC and BSD-3-Clause texts, and a note on the screenshots. | Manual check against each package's `LICENSE` file in `node_modules`. |

Final frontend gate after all fixes: `npm run lint` clean; `npm run typecheck` clean; `npm test` **32 files, 271 tests passed**; `npm run build` built (one existing chunk-size warning: 541 kB script).

Python: `tests/unit/test_web_workspace_guide.py tests/test_docs_references.py` **12 passed**. Mutation: one cited image moved away gives **1 failed** (`test_cited_paths_routes_and_links_exist`), restored. Wider set (`test_web_workspace_guide.py`, `test_notebooks_guide.py`, `test_starter_notebook.py`, `test_docs_references.py`, `tests/test_file_size_ceiling.py`, `-m "not slow"`): **46 passed**.

## Open findings (not fixed)

1. **Form fields without `id` or `name`.** Chrome reports the "A form field element should have an id or name attribute" issue (count 10 to 40 per view). Each field has a visible label, so this is not an accessibility failure. Fix option: give each control a `name`. Left open: it touches many components.
2. **Canvas node cards are small at fit-view.** At 1280 px the flow surface is about 380 px wide, so a six-node graph renders at 0.35 to 0.45 zoom. The Nodes and Connections lists carry the same information as text. Options: (a) a wider centre column when the inspector is closed; (b) a taller surface. Design choice, not changed.
3. **Bundle size warning.** The single script is 541 kB (163 kB gzip). Code splitting is a later optimisation (task 9.4 scope note).
4. **Narrow navigation.** At 320 px and 390 px the navigation list scrolls sideways inside its own container (`overflow-x: auto`). The page itself does not scroll sideways. This is intended.
5. **Validation effective-value text stays after reload.** After a reload, "Effective value" lines from the last validation are not shown until the next Validate. Matches the copy "from the last validation". No change.

## Responsive, zoom and focus checks

| Check | Result |
|---|---|
| 1280 px, all seven views, light and dark | PASS. Dark theme sets `data-theme="dark"`, body `rgb(18, 15, 14)`, native controls follow `color-scheme`. |
| 768 px: Canvas, Library, Runs | PASS after D4. Page width equals viewport. Canvas uses two columns and moves the inspector below. |
| 390 px: Canvas, Library, Runs | PASS after D4. One column. |
| 320 px: all seven views | PASS. Page width 320 on every view. Only the navigation list overflows, inside its scroll container. Screenshot: `settings-light-320.png`. |
| 200 % zoom (CSS viewport 640 px at device pixel ratio 2, the same layout as 1280 px at 200 %): Canvas, Library, Runs | PASS. Page width 640, no element outside the viewport except inside scroll containers. |
| Keyboard focus walk, Canvas, 1280 px | PASS after D5. Order: Skip to content, Theme, Inspector, seven navigation links, Pipeline, Title, Profile, Collection, Template, Start from template, 19 catalogue buttons (the unavailable rerank button is disabled and skipped), six flow connections, six flow nodes, Zoom In, Zoom Out, Fit View, React Flow attribution, Nodes list, Connections list with Remove buttons, Connect ports selects, node settings, Save layout, Save revision, Validate, Run, Input query. Every stop showed a 2 px focus outline with `:focus-visible`. |
| Keyboard node editing | PASS. Focus node `rrf`, Enter selects it, ArrowDown moves it from y 130 to 135; the draft in local storage records `{x: 580, y: 135}`. |
| Console | No `error` or `warning` messages on any view. Only the Chrome "issue" in open finding 1. |

## Guide action walk

Each action that `docs/guides/web-workspace.md` documents, tried against the running server. UI = through the page; API = `fetch` in the signed-in page (session) or `scratchpad/e2e/api_walk.py` (bearer, standard library only); CLI = `omrg web` through `run_cli()`.

### Start, options, one server per workspace (CLI)

| Action | How | Result |
|---|---|---|
| Launch message and one-time link on stderr | launcher uses the CLI `_bind_socket` and `_serve` | PASS (link printed; stdout empty in all CLI runs below) |
| `--host 0.0.0.0` refused | CLI | PASS, exit 2, "Refusing to bind to '0.0.0.0' …" |
| `--root` that does not exist | CLI | PASS, exit 2, "Approved root is not an existing directory" |
| `--experiment-root` that does not exist | CLI | PASS, exit 2 |
| `--port` already in use | CLI | PASS, exit 1, "Cannot listen on 127.0.0.1:63640: Address already in use" |
| Second server on the same `--workspace` | CLI | PASS, exit 1, the guide's message |
| Missing `web` extra message | not run (cannot uninstall); covered by `test_missing_extra_message_matches_the_guide` | NOT RUN |

### Sign in

| Action | How | Result |
|---|---|---|
| Fragment removed from the address bar | UI | PASS |
| Session cookie is HttpOnly (not visible to script) | UI | PASS |
| Wrong or reused bootstrap refused | API session | PASS, 401 |
| `GET /v1/session` returns `workspace`; Settings shows it | API, UI | PASS |
| Issue bearer with `graph`, `read`, `run` | API session | PASS, 201, token shown once |
| Bearer with a session-only scope (`files`) refused | API session | PASS, 400 |
| List credentials shows no secret | API session | PASS |
| Revoke applies on the next request | API session | PASS, 200 then 401 |
| Bearer cannot use session-only routes: `GET /v1/roots`, `GET /v1/credentials`, `POST /v1/ingestions`, `POST /v1/workspace/cleanup/preview` | API bearer | PASS, 403 each |
| Experiment-bound credential: runs only in its context, cannot read the live library | API bearer | PASS (see end-to-end.md) |
| Experiments view: issue bound credential, shown once, Hide token removes it from the page | UI | PASS |

### Request checks

| Action | Result |
|---|---|
| Foreign `Host` gets 400 | PASS |
| Foreign `Origin` on `/v1` gets 403 | PASS |
| Cross-site fetch (`Sec-Fetch-Site: cross-site`) gets 403 | PASS |
| Credential in the query string gets 400; the access log shows `token=***` | PASS |
| `GET /v1/health` is public; a protected route without credentials gets 401 | PASS |

### File access and uploads

| Action | How | Result |
|---|---|---|
| `GET /v1/roots` lists the operator root and the managed upload root | API session; Settings view | PASS |
| Ingestion path outside the roots gets 403 | API session | PASS |
| Path escaping a root with `..` gets 403 | API session | PASS |
| Preflight accepts `report.pdf` 1 MiB and stores nothing | API session | PASS, 200 |
| Preflight over 50 MiB gets 413; archive gets 415; name with a separator or a hidden name gets 400 | API session | PASS |
| `POST /v1/uploads` with a percent-encoded `X-Upload-Name` returns `id`, `name`, `size`, `sha256` and no server path | API session | PASS (`note é.md`) |
| Library upload of `bundle.zip` is refused before sending | UI | PASS, "File type .zip is not supported … Archives are not extracted." |
| Library upload and ingest of `upload-notes.md` | UI | PASS, 5 sources, 7 chunks, job "Completed" |

### Jobs and graph runs

| Action | How | Result |
|---|---|---|
| `POST /v1/ingestions` gives 202 and a job; poll `GET /v1/jobs/{jobId}` to `completed` | API session | PASS |
| `POST /v1/codebase-maps` gives 202; job completes | API session | PASS |
| Canvas: start from template, remove node, add nodes, connect ports, save revision, validate, run | UI | PASS (end-to-end.md) |
| Invalid graph gets 422 with issues | API bearer (`POST /v1/pipelines/validate` with a broken rewiring) | PASS, 422 with `issues` |
| Invalid input gets 422, no run starts | API bearer | PASS |
| Submit gives 202 with a run record | API bearer | PASS |
| Cancel | API bearer | PASS, `cancelling` then `cancelled` |
| Retry of a cancelled run gives 202 | API bearer | PASS |
| Full queue gets 429 | not run (needs 16 waiting items with a gated Engine); covered by unit tests | NOT RUN |

### Run events

| Action | Result |
|---|---|
| Polling with `after_sequence`; `last_sequence` and `complete` | PASS, 23 events, then empty and complete |
| SSE `text/event-stream`; `Last-Event-ID: 20` replays 21 to 23 and ends with `run.end` | PASS |
| SSE `?after=22` resumes at 23 | PASS |
| Stream ends with `run.end` for a finished run, also during shutdown | PASS |
| Closing a stream does not cancel the run | PASS (runs stayed `succeeded`) |
| Runs view replay is labelled as replay ("Replay of recorded events. Nothing runs again.") | PASS |

### Destructive actions

| Action | How | Result |
|---|---|---|
| Library delete source: preview text, "Nothing has changed yet", Confirm deletion removes 1 chunk | UI | PASS |
| Delete preview returns a token, `validity: durable` (LanceDB) | API session | PASS |
| Delete without a token gets 428 | API session | PASS |
| Token used for another selector gets 409 | API session | PASS |
| Library profile change preview lists each setting and when it applies; Cancel changes nothing | UI | PASS |
| Profile change confirm; `chunk_count_unchanged` 6; reused token gets 409 | API session | PASS |
| Workspace cleanup preview and apply | API session | PASS. Apply removed 0 runs: the cancelled run is kept because its retry refers to it. The response lists the skip reason. |

### Errors and the application

| Action | Result |
|---|---|
| Unknown `/v1` path gives the JSON envelope 404, not HTML | PASS |
| Non-`/v1` path (`/library`) serves the application | PASS |
| Missing asset gives a plain 404 | PASS |

### Search, Ask, Runs, Experiments, Settings (UI)

| Action | Result |
|---|---|
| Search with Hybrid On: rows show score and score kind ("Reciprocal rank fusion (rrf_v1)"), source, chunk position, "Present on this machine" | PASS |
| Show chunk, then Next chunk and Previous chunk; Next disabled on the last chunk | PASS |
| Arabic chunk renders right to left; English identifiers stay in order | PASS |
| Ask: "Cited" status with the guarantee text "No verifier checked the claims"; citations; evidence supplied to the model with dense score kinds | PASS |
| Runs: filter, select run, admitted snapshot (revision, graph hash, operation versions, settings "redacted by the server", inputs), replay controls, node outcomes, node inspector, evidence table, full chunk viewer | PASS |
| Experiments: register form, context table with store and index identity, Revoke button, bound credential, editor panel says no plugin is registered and the workspace works without it, experiment runs table | PASS after D3 |
| Settings: notice that it does not edit `.env`, workspace, runtime (18 of 19 operations; rerank not available), file access table, theme, plugin registration form | PASS |
| Theme: System, Light, Dark; choice persists across reloads | PASS |

### Stop the server

| Action | Result |
|---|---|
| SIGINT: stops admission, ends the open stream, lifespan shutdown completes | PASS. Log: "Shutting down", "Application shutdown complete." Port free afterwards; no launcher process left. |

### Not verified

1. Missing `web` extra message in a real environment without FastAPI (unit test only).
2. Queue-full 429 (unit tests only).
3. Notebook plugin registration and a real marimo editor (no install; task 8.4).
4. A cross-process write warning on a Chroma store (`validity: process-local`): only LanceDB was used.
5. A real `omrg web` process started from the console script: the launcher uses the CLI's own bind and serve functions with an injected offline Engine, so `compose.build_engine()` was not exercised.
6. Reduced-motion rendering of an active run: the offline run finishes in 0.04 s, so no active-edge animation was observable.
7. Safari and Firefox.

## Attribution

`web/THIRD_PARTY_NOTICES.md` now lists OpenChamber (theme values, unchanged) and the 17 npm packages in the built bundle with their licence texts (D6). The React Flow attribution link stays visible on the canvas. The guide's Screens section cites the notices file.
