# Tasks

## 1. Dependencies and wiring

- [x] 1.1 Add the frontend dependencies to `web/package.json`: `tailwindcss` v4, `@tailwindcss/vite`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `tw-animate-css`, `@radix-ui/react-slot`, `@radix-ui/react-dialog`, `@radix-ui/react-label`, `@radix-ui/react-select`, `@radix-ui/react-tooltip`, `@radix-ui/react-separator`; run `npm install` and record the lockfile diff.
- [x] 1.2 Wire the Vite plugin in `web/vite.config.ts`; add the Tailwind theme and utilities imports (no preflight) and the `@theme inline` bridge aliasing surface, text, accent, status, radius, font and size tokens to the `tokens.css` custom properties; the existing CSS imports move into `app.css` as layered imports (see group 4).
- [x] 1.3 Add `web/components.json` (new-york, tsx, `cssVariables: true`, aliases pointing at `src/components/ui` and `src/styles/app.css`).
- [x] 1.4 Add the `cn()` helper (clsx + tailwind-merge) under `web/src/lib/`.
- [x] 1.5 Update `web/THIRD_PARTY_NOTICES.md` with Radix (MIT), Tailwind (MIT), class-variance-authority (Apache-2.0), clsx and tailwind-merge (MIT), lucide (ISC) and tw-animate-css (MIT).

## 2. Primitives

- [x] 2.1 Port `button` from OMMS with omrg tokens: default (tinted primary), destructive, outline, secondary, ghost, link and chip variants; h-9 default, h-8 small, h-6 extra-small; verify tint strengths against the design reference.
- [x] 2.2 Port `badge` with status and neutral variants; unit-test colour-text pairing.
- [x] 2.3 Port `card`, `separator` and `table` primitives (flat, 1px border, panel radius).
- [x] 2.4 Port `input`, `select`, `label` and `tooltip` with the 36px control height, focus ring and Radix behaviour intact.
- [x] 2.5 Port `dialog` with focus trap, Escape close, focus return and restrained elevation; test the keyboard flow.

## 3. Verification

- [x] 3.1 Prove the bridge: render a fixture using bridged utilities in light and dark; assert computed colours match the `tokens.css` values; assert that every pre-existing view has identical computed styles and element boxes before and after, in both themes.
- [x] 3.2 Run `npm run test`, `npm run lint`, `npm run typecheck`, `npm run build`; record exact results.
- [x] 3.3 Run `openspec validate add-web-ui-stack --strict` and resolve findings.
- [x] 3.4 Confirm no existing view imports a new primitive (coexistence check per design D3).

## 4. Stylesheet architecture

- [x] 4.1 Make `app.css` the stylesheet entry: declare the layer order `theme, base, vendor, legacy, components, utilities`, import Tailwind theme and utilities, React Flow (`vendor`) and every hand-written stylesheet (`legacy`); move the former `app.css` rules to `legacy.css`; remove every component-level CSS import so only `main.tsx` imports CSS.
- [x] 4.2 Rename the legacy typography classes to `type-page-title`, `type-section-title`, `type-meta` and `type-code` in `legacy.css` and all markup; remove the undefined `text-subsection-title` class names and the `outline` panel modifier that collided with Tailwind utilities.
- [x] 4.3 Add `--status-*-label` and `--shadow-floating` to `tokens.css` in both themes; bridge them as `text-status-*-label` and `shadow-floating`; use them in the badge and dialog primitives; add `tokens.test.ts` asserting 4.5:1 for every label on its tint over the canvas, elevated and muted surfaces in both themes.
- [x] 4.4 Add the `dark` custom variant following `data-theme`, then the system preference; test it in `bridge.test.ts`.
- [x] 4.5 Add `cascade.test.ts` (layer order, layered imports, single CSS entry, no class-name collisions) and `bridge.test.ts` (utilities resolve to token variables, aliases point at declared tokens, no literal colours); set `test.css.include` in `vite.config.ts` so `?raw` CSS reads work under Vitest; confirm each test fails when the code it guards is broken.
- [x] 4.6 Compare computed styles and element boxes for all seven views in light and dark at 1280px and 390px against a baseline build of the previous commit; record zero differences.
