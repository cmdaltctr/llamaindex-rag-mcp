# Tasks

All paths are under `web/src/studio/` unless stated. Run web commands from `web/`. Write each test first, run it, and confirm that it fails before you change the code.

## 1. Preparation

- [ ] 1.1 Confirm that `studio-canvas-layout` is merged into `integration/core-web`: `web/src/studio/panelSections.ts` and `CanvasPanel.tsx` exist on that branch. Stop if they do not.
- [ ] 1.2 Confirm that `organise-backend-folders`, `unify-profiles-and-pipelines` and `studio-profiles-gallery` are merged into `integration/core-web`: `src/omrg/transports/api/routes/graphs.py` returns `nodes` from a draft check, and `panelSections.ts` holds the title "Step settings". Stop if they do not.
- [ ] 1.3 Create the sibling worktree `llamaindex-rag-mcp-feat-clarify-canvas-steps` on branch `feat/clarify-canvas-steps` from `integration/core-web`. Verify with `git rev-parse --show-toplevel` and `git branch --show-current`.
- [ ] 1.4 Run `npm run test` in the new worktree before any edit. Record that the suite passes, so later failures belong to this change.

## 2. Plain labels and value text

- [ ] 2.1 Add failing cases to `schema.test.ts`: `paramFields` gives `label` "Number of results" for `top_k`, "Minimum similarity" for `similarity_threshold`, "Reranker" for Prepare query `rerank` and for Cross-encoder rerank `enabled`, and "Fusion constant (k)" for `rrf_k`. A field missing from the map gets its schema title in sentence case. Run `npx vitest run src/studio/schema.test.ts` and confirm the failures.
- [ ] 2.2 Add a failing case to `schema.test.ts` that every parameter of every operation in `test/catalogueFixture.ts` gets its label from the map, not from the fallback.
- [ ] 2.3 Add a failing case to `schema.test.ts` for `optionLabel`: `metadata.taxonomy_mode` maps `category` and `file_type` to "Category" and "File type"; an unmapped option returns its raw value.
- [ ] 2.4 Create `labels.ts` with `fieldLabel` and `optionLabel` and the maps in design D3. Add `label` to the `ParamField` type and to `paramFields` in `schema.ts`. Keep `title`. Run `schema.test.ts` and confirm that it passes.
- [ ] 2.5 Write failing `stepSummary.test.ts` for `mainSettings`: Prepare query gives `top_k`, `similarity_threshold`, `rerank` and 2 more; Dense retrieval gives `collection` and 0 more; Threshold and top-k gives none. Use descriptors from `test/catalogueFixture.ts`.
- [ ] 2.6 Add failing cases to `stepSummary.test.ts` for `settingValue`, one case for each of the seven rules in design D4. Include "Off (set here)", "10 (from profile)", "4 (from server settings)", "From profile", "Server default" and "0 (default)".
- [ ] 2.7 Add a failing case to `stepSummary.test.ts` for `firstSentence`: the text up to the first ". ", and the whole text when it has no full stop.
- [ ] 2.8 Create `stepSummary.ts` with `mainSettings`, `settingValue` and `firstSentence`. Run `stepSummary.test.ts` and confirm that it passes.

## 3. Values without Validate, and the embedding model

