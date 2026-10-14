# Visual foundations

## Source and current state

The palette comes from the `openchamber-light` and `openchamber-dark` themes at OpenChamber revision `02306f32e4d191e4840440cbafa643ae899471c2`. A distilled copy lives in the change folder, so no OpenChamber checkout is needed:

- `openspec/changes/redesign-web-workspace/references/openchamber-design.md`
- `openspec/changes/redesign-web-workspace/references/openchamber-light.json` and `openchamber-dark.json`

After the change is archived, these files move under `openspec/changes/archive/`.

`web/src/styles/tokens.css` already implements the palette. It is the single source of truth. Components never contain literal colours. `web/src/styles/app.css` holds layout, typography roles, and the legacy shared controls.

## Palette and tokens

| Role | Light | Dark | Token |
| --- | --- | --- | --- |
| Canvas | `#fdfcfa` | `#120f0e` | `--surface-canvas` |
| Elevated | `#f8f7f5` | `#181715` | `--surface-elevated` |
| Muted (nav, top bar) | `#f7f6f4` | `#171615` | `--surface-muted` |
| Text | `#393a34` | `#c9c5ba` | `--text-primary` |
| Secondary text | `#5c5c54` | `#8f8b81` | `--text-secondary` |
| Border | `#e5e1de` | `#242323` | `--border` |
| Border on hover | `#cbc7c2` | `#504e4c` | `--border-hover` |
| Accent | `#b35017` | `#da7c47` | `--accent` |
| Accent hover / pressed | `#9a4310` / `#85390c` | `#eb8c57` / `#fd9b66` | `--accent-hover` / `--accent-active` |
| Accent label (text on tint) | `#9a4310` | `#fd9b66` | `--accent-label` |
| Selected fill | `#a9998f2b` | `#c8c6c52b` | `--selection` |
| Hover / pressed overlay | `#0000000d` / `#00000014` | `#ffffff12` / `#ffffff1f` | `--interactive-hover` / `--interactive-active` |
| Focus ring | `#b35017` | `#da7c47` | `--focus-ring` |
| Error / warning | `#b7493f` / `#8d6c15` | `#da5b4a` / `#c67f13` | `--status-error` / `--status-warning` |
| Success / info | `#5f8d3d` / `#2d72c4` | `#76ad4f` / `#479fe6` | `--status-success` / `--status-info` |

Tinted primary buttons use `--accent-tint`, `--accent-tint-hover`, `--accent-tint-active`, and `--accent-tint-border`. Strengths are 10% / 16% / 22% on light and 16% / 22% / 30% on dark.

Theme selection: the system preference applies unless the root element carries `data-theme="light"` or `data-theme="dark"`. Dark values appear twice in `tokens.css` (media query and `data-theme`). When you add a token, define it in all three places.

### Bridge caution

Tailwind v4 reads `--color-*` as colours and `--text-*` as font sizes inside `@theme`. The tokens `--text-primary` and `--text-secondary` are colours. Alias them as `--color-text-primary: var(--text-primary)` in the bridge. Do not rename the tokens.

A Tailwind utility with no matching theme name produces no CSS and no error. After you add or generate a component, check that every colour, radius, and font class resolves in the browser.

## Contrast

Computed on 14 October 2026 from the token values. WCAG AA needs 4.5:1 for normal text and 3:1 for large text and UI boundaries.

| Pair | Light | Dark |
| --- | --- | --- |
| Text on canvas | 11.20 | 11.07 |
| Secondary text on elevated | 6.30 | 5.27 |
| Secondary text on muted | 6.24 | 5.32 |
| Accent on canvas (links, focus ring) | 5.02 | 6.32 |
| Accent label on tint, rest / hover / pressed | 5.62 / 5.14 / 4.73 | 7.42 / 6.66 / 5.69 |
| Status colour on canvas: error / warning / success / info | 5.07 / 4.78 / **3.82** / 4.75 | 5.07 / 5.86 / 7.14 / 6.70 |
| Status colour as text on its own 10% tint over elevated: error / warning / success / info | **4.26 / 4.04 / 3.28 / 4.01** | **4.28** / 4.87 / 5.79 / 5.46 |

Bold values fail AA for normal text. A badge label at 13px is normal text. Do not use the raw status colour as badge text.

Derive a label colour by mixing the status colour with the text colour:

```css
--status-error-label: color-mix(in srgb, var(--status-error) 60%, var(--text-primary));
```

