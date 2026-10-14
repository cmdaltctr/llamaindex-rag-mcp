# Design

## Context

`web/` is a React 19.3 + Vite SPA with zero UI dependencies beyond `@xyflow/react`; all styling is hand-written CSS over `web/src/styles/tokens.css` (semantic custom properties adapted from OpenChamber). OMMS runs React 19 + Tailwind v4 (`@tailwindcss/vite`, CSS-first) + shadcn-style components (`components.json`, new-york) on Radix primitives with cva/clsx/tailwind-merge and lucide-react, and its `omms-design` skill now documents that stack as the baseline.

## Goals and Non-Goals

Goals: install the stack; bridge tokens; ship one set of accessible primitives styled by the OpenChamber palette; leave every existing view untouched.

Non-goals: migrating existing views to Tailwind classes; changing any behaviour or copy; adopting a component library beyond the shadcn pattern; server-side rendering.

## Decisions

### D1. Tailwind v4, CSS-first, tokens stay authoritative

Use `@tailwindcss/vite` with `@import "tailwindcss"` and a `@theme inline` block that aliases Tailwind colour/radius/font names to the existing `--surface-*`, `--text-*`, `--accent*`, `--status-*`, `--radius-*` custom properties. `tokens.css` remains the single source of truth; light/dark switching keeps working through `prefers-color-scheme` and `data-theme` exactly as today. No `tailwind.config` file exists in v4; none is created.

### D2. shadcn pattern, OMMS as the source of component code

Add `components.json` (new-york, `tsx`, `cssVariables: true`, css path `src/styles/app.css`) so the shadcn CLI can add primitives later. The first ten primitives (`button`, `badge`, `card`, `dialog`, `input`, `select`, `label`, `tooltip`, `separator`, `table`) are ported from the OMMS implementations (`web/src/lib/components/ui/` in the OMMS repo) and adapted: omrg token names, no OMMS i18n hooks, Radix props kept intact. `cn()` is the standard clsx + tailwind-merge helper.

### D3. Coexistence, not migration

The new primitives live beside the legacy `.button`, `.control`, `.panel` CSS. Nothing existing switches to them in this change; `redesign-web-workspace` migrates view by view. This keeps the diff reviewable and the old tests green.

### D4. Icons

`lucide-react` replaces the planned inline SVG icon module from `redesign-web-workspace` (that change's tasks are updated accordingly). Licence notice (ISC) goes into `web/THIRD_PARTY_NOTICES.md`.

### D5. Accessibility contract travels with the primitives

Radix gives focus trapping, Escape handling, aria wiring and focus return in dialogs, selects and tooltips for free; the ports must not strip them. Button variants keep the tinted primary treatment (10/16/22% light, 16/22/30% dark) documented in `openspec/changes/redesign-web-workspace/references/openchamber-design.md`.

## Risks and Trade-offs

- Two styling systems coexist until the redesign finishes; accepted, bounded by D3.
- Tailwind v4 CSS-first is newer than v3 patterns; mitigated by following the OMMS wiring rather than inventing one.
- Larger node_modules and bundle; the primitives are small and tree-shaken.

## Migration Plan

None needed for users: no route, markup or behaviour changes. Rollback is deleting the new files and dependencies.

## Open Questions

None blocking.
