# Proposal

## Why

A user profile should be fully editable in Studio. Today some settings are only reachable through the HTTP API. Hybrid retrieval has no switch: a user must add Sparse retrieval and Reciprocal rank fusion from Operations and rewire five connections by hand, and nothing is labelled "hybrid". On 2026-10-20 the only practical way to turn hybrid on for a user profile was a `POST /v1/pipelines/{id}/revisions` call with the template graph. The audit in `design.md` lists the other gaps: the step card shows settings but cannot change them, graph-wide overrides are invisible, the rerank candidate factor has no control, the metadata filter cannot be edited, and the profile description cannot be changed.

## What Changes

Must:

- Pipeline settings get a "Hybrid retrieval" switch on the Search and Answer pipelines of a user profile. On adds a Sparse retrieval step and a Reciprocal rank fusion step with the canonical wiring (`pipeline_templates._search_graph(hybrid=True)`). Off removes them and connects Dense retrieval to the step that fusion fed. Other steps keep their settings and positions. The switch reads its state from the graph shape. It is disabled, with the reason, when the shape is custom, when an operation is unavailable on the host, and on a built-in profile.
- The settings icon on each step card becomes a button. It opens a small panel next to the card with the same controls as Step settings for that step: every editable setting, the bypass switch where the operation has one, and "Open in Step settings".
- Pipeline settings list the pipeline-wide overrides that the graph already holds, with plain labels, values and a Remove button. Today they change values on the cards but cannot be seen or removed.

Should:

- Pipeline settings on Search and Answer get a "Rerank candidate factor" field. It writes the pipeline-wide override `retrieval.rerank_fetch_multiplier`, the only allowed lever that no step parameter carries.
- The Metadata filter of Prepare query becomes editable as JSON text, in Step settings and in the card panel. Today it reads "This parameter type cannot be edited on the canvas yet."
- The canvas header gets an inline description editor for a user profile. The API already accepts the description. The PDF reader setting gets the plain label "PDF reader".

Later (follow-up change, not in this change):

- A full pipeline-wide override editor for every allowed lever. This needs a lever catalogue in the API and an `openapi.yaml` change.
- Knowledge Base › Profile: an "Open in Studio" link, and plain labels in place of lever paths in the change preview.
- A base profile choice for a user profile's pipelines. The current spec forbids it, so it needs a product decision.
- A hybrid badge on profile cards, and the Answer pipeline's shape in the profile change preview.

No breaking changes. No new dependency. No API change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `workspace-studio`: Pipeline settings gain the hybrid retrieval switch, the pipeline-wide settings list and the rerank candidate factor. The canvas header gains the description editor.
- `pipeline-canvas`: the step card settings icon becomes a button that opens editable settings next to the card. Object settings such as the metadata filter are edited as JSON text.

## Impact

- Front end only, in `web/src/studio/` (new `hybrid.ts`, `StepSettingsFields.tsx`, `StepCardSettings.tsx`, `PipelineOverrides.tsx`, `ProfileDescriptionEditor.tsx`; changes to `PipelineBar.tsx`, `OperationNode.tsx`, `FlowSurface.tsx`, `CanvasEditor.tsx`, `NodeInspector.tsx`, `ParamField.tsx`, `schema.ts`, `labels.ts`, `ProfileHeader.tsx`) and `web/src/api/profiles.ts` (the description field of `ProfileUpdateInput`).
- One new shared fixture, `web/src/studio/hybridShape.json`, and one pytest that pins it to `src/omrg/pipeline_templates.py`. The pytest raises the executed count in `tests/test_clean_base_tripwire.py` by its case count.
- Docs: the Studio sections of `docs/guides/web-workspace.md`.
- No change to `src/omrg/transports/api/`, `openapi.yaml`, `web/src/api/client.ts`, `ApiProvider.tsx`, `bootstrap.ts`, `main.tsx` or `lib/errors.ts`, which the `persistent-web-auth-token` change edits.
