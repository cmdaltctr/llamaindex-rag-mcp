# Design

## Context

See proposal.md (Why). This section lists only the current code that the design builds on. All web paths are in the `studio-canvas-layout` worktree (`llamaindex-rag-mcp-feat-studio-canvas-layout/web/src/studio/`), which merges before this change. Backend paths use the folder layout of `organise-backend-folders`, which lands first.

- The card (`OperationNode.tsx:46-94`) shows the title, the node id (`:63`), the family badge, the raw operation id (`:67`), and each port name with its type kind (`:31-32`). `OperationNodeData` (`:8-16`) has no parameters and no effective values.
- `FlowSurface.tsx:52-71` builds the node data. Its `useMemo` depends on nodes, positions, selection, sizes, catalogue, issues and run states. It sets the node `ariaLabel` to `Node <id>, <operation>` (`:60`).
- Effective values come today only from an admission check: `POST /v1/pipelines/validate` with `inputs` returns `nodes[].controls` (`src/omrg/transports/api/routes/graphs.py:233-251`). A draft check without inputs returns none (`:256-261`). Each control has `lever`, `value`, `source` (`node`, `graph`, `environment` or `profile`, `core/pipelines/snapshot.py:25-36`) and a technical `detail` (`core/pipelines/admission.py:166-176`). `unify-profiles-and-pipelines` (requirement "The draft check reports effective control values", design D24) makes the draft check return the same `nodes[].controls`, also in its 422 body for a draft with issues.
- `useCanvasSession.ts:41,46` keeps the last report and derives `controls` from `report.nodes`. `web/src/api/pipelines.ts:164` already types `nodes` as optional. Nothing clears the report when the draft changes, so a value can be out of date. Today only the settings section shows it (`CanvasEditor.tsx:142`), with the text "Effective value: Off (profile: profile 'documents' (collection)), from the last validation." (`ParamField.tsx:34`).
- `schema.ts:45-67` turns the parameter JSON schema into fields. The label is the Pydantic title, for example "Top K" or "Rrf K" (`schema.ts:54`). `ParamField.tsx:163-164` shows that title and the lever path in a `code` line.
- `NodeInspector.tsx:41-62` shows "Node `<id>`", the family badge, the operation id, the full description and each issue with its code.
- The catalogue order of parameters is the Pydantic field order, kept through `model_json_schema()` and JSON. Operations without parameters: `source.discover`, `prepare.normalise`, `embed.chunks`, `select.threshold`, `answer.prepare_evidence`, `answer.cite`.
- `GET /v1/connections` already returns, per provider, `roles` and `models` with labels (`compose_connections.py:74-137`). The provider that holds the `embeddings` role carries a model labelled `embeddings`. The web has `connectionsQuery` (`web/src/api/queries.ts:144`).
- React Flow 12.12 makes each node focusable (`tabIndex 0`), gives it `role="group"`, takes the name from the node `ariaLabel`, and selects a focused node on Enter or Space. `app.css:183-187` already draws the focus outline on `.react-flow__node:focus-visible`.
- Panel section titles are in `panelSections.ts:12-19`. `studio-profiles-gallery` (design D13) renames two of them: "Nodes and connections" becomes "Steps and connections", and "Node settings" becomes "Step settings". It also changes the inspector strings to "Select a step to edit its settings.", "Bypass this step" and "Remove step". This design uses the new names.

## Goals / Non-Goals

**Goals:**

- A user who sees a card knows what the step does, what its main settings are, and that a click opens them.
- Every value on screen says where it comes from, and no value is shown after it stops being true.
- Values show without run inputs and without pressing Validate.
- Internal identifiers stay available to advanced users, one click away.

**Non-Goals:**

- No change to the HTTP API, the OpenAPI file, Python code or the catalogue text. `unify-profiles-and-pipelines` adds the draft check values (D12). Catalogue descriptions stay as the backend writes them.
- No editing on the card itself. The card shows values. Step settings edits them.
- No embedding model control. `add-profile-embedding-model` adds it and replaces the read-only line.
- No rename of panel sections or inspector strings. `studio-profiles-gallery` owns `workspace-studio`, where the section names live, and makes the rename.
- No change to the Operations list or the Steps and connections outline. They keep operation ids and node ids, because keyboard users pick steps and ports by them there.
- No change to the issue list under Revision and run. It keeps the issue codes, and only the user's Validate fills it (D5).

## Decisions

### D1. The card shows meaning first and moves codes to Step settings

The card shows, top to bottom: step name with the family badge and a settings icon; the node id in muted text only when another step has the same name; a one-line summary; up to three settings lines and a "+N more in Step settings" line; "No settings" when the operation has no parameters; the Embed chunks model line; the run status and the Bypassed and Unavailable badges; the input and output port names; the issue messages. The node id, the operation id and the type kinds leave the card. The handle `title` keeps the port name and drops the type kind.

