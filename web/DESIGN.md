---
version: alpha
name: OMRS Workspace
description: >-
  Local research workspace for OMRS. Warm neutral surfaces, one burnt-orange
  accent used as a tint, compact system type, flat cards. Adapted from
  OpenChamber (MIT) at revision 02306f32e4d191e4840440cbafa643ae899471c2.
  Front matter holds the light theme; dark values are in the Colors section.
  web/src/styles/tokens.css is the source of truth for every value.
colors:
  primary: "#b35017"
  primary-hover: "#9a4310"
  primary-active: "#85390c"
  primary-label: "#9a4310"
  primary-tint: "rgb(179 80 23 / 0.1)"
  primary-tint-hover: "rgb(179 80 23 / 0.16)"
  primary-tint-active: "rgb(179 80 23 / 0.22)"
  primary-tint-border: "rgb(179 80 23 / 0.3)"
  neutral: "#fdfcfa"
  surface-elevated: "#f8f7f5"
  surface-muted: "#f7f6f4"
  text-primary: "#393a34"
  text-secondary: "#5c5c54"
  border: "#e5e1de"
  border-hover: "#cbc7c2"
  selection: "#a9998f2b"
  focus-ring: "#b35017"
  status-error: "#b7493f"
  status-warning: "#8d6c15"
  status-success: "#5f8d3d"
  status-info: "#2d72c4"
  status-error-label: "#85433b"
  status-warning-label: "#6b5821"
  status-success-label: "#506c39"
  status-info-label: "#325c8a"
typography:
  page-title:
    fontFamily: system-ui
    fontSize: 1.5rem
    fontWeight: 600
    lineHeight: 1.25
  section-title:
    fontFamily: system-ui
    fontSize: 1.125rem
    fontWeight: 600
    lineHeight: 1.4
  subsection-title:
    fontFamily: system-ui
    fontSize: 0.9375rem
    fontWeight: 600
    lineHeight: 1.4
  ui:
    fontFamily: system-ui
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.45
  meta:
    fontFamily: system-ui
    fontSize: 0.8125rem
    fontWeight: 400
    lineHeight: 1.5
  code:
    fontFamily: ui-monospace
    fontSize: 0.75rem
    fontWeight: 400
    lineHeight: 1.5
rounded:
  small: 9px
  control: 10px
  panel: 12px
spacing:
  "1": 4px
  "2": 8px
  "3": 12px
  "4": 16px
  "6": 24px
  "8": 32px
  control-height: 36px
  control-height-small: 32px
  touch-target: 44px
components:
  button-primary:
    backgroundColor: "{colors.primary-tint}"
    textColor: "{colors.primary-label}"
    typography: "{typography.ui}"
    rounded: "{rounded.control}"
    height: 36px
  button-primary-hover:
    backgroundColor: "{colors.primary-tint-hover}"
  button-primary-active:
    backgroundColor: "{colors.primary-tint-active}"
  button-chip-selected:
    backgroundColor: "{colors.selection}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
  card:
    backgroundColor: "{colors.surface-elevated}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.panel}"
    padding: 16px
  field:
    backgroundColor: "{colors.surface-elevated}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    height: 36px
  top-bar:
    backgroundColor: "{colors.surface-muted}"
    textColor: "{colors.text-primary}"
  nav-item-active:
    backgroundColor: "{colors.selection}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    height: 36px
  badge-success:
    textColor: "{colors.status-success-label}"
    typography: "{typography.meta}"
    rounded: "{rounded.small}"
  badge-error:
    textColor: "{colors.status-error-label}"
    typography: "{typography.meta}"
    rounded: "{rounded.small}"
  badge-warning:
    textColor: "{colors.status-warning-label}"
    typography: "{typography.meta}"
    rounded: "{rounded.small}"
  badge-info:
    textColor: "{colors.status-info-label}"
    typography: "{typography.meta}"
    rounded: "{rounded.small}"
  page:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.text-primary}"
  meta-text:
    textColor: "{colors.text-secondary}"
    typography: "{typography.meta}"
  link:
    textColor: "{colors.primary}"
---

# OMRS Workspace design

