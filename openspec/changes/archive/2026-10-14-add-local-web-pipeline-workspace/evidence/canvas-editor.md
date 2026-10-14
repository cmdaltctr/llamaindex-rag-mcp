# Canvas editor (tasks 7.2 and 7.3)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted work tree.

All commands ran in `web/`. No npm dependency was added.

## Scope

- **7.2:** the catalogue palette, a custom node for each operation, typed handles, connection checks, an inspector generated from the JSON schema, Inherit/On/Off lever controls, the bypass toggle and keyboard editing.
- **7.3:** Save layout, Save revision, Validate, Run, Cancel and Refresh status. The submitted run keeps a frozen snapshot. The unsaved draft is kept in browser storage for each pipeline.

## API contract used

The real routes in `src/omrg/transports/api/routes_graphs.py` and `routes_runs.py` exist. The client follows them. These points differ from the task brief:

| Brief | Real route or shape | Client |
|---|---|---|
| `POST /v1/pipelines/{id}/validate` | `POST /v1/pipelines/validate`, body `{document, inputs?, collection?}` | Follows the real route |
| Issue `{code, node, port, message}` | `PipelineIssue` has `code, message, node_id, port, edge, lever` | Uses `node_id` and `edge` |
| Templates route | No templates route exists | The canvas starts from an empty graph and says so |

Other points:

- Validation with `inputs` returns the admitted view. It includes `nodes[].controls` with `{lever, value, source, detail}`. The inspector shows this as the effective inherited value.
- Validation without `inputs` is the draft check, which returns no effective values. The canvas sends `inputs` only when every required graph input has a value.
- `POST .../revisions` stores the graph only. The canvas sends the execution document without layout.
- `PUT .../layout` never creates a revision.
- Run statuses come from `core/workspace/records.py`. Cancel is enabled while the run is `queued`, `running` or `cancelling`.

## Files

| File | Purpose |
|---|---|
| `src/api/pipelines.ts` | Typed client. GET requests reuse `getJson`. POST and PUT requests use the same JSON and envelope checks. A 422 response with `issues` becomes `PipelineIssuesError`. Unsafe identifiers are refused before fetch. `client.ts` is unchanged. |
| `src/canvas/graph.ts` | Draft model. It keeps the execution graph (`toDocument`) apart from the layout (`toLayout`: title, positions, viewport, selection). |
| `src/canvas/connections.ts` | `portCompatibility` mirrors `check_port_compatibility`. `checkConnection` adds checks for unknown ports, self connections, duplicates, cardinality and loops. `connectionGuard` is React Flow's `isValidConnection`. |
| `src/canvas/schema.ts` | Reads Pydantic JSON schemas: nullable `anyOf`, local `$ref`, enum, minimum and maximum. Each field is linked to its lever from `lever_params`. |
| `src/canvas/storage.ts`, `useDraft.ts` | Browser storage for one draft per pipeline, plus the open pipeline and the submitted run. Every access uses try/catch. |
| `src/canvas/useCanvasSession.ts` | Server calls and run snapshot. |
| `src/canvas/*.tsx` | `CanvasView`, `PipelineBar`, `Palette`, `FlowSurface`, `OperationNode`, `GraphOutline`, `ConnectionMenu`, `NodeInspector`, `ParamField`, `RunPanel`. The largest is 166 lines. |
| `src/canvas/canvas.css` | Canvas styles. It reads the tokens in `tokens.css` only and maps the React Flow `--xy-*` variables to them. |
| `src/canvas/test/*` | A catalogue fixture (a subset of the real `build_operation_catalogue().describe(...)` output), a fake `/v1` server, helpers and the React Flow jsdom shim. |
| `src/App.tsx` | Minimal edit. The Canvas view renders `CanvasView`. The other views still render `ViewShell`. |

## Behaviour

- **Palette:** a searchable catalogue. Unavailable operations stay in the list, disabled, with the host's reasons shown next to them.
- **Node:** each node has a target handle for each input port and a source handle for each output port. Each port shows its name and kind. Bypassed nodes and validation issues show on the node.
- **Connections:** the check runs on drag (`isValidConnection`) and in the keyboard menu. A refused drag gets the same explanation through `onConnectEnd`. The server stays authoritative, because only the server follows bypass forwarding and host capabilities.
- **Keyboard route:**
  1. Add a node: palette button, then Enter.
  2. Select a node or connection: outline button, then Enter or Space.
  3. Connect: choose "From output", then "To input", then press Connect.
  4. Remove: press Delete or Backspace on an outline item, or on the focused flow surface.
- **Focus and delete keys:** focus is visible through the global `:focus-visible` ring. React Flow's own delete key is turned off (`deleteKeyCode={null}`). Delete and Backspace act only inside the surface or outline, so Backspace in another control cannot delete nodes.
- **Levers:**
  - Nullable booleans show Inherit / On / Off.
  - Nullable numbers show Inherit / Set value.
  - Inherit removes the key from `params` (`null` means inherit).
  - The effective value and its source appear after an admitted validation.
