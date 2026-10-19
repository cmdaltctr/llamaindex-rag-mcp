# Tasks

All paths are under `web/src/studio/` unless stated. Run web commands from `web/`. Write each test first, run it, and confirm that it fails before you change the code.

## 1. Preparation

- [x] 1.1 Confirm that `studio-canvas-layout` is merged into `integration/core-web`: `web/src/studio/panelSections.ts` and `CanvasPanel.tsx` exist on that branch. Stop if they do not.
- [x] 1.2 Confirm that `organise-backend-folders`, `unify-profiles-and-pipelines` and `studio-profiles-gallery` are merged into `integration/core-web`: `src/omrg/transports/api/routes/graphs.py` returns `nodes` from a draft check, and `panelSections.ts` holds the title "Step settings". Stop if they do not.
- [x] 1.3 Create the sibling worktree `llamaindex-rag-mcp-feat-clarify-canvas-steps` on branch `feat/clarify-canvas-steps` from `integration/core-web`. Verify with `git rev-parse --show-toplevel` and `git branch --show-current`.
- [x] 1.4 Run `npm run test` in the new worktree before any edit. Record that the suite passes, so later failures belong to this change.

## 2. Plain labels and value text

- [x] 2.1 Add failing cases to `schema.test.ts`: `paramFields` gives `label` "Number of results" for `top_k`, "Minimum similarity" for `similarity_threshold`, "Reranker" for Prepare query `rerank` and for Cross-encoder rerank `enabled`, and "Fusion constant (k)" for `rrf_k`. A field missing from the map gets its schema title in sentence case. Run `npx vitest run src/studio/schema.test.ts` and confirm the failures.
- [x] 2.2 Add a failing case to `schema.test.ts` that every parameter of every operation in `test/catalogueFixture.ts` gets its label from the map, not from the fallback.
- [x] 2.3 Add a failing case to `schema.test.ts` for `optionLabel`: `metadata.taxonomy_mode` maps `category` and `file_type` to "Category" and "File type"; an unmapped option returns its raw value.
- [x] 2.4 Create `labels.ts` with `fieldLabel` and `optionLabel` and the maps in design D3. Add `label` to the `ParamField` type and to `paramFields` in `schema.ts`. Keep `title`. Run `schema.test.ts` and confirm that it passes.
- [x] 2.5 Write failing `stepSummary.test.ts` for `mainSettings`: Prepare query gives `top_k`, `similarity_threshold`, `rerank` and 2 more; Dense retrieval gives `collection` and 0 more; Threshold and top-k gives none. Use descriptors from `test/catalogueFixture.ts`.
- [x] 2.6 Add failing cases to `stepSummary.test.ts` for `settingValue`, one case for each of the seven rules in design D4. Include "Off (set here)", "10 (from profile)", "4 (from server settings)", "From profile", "Server default" and "0 (default)".
- [x] 2.7 Add a failing case to `stepSummary.test.ts` for `firstSentence`: the text up to the first ". ", and the whole text when it has no full stop.
- [x] 2.8 Create `stepSummary.ts` with `mainSettings`, `settingValue` and `firstSentence`. Run `stepSummary.test.ts` and confirm that it passes.

## 3. Values without Validate, and the embedding model