This file is the portable summary of the web workspace's visual system, in the [DESIGN.md format](https://github.com/google-labs-code/design.md) (version `alpha`). Read it for intent. For implementation, follow these, in this order:

1. `web/src/styles/tokens.css`: the only source of colour, type, spacing and radius values. If this file and `tokens.css` disagree, `tokens.css` wins; update this file.
2. `web/src/components/ui/`: the primitives. Use them; never re-create them.
3. The `omrs-design` skill (`.agents/skills/omrs-design/`): rules, contrast data, screen guidance and verification steps.
4. `openspec/specs/web-ui-stack/` and the `workspace-*` specs: the behaviour contract.

## Overview

A calm, dense, local research tool. People read evidence here, so the interface stays quiet: warm off-white surfaces, dark warm-grey text, one burnt-orange accent, and status colours that always come with words. Controls are flat and tinted, never solid blocks of colour. Cards are flat with a hairline border. Only floating chrome (the top bar, open panels) has a shadow. Type is the system font, small and tight, with headings set apart by weight more than size.

The app has seven areas in a fixed order: Home, Chat, Knowledge Base, Studio, Experiments, Integrations, Settings. A project is a collection. The URL holds the location; nothing else does.

## Colors

The accent is used as a **tint**: a 10% fill with a 30% border and darker accent text. Solid accent appears only as the focus ring and as link text. Selection (active navigation row, a chosen chip) uses a neutral grey fill, never the accent, so "selected" never looks like "do this".

| Role | Light | Dark | Token in `tokens.css` |
|---|---|---|---|
| Page (canvas) | `#fdfcfa` | `#120f0e` | `--surface-canvas` |
| Elevated (cards, fields) | `#f8f7f5` | `#181715` | `--surface-elevated` |
| Muted (navigation, top bar) | `#f7f6f4` | `#171615` | `--surface-muted` |
| Text | `#393a34` | `#c9c5ba` | `--text-primary` |
| Secondary text | `#5c5c54` | `#8f8b81` | `--text-secondary` |
| Border / on hover | `#e5e1de` / `#cbc7c2` | `#242323` / `#504e4c` | `--border` / `--border-hover` |
| Accent | `#b35017` | `#da7c47` | `--accent` |
| Accent text on tint | `#9a4310` | `#fd9b66` | `--accent-label` |
| Accent tint rest / hover / pressed | 10% / 16% / 22% | 16% / 22% / 30% | `--accent-tint*` |
| Accent tint border | 30% | 35% | `--accent-tint-border` |
| Selection | `#a9998f2b` | `#c8c6c52b` | `--selection` |
| Focus ring | `#b35017` | `#da7c47` | `--focus-ring` |
| Error / warning | `#b7493f` / `#8d6c15` | `#da5b4a` / `#c67f13` | `--status-error` / `--status-warning` |
| Success / info | `#5f8d3d` / `#2d72c4` | `#76ad4f` / `#479fe6` | `--status-success` / `--status-info` |
| Status label (badge text) | 60% status + 40% text | same mix | `--status-*-label` |

Raw status colours fail WCAG AA as text on their own 10% tint (success is 3.28:1 in light). Badge text therefore uses the `--status-*-label` mix, which reaches at least 4.5:1 in both themes; `web/src/styles/tokens.test.ts` asserts it. Raw status colours are for borders, dots and icons only (3:1 is enough there).

Translucent tokens (`primary-tint*`, `selection`) only have a contrast ratio once blended over the surface beneath them. Blended over canvas, elevated and muted, accent text on the rest tint measures 5.34 to 5.61:1 and text on the selection fill 9.27 to 9.70:1. `npx @google/design.md lint` (0.4.0) does not blend alpha, so it reports false contrast warnings for `button-primary`, `button-chip-selected` and `nav-item-active`; ignore those three. Its `orphaned-tokens` warnings are expected too: border, focus and raw status colours are used by the primitives, not by the component entries above.

The theme follows the system preference unless the root element carries `data-theme="light"` or `data-theme="dark"`.

## Typography

System sans for the interface, system monospace for code, paths, identifiers, model names and score kinds. No web fonts.