The summary is the first sentence of the catalogue description (text up to the first ". "), clamped to one line with `line-clamp-1`. The full text is in the Details area of Step settings.

- Alternative: keep the operation id under the title in small text. Rejected: it is the code that made the user think the card was read-only.
- Alternative: hand-written plain summaries per operation in the web. Rejected: a second copy of the catalogue text that drifts. A later backend change can improve the catalogue text for every client.

### D2. Main settings: catalogue order, collection last, at most three

`mainSettings(operation)` takes the editable fields in catalogue (schema) order, moves the operation's `collection_param` to the end, drops fields of kind `unsupported`, and keeps the first three. The card then says how many fields remain. Examples: Prepare query shows Number of results, Minimum similarity and Reranker, then "+2 more in Step settings" (Collection, Candidates to fetch; Metadata filter is not editable and is not counted). Split into chunks shows its three chunking fields. Dense retrieval shows Collection.

The backend field order therefore sets card priority. `add-pdf-reader-step-setting` should declare `pdf_reader` as the first field of the Read document parameters, so the card shows it first.

- Alternative: a per-operation hint list in the web. Rejected: it duplicates parameter names in a second place and drifts when the backend renames a field.
- Alternative: a new `main_params` field in the catalogue. Rejected: a backend and API change for an order that the field order already gives.
- Alternative: settings with a lever first. Rejected: a new host-owned setting with no lever, such as the PDF reader, would never come first.

### D3. Plain labels live in one web map, keyed by lever, then by parameter name

New `labels.ts` holds `fieldLabel(field)` and `optionLabel(field, value)`. The lookup order is the lever path (for example `retrieval.top_k`), then the parameter name, then the schema title in sentence case ("Rrf K" becomes "Rrf k"). A lever key gives the same label to the same setting on every step: `rerank` on Prepare query and `enabled` on Cross-encoder rerank both read "Reranker".

| Key | Label |
| --- | --- |
| `retrieval.top_k` | Number of results |
| `retrieval.similarity_threshold` | Minimum similarity |
| `retrieval.rerank_enabled` | Reranker |
| `retrieval.hybrid_rrf_k` | Fusion constant (k) |
| `chunking.chunk_size` | Chunk size |
| `chunking.chunk_overlap` | Chunk overlap |
| `chunking.markdown_chunk_size` | Markdown chunk size |
| `chunking.strategy_fallback` | Fallback chunking |
| `chunking.code_chunk_lines` | Lines per code chunk |
| `metadata.taxonomy_mode` | Metadata categories |
| `answer.verify_claims` | Check claims |
| `collection` | Collection |
| `fetch_k` | Candidates to fetch |
| `metadata_filter` | Metadata filter |
| `expand_window` | Neighbour chunks to add |
| `include_diagnostics` | Include diagnostics |

Option labels: `chunking.strategy_fallback` maps `markdown`, `code`, `sentence` to "Markdown", "Code", "Sentences". `metadata.taxonomy_mode` maps `category`, `file_type` to "Category", "File type". An option without a label shows its raw value. The select keeps the raw value as the item value, so saved parameters do not change.

`paramFields` (`schema.ts`) adds a `label` property from `fieldLabel`. Card, legend, input label and select name all use `label`. The raw `title` stays on the field for the Details area.

- Alternative: set Pydantic `title=` on each parameter in Python. Rejected for this change because it is web only. It is the better long-term home, because MCP and CLI clients would get the same labels. Recorded as a follow-up (Open Questions).

### D4. One value text, shared by card and Step settings

New `stepSummary.ts` holds `settingValue(field, node, control, graph)`. The rules, first match wins:

1. The node sets the parameter (not `null`): "<value> (set here)".
2. The field has a lever and a current control exists: "<value> (<source>)", where the source is "set here" (`node`), "from pipeline settings" (`graph`), "from server settings" (`environment`) or "from profile" (`profile`).
3. The field has a lever that the draft's graph overrides set: "<value> (from pipeline settings)".
4. The field has a lever: "From profile".
5. The field is the collection parameter: "<collection> (from pipeline settings)" when the draft names a collection, else "Server default".
6. The schema has a non-null default: "<value> (default)".
7. Otherwise: "Default".

A current control comes from the automatic draft check or from the user's Validate (D5). Rule 4 applies only while the check runs, or when the check gave no control for that node (a network failure, invalid parameters on that step, or a profile that does not resolve).

Values show as "On" and "Off" for booleans, the option label for enums, and plain text for numbers and strings. In Step settings the note under each control reads "Value in use: <value> (<source>)" for rules 1 to 3. For rule 4 it reads "Comes from the profile. The value shows when the check finishes." The raw control `detail` text moves to Details.