- [x] 3.1 Add an opt-in `connections` option to `test/fakeServer.ts` that answers `GET /v1/connections`. Without the option the route keeps its 404 answer. Run `npm run test` and confirm that no existing test changes result.
- [x] 3.2 Make `test/fakeServer.ts` answer a draft check (no `inputs`) with `nodes` and their controls, in the shape of the `unify-profiles-and-pipelines` draft check. Add an option for a 422 answer whose body holds `issues` and `nodes`, and a counter of draft check calls. Run `npm run test` and record any existing test that now sees values. Update only assertions that expected no value before Validate.
- [x] 3.3 Add `nodes` to the draft check response type and to the validation error body type in `web/src/api/pipelines.ts`. Run `npm run typecheck`.
- [x] 3.4 Write failing tests in a new `CanvasEditor.check.test.tsx`: when a Search pipeline opens, with no Validate, the Prepare query card shows "Number of results: 10 (from profile)" and Step settings shows "Value in use: 10 (from profile)"; before the check returns, Step settings shows "Comes from the profile. The value shows when the check finishes."; a 422 draft answer still gives values to the other steps and leaves the issue list empty.
- [x] 3.5 Add failing tests to `CanvasEditor.check.test.tsx` with fake timers: one parameter edit sends one draft check after 500 ms; three edits within 500 ms send one check; moving a step or changing the selection sends none; after a graph edit the values disappear until the new check returns; an answer for an older draft does not show.
- [x] 3.6 In `useCanvasSession.ts`, add the automatic draft check from design D5: a `useQuery` keyed by the debounced graph document, a 500 ms pause, `nodes` read from a 422 body, and no change to `issues` or the notice. Store the graph that each check or Validate sent. Return `controls` only while `sameDocument` matches the current draft graph. Run the tests from 3.4 and 3.5 and confirm that they pass.
- [x] 3.7 Change the existing test in `CanvasEditor.settings.test.tsx` that expects no value before Validate: after the draft check, the Reranker note reads "Value in use: Off (from profile)"; after the user changes a graph setting, the note reads "Comes from the profile. The value shows when the check finishes." until the next check; after a layout edit only, the value stays. Run it and confirm that it passes.
- [x] 3.8 Mutation check: make `useCanvasSession.ts` skip the automatic check. Run `CanvasEditor.check.test.tsx` and confirm that at least one test fails. Restore the code.
- [x] 3.9 In `useCanvasSession.ts`, add `useQuery(connectionsQuery(api))` and return `embeddingModel` as design D7 describes. Cover the found, failed and no-role cases in the Group 4 card tests.

## 4. Step card

- [x] 4.1 Create `test/catalogueIngest.ts` with the `source.discover`, `embed.chunks` and `prepare.chunk` descriptors, copied from `build_operation_catalogue().describe(...)` output. Do not add them to `CATALOGUE`, so palette tests do not change.
- [x] 4.2 Write failing `OperationNode.test.tsx`. It renders `FlowSurface` with a small draft, because the card's handles need the React Flow node context. Check each scenario of "Step cards show what each step does": step name, one-line summary, "Reranker: Off (set here)", "Number of results: From profile" while no check has returned, "+2 more in Step settings", "No settings" on Threshold and top-k, port names without type kinds, and no operation id or node id in the card text.
- [x] 4.3 Add failing cases to `OperationNode.test.tsx`: two Dense retrieval steps show `dense` and `dense_2`; the accessible names are "Threshold and top-k step" and "Dense retrieval step, dense_2"; the Bypassed, Unavailable and issue texts still show.
- [x] 4.4 Add failing cases to `OperationNode.test.tsx` for the Embed chunks line: "Model: nomic-embed-text (fixed for collections that already hold vectors)" when the model is known, "Model: unknown (…)" when it is `null`, and no "No settings" on that card.
- [x] 4.5 Add `controls` and `embeddingModel` props to `FlowSurface.tsx`. Build the card lines with `stepSummary.ts`. Set `ariaLabel` as design D10 describes. Add `controls`, `draft.graph.overrides`, `draft.graph.collection` and `embeddingModel` to the `useMemo` dependencies.
- [x] 4.6 Rewrite `OperationNode.tsx` to render the lines from design D1: the `Settings2` icon with `aria-hidden`, the hover border, and handle titles without type kinds. Run `OperationNode.test.tsx` and confirm that it passes.
- [x] 4.7 Pass `session.controls` and `session.embeddingModel` from `CanvasEditor.tsx` to `FlowSurface`. Run `npm run typecheck`.
- [x] 4.8 Change `nodeCard()` in `CanvasEditor.live.test.tsx` to find `.react-flow__node[data-id="<id>"] [data-slot='op-node']`, because the card no longer shows the node id. Run the file and confirm that it passes.
- [x] 4.9 Add a test to `CanvasEditor.edit.test.tsx`: a click on the Threshold and top-k card opens Step settings with that step; Enter on the focused card does the same. If the click does not fire in jsdom, keep the Enter case and record the click for the browser check in 7.5.
- [x] 4.10 Mutation check: make `OperationNode.tsx` skip the settings lines. Run `OperationNode.test.tsx` and confirm that at least one test fails. Restore the code and confirm that the tests pass.
- [x] 4.11 Measure the card heights of the ingestion, search and answer templates at 1280 pixels in a browser. If a card is taller than 170 pixels, raise the row step in `graph.ts` (`freeSlot`) and `drafts.ts` (`gridSlot`) to 240, update `graph.test.ts` and `drafts.test.ts`, and run them.
- [x] 4.12 Run `CanvasEditor.workspace.test.tsx`, `CanvasPanel.test.tsx` and `StudioView.test.tsx`. Confirm that they pass with no edits beyond 3.2.
- [x] 4.13 Add a "Step cards" subsection to "Studio canvas layout" in `docs/guides/web-workspace.md`: what a card shows, what "set here" and "from profile" mean, that values show without Validate, and that a click opens Step settings.

