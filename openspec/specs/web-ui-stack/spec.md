# web-ui-stack Specification

## Purpose
The Tailwind v4 + shadcn-style component stack for the web workspace: build wiring, the token bridge, and the primitive set with its visual and accessibility contract.

## Requirements

### Requirement: Status labels meet WCAG AA

`web/src/styles/tokens.css` SHALL define `--status-error-label`, `--status-warning-label`, `--status-success-label` and `--status-info-label` as 60% of the status colour mixed with 40% of `--text-primary`, declared once so both themes follow `--text-primary`. The bridge SHALL expose them as `text-status-*-label`, and badges SHALL use them for text. Each label SHALL have a contrast ratio of at least 4.5:1 on its status colour at 10% opacity over the canvas, elevated and muted surfaces, in light and dark themes.

#### Scenario: A palette change lowers a label contrast

- **WHEN** a status colour, surface colour, text colour or mix percentage changes so that any label falls below 4.5:1 on its tint in either theme
- **THEN** the token test MUST fail

### Requirement: The elevation token and dark variant follow the theme

`tokens.css` SHALL define `--shadow-floating` for both themes, exposed as the `shadow-floating` utility. The Tailwind `dark` variant SHALL apply when `data-theme="dark"` is set, or when the system prefers dark and `data-theme="light"` is not set.

#### Scenario: Dark variant with the system preference

- **WHEN** the system prefers dark and `data-theme` is unset
- **THEN** `dark:` utilities MUST apply

#### Scenario: Light override

- **WHEN** the system prefers dark and `data-theme="light"` is set
- **THEN** `dark:` utilities MUST NOT apply

### Requirement: The shadcn CLI is configured

`web/components.json` SHALL configure the shadcn new-york style with TypeScript and CSS variables so `npx shadcn@latest add <component>` installs into the project's component directory using the bridged tokens.

#### Scenario: Adding a primitive later

- **WHEN** a maintainer runs the shadcn add command for a new primitive
- **THEN** the generated files MUST land in `web/src/components/ui/` and compile against the token bridge without manual edits

### Requirement: The first primitive set ships with the OpenChamber treatment

`web/src/components/ui/` SHALL provide button, badge, card, dialog, input, select, label, tooltip, separator and table primitives styled with the OpenChamber palette and geometry from the design reference: tinted primary buttons (10/16/22% light, 16/22/30% dark rest/hover/pressed with saturated border and label colour), flat cards with 1px borders, 10px control radius, 36px default control height, and 150ms transitions.

#### Scenario: Primary button rendering

- **WHEN** a default button renders in light theme
- **THEN** its fill, border and text MUST use the accent tint tokens at the documented strengths

#### Scenario: Badge variants

- **WHEN** a status badge renders for each status token
- **THEN** fill and border MUST derive from that status colour, the text MUST use that status's label token, and the value MUST be visible as text

### Requirement: Primitives keep the Radix accessibility contract

Dialog, select, tooltip and label primitives SHALL keep their Radix behaviour: focus trapping, Escape to close, focus return, aria attributes and keyboard navigation. Icon-only controls SHALL carry an accessible name.

#### Scenario: Dialog keyboard flow

- **WHEN** a user opens a dialog ported from Radix and presses Escape
- **THEN** the dialog MUST close and focus MUST return to the trigger

### Requirement: Tailwind builds with preflight and the token bridge

The web build SHALL compile Tailwind CSS v4 through `@tailwindcss/vite` and SHALL expose the semantic custom properties from `web/src/styles/tokens.css` to utility classes through a `@theme inline` block that holds no literal colours. Tailwind's preflight reset SHALL load into the `base` cascade layer. Light and dark themes SHALL switch through the `prefers-color-scheme` and `data-theme` mechanisms.

#### Scenario: Utility classes read the tokens

- **WHEN** a component uses a bridged utility class such as a surface or accent colour
- **THEN** the rendered value MUST come from the `tokens.css` custom property in the active theme

#### Scenario: A bridge alias points at a missing token

- **WHEN** an alias in the `@theme inline` block references a custom property that `tokens.css` does not declare
- **THEN** the bridge test MUST fail

#### Scenario: Preflight is loaded

- **WHEN** the app builds
- **THEN** Tailwind's preflight rules MUST be present in the `base` layer of the generated stylesheet

### Requirement: Only two stylesheets exist, loaded through one layered entry

`web/src/styles/tokens.css` and `web/src/styles/app.css` SHALL be the only stylesheets in `web/src`. `app.css` SHALL declare the cascade layers `theme, base, vendor, components, utilities` in that order, SHALL load Tailwind's theme, preflight and utilities into their layers, and SHALL import third-party stylesheets into the `vendor` layer. Overrides that must target a third-party library's own class names SHALL live in `app.css` under the `components` layer. Only `main.tsx` SHALL import CSS (`tokens.css`, then `app.css`); components SHALL NOT import stylesheets.

#### Scenario: A utility beats a vendor rule

- **WHEN** an element carries a Tailwind utility and also matches a vendor rule for the same property, including a rule with higher specificity
- **THEN** the utility MUST win

#### Scenario: A component imports a stylesheet

- **WHEN** a component file contains a `.css` import
- **THEN** the cascade test MUST fail, because the rule would sit outside every layer and override utilities

#### Scenario: Another stylesheet is added

- **WHEN** a `.css` file other than `tokens.css` and `app.css` exists under `web/src`
- **THEN** the cascade test MUST fail
