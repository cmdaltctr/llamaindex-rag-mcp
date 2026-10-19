# Experiments view, plugin panel and canvas templates (task 8.6 frontend, gaps from 7.3 and 7.6)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted working tree.
Design D9 and D10. Specs `notebook-plugins` and `pipeline-canvas`.
Input: `experiment-transport.md` (routes, shapes, `trust_notice`, `token_delivery`).
No npm dependency was added. No Python, `tasks.md` or `pyproject.toml` file was changed.

## Files

| File | Job |
|---|---|
| `web/src/api/experiments.ts` (new) | Client for `GET/POST /v1/experiments`, `DELETE /v1/experiments/{id}`, bound `POST /v1/credentials`. `workspacePath` joins a folder to an approved root. `safeId` refuses unsafe path segments. |
| `web/src/api/plugins.ts` (new) | Client for list, register, recheck, unregister, open editor and stop editor. `editorTabUrl` accepts only a loopback `http` URL without query, fragment or user info. `editorToken` accepts only `response_body_once`. |
| `web/src/experiments/` (new) | `ExperimentsView`, `RegisterForm`, `ContextTable`, `CredentialPanel`, `NotebookPanel`, `OpenEditorForm`, `EditorList`, `ExperimentRuns`, `OneTimeSecret`, `ConfirmAction`, `labels.ts`, `experiments.css`, `test/experimentsServer.ts`. |
| `web/src/views/settings/PluginSection.tsx`, `PluginRegisterForm.tsx` (new) | Settings plugin panel. Replaces "No plugin routes yet". |
| `web/src/views/settings/SettingsView.tsx` | Uses `PluginSection`. Notice text changed: plugin registration is the only change made in Settings. |
| `web/src/canvas/templates.ts`, `TemplatePicker.tsx` (new) | `GET /v1/pipeline-templates` and "Start from template". |
| `web/src/canvas/useCanvasSession.ts` | New `startDraft(draft)`: a new unsaved draft; saved pipelines and revisions do not change. |
| `web/src/canvas/CanvasView.tsx`, `canvas.css` | Template picker replaces the "does not offer starting templates" line. |
| `web/src/canvas/test/fakeServer.ts` | Optional `templates` route. |
| `web/src/App.tsx` | One import and one `experiments` branch. |
| `web/src/api/documents.ts` | Lead follow-up: `CollectionInfo.profile` and `SessionInfo.workspace` (both string or null). |
| `web/src/views/library/ProfilePanel.tsx`, `LibraryView.tsx` | Lead follow-up: show the stored profile; reload the collection list after a confirmed change. |
| `web/src/views/test/fakeDocumentsServer.ts` | Collection fixtures carry `profile`. |
| `web/src/views/library/LibraryProfile.test.tsx` (new) | Stored profile tests. |

The largest component is `OpenEditorForm.tsx` (122 lines).

## Behaviour

### Experiments view

- The server `trust_notice` shows verbatim in a "Trust notice" region with warning styling, above all controls. The Notebook editor panel shows it again.
- Register: choose an approved root from `roots`, type a folder inside it, a name and the permitted actions (read, ingest). `joinRootPath` refuses absolute paths, `~`, drive letters and `..` before any request. The server receives the absolute path it expects. A server without a root shows the `--experiment-root` instruction and no form.
- Contexts table: name and id, status, workspace, store backend and store path, index identity, embedding provider and model, permitted actions.
- Revoke asks first. The warning states that a started run finishes, bound credentials stop working, and workspace files are not touched. Revoked rows have no button.
- Credential: choose an active context, label and scopes (graph, read, run). The token shows once with "Copy token" and "Hide token" and the note "Shown once". The panel names `OMRG_TOKEN_FILE` and `OMRG_EXPERIMENT_CONTEXT`. The token is in component state only.
- Experiment runs: `GET /v1/runs?limit=100`, filtered to runs with `resources.experiment.context_id`. Shows run id, status, context, index identity and creation time. "Open the Runs view" links to `#/runs`.

### Notebook editor

- With a compatible, launchable plugin: choose plugin, active context and a relative `.py` notebook. "Open notebook editor" stays disabled until the consent box is ticked.
- After `POST /v1/plugins/{name}/editors`: the page reads the token through `editorToken`, checks the address through `editorTabUrl`, then calls `window.open(url, "_blank", "noopener,noreferrer")`. The token never goes into the address.
- Token delivery follows `token_delivery.method = "response_body_once"`: the page shows the token once for the editor sign-in page. A fallback link "Open the editor tab again" (`rel="noopener noreferrer"`) covers popup blockers.
- No `iframe`, `frame`, `embed` or `object` element. The copy says that the page does not embed the editor.
- Running editors list with Stop (asks first; notebook files are kept).
- No plugin, or an incompatible or unavailable plugin: the server `message` and `install_hint` show verbatim with "The workspace works without the plugin." No install or update button.