## 5. Step settings

- [x] 5.1 Change the existing assertions in `CanvasEditor.settings.test.tsx` to the new text: group "Enabled" becomes "Reranker", group "Top K" becomes "Number of results", "Top K value" becomes "Number of results value", and the effective note becomes "Value in use: Off (from profile)". Keep the "Bypass this step" and "Remove step" assertions from `studio-profiles-gallery` as they are. Run the file and confirm the failures.
- [x] 5.2 Add a failing test to `CanvasEditor.settings.test.tsx`: the lever path `retrieval.rerank_enabled` and the operation id `select.rerank` are not visible until the user opens Details; Details is closed at first and then shows the node id, the operation id and version, the lever path and the control detail.
- [x] 5.3 Add a failing test to `CanvasEditor.settings.test.tsx` with Extract metadata: the options read "Category" and "File type", and choosing "File type" saves the parameter value `file_type`.
- [x] 5.4 Change the heading assertions in `CanvasEditor.edit.test.tsx` (the two `/Node dense/` checks) to the step name "Dense retrieval". In the server-issue test, check that the code `incompatible_ports` shows in Step settings only inside Details, and that the message shows outside it.
- [x] 5.5 Update `ParamField.tsx`: use `field.label` for the legend, the input label, the checkbox label and the select name; show option labels; remove the lever `code` line; write the note texts from design D4.
- [x] 5.6 Create `NodeDetails.tsx` as design D8 describes. In `NodeInspector.tsx`, use the step name as the heading, show the one-line summary, keep issue messages without codes, and render `NodeDetails` last. Run `CanvasEditor.settings.test.tsx` and `CanvasEditor.edit.test.tsx` and confirm that they pass.
- [x] 5.7 Mutation check: make `ParamField.tsx` use `field.title` again. Run `CanvasEditor.settings.test.tsx` and confirm that it fails. Restore the code.
- [x] 5.8 Describe Step settings in `docs/guides/web-workspace.md`: plain labels, "Value in use", the automatic check, when a value disappears, and the Details area.

## 6. Canvas intro line

- [x] 6.1 Add a failing test to `CanvasEditor.edit.test.tsx`: the intro text "Build your own profile. Click a step to change it in Step settings. Drag from one port to another to connect steps, or use Connect ports." shows under the `h1` for an empty pipeline and for a pipeline with steps, and it is not inside `.react-flow`. The empty state reads "The graph is empty. Add a step from Operations to start."
- [x] 6.2 Add `CANVAS_INTRO` and render it in the slim bar of `CanvasEditor.tsx`. Change the empty-state message. Run the test from 6.1 and confirm that it passes.
- [x] 6.3 Add the intro line to `docs/guides/web-workspace.md` and re-capture `studio-canvas-light-1280.png`, `studio-canvas-dark-1280.png` and `studio-canvas-light-390.png` with a pipeline with steps open.

## 7. Verification

- [x] 7.1 Run `npm run lint`, `npm run typecheck`, `npm run test` and `npm run build` in `web/`. Record PASS or FAIL for each.
- [x] 7.2 Run `git diff --stat integration/core-web` and confirm that no file under `src/`, `tests/` or `src/omrg/transports/api/openapi.yaml` changed. No Python test run is needed.
- [x] 7.3 Confirm that every changed or new file under `web/src/studio/` has fewer than 500 lines.
- [x] 7.4 Run `openspec validate clarify-canvas-steps --strict` and confirm that it passes.
- [x] 7.5 Open the canvas with a throwaway server (omrg-design verification guide). In light and dark at 1280 pixels and at 390 pixels, check: card text, values without Validate, values that disappear and come back after an edit, hover border, focus outline, click and Enter open Step settings, Details opens and closes, and the intro line wraps without horizontal scroll.

