# Studio canvas: wireframe of the proposed layout

Draft 3, 16 October 2026 (draft 2 plus fixes from the plan review). Local only. It shows what the OpenSpec change `studio-canvas-layout` will build on `#/studio/<pipeline-id>`. The change lives in the worktree `llamaindex-rag-mcp-feat-studio-canvas-layout` (branch `feat/studio-canvas-layout`). Nothing is built yet. Use this page to check the idea before apply.

What changed from draft 1: the panel no longer docks beside the canvas. It floats over the canvas, it shrinks to an icon rail, and every section has its own icon.

Source of truth: `openspec/changes/studio-canvas-layout/` (proposal, design, three spec deltas, tasks) in that worktree.

How to read the drawings:

| Mark | Means |
|---|---|
| `[ Run ]` | Primary button |
| `( Validate )` | Secondary or outline button |
| `[____________]` | Text field |
| `[ v documents ]` | Select |
| `{draft changed}` | Status badge (word inside) |
| `▾` `▸` | Accordion section open or closed |
| `▌` | Active navigation row or highlighted rail icon |
| `░` | The canvas, under a floating card |
| `...` | More rows of the same kind |

Widths are drawn for a 1280 px window unless marked.

---

## 1. Today (what you see now)

```
+--------------+----------------------------------------------------------+-------------+
| OMRS  v2.2.0 | Test                              ( All pipelines )      |             |
| ⌂ Home       | Connect pipeline stages, check the graph and run it.     |             |
| ◯ Chat       | [ Title ] [ Profile ] [ Collection ]   <- settings row   | Operations  |
| ▤ Knowledge  |  +----------------------------------------------------+  | [search...] |
| ▌⟜ Studio    |  |                                                    |  | cite        |
| ⚗ Experiments|  |             canvas, 60 vh, a small box             |  | prepare_ev  |
| ⏚ Integrations|  |                                                    |  | ...         |
| ⚙ Settings   |  +----------------------------------------------------+  +-------------+
|              | +--------------------+ +---------------------------+     | Node cite   |
|              | | Nodes              | | Connect ports             |     +-------------+
|              | +--------------------+ +---------------------------+
|              | +----------------------------------------------------+  page scrolls
|              | | Revision and run                                   |  down from here
+--------------+----------------------------------------------------------+
```

Problems: the canvas is small, controls are far apart, and it is hard to see which card does what.

---

## 2. Proposed, desktop (1024 px and wider), panel expanded

The navigation is the icon column. The canvas fills the whole area under the slim bar. One card floats over its right side. The page does not scroll.

```
+----+------------------------------------------------------------------------------------+
|OMRS| OMRS  Local workspace                                  ( 1 collection )   ☾       |
+----+------------------------------------------------------------------------------------+
| ⌂  | Test  {draft changed}                                    ( ← All pipelines )       |
| ◯  +------------------------------------------------------------------------------------+
| ▤  |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ ┌───────────────────────────┐ ░░░░░░|
|▌⟜  |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ Panel                 [⇥] │ ░░░░░░|
| ⚗  |░░░░  +--------------+     +--------------+░░░░ ├───────────────────────────┤ ░░░░░░|
| ⏚  |░░░░  | cite         |---->| prepare_ev   |░░░░ │ ⚙ ▸ Pipeline settings     │ ░░░░░░|
| ⚙  |░░░░  | {answer}     |     | {answer}     |░░░░ ├───────────────────────────┤ ░░░░░░|
|    |░░░░  +--------------+     +------+-------+░░░░ │ ▦ ▾ Operations            │ ░░░░░░|
|    |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░|░░░░░░░░░░░░ │   [ search operations...] │ ░░░░░░|
|    |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░v░░░░░░░░░░░░ │   Resolve citations {answer}│ ░░░░░|
|    |░░░░░░░░░░░░░░░░░░░░░░░░░ +--------------+░░░░░░ │   answer.cite             │ ░░░░░░|
|    |░░░░░░░░░░░░░░░░░░░░░░░░░ | synthesise   |░░░░░░ │   Prepare evidence ...    │ ░░░░░░|
|    |░░░░░░░░░░░░░░░░░░░░░░░░░ +--------------+░░░░░░ ├───────────────────────────┤ ░░░░░░|
|    |░░░░ [-] [+] [fit]  (zoom controls)░░░░░░░░░░░░░░ │ ☰ ▸ Nodes and connections│ ░░░░░░|
|    |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ ⌁ ▸ Connect ports         │ ░░░░░░|
|    |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ ▷ ▸ Revision and run      │ ░░░░░░|
|    |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ ⚙ ▸ Node settings         │ ░░░░░░|
|    |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ └───────────────────────────┘ ░░░░░░|
+----+------------------------------------------------------------------------------------+
 3.5rem   canvas: full width, under the card          card: 22rem, floats, shadow, scrolls inside
```