| Role | Size | Weight | Utility |
|---|---|---|---|
| Page title (one `h1` per view) | 1.5rem | 600 | `text-page-title` |
| Section title | 1.125rem | 600 | `text-section-title` |
| Subsection, card title | 0.9375rem | 600 | `text-subsection-title` |
| Interface text | 0.875rem | 400 | `text-ui` |
| Meta, helper, badge | 0.8125rem | 400 | `text-meta` |
| Code | 0.75rem | 400 | `text-code` with `font-mono` |

Copy is plain British English. Buttons say what they do ("Upload files", "Run pipeline"). Errors say what failed and offer one action.

## Layout

```
+--------------------------------------------------------------+
| top bar: brand · engine status pill · theme       (muted)     |
+------------+-------------------------------------------------+
| navigation | main area                                       |
| 13rem      | view title, then content                        |
| (muted)    | detail regions open inside the view on select   |
+------------+-------------------------------------------------+
```

- Spacing steps: 4, 8, 12, 16, 24, 32px. 8px between an icon and its label, 12px inside a card, 16px card padding, 24px between related groups, 32px between page sections. Never one gap everywhere.
- Controls are 36px high (32px small). Touch targets on narrow screens are at least 44px.
- Chat's transcript is a centred column of `min(100%, 48rem)`.
- Studio opens on a gallery of profile cards. A profile canvas takes the full main area; one floating panel holds six sections: Pipeline settings, Operations, Steps and connections, Connect ports, Revision and run, Step settings.
- Settings has seven sections, switched by `chip` buttons: Appearance, Providers, Chat, MCP, Server log, Runtime, Workspace. Each chip writes `#/settings/<section>`.
- The Providers section shows one card per registered LLM provider in `MasonryColumns` (1, 2 or 3 column stacks, each card in the shortest column), because the cards have different heights. A key field is write-only: `Input type="password"`, emptied after save, never filled with a saved key. A field set from the environment or the config file is locked and says so in text ("Set from environment (read-only here)", "Set from config file (read-only here)" with the lock text from the server). A key set from a key file is not locked: the card says "Set from key file (read-only here). Saving a key in the keychain overrides it." and keeps the key input. Saved values apply at once, so the section shows no restart banner.
- The Ollama card has a number `Input` "Context window (tokens)" (min 2048, max 262144) with the source line. The llama.cpp card has a "Local server" panel: a state `Badge` with text (`stopped`, `starting`, `running`, `failed`), a friendly line for each fixed reason, `Input` fields for program path, model, context window and idle sleep with source lines, a one-line note on what idle sleep does, and Start, Stop and Restart `Button`s. Start is disabled while starting or running. Stop is disabled while stopped. The panel says "omrs starts and stops only this server. It never touches a server you started yourself." and shows "Restart to apply" when saved values differ from the running ones. Program path and model are read-only without the `credentials` scope. The panel never shows output of the server.
- The Chat section holds a provider `Select`, a model `Input`, List models, Test, Save and Clear. A provider that is not ready is disabled and shows its reason. A cloud provider shows a notice that questions and passages leave this machine.
- Card grids use `items-start` so short cards do not stretch.
- Cards of the same size use a plain grid: `grid grid-cols-1 items-start gap-3 md:grid-cols-2 xl:grid-cols-3`.
- Cards of different heights in one group use `MasonryColumns` (`web/src/components/MasonryColumns.tsx`). It fits as many columns of at least 300px as the area allows, up to three, and puts each card in the shortest column. It places the cards again when a size changes, but not while focus is inside the cards, so a card that grows during an edit stays in its column.
- A tall card stays in one column at its full length. It does not span two columns or put its content side by side. An extra panel sits under the card's fields after `border-t border-border pt-3`.
- Card groups do not use CSS columns (`columns-2`) or native CSS masonry (`grid-lanes`).
- A small fixed group where the order is important can be placed by hand in column stacks, as Settings > MCP does.
- Each part of a card (one setting, field, read-only list, status block or drop zone) sits in its own `CardInset` mini card: `rounded-control border border-border bg-background/60 p-3`, lighter than the card, no shadow. `SettingRow`, `KeySettingRow` and `ReadingSettingRow` render one already. A `Card` never sits inside a `Card`.
- Use logical properties only (`ms-*`, `pe-*`, `border-s`, `text-start`), so the layout mirrors for right-to-left text.
- At 390px wide there is no horizontal page scroll.