- [ ] 3.1 Add an opt-in `connections` option to `test/fakeServer.ts` that answers `GET /v1/connections`. Without the option the route keeps its 404 answer. Run `npm run test` and confirm that no existing test changes result.
- [ ] 3.2 Make `test/fakeServer.ts` answer a draft check (no `inputs`) with `nodes` and their controls, in the shape of the `unify-profiles-and-pipelines` draft check. Add an option for a 422 answer whose body holds `issues` and `nodes`, and a counter of draft check calls. Run `npm run test` and record any existing test that now sees values. Update only assertions that expected no value before Validate.
- [ ] 3.3 Add `nodes` to the draft check response type and to the validation error body type in `web/src/api/pipelines.ts`. Run `npm run typecheck`.
- [ ] 3.4 Write failing tests in a new `CanvasEditor.check.test.tsx`: when a Search pipeline opens, with no Validate, the Prepare query card shows "Number of results: 10 (from profile)" and Step settings shows "Value in use: 10 (from profile)"; before the check returns, Step settings shows "Comes from the profile. The value shows when the check finishes."; a 422 draft answer still gives values to the other steps and leaves the issue list empty.
- [ ] 3.5 Add failing tests to `CanvasEditor.check.test.tsx` with fake timers: one parameter edit sends one draft check after 500 ms; three edits within 500 ms send one check; moving a step or changing the selection sends none; after a graph edit the values disappear until the new check returns; an answer for an older draft does not show.
- [ ] 3.6 In `useCanvasSession.ts`, add the automatic draft check from design D5: a `useQuery` keyed by the debounced graph document, a 500 ms pause, `nodes` read from a 422 body, and no change to `issues` or the notice. Store the graph that each check or Validate sent. Return `controls` only while `sameDocument` matches the current draft graph. Run the tests from 3.4 and 3.5 and confirm that they pass.
- [ ] 3.7 Change the existing test in `CanvasEditor.settings.test.tsx` that expects no value before Validate: after the draft check, the Reranker note reads "Value in use: Off (from profile)"; after the user changes a graph setting, the note reads "Comes from the profile. The value shows when the check finishes." until the next check; after a layout edit only, the value stays. Run it and confirm that it passes.
- [ ] 3.8 Mutation check: make `useCanvasSession.ts` skip the automatic check. Run `CanvasEditor.check.test.tsx` and confirm that at least one test fails. Restore the code.
- [ ] 3.9 In `useCanvasSession.ts`, add `useQuery(connectionsQuery(api))` and return `embeddingModel` as design D7 describes. Cover the found, failed and no-role cases in the Group 4 card tests.

## 4. Step card

- [ ] 4.1 Create `test/catalogueIngest.ts` with the `source.discover`, `embed.chunks` and `prepare.chunk` descriptors, copied from `build_operation_catalogue().describe(...)` output. Do not add them to `CATALOGUE`, so palette tests do not change.
- [ ] 4.2 Write failing `OperationNode.test.tsx`. It renders `FlowSurface` with a small draft, because the card's handles need the React Flow node context. Check each scenario of "Step cards show what each step does": step name, one-line summary, "Reranker: Off (set here)", "Number of results: From profile" while no check has returned, "+2 more in Step settings", "No settings" on Threshold and top-k, port names without type kinds, and no operation id or node id in the card text.
- [ ] 4.3 Add failing cases to `OperationNode.test.tsx`: two Dense retrieval steps show `dense` and `dense_2`; the accessible names are "Threshold and top-k step" and "Dense retrieval step, dense_2"; the Bypassed, Unavailable and issue texts still show.
- [ ] 4.4 Add failing cases to `OperationNode.test.tsx` for the Embed chunks line: "Model: nomic-embed-text (fixed for collections that already hold vectors)" when the model is known, "Model: unknown (…)" when it is `null`, and no "No settings" on that card.
- [ ] 4.5 Add `controls` and `embeddingModel` props to `FlowSurface.tsx`. Build the card lines with `stepSummary.ts`. Set `ariaLabel` as design D10 describes. Add `controls`, `draft.graph.overrides`, `draft.graph.collection` and `embeddingModel` to the `useMemo` dependencies.
- [ ] 4.6 Rewrite `OperationNode.tsx` to render the lines from design D1: the `Settings2` icon with `aria-hidden`, the hover border, and handle titles without type kinds. Run `OperationNode.test.tsx` and confirm that it passes.
- [ ] 4.7 Pass `session.controls` and `session.embeddingModel` from `CanvasEditor.tsx` to `FlowSurface`. Run `npm run typecheck`.
- [ ] 4.8 Change `nodeCard()` in `CanvasEditor.live.test.tsx` to find `.react-flow__node[data-id="<id>"] [data-slot='op-node']`, because the card no longer shows the node id. Run the file and confirm that it passes.
- [ ] 4.9 Add a test to `CanvasEditor.edit.test.tsx`: a click on the Threshold and top-k card opens Step settings with that step; Enter on the focused card does the same. If the click does not fire in jsdom, keep the Enter case and record the click for the browser check in 7.5.
- [ ] 4.10 Mutation check: make `OperationNode.tsx` skip the settings lines. Run `OperationNode.test.tsx` and confirm that at least one test fails. Restore the code and confirm that the tests pass.
- [ ] 4.11 Measure the card heights of the ingestion, search and answer templates at 1280 pixels in a browser. If a card is taller than 170 pixels, raise the row step in `graph.ts` (`freeSlot`) and `drafts.ts` (`gridSlot`) to 240, update `graph.test.ts` and `drafts.test.ts`, and run them.
- [ ] 4.12 Run `CanvasEditor.workspace.test.tsx`, `CanvasPanel.test.tsx` and `StudioView.test.tsx`. Confirm that they pass with no edits beyond 3.2.
- [ ] 4.13 Add a "Step cards" subsection to "Studio canvas layout" in `docs/guides/web-workspace.md`: what a card shows, what "set here" and "from profile" mean, that values show without Validate, and that a click opens Step settings.