### Settings plugin panel

- Lists every plugin with status label (Compatible, Incompatible, Not checked, Needs approval, Unavailable), server detail, version and executable. An unknown status shows as "Unknown status (raw value)".
- Register: manifest path, executable path, and an approval checkbox. The button stays disabled until approval. Server refusals show verbatim.
- Recheck shows the new detail. Unregister asks first.

### Canvas template start

- "Start from template" lists `title` and `description` from `GET /v1/pipeline-templates`. Loading gives a new unsaved draft with the template title, laid out on the `addNode` grid.
- The copy says the template is an editable starting point and must be saved as a revision before a run.
- Loading over unsaved work asks first ("Replace draft" or "Keep my draft").
- The empty-graph start stays. When the route fails, the picker says "Templates are not available" and the empty graph is still offered.

### Lead follow-up: workspace and stored profile

- Settings shows the workspace path from `GET /v1/session` `workspace`. The derivation from the managed uploads root is removed. A `null` value shows "The server did not report the workspace folder."
- The Library profile panel shows "Stored profile: <name>" from the `GET /v1/collections` item, or "No profile is stored for this collection." for `null`. After a confirmed change, the collection list reloads, so the stored profile updates.

All server text renders as React text nodes. No file uses `dangerouslySetInnerHTML` or `innerHTML`.

## Test-first record

| Step | Command | Result |
|---|---|---|
| Baseline | `npm test` | 215 passed |
| Client tests before modules | `npx vitest run src/api/experiments.test.ts src/api/plugins.test.ts` | 2 suites failed (modules missing) |
| After modules | same | 23 passed |
| View, settings and canvas tests before components | `npx vitest run src/experiments src/views/settings src/canvas` | 3 suites failed (modules missing); 7 tests failed (5 template, 1 old canvas assertion, 1 settings plugin panel) |
| After components | same, then `npm test` | first run: 1 App test failed (Settings lost its empty state); fixed with a plugin empty state |
| Follow-up tests before the change | `npx vitest run src/views/settings src/views/library` | 4 failed (2 workspace, 2 stored profile), 28 passed |
| After the change | `npx vitest run src/views` | 49 passed |

## Guard breaks

Script `scratchpad/exp-view/mutate.py`: one change, run the related test files, restore, compare SHA-256. Every mutation made at least one test fail.

| Id | Change | Failing tests |
|---|---|---|
| M1 | Token added to the editor tab URL | 1 (`opens the editor in a new tab with noopener ...`) |
| M2 | Open button enabled without consent | 1 (`needs explicit consent ...`) |
| M3 | Token written to `localStorage` | 2 (credential and editor token tests) |
| M4 | Confirmation step removed | 3 (revoke, stop, unregister) |
| M5 | Any editor host accepted | 4 (`refuses ...` cases and the remote-address view test) |
| M6 | Plugin register without approval | 1 |
| M7 | Template document ignored | 2 |
| M8 | Live-library runs not filtered out | 1 |
| M9 | Workspace derived from the uploads root again | 2 |
| M10 | Stored profile ignored | 2 |
| M11 | No collection reload after a profile change | 1 |

## Final results

| Command | Result |
|---|---|
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm test` | PASS, 32 files, 270 tests |
| `npm run build` | PASS (output in the gitignored `src/omrg/transports/api/static/`; existing chunk-size warning) |

## Open items

1. `web/src/lib/views.ts` (not owned) still gives the Experiments summary as "Notebook tools registered for this workspace." It should name workspaces, credentials, the editor and runs.
2. The Runs view has no deep link to one run. "Open the Runs view" opens the list; the user selects the run id shown in the Experiments table.
3. The marimo sign-in page format is unconfirmed (task 8.4). The UI tells the user to paste the token into the editor sign-in page. Confirm this against a real marimo installation.
4. `window.open` runs after the open request returns, so a browser can block the tab. The fallback link covers this. Browser evidence is still needed (task 7.7).
5. Not checked in a real browser at 1280, 768, 390 and 320 px, or in both themes (task 7.7).