### D5. The canvas checks the draft by itself, and values follow the draft

`useCanvasSession` runs the draft check (`validatePipeline` with the draft document and no `inputs`) by itself:

- when a pipeline opens;
- 500 ms after the last change to the graph document. Layout edits (position, selection, viewport) do not change the document and start no check.

It uses one `useQuery` keyed by the debounced document. TanStack Query drops a response for an older key, so a slow answer for an old draft never shows. A 422 answer is data: the session reads `nodes` from the error body (`ApiError.body`).

The session keeps the graph that each check or Validate sent, next to its report. `controls` is the report's controls only while `sameDocument(checkedGraph, draft.graph)` is true (`graph.ts:130`); otherwise it is empty until the next check returns. The user's Validate, with or without run inputs, replaces the report as today.

The automatic check fills only `controls`. It does not change the issue list, the issue badges on cards or the notice. Those still come from the user's Validate. The check also runs on a read-only canvas, because it writes nothing.

- Alternative: values only after Validate with run inputs (the earlier design of this change). Rejected: the user wants values without pressing Validate.
- Alternative: check on every keystroke. Rejected: one request per key.
- Alternative: show the automatic check's issues live. Rejected for this change: a half-built graph shows many issues while the user edits, and the issue list and its tests would change. A later change can add it.
- Alternative: clear the report inside every `update` call. Rejected: layout edits would also clear it.
- Alternative: compare per node. Rejected: graph profile, collection and overrides change every node's value, so a per-node check needs the same graph comparison and more code.

### D6. The node data carries ready-made lines

`FlowSurface` gets two new props, `controls` (from `useCanvasSession`) and `embeddingModel`. For each node it computes `title`, `summary`, `showNodeId`, `settings` (label and value text), `moreSettings` and, for `embed.chunks`, `modelLine`, and puts them in `OperationNodeData`. `OperationNode` only renders. The `useMemo` dependency list adds `controls`, `draft.graph.overrides`, `draft.graph.collection` and `embeddingModel`. `CanvasEditor` passes `session.controls` and `session.embeddingModel`.

This keeps the rules in `stepSummary.ts`, which a plain unit test can cover without React Flow.

### D7. The embedding model comes from the connection summary

`useCanvasSession` adds `useQuery(connectionsQuery(api))` and derives `embeddingModel`: the provider whose `roles` include `embeddings`, then its model labelled `embeddings`. When the query fails, is pending, or finds none, the value is `null` and the line reads "Model: unknown (fixed for collections that already hold vectors)". The line replaces "No settings" on Embed chunks, because the step has a model even with no parameters. The model name is in a `code` element (copy rule: model identifiers stay literal).

The text "fixed for collections that already hold vectors" is true today: each collection stores its embedding identity and the store refuses a mismatch (`core/vectordb/identity.py:31-44`, `core/pipelines/validation.py:226-243`).

- Alternative: add the host model to the operation catalogue or a new endpoint. Rejected: a backend change, and `add-profile-embedding-model` will define the real source.

### D8. Details is a native disclosure

New `NodeDetails.tsx` renders `<details>` with `<summary>Details</summary>`, closed by default, as `RunPanel.tsx:54` and `experiments/runs/NodeInspector.tsx:34` already do. It lists node id, operation id and version, full description, each field's label with its lever path, each port with its type kind and cardinality, each issue code, and each control's `detail` text. Identifiers are in `code` elements with `[overflow-wrap:anywhere]`.

- Alternative: the accordion primitive. Rejected: an accordion inside an accordion section adds a heading level and more markup for one disclosure.

### D9. The intro line sits in the slim bar

The slim bar in `CanvasEditor.tsx:98-104` holds the `h1` and the notices. The intro is a `p` (`text-meta text-muted-foreground`) under the `h1`, above the notices, from one exported constant `CANVAS_INTRO`. It shows whatever the graph holds. Text: "Build your own profile. Click a step to change it in Step settings. Drag from one port to another to connect steps, or use Connect ports." The line names the sections "Step settings" and "Connect ports", so the user can find them, and it names the keyboard route. The empty state reads "The graph is empty. Add a step from Operations to start."

The word "profile" matches `unify-profiles-and-pipelines`. "Step settings" is the section name from `studio-profiles-gallery`. The constant is the one place to change if either name changes.

- Alternative: "Click a step to change its settings in Step settings." Rejected: "settings" twice in one short sentence.
- Alternative: a React Flow `Panel` over the surface. Rejected: it covers steps and competes with the floating panel on the right.

### D10. The card announces that it opens settings

