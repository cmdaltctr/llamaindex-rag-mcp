# OpenChamber design reference for the apply phase

Source: OpenChamber at revision `02306f32e4d191e4840440cbafa643ae899471c2`, MIT licence (Copyright (c) 2025 Bohdan Triapitsyn). The two theme JSONs sit beside this file. `web/src/styles/tokens.css` already implements the palette; this file exists so the implementation phase never needs the OpenChamber checkout again.

## Palette

| Role | Light | Dark | omrg token |
| --- | --- | --- | --- |
| Canvas | `#fdfcfa` | `#120f0e` | `--surface-canvas` |
| Elevated | `#f8f7f5` | `#181715` | `--surface-elevated` |
| Muted | `#f7f6f4` | `#171615` | `--surface-muted` |
| Text | `#393a34` | `#c9c5ba` | `--text-primary` |
| Secondary text | `#5c5c54` | `#8f8b81` | `--text-secondary` |
| Border | `#e5e1de` | `#242323` | `--border` |
| Border hover | `#cbc7c2` | `#504e4c` | `--border-hover` |
| Accent | `#b35017` | `#da7c47` | `--accent` |
| Accent hover / active | `#9a4310` / `#85390c` | `#eb8c57` / `#fd9b66` | `--accent-hover` / `--accent-active` |
| Selected fill | `#a9998f2b` | `#c8c6c52b` | `--selection` |
| Hover / press overlay | `#0000000d` / `#00000014` | `#ffffff12` / `#ffffff1f` | `--interactive-hover` / `--interactive-active` |
| Error | `#b7493f` | `#da5b4a` | `--status-error` |
| Warning | `#8d6c15` | `#c67f13` | `--status-warning` |
| Success | `#5f8d3d` | `#76ad4f` | `--status-success` |
| Info | `#2d72c4` | `#479fe6` | `--status-info` |

## Typography

System sans stack for UI; monospace stack for code, ids, paths. Headings differ by weight, not size.

| Role | Size | Weight | Line height |
| --- | --- | --- | --- |
| Page title | 1.5rem | 600 | 1.25 |
| Section | 1.125rem | 600 | 1.4 |
| Subsection | 0.9375rem | 600 | 1.4 |
| UI text | 0.875rem | 400 | 1.45 |
| Meta / helper | 0.8125rem | 400 | 1.5 |
| Code | 0.75rem | 400 | readable |

## Geometry

- Control heights: default 2.25rem (36px), small 2rem (32px), touch 2.75rem on narrow screens.
- Radii: control 10px, small 9px, extra-small 7px, panel 12px.
- Gaps: icon-to-label 6 to 8px; groups in a card 12px; card padding 16px; sibling sections 32px.
- Borders: 1px `--border`. Cards flat. Elevation (subtle shadow) on the top bar and floating panels only.

## Interaction states

- Primary action: tinted fill at rest 10% light / 16% dark accent, hover 16% / 22%, pressed 22% / 30%; saturated tint border (12% / 20%); accent-coloured label (`--accent-label`).
- Selection (navigation, chips): neutral selected fill `--selection` with normal text; never the accent. A chip represents selection independently of the primary action.
- Focus: 2px solid `--focus-ring` outline, offset 2px (OpenChamber uses a 3px ring; omrg keeps its outline token).
- Transitions: 150ms ease on background, border, colour, opacity. Respect `prefers-reduced-motion`.
- Status colour always pairs with text or an icon; colour alone never carries meaning.

## Badge convention

Every category, type, or keyword label gets a colour. Status badges use the status tokens (tinted fill at roughly 10%, coloured border, coloured text). Profile labels (`documents`, `codebase`) and node kinds use a stable hue hash: `oklch(0.42 0.13 hue)` text in light mode, `oklch(0.8 0.13 hue)` in dark, on a transparent fill with a `border-current` outline. One label, one hue, everywhere.

## Chat layout skeleton

Centre the transcript at `min(100%, 48rem)`; dock the composer at the bottom of the same column; citation chips under each answer; evidence in a collapsible section. No bubbles framework; plain message rows with role labels.

## Sources in the OpenChamber tree

- Themes: `packages/ui/src/lib/theme/themes/openchamber-{light,dark}.json` (copied here).
- Typography: `packages/ui/src/styles/typography.css`.
- Buttons: `packages/ui/src/components/ui/button.tsx`.
- Design tokens: `packages/ui/src/styles/design-system.css`.