## 8. Edge animation after review

- [x] 8.1 Add failing tests in `runs/runState.test.ts`: `edgeRunStyle` takes a third argument `recentlyFinished`; a succeeded step with it gives `flow-edge--done` and `animated`, and with reduced motion gives `flow-edge--done` and no `animated`; a running step keeps `flow-edge--active`; a failed step with it gives no style. Add cases for a new `finishedNodes(previous, next)`: only a step that went from running to succeeded counts.
- [x] 8.2 Add failing tests in `runs/useRecentlyFinished.test.tsx` with fake timers: a step that goes from running to succeeded in a live run is in the set for 1500 ms and then leaves it; a run that is not live never fills it; a step that first appears as succeeded is not in it; two steps that finish together leave together.
- [x] 8.3 Add a failing test in `CanvasEditor.live.test.tsx`: after `node_started` and `node_completed` for the Dense retrieval step, the edge into it has `flow-edge--done` and `animated`, and loses both after the hold time.
- [x] 8.4 Add `finishedNodes` and the `recentlyFinished` argument to `runs/runState.ts`, create `runs/useRecentlyFinished.ts`, add the `finishedNodes` prop to `FlowSurface.tsx`, and pass it from `CanvasEditor.tsx` with `monitor.live`. Add `.flow-edge--done` to `styles/app.css`. Run the three test files and confirm they pass.
- [x] 8.5 Mutation check: make `useRecentlyFinished` ignore `live`. Run `useRecentlyFinished.test.tsx` and confirm at least one test fails. Restore the code.
- [x] 8.6 Describe the edge animation in `docs/guides/web-workspace.md`.
- [x] 8.7 Check in a browser that an edge animates after a step finishes in a live run, and does not for a finished run. Record BLOCKED with the reason if no answer model exists to produce a live run.

## 9. Smooth-step connections after review

- [x] 9.1 Add a failing test in `CanvasEditor.live.test.tsx`: every connection of the Search template has the class `react-flow__edge-smoothstep`, and none has `react-flow__edge-default`. The existing "rewires a saved template" test in `CanvasEditor.edit.test.tsx` already checks that a saved revision holds the exact edge objects and a saved layout holds exactly `positions`, `selection` and `viewport`, so it guards that no line type is saved.
- [x] 9.2 Set `type: "smoothstep"` on each edge in `FlowSurface.tsx`. Run both test files and confirm they pass.
- [x] 9.3 Mutation check: remove the type. Run the new test and confirm it fails. Restore the code.
- [x] 9.4 Check in a browser that the long wrap-around connection is a stepped line in light and dark, and that selected and animated edges still look right. Describe the line shape in `docs/guides/web-workspace.md`.

## 10. Expanding summary after review

- [x] 10.1 Add failing tests in `OperationNode.test.tsx`: the summary is a button with `aria-expanded` false and the class `line-clamp-1`; a click gives `aria-expanded` true and removes `line-clamp-1`; a second click restores both; a click and Enter on the summary do not call `onChange` (no selection), and a click on the step name does. Let `renderCards` take an `onChange`.
- [x] 10.2 Make the summary in `OperationNode.tsx` a button with `nodrag nopan`, a local expanded state, and click and key handlers that stop propagation. Run the tests and confirm they pass.
- [x] 10.3 Mutation check: remove the `stopPropagation` calls. Run the tests and confirm the selection tests fail. Restore the code.
- [x] 10.4 Describe the expanding summary in `docs/guides/web-workspace.md`. Check in a browser that a click expands the text, a second click folds it, and the card does not select.

## 11. Intro line moves out of the popovers after review

