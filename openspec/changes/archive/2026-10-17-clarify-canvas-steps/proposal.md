# Proposal

## Why

A user clicked the "Discover sources" card on the Studio canvas and thought the canvas was read-only. The card shows internal codes (the operation id `source.discover`, the node id and the port type kinds) and no settings. The settings exist, but they sit in a section of the side panel, and nothing on the card says so. The values that the settings use show only after the user validates with run inputs. The user is building a GUI for the whole system, so each step card must say what the step does, what you can change, and which value is in use now.

## What Changes

This change is web only. It depends on `studio-canvas-layout`, which merges first and adds the floating panel and its sections (`web/src/studio/panelSections.ts`). It uses two things from changes that ship together before it: the effective values that `unify-profiles-and-pipelines` adds to the draft check, and the section name "Step settings" that `studio-profiles-gallery` gives the settings section.

- **Step card** (`OperationNode.tsx`):
  - Shows the plain step name (the catalogue title) and a one-line summary from the catalogue description.
  - Shows up to three main settings, each with its value and where the value comes from. Examples: "Chunk size: 1024 (from profile)", "Reranker: Off (set here)".
  - Shows "No settings" for a step with no parameters.
  - Shows port names without type kinds.
  - Shows the handle of a connected port in green.
  - Keeps the run status and the Bypassed, Unavailable and issue badges.
  - No longer shows the node id, the operation id or the port type kinds. The node id shows only when two steps have the same name.
  - Shows a settings icon and a hover and focus state, so the user can see that the card opens its settings. The card has an accessible name, for example "Discover sources step".
- **Embed chunks card**: shows a read-only line "Model: `<host model>` (fixed for collections that already hold vectors)". The model name comes from the existing `GET /v1/connections` response. The per-profile model setting is a separate change (`add-profile-embedding-model`).
- **Step settings** (`NodeInspector.tsx`, `ParamField.tsx`):
  - The heading is the step name.
  - Field labels are plain, for example "Number of results" for `top_k` and "Reranker" for the rerank `enabled` control.
  - Choice options show readable labels where a mapping exists. The saved values do not change.
  - The value note says which value is in use and where it comes from.
  - A collapsed "Details" area holds the node id, the operation id and version, the full description, the setting paths (for example `chunking.chunk_size`), the port types and the issue codes.
- **Values without Validate**: the canvas runs the draft check by itself when a pipeline opens and after each graph edit, with a short delay. Cards and Step settings show each value as soon as the check returns. A value shows only while the draft still matches the graph that was checked. The automatic check does not change the issue list; the user's Validate still does.
- **Canvas intro line**: one visible line, with a little vertical padding, above the pipeline tabs: "Build your own profile. Click a step to change it in Step settings. Drag from one port to another to connect steps, or use Connect ports." Each pipeline tab (Ingest, Search, Answer) also has an "i" info button with no chevron. A click opens a popover with the description of that pipeline and, for a built-in profile, the read-only note. For a built-in profile, "Duplicate to edit" sits beside "All profiles".
- **Edge animation**: while a run is live, the edge into a step that just finished animates in the success colour for 1.5 seconds. The edge into a running step keeps its animation. A run that had finished before the canvas began to watch it shows no animation. Reduced motion shows a static highlight.
- **Smooth-step connections**: the canvas draws each connection as a smooth-step line (right-angle bends with rounded corners) instead of the default diagonal curve. The shape is presentation only and is not saved.
- **Hideable header**: a "Hide header" toggle at the right end of the title row slides the intro line and the pipeline tabs up. The title row stays, with "Duplicate to edit" and "All profiles", so the canvas has more room. The toggle then reads "Show header". It starts shown on every visit.
- **Settings mini card**: the settings on a step card sit in a mini card inside the card. A button "+N more settings" shows the other settings in place, and "Show fewer settings" folds them. It does not select the card.
- **Expanding summary**: the one-line summary on a step card is a button. A click shows the whole sentence on the card and a second click folds it again. It does not select the card.
- **Profile sentence**: the `pipeline-canvas` requirement no longer says that a pipeline selects `documents`, `codebase` or collection inheritance. Each pipeline inherits settings from its profile's base profile, and a step setting overrides the inherited value.

This change makes no API, Python, stored-data or graph-model change. Saved revisions and parameter values stay byte-for-byte the same.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `pipeline-canvas`: "Node controls show effective behaviour" changes so that settings use plain labels, show the source of each value, keep technical identifiers in a collapsed Details area, show values from the automatic draft check, and drop values that no longer match the draft. Its profile sentence follows the profile's base profile. New requirements cover the step card content, the card's settings affordance and the canvas intro line.

## Impact

- **Code (web only):** `web/src/studio/OperationNode.tsx`, `FlowSurface.tsx`, `CanvasEditor.tsx`, `NodeInspector.tsx`, `ParamField.tsx`, `schema.ts`, `useCanvasSession.ts`; `web/src/api/pipelines.ts` (the draft check `nodes` type); new `web/src/studio/stepSummary.ts` (main settings and value text), `web/src/studio/labels.ts` (plain labels) and `web/src/studio/NodeDetails.tsx` (the Details area).
- **Tests:** `CanvasEditor.settings.test.tsx`, `CanvasEditor.live.test.tsx`, `CanvasEditor.edit.test.tsx`, `schema.test.ts` and `test/fakeServer.ts` change. `CanvasEditor.workspace.test.tsx` and `CanvasPanel.test.tsx` are re-run with no change expected. New `OperationNode.test.tsx`, `stepSummary.test.ts`, `CanvasEditor.check.test.tsx` and the fixture `test/catalogueIngest.ts`. Section lookups use the names from `studio-profiles-gallery`: "Step settings", "Steps and connections", "Remove step", "Bypass this step" and "Select a step to edit its settings."
- **Docs:** `docs/guides/web-workspace.md` (Studio canvas section) and the Studio canvas screenshots.
- **Dependencies:** none. `lucide-react` already provides the `Settings2` icon.
- **Order:** apply after `studio-canvas-layout` merges, after `organise-backend-folders` lands, and after `unify-profiles-and-pipelines` and `studio-profiles-gallery` merge. The first gives the draft check values; the second gives the "Step settings" name and the word "profile" in the intro line (see design D9 and D12).
- **Not affected:** the HTTP API, OpenAPI, Python code, saved graphs, the run service and the other workspace areas.
