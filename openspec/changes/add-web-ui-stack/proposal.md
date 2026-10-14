# Proposal

## Why

The web workspace uses hand-written CSS with no component primitives. Every control (buttons, badges, dialogs, selects) must be built and maintained from scratch, and the upcoming `redesign-web-workspace` change needs a full set of polished, accessible controls quickly. OMMS, whose design guidance this project follows, runs React 19 + Tailwind v4 + shadcn-style components on Radix + lucide-react, inherited from the openmem fork. Adopting the same stack here makes the two codebases share one component language and speeds up the redesign. The owner has approved adding these dependencies; this change is that approval on record.

## What Changes

- Add to `web/`: `tailwindcss` v4 with `@tailwindcss/vite`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `tw-animate-css`, and the Radix primitives needed by the first component set (`react-slot`, `react-dialog`, `react-label`, `react-select`, `react-tooltip`, `react-separator`).
- Add `web/components.json` (shadcn new-york style, CSS variables on) so `npx shadcn@latest add` works for future primitives.
- Bridge the existing `web/src/styles/tokens.css` variables into Tailwind through a `@theme inline` block; `tokens.css` stays the single source of truth and every existing CSS rule keeps working unchanged.
- Scaffold the first shadcn-style primitives in `web/src/components/ui/`, adapted from the OMMS implementations to the omrg tokens: `button`, `badge`, `card`, `dialog`, `input`, `select`, `label`, `tooltip`, `separator`, `table`.
- No view changes in this change: existing views keep their current markup and styles. The primitives are additive and get consumed by `redesign-web-workspace`.

## Capabilities

### New Capabilities

- `web-ui-stack`: Tailwind v4 build wiring, the token bridge, and the shadcn-style primitive set with their visual and accessibility contract.

### Modified Capabilities

None.

## Impact

- **Dependencies**: eight frontend packages added to `web/package.json` (one Vite plugin, one CSS package, five utility/icon packages, Radix primitives). This change is the approved exception to the "ask before new core dependencies" boundary; the list is fixed here and any addition beyond it needs a new approval.
- **Build**: `web/vite.config.ts` gains the Tailwind plugin; `web/src/styles/` gains the `@theme inline` bridge; no Python-side change; wheel build unaffected beyond larger static assets.
- **Licences**: Radix (MIT), Tailwind (MIT), cva (Apache-2.0), clsx+tailwind-merge (MIT), lucide (ISC), tw-animate-css (MIT) recorded in `web/THIRD_PARTY_NOTICES.md`.
- **Sequencing**: apply before `redesign-web-workspace`, which consumes the primitives.