## Elevation & Depth

One shadow, `--shadow-floating` (utility `shadow-floating`): `0 1px 3px` at 8% black in light and 40% in dark. It goes on the top bar and on floating panels (dialogs, popovers, open detail regions) only. Cards, tables and fields stay flat with a 1px border. In dark mode the chrome separates from the page by border and shadow, never by a new colour.

## Shapes

| Use | Radius | Utility |
|---|---|---|
| Buttons, fields, navigation rows | 10px | `rounded-control` |
| Badges, small chips | 9px | `rounded-small` |
| Cards, panels, dialogs | 12px | `rounded-panel` |

Borders are 1px. Focus is a 2px outline in `--focus-ring`, offset 2px, on `:focus-visible` only.

## Components

Use the primitives. Import them; do not copy their classes.

```tsx
// web/src/<area>/SomeView.tsx: relative imports; the project has no path alias
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent, CardInset } from "../components/ui/card";
import { cn } from "../lib/utils";
```

| Primitive | Variants and rules |
|---|---|
| `Button` | `default` (accent tint), `destructive` (error tint), `outline`, `secondary`, `ghost`, and `chip`. One primary action per region. `type="button"` unless it submits. |
| `Button` `chip` | Section switching and selection (a view tab, a chosen filter). Transparent with a hairline border at rest; the neutral `--selection` fill when `aria-pressed="true"` (or `data-selected="true"`). Never the primary action, and never the accent, so "selected" does not read as "do this". Set `aria-pressed` on every chip. Front matter entry: `button-chip-selected`. |
| `Badge` | `neutral`, `accent`, `error`, `warning`, `success`, `info`, and `hue`. Text always states the value. |
| `Badge` `hue` | Collection profiles and node kinds. Write `<Badge variant="hue">label</Badge>`. Transparent fill; the border takes the text colour. Text is `oklch(0.42 0.13 <hue>)` in light and `oklch(0.8 0.13 <hue>)` in dark. The hue (0 to 359) comes from a stable hash of the label, `hueFor` in `web/src/components/ui/badge.tsx`, so one label has one colour everywhere. Pass `hue` only to override it. The colour never carries meaning alone: the label text states the value. |
| `Card` | Flat, 1px border, 12px radius, 16px padding. No shadow. |
| `Dialog` | Radix. Focus trap, Escape closes, focus returns to the trigger, `DialogTitle` required, `shadow-floating`. |
| `Input`, `Select`, `Label` | 36px, elevated fill, visible label bound by `htmlFor`, message tied by `aria-describedby`. |
| `Tooltip` | Supplements a visible label; never the only label. |
| `Table`, `Separator` | Dense lists (sources, runs, integrations); hairline dividers. |

Status mapping used everywhere:

| Value | Badge |
|---|---|
| Run `succeeded`, answer `ok`, integration available | `success` |
| Run `failed`, answer `error` | `error` |
| Answer `no_evidence`, `generation_unverified`, `unverified_claims` | `warning` |
| Run `queued`, `running`, `cancelling` | `info` |
| Run `cancelled`, `skipped`, `bypassed`, integration not installed | `neutral` |

Icons come from `lucide-react` at 16px in `currentColor`, marked `aria-hidden` beside text. An icon-only control has an accessible name.

## Do's and Don'ts

Do:

- Read colours, sizes and radii through the bridged utilities (`bg-card`, `text-muted-foreground`, `rounded-panel`, `text-meta`).
- Pair every status colour with words.
- Give every empty state an icon, one sentence and one action.
- Show failures as one friendly line plus one action; send the raw message to the console.
- Keep files under 500 lines and put new view code in its area folder.

Don't:

- Write hand-written CSS or import a `.css` file from a component. Only `tokens.css` and `app.css` exist.
- Put a literal colour in a component, or use raw status colours as text.
- Use the accent for selection, or solid accent fills for buttons.
- Add shadows to cards, or animate layout. Respect `prefers-reduced-motion`.
- Wrap a primitive to override its height, radius or colour; change the primitive instead.
- Add a dependency without the owner's approval.
