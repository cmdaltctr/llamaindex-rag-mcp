# Tasks

Work in the sibling worktree `llamaindex-rag-mcp-feat-studio-full-settings` on `feat/studio-full-settings`. Before each command that changes state, check `git rev-parse --show-toplevel` and `git branch --show-current`. Read `web/DESIGN.md` and load the `omrg-design` skill before UI work. There is no Prettier config: match the style by hand. Commit each group with `uv run --no-sync git commit` and a Conventional Commit message.

## 1. Hybrid shape file and parity test

- [x] 1.1 Test first: add `tests/unit/test_hybrid_shape_parity.py`. It builds `_search_graph(None, hybrid=True, rerank=True)` and `_search_graph(None, hybrid=False, rerank=True)` from `src/omrg/pipeline_templates.py` and compares their node and edge difference with `web/src/studio/hybridShape.json`. Verify: `uv run --no-sync pytest tests/unit/test_hybrid_shape_parity.py -q` fails because the JSON file does not exist.
- [x] 1.2 Add `web/src/studio/hybridShape.json` with the two added steps, the three connections into and between them, and the rule that moves each Dense retrieval `evidence` connection to fusion `evidence`. Verify: task 1.1 passes. Change one port name in the JSON file and confirm the test fails, then restore it.
- [x] 1.3 Raise the executed count in `tests/test_clean_base_tripwire.py` by the new case count, with a comment line in the existing style. Verify: `uv run --no-sync pytest tests/test_clean_base_tripwire.py -q` passes.

## 2. Hybrid switch logic

- [x] 2.1 Test first: add `web/src/studio/hybrid.test.ts` for `hybridState`, `enableHybrid` and `disableHybrid`. Cover: on and off on the canonical Search and Answer graphs; off after on gives the first graph back apart from the layout of the removed steps; Prepare query and Dense retrieval params survive; the Dense retrieval `collection` is copied to Sparse retrieval; existing positions do not change; ids `sparse_2` and `fuse_2` when `sparse` and `fuse` are taken; "custom" for two Dense retrieval steps, for a fusion step without Sparse retrieval, and for a graph with no Prepare query to Dense connection; "unavailable" with the catalogue reason. Verify: `npm test -- hybrid` fails in `web/` because `hybrid.ts` does not exist.
- [x] 2.2 Add `web/src/studio/hybrid.ts`. It reads the step and connection shape from `hybridShape.json` and uses the helpers in `graph.ts`. Verify: task 2.1 passes. Break the edge move in `enableHybrid` and confirm at least one case fails, then restore it.

## 3. Pipeline settings: hybrid switch, pipeline-wide settings, rerank candidate factor

- [x] 3.1 Test first: add `web/src/studio/PipelineBar.test.tsx`. Cover each scenario of "Pipeline settings switch hybrid retrieval" and "Pipeline settings show pipeline-wide settings": the switch shows on Search and Answer only; it reads the saved shape; it is disabled with a reason for a custom shape, an unavailable operation and a built-in profile; an API override shows with its plain label and Remove; "Rerank candidate factor" writes and removes `retrieval.rerank_fetch_multiplier` and refuses 0. Verify: the tests fail before the change.
- [x] 3.2 Add `web/src/studio/PipelineOverrides.tsx`, and add the hybrid switch and the overrides list to `PipelineBar.tsx`. Pass `purpose` and the catalogue from `CanvasEditor.tsx`. Add the label "Rerank candidate factor" for `retrieval.rerank_fetch_multiplier` to `labels.ts`. Verify: task 3.1 passes, and `CanvasEditor.settings.test.tsx` and `CanvasEditor.readonly.test.tsx` still pass.
- [x] 3.3 Test first: in `web/src/studio/CanvasEditor.edit.test.tsx`, turn hybrid on through the panel with the fake server, save a revision, and check the saved document holds `retrieve.sparse`, `combine.rrf`, the four new connections and no Dense retrieval to Cross-encoder rerank connection. Verify: the test fails before task 3.2 is wired into `CanvasEditor`, then passes.
- [x] 3.4 Update the Studio canvas layout section of `docs/guides/web-workspace.md`: the hybrid switch, the pipeline-wide settings list and the rerank candidate factor. Use ASD-STE100 style. Verify: `grep -n "Hybrid retrieval" docs/guides/web-workspace.md` finds the new text, and the Sign in section is unchanged.

## 4. Card settings panel