- Name: the node `ariaLabel` becomes "<step name> step", plus ", <node id>" when the name repeats.
- Icon: `Settings2` from `lucide-react`, the Step settings section icon (`panelSections.ts:18`), with `aria-hidden`. It links the card to the section by sight.
- Hover: in the default state only, the border changes from `border-border-hover` to `border-muted-foreground` with `transition-colors duration-150`. Selected, error and running borders do not change on hover. The drag cursor stays as React Flow sets it.
- Focus and keyboard: no new code. React Flow and `app.css:183-187` already give focus, the outline and Enter or Space selection. `CanvasPanel` already opens Step settings on a new selection.

### D11. Spec ownership

This change MODIFIES the whole requirement "Node controls show effective behaviour" in `pipeline-canvas`. It copies the baseline text and every baseline scenario, with one sentence changed. The baseline sentence "Profile selection SHALL support documents/codebase or collection inheritance." contradicts user profiles: a slot graph names its base profile, and Studio shows the base profile as text (`unify-profiles-and-pipelines` D8, `studio-profiles-gallery` D8). It becomes "Each pipeline SHALL inherit settings from its profile's base profile, and a step setting SHALL override the inherited value." No other change modifies this requirement. `studio-profiles-gallery` only ADDS a read-only canvas requirement to `pipeline-canvas`.

### D12. The backend half of "values without Validate" lives in `unify-profiles-and-pipelines`

The draft check must return effective values for every lever field without run inputs. That requirement is an ADDED requirement in the `pipeline-graphs` delta of `unify-profiles-and-pipelines` ("The draft check reports effective control values", design D24). It resolves the collection from the node parameter, then `graph.collection`, then the request collection, then the host default, and the profile from `graph.profile`, then the collection's profile.

Why there: that change already modifies `routes/graphs.py` and the validate route, adds the other `pipeline-graphs` requirements, and runs the Python tests. This change stays web only, with no Python test run (task 7.2).

- Alternative: an ADDED requirement in this change. Rejected: a web-only change would carry backend code and backend tests.

### D13. User-facing words say "step"

Every string this change adds says "step": "+N more in Step settings", "<step name> step", "Add a step from Operations", and the intro line. The strings it reads from `studio-profiles-gallery` are "Step settings", "Steps and connections", "Select a step to edit its settings.", "Bypass this step" and "Remove step". Test strings that this change writes or edits use these names:

| Test file | Strings |
| --- | --- |
| `CanvasEditor.settings.test.tsx` | "Value in use: Off (from profile)", "Number of results", "Reranker", the kept "Bypass this step" checks |
| `CanvasEditor.edit.test.tsx` | the intro line, "The graph is empty. Add a step from Operations to start.", the heading "Dense retrieval", a click that opens "Step settings" |
| `CanvasEditor.check.test.tsx` (new) | "Number of results: 10 (from profile)" without Validate, "Comes from the profile. The value shows when the check finishes." |
| `OperationNode.test.tsx` (new) | "+2 more in Step settings", "Threshold and top-k step", "Dense retrieval step, dense_2" |

## Risks / Trade-offs

- [The automatic check sends a request after each pause in editing] → It waits 500 ms after the last graph change, makes no model call and writes nothing. Layout edits send none.
- [The check is slow or fails] → Cards and Step settings show "From profile" with no number until a check returns. The canvas keeps working.
- [A stale response could show old values] → The query key is the document, so TanStack Query ignores an answer for an older draft, and `sameDocument` drops values that no longer match.
- [Taller cards overlap on the 260 by 180 pixel grid (`graph.ts:156`, `drafts.ts:21`)] → Ports lose their type-kind line and the summary is one line. Task 4.11 measures template cards and raises the row step if a card is taller than 170 pixels. Positions are layout only, so revisions do not change.
- [The label map drifts when the backend adds or renames a parameter] → The fallback is the schema title in sentence case, so a new field still shows. A test checks that each fixture parameter gets a label from the map.
- [The connection summary reads the model name from settings, while the store identity uses the embedder's `model_name` (`compose_pipelines.py:74-80`)] → They agree for the three providers today. `add-profile-embedding-model` replaces this line.
- [React Flow's click selection may not fire in jsdom] → The click test uses the same handler as Enter. If the click does not fire in jsdom, the test uses Enter and the browser check covers the click.
- [Merge conflicts with `studio-canvas-layout` and `studio-profiles-gallery`, which edit the same files] → Apply after both merge to `integration/core-web`.

## Migration Plan

Web only. No stored data changes. Saved revisions, layouts and parameter values stay the same. Apply after `studio-canvas-layout`, `organise-backend-folders`, `unify-profiles-and-pipelines` and `studio-profiles-gallery`. To roll back, revert the web commit; the backend draft check values stay and do no harm.

## Open Questions

1. Should a later backend change set plain Pydantic titles on parameters, so MCP and CLI clients share the labels in D3?
