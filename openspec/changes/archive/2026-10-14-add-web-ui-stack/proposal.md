# Proposal

## Why

The web workspace uses hand-written CSS with no component primitives. Every control (buttons, badges, dialogs, selects) must be built and maintained from scratch, and the upcoming `redesign-web-workspace` change needs a full set of polished, accessible controls quickly. OMMS, whose design guidance this project follows, runs React 19 + Tailwind v4 + shadcn-style components on Radix + lucide-react, inherited from the openmem fork. Adopting the same stack here makes the two codebases share one component language and speeds up the redesign. The owner has approved adding these dependencies; this change is that approval on record.

## What Changes

- Add to `web/`: `tailwindcss` v4 with `@tailwindcss/vite`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `tw-animate-css`, and the Radix primitives needed by the first component set (`react-slot`, `react-dialog`, `react-label`, `react-select`, `react-tooltip`, `react-separator`).
- Add `web/components.json` (shadcn new-york style, CSS variables on) so `npx shadcn@latest add` works for future primitives.
- Bridge the existing `web/src/styles/tokens.css` variables into Tailwind through a `@theme inline` block; `tokens.css` stays the single source of truth.
- Make `web/src/styles/app.css` the single stylesheet entry. It declares the cascade layers `theme, base, vendor, legacy, components, utilities` and imports Tailwind (theme and utilities only, no reset), React Flow and every hand-written stylesheet into a layer. Hand-written rules move to `legacy.css` and the per-view CSS files, now imported only from `app.css`, so a Tailwind utility always beats a legacy rule. Component files no longer import CSS.
- Rename the four legacy typography classes (`.text-code`, `.text-page-title`, `.text-section-title`, `.text-meta`) to `.type-code`, `.type-page-title`, `.type-section-title`, `.type-meta`, because the old names collide with Tailwind utilities that the bridge generates.
- Add the tokens that the primitives need and `tokens.css` lacked: `--status-*-label` (readable status text on a tint, checked against WCAG AA in both themes) and `--shadow-floating`. Add a `dark:` variant that follows `data-theme`, then the system preference, so shadcn CLI templates work.
- Scaffold the first shadcn-style primitives in `web/src/components/ui/`, adapted from the OMMS implementations to the omrg tokens: `button`, `badge`, `card`, `dialog`, `input`, `select`, `label`, `tooltip`, `separator`, `table`.
- Add guard tests that fail when a stylesheet bypasses its layer, when a legacy class name collides with a utility, when a bridge alias points at a missing token, or when a status label drops below 4.5:1.
- No visible or behavioural change in any view. The only edits to view files are the mechanical class renames and the removal of CSS imports, verified by identical computed styles and element boxes before and after. The primitives are additive and get consumed by `redesign-web-workspace`.

## Capabilities

### New Capabilities

- `web-ui-stack`: Tailwind v4 build wiring, the token bridge, and the shadcn-style primitive set with their visual and accessibility contract.

### Modified Capabilities

None.

## Impact

- **Dependencies**: thirteen direct frontend packages added to `web/package.json`, all pinned exactly (two build packages, `tailwindcss` and `@tailwindcss/vite`; `tw-animate-css`; four utility and icon packages, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`; six Radix primitives). This change is the approved exception to the "ask before new core dependencies" boundary; the list is fixed here and any addition beyond it needs a new approval.
- **Build**: `web/vite.config.ts` gains the Tailwind plugin and a Vitest option that lets guard tests read CSS source; `web/src/styles/` gains the layered entry, `legacy.css` and the `@theme inline` bridge; no Python-side change; wheel build unaffected beyond larger static assets.
- **Frontend files**: `web/src/styles/tokens.css` gains `--status-*-label` and `--shadow-floating`; 13 CSS import lines move out of view files into `app.css`; 52 view and component files have legacy typography class names renamed (mechanical, no markup structure change).
- **Licences**: Radix (MIT), Tailwind (MIT), cva (Apache-2.0), clsx+tailwind-merge (MIT), lucide (ISC), tw-animate-css (MIT) and their transitive MIT and ISC packages recorded in `web/THIRD_PARTY_NOTICES.md`.
- **Sequencing**: apply before `redesign-web-workspace`, which consumes the primitives.
