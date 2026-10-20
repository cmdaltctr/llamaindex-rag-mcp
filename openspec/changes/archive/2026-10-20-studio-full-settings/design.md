# Design

## Context

See `proposal.md` for the motivation. This section records the audit that sets the scope. Paths are relative to the repository root. Line numbers are at `v3` commit `7a0efe1`.

### Where Studio edits a pipeline today

- Pipeline settings (`web/src/studio/PipelineBar.tsx:14-30`): the base profile as text and the graph collection. Nothing else.
- Step settings (`web/src/studio/NodeInspector.tsx:36-123`): the bypass switch when the operation has one (69-78), the embedding model on Embed chunks (79), one control for each schema parameter (80-90), graph input and output check boxes (91-115) and Remove step (116-120).
- The step card (`web/src/studio/OperationNode.tsx`): the mini card shows up to three settings and expands "+N more settings" in place (110-148). It is read-only text. The settings icon at line 192 is decorative (`aria-hidden`), not a control.
- A parameter whose schema type is not a string, number, integer, boolean or enum gets kind `unsupported` (`web/src/studio/schema.ts:42-53`). Step settings then shows "This parameter type cannot be edited on the canvas yet." (`web/src/studio/ParamField.tsx:154`), and the card leaves it out (`web/src/studio/stepSummary.ts:30`).
- Graph-wide `overrides` load and save with the draft (`web/src/studio/graph.ts:88`, `:112`) and show as "(from pipeline settings)" on cards (`web/src/studio/stepSummary.ts:64-65`). No control lists, adds or removes them.

### Gap table

"FE" means a front-end change is enough. "BE" means the API or core must change too.

| Setting | Declared at | Where Studio sets it today | State | Proposed place | Needs |
| --- | --- | --- | --- | --- | --- |
| `retrieval.top_k` | `core/pipelines/levers.py:57`; Prepare query param (`core/retrieval/graph_adapters_catalogue.py:104-108`) | Step settings, card text | Editable in panel; card read-only | Card panel too (must) | FE |
| `retrieval.similarity_threshold` | `levers.py:61`; Prepare query param | Step settings, card text | Same as above | Card panel too (must) | FE |
| `retrieval.rerank_enabled` | `levers.py:58`; Prepare query `rerank`, Cross-encoder rerank `enabled` (`graph_adapters_catalogue.py:160`) | Step settings, card text | Same as above | Card panel too (must) | FE |
| `retrieval.hybrid_enabled` | `levers.py:59`; graph shape decides (`core/profiles/contract.py:92`, `core/retrieval/graph_adapters_values.py:67`) | Nowhere. Only by adding two steps and five connections by hand | Missing | Pipeline settings "Hybrid retrieval" switch (must) | FE |
| `retrieval.hybrid_rrf_k` | `levers.py:60`; Reciprocal rank fusion `rrf_k` (`graph_adapters_catalogue.py:146`) | Step settings once a fusion step exists | Editable | Card panel too (must) | FE |
| `retrieval.rerank_fetch_multiplier` | `levers.py:62`; no step parameter | Nowhere | Missing | Pipeline settings "Rerank candidate factor" (should) | FE |
| `answer.verify_claims` | `levers.py:63`; Check claims `verify_claims` (`core/answer/graph_adapters.py:415`) | Step settings, card text | Editable in panel | Card panel too (must) | FE |
| `chunking.chunk_size`, `chunk_overlap`, `markdown_chunk_size` | `levers.py:64-68`; Split into chunks (`core/ingestion/graph_adapters_catalogue.py:246-250`) | Step settings, card text | Editable in panel | Card panel too (must) | FE |
| `chunking.code_chunk_lines`, `strategy_fallback` | `levers.py:69-75`; Read document (`ingestion/graph_adapters_catalogue.py:195-198`) | Step settings, card text | Editable in panel | Card panel too (must) | FE |
| `metadata.taxonomy_mode` | `levers.py:76-81`; Enrich metadata (`ingestion/graph_adapters_catalogue.py:229`) | Step settings, card text | Editable in panel | Card panel too (must) | FE |
| Graph-wide `overrides` (any lever) | `core/pipelines/admission.py:205-210` | Shown as a source on cards only | Read-only, hidden | Pipeline settings list with Remove (must); full editor (later) | FE (list); BE for a lever catalogue (later) |
| Graph collection | graph document | Pipeline settings | Editable | No change | None |
| Step collection (Prepare query, Dense, Sparse, Identify, Commit) | `collection_param` (`graph_adapters_catalogue.py:103,121,134`; `ingestion/graph_adapters_catalogue.py:179,285`) | Step settings | Editable in panel | Card panel too (must) | FE |
| Candidates to fetch (`fetch_k`) | Prepare query (`graph_adapters_catalogue.py:48`) | Step settings | Editable in panel | Card panel too (must) | FE |
| Metadata filter (`metadata_filter`) | Prepare query (`graph_adapters_catalogue.py:49`), JSON object | Nowhere ("cannot be edited on the canvas yet") | Missing | JSON text field in Step settings and card panel (should) | FE |
| Neighbour chunks to add (`expand_window`) | Assemble context (`graph_adapters_catalogue.py:77`) | Step settings | Editable in panel | Card panel too (must) | FE |
| Include diagnostics | Write answer (`core/answer/graph_adapters.py:108`) | Step settings | Editable in panel | Card panel too (must) | FE |
| PDF reader (`pdf_reader`) | Read document (`ingestion/graph_adapters_catalogue.py:115`), not a lever | Step settings, label "Pdf reader" | Editable | Card panel; label "PDF reader" (should) | FE |
| Bypass a step | Normalise, Enrich, Rerank, Check claims (`ingestion/graph_adapters_catalogue.py:213,228`; `graph_adapters_catalogue.py:159`; `answer/graph_adapters.py:414`) | Step settings check box; card shows a badge | Editable in panel | Card panel too (must) | FE |
| Embedding model of the profile | ADR-081, `PUT /v1/profiles/{id}/embedding` | Step settings of Embed chunks (`NodeInspector.tsx:79`) | Editable | No change. The card panel links to Step settings | None |
| Graph inputs and outputs | graph document | Step settings (`NodeInspector.tsx:91-115`) | Editable | No change | None |
| Base profile of the graph | graph document `profile` | Pipeline settings text; `setProfile` exists but is unused (`web/src/studio/graph.ts:239`) | Read-only by spec (`openspec/specs/workspace-studio/spec.md:52`) | Later, after a product decision | FE + spec |
| Profile title | `PATCH /v1/profiles/{id}` | Canvas header and gallery pencil | Editable | No change | None |
| Profile description | `PATCH /v1/profiles/{id}` accepts it (`src/omrg/transports/api/routes/profiles.py:54-60,141-161`); `ProfileUpdateInput` has no field (`web/src/api/profiles.ts:49-51`) | Gallery card shows it read-only | Missing | Canvas header editor (should) | FE |
| Collection's profile | `POST` profile change flow | Knowledge Base › Profile (`web/src/knowledge-base/ProfilePanel.tsx`) | Editable; lever paths shown raw (`ProfilePanel.tsx:148`); no link to Studio | Plain labels and "Open in Studio" (later) | FE |
| Host-owned settings (embed provider, rerank model and backend, sparse backend, verify model, host PDF reader) | `levers.py:86-116` | Settings › Configuration, read-only | Host-owned by design, not a profile setting | Out of scope | n/a |

