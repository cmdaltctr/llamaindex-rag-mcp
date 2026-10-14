# Design

## Context

`web/` is a React 19.3 + Vite SPA with zero UI dependencies beyond `@xyflow/react`; all styling is hand-written CSS over `web/src/styles/tokens.css` (semantic custom properties adapted from OpenChamber). OMMS runs React 19 + Tailwind v4 (`@tailwindcss/vite`, CSS-first) + shadcn-style components (`components.json`, new-york) on Radix primitives with cva/clsx/tailwind-merge and lucide-react, and its `omms-design` skill now documents that stack as the baseline.

## Goals and Non-Goals

Goals: install the stack; bridge tokens; make the cascade order explicit so Tailwind and legacy CSS coexist without specificity fights; ship one set of accessible primitives styled by the OpenChamber palette; leave every existing view looking and behaving exactly as before.

Non-goals: migrating existing views to Tailwind classes or primitives; changing any behaviour or copy; adopting a component library beyond the shadcn pattern; server-side rendering.

## Decisions

### D1. Tailwind v4, CSS-first, tokens stay authoritative

Use `@tailwindcss/vite` with `@import "tailwindcss/theme.css"` and `@import "tailwindcss/utilities.css"` (not the full `@import "tailwindcss"`, which would load Tailwind's preflight reset over the existing hand-written styles) and a `@theme inline` block that aliases Tailwind colour/radius/font/size names to the existing `--surface-*`, `--text-*`, `--accent*`, `--status-*`, `--radius-*` custom properties. `tokens.css` remains the single source of truth and the bridge holds no literal colours; light/dark switching keeps working through `prefers-color-scheme` and `data-theme` exactly as today. No `tailwind.config` file exists in v4; none is created.

### D2. shadcn pattern, OMMS as the source of component code

Add `components.json` (new-york, `tsx`, `cssVariables: true`, css path `src/styles/app.css`, which is the stylesheet entry from D6) so the shadcn CLI can add primitives later. The first ten primitives (`button`, `badge`, `card`, `dialog`, `input`, `select`, `label`, `tooltip`, `separator`, `table`) are ported from the OMMS implementations (`web/src/lib/components/ui/` in the OMMS repo) and adapted: omrg token names, no OMMS i18n hooks, Radix props kept intact. `cn()` is the standard clsx + tailwind-merge helper.

### D3. Coexistence, not migration

The new primitives live beside the legacy `.button`, `.control`, `.panel` CSS, which now sits in the `legacy` cascade layer (D6). Nothing existing switches to the primitives in this change; `redesign-web-workspace` migrates view by view. The only edits to existing view files are mechanical: removing component-level CSS imports (D6) and renaming four typography classes (D6). Both are verified behaviour-neutral by comparing computed styles and element boxes for every view before and after. This keeps the diff reviewable and the old tests green.

### D4. Icons

`lucide-react` replaces the planned inline SVG icon module from `redesign-web-workspace` (that change's tasks are updated accordingly). Licence notice (ISC) goes into `web/THIRD_PARTY_NOTICES.md`.

### D5. Accessibility contract travels with the primitives

Radix gives focus trapping, Escape handling, aria wiring and focus return in dialogs, selects and tooltips for free; the ports must not strip them. Button variants keep the tinted primary treatment (10/16/22% light, 16/22/30% dark) documented in `openspec/changes/redesign-web-workspace/references/openchamber-design.md`.

### D6. Cascade layers make coexistence mechanical

Unlayered legacy rules beat every layered rule, so Tailwind utilities would lose to any legacy rule with the same property. The first draft hit this: a legacy `.text-meta` overrode the colour set by a badge utility. Instead of raising utility specificity (`!important`), `app.css` is the one stylesheet entry and declares `@layer theme, base, vendor, legacy, components, utilities`. Tailwind theme and utilities load into their own layers (no preflight), React Flow CSS loads into `vendor`, and every hand-written stylesheet loads into `legacy`. A utility on a migrated element then beats every legacy rule whatever its specificity. The hand-written rules from the old `app.css` move to `legacy.css`.

Layers only work if nothing loads CSS around the entry. Component files therefore stop importing CSS, and only `main.tsx` imports `tokens.css` then `app.css`. New stylesheets are added to `app.css` in a layer.

The four legacy typography classes shared names with Tailwind utilities the bridge generates (`text-meta`, `text-code`, `text-page-title`, `text-section-title`). Layering would resolve the clash only by accident of order, and the same name would mean two things. They are renamed to `type-*`, which removes the collision at the source. Two other collisions found by the guard test (a `text-subsection-title` class that no rule defined, and an `outline` panel modifier that matched the Tailwind `outline` utility) are removed from the markup.

Three guard tests protect this: `cascade.test.ts` (layer order, every non-Tailwind import is layered, only `main.tsx` imports CSS, no class name in markup or legacy CSS matches a generated utility), `bridge.test.ts` (utilities resolve to token variables, aliases point at declared tokens, no literal colours) and `tokens.test.ts` (D7). Vitest blanks all CSS imports even with `?raw`, so `vite.config.ts` sets `test.css.include` for `.css?raw` reads.

### D7. Tokens the primitives need live in `tokens.css`

- `--status-{error,warning,success,info}-label` mix 60% of the status colour with 40% of `--text-primary` (`color-mix(in srgb, ...)`), declared once on `:root` so both themes follow `--text-primary`. Raw status colours fail 4.5:1 as badge text on their own tint (success is 3.28:1 in light). `tokens.test.ts` computes the ratio on the 10% tint over canvas, elevated and muted surfaces in both themes, and the bridge exposes the labels as `text-status-*-label`. Because the mix is declared in `tokens.css` rather than the bridge, every consumer reads one definition.
- `--shadow-floating` is the restrained elevation used by dialogs and floating panels (`0 1px 3px` at 8% black in light, 40% in dark).
- A `dark` custom variant follows `data-theme="dark"`, then the system preference unless `data-theme="light"`, matching `tokens.css`. Tokens already switch per theme, so most classes need no `dark:` prefix. The variant exists so components added with the shadcn CLI, whose templates use `dark:`, work unedited.

## Risks and Trade-offs

- Two styling systems coexist until the redesign finishes; accepted, bounded by D3 and made safe by D6.
- Layering changes which rule wins when a legacy rule and a utility both apply; mitigated because no existing view uses utilities, and a computed-style and element-box comparison of all seven views in both themes at 1280px and 390px showed no differences.
- Renaming four classes across 52 files is wide; mitigated because it is mechanical, the guard test fails on any leftover collision, and the full suite passes.
- Tailwind v4 CSS-first is newer than v3 patterns; mitigated by following the OMMS wiring rather than inventing one.
- Tailwind emits inert self-referencing `--radius-*`, `--font-*` and `--text-*` declarations in its theme layer for the aliases that already share Tailwind's names. The unlayered declarations in `tokens.css` always win, so they have no effect; `app.css` documents this.
- Larger node_modules and bundle; the primitives are small and tree-shaken.

## Migration Plan

None needed for users: no route or behaviour changes and no visible difference. Rollback is reverting this change as one unit: the new files, the dependencies, the CSS import moves and the class renames.

## Open Questions

None blocking.