## 5. Step settings

- [ ] 5.1 Change the existing assertions in `CanvasEditor.settings.test.tsx` to the new text: group "Enabled" becomes "Reranker", group "Top K" becomes "Number of results", "Top K value" becomes "Number of results value", and the effective note becomes "Value in use: Off (from profile)". Keep the "Bypass this step" and "Remove step" assertions from `studio-profiles-gallery` as they are. Run the file and confirm the failures.
- [ ] 5.2 Add a failing test to `CanvasEditor.settings.test.tsx`: the lever path `retrieval.rerank_enabled` and the operation id `select.rerank` are not visible until the user opens Details; Details is closed at first and then shows the node id, the operation id and version, the lever path and the control detail.
- [ ] 5.3 Add a failing test to `CanvasEditor.settings.test.tsx` with Extract metadata: the options read "Category" and "File type", and choosing "File type" saves the parameter value `file_type`.
- [ ] 5.4 Change the heading assertions in `CanvasEditor.edit.test.tsx` (the two `/Node dense/` checks) to the step name "Dense retrieval". In the server-issue test, check that the code `incompatible_ports` shows in Step settings only inside Details, and that the message shows outside it.
- [ ] 5.5 Update `ParamField.tsx`: use `field.label` for the legend, the input label, the checkbox label and the select name; show option labels; remove the lever `code` line; write the note texts from design D4.
- [ ] 5.6 Create `NodeDetails.tsx` as design D8 describes. In `NodeInspector.tsx`, use the step name as the heading, show the one-line summary, keep issue messages without codes, and render `NodeDetails` last. Run `CanvasEditor.settings.test.tsx` and `CanvasEditor.edit.test.tsx` and confirm that they pass.
- [ ] 5.7 Mutation check: make `ParamField.tsx` use `field.title` again. Run `CanvasEditor.settings.test.tsx` and confirm that it fails. Restore the code.
- [ ] 5.8 Describe Step settings in `docs/guides/web-workspace.md`: plain labels, "Value in use", the automatic check, when a value disappears, and the Details area.

## 6. Canvas intro line

- [ ] 6.1 Add a failing test to `CanvasEditor.edit.test.tsx`: the intro text "Build your own profile. Click a step to change it in Step settings. Drag from one port to another to connect steps, or use Connect ports." shows under the `h1` for an empty pipeline and for a pipeline with steps, and it is not inside `.react-flow`. The empty state reads "The graph is empty. Add a step from Operations to start."
- [ ] 6.2 Add `CANVAS_INTRO` and render it in the slim bar of `CanvasEditor.tsx`. Change the empty-state message. Run the test from 6.1 and confirm that it passes.
- [ ] 6.3 Add the intro line to `docs/guides/web-workspace.md` and re-capture `studio-canvas-light-1280.png`, `studio-canvas-dark-1280.png` and `studio-canvas-light-390.png` with a pipeline with steps open.

## 7. Verification

- [ ] 7.1 Run `npm run lint`, `npm run typecheck`, `npm run test` and `npm run build` in `web/`. Record PASS or FAIL for each.
- [ ] 7.2 Run `git diff --stat integration/core-web` and confirm that no file under `src/`, `tests/` or `src/omrg/transports/api/openapi.yaml` changed. No Python test run is needed.
- [ ] 7.3 Confirm that every changed or new file under `web/src/studio/` has fewer than 500 lines.
- [ ] 7.4 Run `openspec validate clarify-canvas-steps --strict` and confirm that it passes.
- [ ] 7.5 Open the canvas with a throwaway server (omrg-design verification guide). In light and dark at 1280 pixels and at 390 pixels, check: card text, values without Validate, values that disappear and come back after an edit, hover border, focus outline, click and Enter open Step settings, Details opens and closes, and the intro line wraps without horizontal scroll.