Two findings shape the design:

1. Only two allowed levers have no step control: `retrieval.hybrid_enabled` and `retrieval.rerank_fetch_multiplier`. Hybrid is decided by the graph shape, so it needs a shape switch, not an override. The fetch multiplier needs a pipeline-wide override.
2. `GET /v1/pipeline-templates` shapes the retrieval chain from the collection's settings (`src/omrg/compose_pipelines.py:201-225`). It takes no `hybrid` argument (`src/omrg/transports/api/routes/templates.py:61`), and the web never calls it.

## Goals / Non-Goals

**Goals:**

- Every lever and step parameter of a user profile can be set from Studio, through the step card or the right panel.
- The hybrid switch gives the same steps and connections as the canonical template, and keeps the user's other edits.

**Non-Goals:**

- No change to how a graph runs, validates or resolves settings.
- No editor for host-owned settings.
- No new API route, so this change does not touch `openapi.yaml`.

## Decisions

### D1. The hybrid switch is a pure draft transform in the web, pinned to the Python template

`web/src/studio/hybrid.ts` holds three pure functions: `hybridState(draft, catalogue)`, `enableHybrid(draft)` and `disableHybrid(draft)`. They return a new draft. The switch is an ordinary draft edit, so the user saves it as a revision, and the save warning for a profile in use applies.

The canonical delta lives in one JSON file, `web/src/studio/hybridShape.json`: the two added steps (`sparse` with `retrieve.sparse`, `fuse` with `combine.rrf`) and the three added connections. A pytest builds `_search_graph(None, hybrid=True, rerank=True)` and `_search_graph(None, hybrid=False, rerank=True)` from `src/omrg/pipeline_templates.py` and checks that their difference equals the JSON file. If the template changes, the pytest fails and names the file to update.

Alternatives considered:

- Add `?hybrid=true` to `GET /v1/pipeline-templates` and diff the result in the web. This needs a route change and an `openapi.yaml` change, which overlap with the `persistent-web-auth-token` change. It also needs a network call for a local edit.
- Replace the whole graph with the template. This loses the user's step settings, positions and any added steps.