- [x] 4.1 Test first: move the bypass switch and the parameter controls of `NodeInspector.tsx` into a new `StepSettingsFields.tsx`. Add `web/src/studio/StepSettingsFields.test.tsx` that renders it for Prepare query and Cross-encoder rerank and checks the labels, the value notes, the read-only state and the bypass switch. Verify: the new tests and the existing `CanvasEditor.settings.test.tsx` pass, and `NodeInspector.tsx` renders `StepSettingsFields`.
- [x] 4.2 Test first: extend `web/src/studio/OperationNode.test.tsx` and add `CanvasEditor` cases for each scenario of "Step cards open their settings" and "The card settings panel edits a step in place": the button name "Settings for <step name>"; `aria-expanded`; a number set from the card; bypass from the card; Backspace in a panel field keeps the step; "Open in Step settings" selects the step and opens Step settings; Escape returns focus to the button; disabled controls on a built-in profile; Embed chunks shows the model line and no model control. Verify: the tests fail before the change.
- [x] 4.3 Add `StepCardSettings.tsx` (the `Popover` with `StepSettingsFields` and "Open in Step settings") and a React context for the edit callbacks, provided in `CanvasEditor.tsx`. Replace the decorative icon in `OperationNode.tsx` with the button. Verify: task 4.2 passes, and `OperationNode.internals.test.tsx` and `FlowSurface.readonly.test.tsx` still pass.
- [x] 4.4 Update `docs/guides/web-workspace.md` for the card settings button. Verify: the guide names "Settings for <step name>" and "Open in Step settings".

## 5. Metadata filter, labels and description

- [x] 5.1 Test first: in `schema.test.ts`, `stepSummary.test.ts` and a new `ParamField.test.tsx`, cover the scenarios of "Object settings are edited as JSON text": kind `json` for `metadata_filter`, a valid object saved, "Enter a JSON object." for invalid text with no draft change, empty text removes the parameter, compact JSON on the card, and Prepare query now counts six editable settings. Also check the label "PDF reader". Verify: the tests fail before the change.
- [x] 5.2 Add the `json` kind in `schema.ts`, the JSON text control in `ParamField.tsx`, compact JSON in `stepSummary.ts`, and the label "PDF reader" in `labels.ts`. Verify: task 5.1 passes, and every existing `web/src/studio` test passes.
- [x] 5.3 Test first: add `web/src/studio/ProfileDescriptionEditor.test.tsx` for "User profiles can be described in place": Enter sends `{description}` to `PATCH /v1/profiles/{id}`, Escape sends nothing, over 1000 characters is refused, a failure keeps the old text and shows a Retry line, and a built-in profile shows no pencil. Verify: the tests fail before the change.
- [x] 5.4 Add `description?: string` to `ProfileUpdateInput` in `web/src/api/profiles.ts`, add `ProfileDescriptionEditor.tsx` and show it in `ProfileHeader.tsx`. Verify: task 5.3 passes, and `ProfileHeader.test.tsx` and `ProfileTitleEditor.test.tsx` still pass.
- [x] 5.5 Update `docs/guides/web-workspace.md` ("Profiles in Studio") for the metadata filter and the description editor. Verify: the guide no longer says that object settings cannot be edited, if it said so.

## 6. Browser check on a throwaway server

Finding from task 6.2: on Answer, Sparse retrieval covered Prepare evidence. `enableHybrid` now puts each new step in the nearest free slot below Dense retrieval (test "places the new steps clear of every other step" in `hybrid.test.ts`).

- [x] 6.1 Build the web (`npm run build` in `web/`). Start `omrg web` from the worktree venv on a free port (not 8765), with `--workspace` and `HOME` under the scratch folder and `OMRG_CONFIG_DIR` in that folder. Never use the login item, `~/.omrg`, `~/.config/omrg` or `uv tool install`. Verify: the launch link opens in a new Orca tab.
- [x] 6.2 At 1280 px wide: duplicate `documents`, open Search, turn hybrid on, check the canvas shows Sparse retrieval and fusion with the right connections, save a revision, reload and check the switch shows on. Open Answer and repeat. Turn hybrid off and save. Verify: screenshots show each state, and `GET /v1/pipelines/{id}` holds the expected shape.
- [x] 6.3 At 1280 px wide: open the card settings panel on Prepare query, set "Number of results" and a metadata filter, bypass Cross-encoder rerank, use "Open in Step settings", and set "Rerank candidate factor". Verify: the cards show "(set here)" values, the panel fits on screen, and the draft check shows no issue.
- [x] 6.4 At 390 px wide: repeat a short pass of 6.2 and 6.3. Verify: no horizontal page scroll, the card panel stays inside the viewport, and the switch and the overrides list are usable.
- [x] 6.5 Stop the server and close the tab. Verify: the port is free again.

## 7. Integration and merge

Tasks 7.2, 7.4 and 7.5 belong to the integrator. Do not archive the change before they pass.

- [x] 7.1 Run `npm run lint`, `npm run typecheck` and `npm test` in `web/`. Verify: all pass, and every changed file stays under 500 lines.
- [ ] 7.2 Merge `v3` into the feature branch if `v3` moved (for example after `persistent-web-auth-token` lands). Resolve `tests/test_clean_base_tripwire.py` and `docs/guides/web-workspace.md` by hand, then set the tripwire count from a fresh measurement. Verify: `git status` is clean after the merge commit.
- [x] 7.3 Run `openspec validate studio-full-settings --strict` and `openspec validate --all --strict`. Verify: both pass.
- [ ] 7.4 Run `env -u OPENROUTER_API_KEY -u ANTHROPIC_API_KEY ./scripts/local_ci.sh`. Verify: every step passes.
- [ ] 7.5 Merge into `v3` from the `v3` worktree with `git merge --no-ff feat/studio-full-settings`. Verify: `git log --oneline -1` in the `v3` worktree shows the merge commit, and the fast suite passes there.