- **Profile:** the choices are "Inherit from each collection" (the field is omitted), `documents` and `codebase`.
- **Draft state:** the panel says whether the draft matches the saved revision or differs from it. Run always submits the saved `revision_id`.
- **Run snapshot:** it is a JSON clone of the saved revision document, taken at submission. Later edits never change it. It survives navigation in browser storage.

## Test-first record

1. I wrote the tests first: `api/pipelines.test.ts`, `canvas/{graph,connections,schema,storage}.test.ts` and `canvas/CanvasView.{edit,run}.test.tsx`.
2. Run 1 had no implementation. Result: 7 files failed at import, so no tests ran.
3. After the pure modules and the client existed, those 5 files gave 36 passed.
4. The first full run of the canvas tests gave 1 failed and 40 passed.
   - The search test used the word "rerank", which also matches the description of `retrieve.prepare_query`. I changed the search word to "cross-encoder".
   - The run also had uncaught `contentRect` errors. React Flow 12.12 reads `entry.contentRect`, which the shim in the React Flow testing guide omits. I added it to the stub.
5. After these fixes, all 41 canvas tests passed. The full suite gave 89 passed, with no console warnings.
6. I made the snapshot test stronger. The draft is now changed before submission, so the test also catches a snapshot taken from the live draft.

### Mutation checks

A scratch script broke one guard at a time and ran the full suite. It then restored the file and compared SHA-256 hashes. All files were restored.

| Mutation | Result |
|---|---|
| Cycle check disabled | 1 failed |
| Cardinality check disabled | 1 failed |
| Score-kind check disabled | 3 failed |
| Snapshot taken from the live draft | 1 failed |
| Revision body carries layout | 1 failed |
| Number field skips the schema check | 1 failed |
| Storage read without try/catch | 5 failed |
| Outline ignores Delete and Backspace | 1 failed |
| Unavailable operations enabled | 1 failed |
| Bypass toggle on every node | 1 failed |
| Effective controls ignored | 1 failed |
| Validation issues not passed to nodes | 1 failed |

## Scenario coverage

| Spec scenario or task item | Test |
|---|---|
| Template is rewired; saved edges decide execution | `rewires a saved template and saves the new connections, with layout kept apart`, `graph.test.ts` "rewires the saved document" |
| Incompatible connection or cycle is explained | `explains an incompatible connection and does not add it`, `connections.test.ts` (kind, score kind, provenance, cardinality, loop, self, duplicate, drag guard) |
| Draft differs from saved revision | `runs the saved revision and keeps the admitted snapshot after later draft edits` ("The draft differs from revision 1.") |
| Reranker disabled with a click; profile default restored | `writes Inherit, On and Off for a lever and shows the effective inherited value` |
| Active run has an edited toggle | Same run test: Off before submission and Inherit after it; the snapshot keeps `"enabled": true` |
| Graph edited using a keyboard | `adds and connects nodes with the keyboard and saves the wiring`, `deletes a selected node with Delete and a connection with Backspace` |
| Schema validation | `refuses values outside the parameter schema`, `schema.test.ts` |
| Bypass only when declared | `offers a bypass only when the operation declares one` |
| Profile inheritance | `selects the graph profile and keeps collection inheritance by default` |
| Layout apart from execution | `graph.test.ts` "changes only the layout…", `saves the layout without creating a revision` |
| Server issues on nodes and ports | `shows server validation issues on the matching node and port` |
| Unavailable operations | `lists the catalogue and disables unavailable operations with their reasons` |
| Draft persistence; storage throws | `restores the unsaved draft…`, `keeps working when browser storage throws`, `storage.test.ts` |

## Commands

| Command | Result |
|---|---|
| `npm run lint` | PASS, exit 0 |
| `npm run typecheck` | PASS, exit 0 |
| `npm test` | PASS, 11 files, 89 tests |
| `npm run build` | PASS. Output: CSS 30.49 kB (5.77 kB gzip), JS 444.98 kB (139.14 kB gzip). React Flow and its stylesheet are now in the bundle. |

## Not run or partial

- **NOT RUN:** a real browser check against a live `omrg web` server. This means no layout check at 320 px or 200% zoom, no dark theme screenshot and no real drag test. jsdom covers behaviour only.
- **NOT RUN:** a screen reader pass. Labels, groups, `aria-pressed`, `role="status"` and `role="alert"` are covered by role queries in the tests.
- **PARTIAL:** run status updates only on submit, cancel and "Refresh status". Live events and the stream are task 7.4.
- **PARTIAL:** graph-wide `overrides` keep their stored values, but the canvas has no editor for them. The `metadata_filter` (object) parameter shows a "cannot be edited on the canvas yet" note.
- **OPEN:** the server has no templates route. The canvas says "This server does not offer starting templates yet" and starts from an empty graph. If a route is added later, the palette needs a template picker.
- **OPEN:** `describe_operations` reads private Engine attributes (its own docstring says so). The client depends only on the JSON shape.
