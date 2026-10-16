# Proposal

## Why

The Studio canvas sub-page (`#/studio/<pipeline-id>`) does not look or work like a canvas studio. The workspace navigation takes 13 rem of width. The flow surface is a 60 vh box in the middle of a scrolling page. Six separate cards (pipeline settings, Operations, Nodes and Connections, Connect ports, Revision and run, Node settings) sit above, below and beside it. The user must scroll to find a control and cannot see what each card is for. The canvas is the main tool, so it should have the whole screen, with the controls floating on top of it.

## What Changes

- On the canvas sub-page the workspace navigation collapses to its icon column by itself. The stored per-browser navigation choice stays unchanged. Other pages keep their current behaviour.
- The flow surface fills the whole main area from the top bar to the bottom of the window. The page padding is removed on this sub-page. A slim bar keeps the pipeline title (as the page `h1`), the "All pipelines" link and the notices.
- One panel floats over the right side of the canvas. It is one card with accordion sections, each with its own icon:
  1. Pipeline settings (Title, Profile, Collection), at the top, above Operations
  2. Operations (the catalogue)
  3. Nodes and connections (the outline)
  4. Connect ports (the keyboard connection menu)
  5. Revision and run
  6. Node settings (the selected node)
- The panel shrinks. A button in its header collapses it to a narrow floating icon rail, in the style of the app navigation icon column. The rail has one icon button per section. Pressing an icon expands the panel and opens that section.
- Several sections can be open at the same time. Operations is open on first load. Selecting a node opens Node settings and starting a run opens Revision and run. If the panel is collapsed, it stays collapsed and the rail icon shows the section as open.
- A small accordion primitive is added to `web/src/components/ui/`. It keeps the Radix accessibility contract.
- No change to the graph model, the draft, the run behaviour, the API or the keyboard controls. Every control that exists today stays reachable.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `workspace-studio`: the canvas sub-page requirement changes from "flow surface in the main column, palette in a right-hand column" to "flow surface fills the main area, one floating panel on the right". It also gains a requirement for the accordion sections (icons, order, default open state) and one for collapsing the panel to an icon rail.
- `workspace-presentation`: gains a requirement that the navigation collapses on the canvas sub-page without changing the stored choice.
- `web-ui-stack`: gains a requirement that the accordion primitive keeps the Radix accessibility contract.

## Impact

- **Code (web only):** `web/src/App.tsx` (shell padding and navigation state), `web/src/components/AppNav.tsx` (no change expected), `web/src/lib/navCollapsed.ts` (read-only use), `web/src/studio/CanvasEditor.tsx` (layout), `web/src/studio/FlowSurface.tsx` (height), `web/src/studio/Palette.tsx`, `GraphOutline.tsx`, `ConnectionMenu.tsx`, `RunPanel.tsx`, `NodeInspector.tsx`, `PipelineBar.tsx` (drop their card chrome), and new `web/src/studio/CanvasPanel.tsx`, `web/src/studio/panelSections.ts` (the six sections with their icons) and `web/src/components/ui/accordion.tsx`.
- **Tests:** the four `CanvasEditor.*.test.tsx` files and `StudioView.test.tsx` find controls by region name. They need updates where a region becomes an accordion section.
- **Dependencies:** one new pinned package, `@radix-ui/react-accordion@1.3.1` (peer range includes React 19). The user approved it on 2026-10-16.
- **Docs:** `docs/guides/web-workspace.md` and the two Studio canvas screenshots (`studio-canvas-light-1280.png`, `studio-canvas-dark-1280.png`). The files have no generation script, so the tasks include a manual re-capture.
- **Not affected:** Python code, the HTTP API, stored data and the other six areas.