Computed in sRGB, a 60% status / 40% text mix reaches 6.01 (error), 5.69 (warning), 4.96 (success), and 5.71 (info) in light, and passes in dark. Use the status colour for the border and the 10% fill. Use the label colour for text. The owner approved this fix. Redesign task 1.3 adds the `--status-*-label` tokens to `tokens.css` and a test for the ratios. Re-check in the browser, because `color-mix` results depend on the colour space.

The status colour as a UI boundary (icon, dot, border) needs 3:1. Success on canvas in light is 3.82, which passes for that use only.

## Typography

System sans for UI, monospace for code, identifiers, paths, and model names. Headings differ by weight and a small size step. Do not download fonts.

| Role | Token | Size | Weight | Line height |
| --- | --- | --- | --- | --- |
| Page title | `--text-page-title` | 1.5rem | 600 | 1.25 |
| Section title | `--text-section-title` | 1.125rem | 600 | 1.4 |
| Subsection | `--text-subsection-title` | 0.9375rem | 600 | 1.4 |
| UI text | `--text-ui` | 0.875rem | 400 | 1.45 |
| Meta, helper | `--text-meta` | 0.8125rem | 400 | 1.5 |
| Code | `--text-code` | 0.75rem | 400 | readable |

`app.css` defines `.text-page-title`, `.text-section-title`, `.text-meta`, and `.text-code`. Keep heading levels in order: one `h1` per view, which receives focus after navigation. Preserve browser zoom and wrapping. Do not use fixed heights on text containers.

## Spacing and geometry

| Use | Target | Token |
| --- | --- | --- |
| Icon to label gap | 6 to 8px | `--space-2` is 8px |
| Groups inside one card | 12px | `--space-3` |
| Card padding, field stack | 16px | `--space-4` |
| Related groups | 24px | `--space-6` |
| Sibling page sections | 32px | `--space-8` |
| Default control height | 36px | `--control-height` |
| Small control height | 32px | `--control-height-small` |
| Extra-small, dense rows only | 24px | none; add only if used |
| Touch target on narrow screens | 44px | `--touch-target` |
| Control radius | 10px | `--radius-control` |
| Small radius | 9px | `--radius-small` |
| Panel radius | 12px | `--radius-panel` |
| Border | 1px | `--border` |

Space a group by the distance between its parts: tighter inside a card, wider between sections. Do not use one gap everywhere, and do not add one-off margins. Use `items-start` on a card grid so a short card does not stretch.

Cards are flat with a 1px border. Elevation is a subtle shadow on the top bar and floating panels only: `0 1px 3px rgb(0 0 0 / 0.08)` in light and `0 1px 3px rgb(0 0 0 / 0.4)` in dark. Add these as elevation tokens, not literals in components. Dark chrome stays distinguishable from the canvas by border and shadow, not by a new colour.

Layout uses logical properties only (`margin-inline`, `padding-block`, `inset-inline-start`, `border-inline-end`). In Tailwind use `ms-*`, `me-*`, `ps-*`, `pe-*`, `start-*`, `end-*`, `border-s`, `border-e`, `text-start`. Do not add physical `left` or `right` rules.

## Interaction states

- Primary action: tinted fill, saturated tint border, `--accent-label` text.
- Selection (navigation, chips): neutral `--selection` fill with normal text. Never the accent. A chip marks selection and stays visually separate from the primary action.
- Hover applies to interactive items only. Hover and pressed overlays sit on the base surface, so fields keep their fill.
- Focus: `outline: 2px solid var(--focus-ring)` with `outline-offset: 2px` on `:focus-visible`. OpenChamber uses a 3px ring. OMRG keeps the outline token. shadcn defaults use `ring-*` classes. Change generated components to the outline.
- Disabled: keep the label visible and the state recognisable. Use `aria-disabled` or `disabled`, and say why when it is not obvious.
- Transitions: 150ms ease (`--transition-fast`) on background, border, colour, and opacity. Animate only opacity and transform in ongoing motion. Respect `prefers-reduced-motion`. Do not change layout on hover.
- Status colour always pairs with text or an icon.

## Theme ownership

`web/src/lib/preferences.ts` owns the per-browser UI state in one versioned `localStorage` entry (`omrg-workspace-ui`): view, theme (`system`, `light`, `dark`), and the inspector flag. Every storage access is guarded, because storage can be missing or throw. `data-theme` on the root element applies the theme. `web/src/theme.test.tsx` covers it.

The redesign changes values and component styles, not theme persistence or startup timing. It does remove the inspector flag and adds versioned keys for the active project (spec: stale keys are dropped). Do not add a second theme store.