Facts shown here:

- The card floats with the floating-surface shadow. The canvas keeps its full width under it.
- `[⇥]` in the card header collapses the card to the rail (section 3).
- Each section header starts with its own icon. The icons in the drawing are rough symbols. The real ones are listed in section 4.
- Pipeline settings is first, above Operations. Operations is open on load. Node settings is also open on load if your saved draft had a node selected. An earlier run does not open Revision and run. The other sections are closed.
- The navigation is the icon column on this route, whatever you saved. Its toggle expands it for this visit only.
- The slim bar holds the page heading (pipeline title), the "All pipelines" link and notices.

---

## 3. Proposed, panel collapsed to the icon rail

The card shrinks to a narrow rail on the right, in the same style as the app navigation column: stacked icons, and a rounded filled highlight on an active one. The canvas has nothing in front of it except this rail.

```
+----+------------------------------------------------------------------------------------+
|OMRS| OMRS  Local workspace                                  ( 1 collection )   ☾       |
+----+------------------------------------------------------------------------------------+
| ⌂  | Test  {draft changed}                                    ( ← All pipelines )       |
| ◯  +------------------------------------------------------------------------------------+
| ▤  |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ ┌────┐ ░░░░░░░|
|▌⟜  |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ ⇤  │ ░░░░░░░|
| ⚗  |░░░░░  +--------------+       +--------------+░░░░░░░░░░░░░░░░░░░░░ ├────┤ ░░░░░░░|
| ⏚  |░░░░░  | cite         |------>| prepare_ev   |░░░░░░░░░░░░░░░░░░░░░ │ ⚙  │ ░░░░░░░|
| ⚙  |░░░░░  | {answer}     |       | {answer}     |░░░░░░░░░░░░░░░░░░░░░ │▌▦ ▌│ ░░░░░░░|  <- open section:
|    |░░░░░  +--------------+       +------+-------+░░░░░░░░░░░░░░░░░░░░░ │ ☰  │ ░░░░░░░|     filled rounded
|    |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░|░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ ⌁  │ ░░░░░░░|     highlight
|    |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░v░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ ▷  │ ░░░░░░░|
|    |░░░░░░░░░░░░░░░░░░░░░░░░░░ +--------------+░░░░░░░░░░░░░░░░░░░░░░░░░ │ ⚙  │ ░░░░░░░|
|    |░░░░░░░░░░░░░░░░░░░░░░░░░░ | synthesise   |░░░░░░░░░░░░░░░░░░░░░░░░░ └────┘ ░░░░░░░|
|    |░░░░ [-] [+] [fit]░░░░░░░░░░ +--------------+░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░|
+----+------------------------------------------------------------------------------------+
```

Rail, close up (top to bottom, with the real icon names):

```
┌────┐
│ ⇤  │  expand the panel                    PanelRightOpen
├────┤
│ ⚙  │  Pipeline settings                   SlidersHorizontal
│▌▦ ▌│  Operations   (open: highlighted)    Blocks
│ ☰  │  Nodes and connections               ListTree
│ ⌁  │  Connect ports                       Cable
│ ▷  │  Revision and run                    Play
│ ⚙  │  Node settings                       Settings2
└────┘
```

