# Tasks

Work in the worktree `llamaindex-rag-mcp-feat-studio-canvas-layout` on branch `feat/studio-canvas-layout`. Run web tests with `npm test` in `web/`. For each test task, run the test first and see it fail, then write the code.

## 1. Accordion primitive

- [x] 1.1 Get the user's approval for `@radix-ui/react-accordion@1.3.1` (design D4). Verify: approved by the user on 2026-10-16.
- [x] 1.2 Write `web/src/components/ui/accordion.test.tsx` for the four `web-ui-stack` scenarios: `aria-expanded` follows open state, Down arrow moves focus to the next header, closed content is not reachable, a leading header icon does not change the accessible name. Verify: the test fails because the file does not exist.
- [x] 1.3 Run `npm install --save-exact @radix-ui/react-accordion@1.3.1` in `web/`. Verify: `package.json` and `package-lock.json` show the exact version and `npm ls @radix-ui/react-accordion` lists one copy.
- [x] 1.4 Add `web/src/components/ui/accordion.tsx` (multiple mode, token styles, optional `aria-hidden` leading icon, chevron that turns with state, visible focus ring). Verify: task 1.2 tests pass.

## 2. Navigation follows the route

- [x] 2.1 Write tests in `web/src/App.test.tsx` for the four `workspace-presentation` scenarios: expanded choice collapses on `#/studio/<id>`, stored choice applies on `#/knowledge-base`, temporary expansion is not stored and resets on re-entry, the gallery `#/studio` is unaffected. Verify: they fail on the current code.
- [x] 2.2 In `web/src/App.tsx`, derive `collapsed` from the route and a local `expandedHere` state (design D1). Leave `web/src/lib/navCollapsed.ts` unchanged. Verify: task 2.1 tests pass and `git diff web/src/lib/navCollapsed.ts` is empty.

## 3. Full-height canvas shell

- [x] 3.1 Write tests in `web/src/App.test.tsx` that on the canvas route `main` has no padding class and the shell uses full height, and that other routes keep their classes. Verify: they fail first.
- [x] 3.2 In `web/src/App.tsx`, switch `min-h-dvh` to `h-dvh` and drop the `main` padding on the canvas route only, with `min-h-0` and `overflow-hidden` from `lg` up and `overflow-auto` below (design D3). Verify: task 3.1 tests pass.
- [x] 3.3 In `web/src/studio/FlowSurface.tsx`, replace `h-[50vh] min-h-64 md:h-[60vh] md:min-h-80` with `h-full min-h-64`. Verify: `FlowSurface` tests still pass.

## 4. Canvas panel

- [x] 4.1 Write `web/src/studio/panelSections.test.ts` and `web/src/studio/CanvasPanel.test.tsx` for the `workspace-studio` scenarios: six sections in order with Pipeline settings before Operations, six different icons, Operations is the only section open at load, a restored selection also opens Node settings at load, a run that exists at load leaves Revision and run closed, each section content is a region named by its title with an `h2` header, two sections can be open, selecting a node after load opens Node settings, starting a run from the panel opens Revision and run, closing Pipeline settings keeps the edited title, Enter and Space toggle a header. Verify: the tests fail because the files do not exist.
- [x] 4.2 Write the rail tests in `CanvasPanel.test.tsx`: the collapse button leaves six rail buttons and an expand button, collapsing moves focus to the expand button and expanding moves it back to the collapse button, a rail button expands the panel and opens its section and moves focus to the header, a rail button on an open section does not close it, the highlight and the ", open" name suffix follow the open sections, selecting a node while collapsed keeps the panel collapsed and highlights Node settings, a collapse and expand round trip keeps the open sections and the draft, each rail button shows a tooltip with its title, and below `lg` the card carries no `lg:hidden` and the rail carries `hidden` (class check, because jsdom has no layout). Verify: the tests fail first.
- [x] 4.3 Remove the outer card and `h2` from `Palette.tsx`, `GraphOutline.tsx`, `ConnectionMenu.tsx`, `RunPanel.tsx` and `NodeInspector.tsx`. Change `PipelineBar.tsx` to one column. Keep their props and inner content. Verify: `npm run build` type-checks.
- [x] 4.4 Add `web/src/studio/panelSections.ts` (id, title, Lucide icon per section: `SlidersHorizontal`, `Blocks`, `ListTree`, `Cable`, `Play`, `Settings2`) and `web/src/studio/CanvasPanel.tsx` with the floating card, the six sections in order, the collapse button (`PanelRightClose`), the rail with the expand button (`PanelRightOpen`), the controlled `open` and `collapsed` state, the render-time selection check and the run-start hook, `h2` headers and CSS-based collapse (design D5, D6). Verify: tasks 4.1 and 4.2 tests pass.
- [x] 4.5 Rewrite the layout in `web/src/studio/CanvasEditor.tsx`: slim bar with the `h1`, the "All pipelines" link and the notices; a `relative` canvas region with the flow surface at full size and the panel layer over it (`pointer-events-none` on the layer, `pointer-events-auto` on the card and rail, `shadow-floating`); a stacked column below `lg`. Remove `PageHeader` use on this route. Give the loading, error and "not found" states in `CanvasPage.tsx` their own `p-4 md:p-6` (design D2, D3, D7). Verify: the page has one `h1`, the shell still moves focus to it after navigation, and a test shows the layer passes pointer events through outside the card.

