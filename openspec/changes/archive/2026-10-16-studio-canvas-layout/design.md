# Design

## Context

The shell (`web/src/App.tsx`) is a CSS grid: a top bar, the navigation column and a `main` with `p-4 md:p-6`. The navigation width comes from `useNavCollapsed`, a per-browser choice stored under `omrg-nav-collapsed`. No route logic touches it.

`CanvasEditor.tsx` renders a `PageHeader`, the notices, then a two-column grid. The left column stacks `PipelineBar`, `FlowSurface` (fixed `h-[50vh] md:h-[60vh]`), `GraphOutline`, `ConnectionMenu` and `RunPanel`. The right column stacks `Palette` and `NodeInspector`. Five of these components draw their own card (`rounded-panel border bg-card p-4` with an `h2`). `FlowSurface` renders only when the graph has nodes. An empty graph shows `EmptyState`.

The shell moves focus to the page `h1` after the user navigates to another area. The canvas page must keep an `h1`.

`web/src/components/ui/` has no accordion. Radix packages in use are pinned (`@radix-ui/react-dialog@1.3.1`, `react-select`, `react-tooltip` and others).

## Goals / Non-Goals

**Goals:**

- The canvas fills the main area on large windows and the page does not scroll.
- One panel, one card, six accordion sections with their own icons, in the order the user asked for. The panel floats over the canvas and shrinks to an icon rail.
- No change to graph, draft, run or API behaviour. No control is lost.
- Each existing component keeps its own file and props. The panel composes them.

**Non-Goals:**

- Moving, dragging or resizing the panel, or a floating title chip in place of the slim bar.
- Saving the open sections or the collapsed state between visits.
- Any change to the gallery page, the other six areas or the mobile navigation row.
- New canvas features, such as a mini-map.

## Decisions

### D1. The route decides the navigation state, and the stored choice stays untouched

