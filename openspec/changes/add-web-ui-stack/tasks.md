# Tasks

## 1. Dependencies and wiring

- [ ] 1.1 Add the frontend dependencies to `web/package.json`: `tailwindcss` v4, `@tailwindcss/vite`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `tw-animate-css`, `@radix-ui/react-slot`, `@radix-ui/react-dialog`, `@radix-ui/react-label`, `@radix-ui/react-select`, `@radix-ui/react-tooltip`, `@radix-ui/react-separator`; run `npm install` and record the lockfile diff.
- [ ] 1.2 Wire the Vite plugin in `web/vite.config.ts`; add the Tailwind import and the `@theme inline` bridge aliasing surface, text, accent, status, radius and font tokens to the `tokens.css` custom properties; keep the existing CSS imports.
- [ ] 1.3 Add `web/components.json` (new-york, tsx, `cssVariables: true`, aliases pointing at `src/components/ui` and `src/styles/app.css`).
- [ ] 1.4 Add the `cn()` helper (clsx + tailwind-merge) under `web/src/lib/`.
- [ ] 1.5 Update `web/THIRD_PARTY_NOTICES.md` with Radix (MIT), Tailwind (MIT), class-variance-authority (Apache-2.0), clsx and tailwind-merge (MIT), lucide (ISC) and tw-animate-css (MIT).

## 2. Primitives

- [ ] 2.1 Port `button` from OMMS with omrg tokens: default (tinted primary), destructive, outline, secondary, ghost, link and chip variants; h-9 default, h-8 small, h-6 extra-small; verify tint strengths against the design reference.
- [ ] 2.2 Port `badge` with status and neutral variants; unit-test colour-text pairing.
- [ ] 2.3 Port `card`, `separator` and `table` primitives (flat, 1px border, panel radius).
- [ ] 2.4 Port `input`, `select`, `label` and `tooltip` with the 36px control height, focus ring and Radix behaviour intact.
- [ ] 2.5 Port `dialog` with focus trap, Escape close, focus return and restrained elevation; test the keyboard flow.

## 3. Verification

- [ ] 3.1 Prove the bridge: render a fixture using bridged utilities in light and dark; assert computed colours match the `tokens.css` values; assert one pre-existing view renders pixel-identical before and after.
- [ ] 3.2 Run `npm run test`, `npm run lint`, `npm run typecheck`, `npm run build`; record exact results.
- [ ] 3.3 Run `openspec validate add-web-ui-stack --strict` and resolve findings; run `graphify update .`.
- [ ] 3.4 Confirm no existing view imports a new primitive (coexistence check per design D3).