- [x] 11.1 Change the failing tests first. In `CanvasEditor.edit.test.tsx`, the intro shows without a click, after the heading and before the pipeline tabs, outside `.react-flow` and outside any popover, and a popover that is open does not hold it. In `ProfileHeader.test.tsx`, the intro shows once above the tabs, a built-in popover holds the description and the read-only note but not the intro, and an editable profile's popover holds the description only.
- [x] 11.2 Move the intro out of the popovers into a `p` with `py-1` above the tabs in `ProfileHeader.tsx`. Run the tests and confirm they pass.
- [x] 11.3 Update `docs/guides/web-workspace.md` and re-capture the three canvas screenshots. Check the line in a browser at 1280 and 390 pixels.

## 12. Settings mini card after review

- [x] 12.1 Add failing tests. In `stepSummary.test.ts`, `mainSettings` also returns the left-over fields as `rest`, and `cardLines` returns `extraSettings` with label and value. In `OperationNode.test.tsx`, the settings sit in an element `[data-slot="node-settings"]` with a border; the Prepare query card has a button "+2 more settings" with `aria-expanded` false; a click shows five settings and the label "Show fewer settings"; a second click folds it; the click and Enter do not call `onChange`; a card with no left-over settings has no such button; "No settings" and the model line sit in the same mini card. Update the old "+2 more in Step settings" assertions.
- [x] 12.2 Return `rest` from `mainSettings`, `extraSettings` from `cardLines`, and render the mini card and the button in `OperationNode.tsx`. Run the tests and confirm they pass.
- [x] 12.3 Mutation check: remove `stopPropagation` from the more button. Confirm the selection test fails. Restore the code.
- [x] 12.4 Update `docs/guides/web-workspace.md`, re-capture the three screenshots, and check in a browser that the mini card shows, expands and folds.
- [x] 12.5 The settings mini card makes Prepare query 257 pixels tall, so the 240 pixel row step from task 4.11 is too small. Raise the row step in `graph.ts` (`freeSlot`) and `drafts.ts` (`gridSlot`) to 280, and update `graph.test.ts` and `drafts.test.ts`. Measure again in a browser and confirm that no card overlaps another in the three templates.

## 13. Hideable header after review

- [x] 13.1 Add failing tests in `CanvasEditor.edit.test.tsx`: "Hide header" exists with `aria-expanded` true; a click hides the intro line, tabs and buttons (the wrapper has `inert`), shows a strip with the profile name and "Show header", and moves focus to it; a click on "Show header" restores everything and moves focus to "Hide header"; a notice still shows while hidden; a new mount starts shown. Add a test in `ProfileHeader.test.tsx`: the button shows only when `onHide` is passed.
- [x] 13.2 Add the `onHide` prop and button to `ProfileHeader.tsx`. Add the collapse state, the sliding wrapper and the strip to `CanvasEditor.tsx`. Run the tests and confirm they pass.
- [x] 13.3 Mutation check: remove `inert` from the hidden wrapper. Confirm the focus test fails. Restore the code.
- [x] 13.4 Describe the header button in `docs/guides/web-workspace.md`. Check in a browser that the header slides, the canvas grows and the strip works at 1280 and 390 pixels.

## 14. Header toggle keeps the title row after review

- [x] 14.1 Change the failing tests first. In `CanvasEditor.edit.test.tsx`: the toggle is one button that is named "Hide header" with `aria-expanded` true, then "Show header" with `aria-expanded` false, and it is the same element and keeps focus; the intro line and the pipeline tabs sit inside `[inert]` while hidden; the profile name and the "All profiles" link do not; no `[data-slot="header-strip"]` exists. In `ProfileHeader.test.tsx`: the toggle shows only when `onToggle` is passed, and reads "Show header" when `collapsed` is true.
- [x] 14.2 Replace `onHide` with `collapsed` and `onToggle` in `ProfileHeader.tsx`, move the sliding wrapper around the intro line and tabs into it, and remove the strip, `flushSync` and `autoFocus` from `CanvasEditor.tsx`. Run the tests and confirm they pass.
- [x] 14.3 Update `docs/guides/web-workspace.md` and re-capture the three screenshots. Check in a browser at 1280 and 390 pixels that the title row stays and the toggle stays in place.
- [x] 14.4 The sliding region clips its content, which cut off the pipeline info popover. Draw the popover panel in a portal on the page body, placed from the button and kept inside the screen width, and close it on scroll and resize. Add tests in `InfoPopover.test.tsx` that failed first.