`Shell` computes `collapsed = onCanvas ? expandedFor !== route.pipelineId : stored`. `onCanvas` is `route.area === "studio" && route.pipelineId !== null`. `expandedFor` is a `useState<string | null>(null)` that holds the pipeline id the user expanded the navigation on. On the canvas the toggle sets it to the current pipeline id, or back to `null`. Elsewhere the toggle calls the existing stored toggle. Opening another pipeline no longer matches the held id, so the navigation is collapsed again. Leaving the canvas clears `expandedFor` during render (`if (!onCanvas && expandedFor !== null) setExpandedFor(null)`, React's "adjust state when a value changes" pattern), so coming back to the same pipeline also starts collapsed. There is no effect. `useNavCollapsed` does not change.

*Why:* The user wants the bar to minimise by itself, not to lose their saved choice. Deriving the value from the route avoids an effect that writes storage on route change.

*Alternatives:* (a) Write the stored value on entering the canvas. This loses the user's choice on the next page. (b) Force the navigation collapsed with no toggle. This removes a control the user may want.

### D2. The panel floats over the canvas and shrinks to an icon rail

At `lg` (1024 px) and above, the canvas region is `relative` and holds the flow surface at full size (`absolute inset-0`, or `h-full w-full`). The panel is an absolutely positioned layer on top: `end-3 top-3`, `w-[22rem]`, `max-h-[calc(100%-1.5rem)]`, with its own vertical scroll, the card tokens and `shadow-floating` (the project uses the elevation token for floating surfaces only, so this fits). Collapsed, the same corner holds the rail: a narrow card (about 3 rem wide) with one icon button per section and an expand button, styled like the app navigation icon column (`size-9` buttons, `rounded-control`, `bg-selection` fill on the highlighted ones). Below `lg` the region is a column: the surface (`h-[60vh]`) then the panel as a normal card, with no rail and no floating, and the page scrolls.

*Why:* The user wants the canvas to take the whole space with the controls floating on top. The rail gives the canvas back almost all of its width when the panel is not needed.

*Alternatives:* (a) A docked 22 rem column (the first draft): never hides nodes, but the canvas loses 22 rem. Rejected after the user's request. (b) A draggable and resizable panel: more flexible, but needs pointer handling and keyboard alternatives. Left out of this change.

### D3. Full-height canvas through the shell, only on the canvas route

On the canvas route the shell uses `h-dvh` instead of `min-h-dvh`, and `main` drops its padding, gets `min-h-0` and, from `lg` up, `overflow-hidden`. Other routes keep their current classes. The editor root is a column: slim bar (`h1`, "All pipelines" link, notices), then the canvas region with `min-h-0 flex-1`. `FlowSurface` changes from `h-[50vh]…` to `h-full`, because React Flow needs a parent with a set height. Below `lg` `main` keeps `overflow-auto` so the page scrolls.

The route rule also covers the loading, error and "not found" states of `CanvasPage`. Those states add the usual `p-4 md:p-6` themselves, so they keep today's spacing.

### D4. One accordion primitive: Radix, `type="multiple"`

Add `web/src/components/ui/accordion.tsx` as a shadcn-style port of `@radix-ui/react-accordion@1.3.1` (peer range includes React 19). Styling uses the existing tokens and a Lucide chevron.

*Why:* This follows how every other primitive in `ui/` is built, and Radix gives the keyboard contract (arrows, Home and End) and `aria-expanded` and `aria-controls` for free.

*Alternatives:* (a) Native `<details>` and `<summary>`: no dependency, but no arrow-key movement and the open state is awkward to control from code. (b) A hand-written button and region component: no dependency, but it repeats a solved accessibility problem. **The user approved this dependency on 2026-10-16.**

### D5. Sections keep their components, and the panel owns the chrome

`web/src/studio/panelSections.ts` lists the six sections once: id, title, icon and a render key. `CanvasPanel.tsx` and the rail both read that list, so the order and icons cannot drift apart. Lucide icons (all present in `lucide-react@1.57.0`):

| Section | Icon |
|---|---|
| Pipeline settings | `SlidersHorizontal` |
| Operations | `Blocks` |
| Nodes and connections | `ListTree` |
| Connect ports | `Cable` |
| Revision and run | `Play` |
| Node settings | `Settings2` |

The collapse and expand buttons use `PanelRightClose` and `PanelRightOpen`. Icons are `aria-hidden`; the title stays the accessible name.

`PipelineBar`, `Palette`, `GraphOutline`, `ConnectionMenu`, `RunPanel` and `NodeInspector` lose their outer card and `h2`. Their inner content, props and behaviour stay as they are. Section titles: "Pipeline settings", "Operations", "Nodes and connections", "Connect ports", "Revision and run", "Node settings". `GraphOutline` today shows the Nodes and Connections lists in one card, so they form one section. Radix gives each section's content `role="region"` named by its header, so the region names change: "Operation catalogue" becomes "Operations" and "Graph outline" becomes "Nodes and connections". The existing tests use those two old names 14 times; task 5.1 renames them. "Latest run" stays as an inner region of Revision and run, so its 3 lookups keep working once the section is open.

The accordion header renders an `h2` (Radix `Accordion.Header asChild`), because the slim bar holds the page `h1`. The default `h3` would skip a level.

`PipelineBar` changes from three columns to one column, because the panel is 22 rem wide.

### D6. Open and collapsed state are controlled in `CanvasPanel`

`CanvasPanel` holds `open: string[]` and `collapsed: boolean` (starts `false`). The initial `open` is `["operations"]`, plus `"node"` when the restored draft already has a selected node (drafts store `layout.selection`).

Two events add a section after load. Neither uses an effect that watches a value, because both values are already set when the page loads (the restored selection, and the latest run from `runsQuery(..., { limit: 1 })`). An effect on them would open sections on load and break the default state.

- **Selection changes to a node.** `CanvasPanel` keeps the previous `selectedNode` in state and compares during render (React's "adjust state when a prop changes" pattern). When the value changes to a node id, it adds `"node"`. The first render does not count as a change.
- **The user starts a run.** The panel's run action calls `session.actions.run()` and, when the run is admitted, adds `"run"`. A run record loaded from the server never opens the section.

Neither event closes a section or changes `collapsed`. When collapsed, the rail shows the added section as open.

Rail buttons are plain buttons, not toggle buttons, because pressing one never closes a section. The open state is in the highlight and in the accessible name ("Operations, open"), so it does not depend on colour. A rail button sets `collapsed` to `false`, adds its section and moves focus to that section's header after the panel renders. The collapse button moves focus to the rail's expand button, and the expand button moves focus back to the collapse button.

The collapsed state uses CSS, not unmounting. From `lg` up, collapsed hides the card (`lg:hidden`) and shows the rail (`hidden lg:flex`). Below `lg` the card always shows and the rail never does. `display: none` takes the hidden card out of the tab order and the accessibility tree. If the window narrows while collapsed, the stacked panel still shows its sections.

State is local to the editor, so it resets when the pipeline changes (the editor is already mounted with `key={pipelineId}`), and it is not stored. The draft lives in the editor, so nothing is lost.

Radix unmounts the content of a closed section. Local, unsaved component state in that section resets when it closes: the operation search text and a half-chosen pair in Connect ports. Draft, selection, run inputs and run identity live above the panel and are not affected.

### D7. The slim bar replaces `PageHeader` on this route

The bar holds the `h1` (pipeline title, or the stored title), the "All pipelines" button and the `Notices` region. The `summary` line ("Connect pipeline stages…") is dropped. The notice region keeps `role="status"` or `role="alert"` as today. The empty-graph `EmptyState` renders in the canvas region, centred.

### D8. Tests and docs

Tests move with the code. Region lookups change from "a section with this label" to "an accordion section with this header", and open-state helpers are shared. New tests cover: route-driven navigation state (the four scenarios), accordion defaults and auto-open, section icons, the collapse and expand round trip, rail highlight and accessible name, focus moves, restored selection and earlier run at load, selection while collapsed, the narrow-window case, and that closing or collapsing keeps the draft. Each new test is shown failing before the code that satisfies it. The two canvas screenshots in `docs/guides/web-workspace.md` are re-captured by hand, because no script produces them.

## Risks / Trade-offs

- **React Flow measures its parent.** A wrong `h-full` chain gives a zero-height canvas. Mitigation: a test asserts the height class chain, and the manual preview check is part of the tasks.
- **The floating panel can cover nodes.** The canvas is full width under it, so a node on the right can sit behind the panel. Mitigation: collapse the panel to the rail, or pan the canvas. The panel's scroll area stays inside the canvas region so it never covers the slim bar. A "fit view with panel offset" option can follow if this proves annoying.
- **Pointer events.** The panel layer must stop pointer events from reaching React Flow (no accidental pan or drag through the card), and the empty area around it must pass them through. Mitigation: only the card and the rail receive pointer events, and a test checks that the layer wrapper has `pointer-events-none` while the card has `pointer-events-auto`.
- **A 22 rem panel with six sections can get long.** The panel scrolls inside its own column. Operations keeps its own list scroll (`max-h-80`), so one open section cannot push the others out of reach.
- **Regions inside accordions.** If a test or a user relied on every card being visible at once, they now need one click. Operations and the selected node open by themselves to limit this.
- **No auto-expand.** If the user collapsed the panel and then selects a node, the settings do not appear until they press the rail icon. This keeps the canvas clear, which is why they collapsed it. The highlight on the rail icon is the signal.
- **Icon-only rail.** Icons alone are not a label. Each rail button has a tooltip and an accessible name, and keyboard focus shows the tooltip.
- **Closed sections reset local state.** Closing Operations clears its search text, and closing Connect ports clears a half-chosen pair. Accepted: the draft is not affected, and keeping every section mounted with `forceMount` would put hidden fields back into the page.
- **New dependency.** Small, same vendor as the other primitives, approved.

## Migration Plan

No data, API or stored-state change. The new code ships with the web bundle. Rollback is a revert of the change. `src/omrg/transports/api/static/` is gitignored, so a merge needs `npm run build` in `web/` before `omrg web` shows the new layout.

## Open Questions

1. **Panel width.** The design keeps 22 rem. Say if you want it wider or narrower.
2. **Remember the collapsed state?** The design resets it on each visit. Storing it per browser (like the navigation choice) is a small follow-up.
3. **Title.** The design keeps the slim bar for the title and the "All pipelines" link. A floating title chip on the canvas would look more like a design tool and is left out for now.