Rail rules:

- Each rail button has a tooltip with its section title. Screen readers hear the title, plus ", open" when that section is open (for example "Operations, open").
- A highlighted rail button means that section is open. Pressing it never closes the section.
- Pressing a rail icon expands the card and opens that section. Focus moves to that section's header.
- Collapsing moves focus to the expand button. Expanding moves it back to the collapse button.
- If you collapse and then narrow the window below 1024 px, the stacked panel shows its sections again.
- Collapsing and expanding keep the open sections, the draft and the selection.
- The panel starts expanded and the collapsed state is not stored between visits.

---

## 4. Section icons

| Section | Icon | Lucide name |
|---|---|---|
| Pipeline settings | sliders | `SlidersHorizontal` |
| Operations | blocks | `Blocks` |
| Nodes and connections | list tree | `ListTree` |
| Connect ports | cable | `Cable` |
| Revision and run | play | `Play` |
| Node settings | gear | `Settings2` |
| Collapse the panel | panel with arrow right | `PanelRightClose` |
| Expand the panel | panel with arrow left | `PanelRightOpen` |

Icons are decoration. The title is the accessible name.

---

## 5. Panel sections, open

### Pipeline settings

```
│ ▾ SlidersHorizontal  Pipeline settings │
│   Title                                │
│   [ Test                             ] │
│   Profile                              │
│   [ v Inherit from each collection   ] │
│   Collection                           │
│   [ Host default                     ] │
```

### Operations

```
│ ▾ Blocks  Operations                   │
│   [ search operations...             ] │
│   Resolve citations         {answer}   │
│   answer.cite                          │
│   Prepare evidence          {answer}   │
│   answer.prepare_evidence              │
│   ...                  (the list scrolls) │
```

### Nodes and connections

```
│ ▾ ListTree  Nodes and connections      │
│   Nodes                                │
│   cite              answer.cite        │
│   prepare_evidence  answer.prepare_ev  │
│   Connections                          │
│   cite.answer -> prepare_ev.answer [x] │
```

### Connect ports (keyboard path)

```
│ ▾ Cable  Connect ports                 │
│   From output  [ v Choose output     ] │
│   To input     [ v Choose input      ] │
│   ( Connect )                          │
```

### Revision and run

```
│ ▾ Play  Revision and run               │
│   ( Save layout ) ( Save revision )    │
│   ( Validate )    [ Run ]              │
│   No saved revision. Save a revision   │
│   before you run.                      │
│   ── after a run starts ──             │
│   Latest run  {running}                │
│   cite {succeeded}  prepare {running}  │
```

### Node settings

```
│ ▾ Settings2  Node settings: cite       │
│   answer.cite                          │
│   Map citation numbers in the answer   │
│   to the supplied chunk lineage.       │
│   Graph inputs and outputs             │
│   ( Use input answer )                 │
│   ( Expose output answer )             │
```

---

## 6. States

### A node is selected, panel expanded

Node settings opens by itself. Other open sections stay open.

```
|  canvas: [cite] highlighted          | │ ▾ Operations   (still open)          │
|                                      | │ ▾ Node settings: cite    <- opened   │
```

### A node is selected, panel collapsed

The panel stays collapsed. The Node settings icon gets the highlight. Press it to expand the panel with the settings.

```
|  canvas: [cite] highlighted          | │ ⚙  │
|                                      | │▌⚙ ▌│  <- Node settings now highlighted
```

### A run starts

Revision and run opens by itself and shows the live progress. On the canvas, each node shows its run state.

```
|  canvas: cite {succeeded} -> prepare_ev {running}  | │ ▾ Revision and run  <- opened │
|                                                    | │   Latest run  {running}       │
```

### Empty graph

The canvas area shows the message. The catalogue stays in the panel.