## 5. Existing tests

- [x] 5.1 Rename the region lookups "Operation catalogue" to "Operations" and "Graph outline" to "Nodes and connections" (14 uses). Update `CanvasEditor.edit.test.tsx`, `CanvasEditor.settings.test.tsx`, `CanvasEditor.workspace.test.tsx`, `CanvasEditor.live.test.tsx` and `StudioView.test.tsx` for the new regions. Open a section in a shared helper where a test needs a closed one. Keep every behaviour assertion. Verify: `npm test` in `web/` passes with the same number of behaviour assertions (no test deleted without a replacement).
- [x] 5.2 For each changed test, confirm it fails when the code under test is broken. Break one line in each new component, run its test, then restore the line. Verify: each test failed once and passes after the restore.

## 6. Preview check and docs

- [x] 6.1 Run `npm run build` in `web/`, restart `omrg web` from the worktree and open `#/studio/<id>` at 1440, 1280, 1024 and 390 px, in light and dark. Verify against `docs/proposal/studio-canvas-wireframe.md`: the navigation is an icon column, the canvas fills the whole area, the panel floats on the right with six icon sections, the collapse button gives the icon rail, a rail icon expands the panel with its section, nothing overflows horizontally.
- [x] 6.2 Check the keyboard path: select a node with the keyboard, open Connect ports, connect two ports, remove a connection, validate. Verify: it works without a pointer (`pipeline-canvas` scenario "Graph is edited using a keyboard").
- [x] 6.3 Check that the draft, selection and run identity survive: edit a title, close its section, navigate to the Knowledge Base and back. Verify: the title is intact. Repeat after collapsing and expanding the panel.
- [x] 6.4 Update the Studio canvas text in `docs/guides/web-workspace.md` and re-capture `studio-canvas-light-1280.png` and `studio-canvas-dark-1280.png` by hand. Add a third capture of the collapsed rail if the guide describes it. Verify: the guide matches the new layout and the images show the floating panel.

## 7. Gates and merge

- [x] 7.1 Run `openspec validate studio-canvas-layout --strict` and `openspec validate --all --strict`. Verify: both exit 0.
- [x] 7.2 Run `./scripts/local_ci.sh` in the worktree. Verify: exit 0. Note that CI also runs `floors` and `extras` jobs that this script does not cover.
- [x] 7.3 Commit with Conventional Commits (`feat(web): …`) on `feat/studio-canvas-layout` and merge into `integration/core-web` after the user confirms the preview. Verify: `git log integration/core-web` shows the merge and the worktree is clean.
- [x] 7.4 Before `git worktree remove`, copy any gitignored artefacts worth keeping to `integration/core-web` (Critical Gotcha 15). Never copy `.env`. Verify: the copy list is checked, then the worktree is removed.