### D2. Shape rules for the switch

State is "on" when the graph has one enabled `retrieve.sparse` step, as `core/profiles/contract.py:92` already decides for the profile preview.

- Turn on needs: one Prepare query, one Dense retrieval, the connection Prepare query → Dense retrieval, and no Sparse retrieval or fusion step. It adds `sparse` and `fuse` (a free id with a suffix when the name is taken), copies the Dense retrieval `collection` parameter to `sparse` when set, connects Prepare query → Sparse retrieval, Dense → fusion and Sparse → fusion, and moves every connection that left Dense retrieval `evidence` to leave fusion `evidence`.
- Turn off needs: one Sparse retrieval fed by Prepare query, one fusion step fed only by Dense and Sparse. It removes both steps and moves every connection that left fusion `evidence` back to Dense retrieval `evidence`.
- Any other shape is "custom". The switch is disabled and one line tells the user to change the steps on the canvas.
- When `retrieve.sparse` or `combine.rrf` is unavailable on the host, the switch is disabled and shows the catalogue reason.
- New steps go below Dense retrieval, in the nearest free slots, so they never cover another step. Existing steps keep their positions. Arrange tidies the layout when the user wants.

### D3. The card panel reuses the Step settings controls

`StepSettingsFields` is extracted from `NodeInspector`: the bypass switch and one `ParamField` for each parameter. Step settings and the card panel both render it, so a control behaves the same in both places. The settings icon on the card becomes a button, "Settings for <step name>". It opens the existing `Popover` primitive (`web/src/components/ui/popover.tsx`), which portals out of the React Flow node, so typing and clicking do not drag or select the card. The panel ends with "Open in Step settings", which selects the step and opens that section. On a read-only graph every control is disabled, as in Step settings.

The node gets the edit callbacks from a React context that `CanvasEditor` provides. This keeps `OperationNodeData` plain and stops React Flow from rebuilding nodes when a callback changes.

Alternative considered: a dropdown menu with check items. It needs `@radix-ui/react-dropdown-menu`, a new dependency, and menus are poor for number fields.

### D4. Pipeline-wide settings in Pipeline settings

`PipelineOverrides` lists each entry of `draft.graph.overrides` with the label from `labels.ts`, the value and a Remove button. On Search and Answer it also shows "Rerank candidate factor" as a number field with Inherit. The field writes or removes `overrides["retrieval.rerank_fetch_multiplier"]`. The draft check validates the value with `lever_error` (`core/pipelines/levers.py:126`), so the web adds only the "whole number of at least 1" check that `ParamField` already does.

### D5. Object parameters are JSON text

`schema.ts` gives a parameter of type `object` the kind `json`. `ParamField` renders a text field that parses on each change. Invalid JSON shows "Enter a JSON object." and does not change the draft. Empty text means Inherit. The card shows the value as compact JSON. Array and other types stay `unsupported`.

### D6. Description editor

`ProfileDescriptionEditor` follows `ProfileTitleEditor`: a pencil opens an inline field, Enter or Save sends `PATCH /v1/profiles/{id}` with `{description}`, and Escape cancels. The server limit is 1000 characters (`routes/profiles.py:60`).

## Risks / Trade-offs

- [The JSON shape file drifts from the Python template] → The parity pytest fails in CI and names the file.
- [A user graph has a shape the rules do not recognise] → The switch says "custom" and changes nothing. No silent rewrite.
- [Two pipelines, one profile] → Search and Answer are separate graphs, so each has its own switch. The switch line names the pipeline it changes. A shared switch is out of scope.
- [The reranker has three controls: Prepare query `rerank`, Cross-encoder rerank `enabled`, and bypass] → Unchanged here. Record it for a later clean-up.
- [Keyboard events inside the card panel reach React Flow] → The panel is portalled, and React Flow ignores key events from inputs. A Vitest case presses Backspace in a panel field and checks that the step stays.
- [Conflict with `persistent-web-auth-token`] → That change edits `web/src/api/{ApiProvider.tsx,bootstrap.ts,client.ts}`, `web/src/main.tsx`, `web/src/lib/errors.ts`, `web/src/components/PowerMenu.tsx`, `web/src/settings/*`, `src/omrg/transports/api/*`, `openapi.yaml` and the Sign in part of `docs/guides/web-workspace.md`. This change edits none of those code files. Both edit `docs/guides/web-workspace.md` (different sections) and `tests/test_clean_base_tripwire.py` (the pinned executed count). Merge v3 into the feature branch before the final CI run, then set the tripwire count from a fresh measurement.

## Migration Plan

No data migration. Saved graphs keep their shape until the user toggles the switch and saves a revision. Rollback is a revert of the web build.