```
|                                      | │ ▾ Operations                         │
|     ⟜  The graph is empty.           | │   [ search operations...           ] │
|     Add an operation from the        | │   Resolve citations ...              │
|     catalogue to start.              | │                                      │
```

### Navigation expanded for this visit

You press the toggle in the icon column. The canvas gets narrower, the floating card keeps its place on the right. The saved choice does not change.

```
+--------------+---------------------------------------------------+
| OMRS  v2.2.0 | Test                       ( ← All pipelines )    |
| ⌂ Home       |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ ┌────────────────┐ ░░|
| ▌⟜ Studio    |░░░░░ canvas (narrower) ░░░░░░░ │ card           │ ░░|
+--------------+---------------------------------------------------+
```

### Light and dark

Both themes use the existing tokens. The card uses the card colour and the floating shadow. The open state is shown by the chevron and by `aria-expanded`, not by colour alone. The rail highlight uses the selection fill, as the navigation does.

---

## 7. Narrow windows (below 1024 px)

The panel does not float and there is no rail. The page scrolls. The canvas keeps a fixed height and the panel is a normal card under it. The navigation is the icon column from 768 px up and the top row below that (unchanged).

```
+----+----------------------------------------+
| ⌂  | Test                 ( ← All pipelines)|
| ◯  +----------------------------------------+
| ▤  |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░|
|▌⟜  |░░░░░ canvas, 60 vh ░░░░░░░░░░░░░░░░░░░░|
| ⚗  |░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░|
| ⏚  +----------------------------------------+
| ⚙  | ┌────────────────────────────────────┐ |
|    | │ ⚙ ▸ Pipeline settings              │ |
|    | │ ▦ ▾ Operations                     │ |
|    | │   ...                              │ |
|    | │ ☰ ▸ Nodes and connections          │ |
|    | │ ⌁ ▸ Connect ports                  │ |
|    | │ ▷ ▸ Revision and run               │ |
|    | │ ⚙ ▸ Node settings                  │ |
|    | └────────────────────────────────────┘ |
+----+----------------------------------------+
```

390 px (phone): the same, with the navigation as one row of icons at the top and one column of content.

---

### Closing a section

The draft is safe. Small unsaved things inside the closed section reset: the operation search text, and a half-chosen pair in Connect ports.

---

## 8. What does not change

- The graph, the draft, the selection, run identity and every API call.
- The keyboard path: select a node, open Connect ports, connect, remove, validate. It works without a pointer.
- Unsaved edits survive a reload, closing a section and collapsing the panel.
- The gallery at `#/studio`, and the other six areas.
- The navigation below the `md` breakpoint.

## 9. Questions and defaults

| # | Question | Status or default |
|---|---|---|
| 1 | New package `@radix-ui/react-accordion@1.3.1` | Approved |
| 2 | Floating panel with icon rail | Decided (this draft) |
| 3 | Panel width | 22 rem. Say if you want it wider. |
| 4 | Remember the collapsed state between visits | No. It resets on each visit. Easy to add later. |
| 5 | Selecting a node while collapsed | The panel stays collapsed and the rail icon highlights. It does not expand by itself, because you collapsed it to see the canvas. |
| 6 | Title as a floating chip on the canvas instead of the slim bar | Not in this change. |
| 7 | Nodes behind the floating card | You can collapse the card or pan the canvas. A "fit view beside the panel" option can follow. |

## 10. Where to look

| Item | Path |
|---|---|
| Proposal | `openspec/changes/studio-canvas-layout/proposal.md` |
| Design (decisions D1 to D8) | `openspec/changes/studio-canvas-layout/design.md` |
| Spec deltas | `openspec/changes/studio-canvas-layout/specs/{workspace-studio,workspace-presentation,web-ui-stack}/spec.md` |
| Tasks (7 groups) | `openspec/changes/studio-canvas-layout/tasks.md` |
| Worktree | `../llamaindex-rag-mcp-feat-studio-canvas-layout` |
