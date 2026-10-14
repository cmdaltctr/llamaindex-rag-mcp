# web-ui-stack delta

## Purpose

The Tailwind v4 + shadcn-style component stack for the web workspace: build wiring, the token bridge, and the primitive set with its visual and accessibility contract.

## ADDED Requirements

### Requirement: Tailwind builds through the Vite plugin with the token bridge

The web build SHALL compile Tailwind CSS v4 through `@tailwindcss/vite` and SHALL expose the existing semantic custom properties from `web/src/styles/tokens.css` to utility classes through a `@theme inline` block. Existing hand-written CSS SHALL continue to apply unchanged, and light and dark themes SHALL keep switching through the same `prefers-color-scheme` and `data-theme` mechanisms.

#### Scenario: Existing styles survive the wiring

- **WHEN** the app builds with the Tailwind plugin enabled
- **THEN** every pre-existing CSS rule MUST still apply and the app MUST render as before

#### Scenario: Utility classes read the tokens

- **WHEN** a component uses a bridged utility class such as a surface or accent colour
- **THEN** the rendered value MUST come from the `tokens.css` custom property in the active theme

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
- **THEN** fill, border and text MUST derive from that status colour with the value visible as text

### Requirement: Primitives keep the Radix accessibility contract

Dialog, select, tooltip and label primitives SHALL keep their Radix behaviour: focus trapping, Escape to close, focus return, aria attributes and keyboard navigation. Icon-only controls SHALL carry an accessible name.

#### Scenario: Dialog keyboard flow

- **WHEN** a user opens a dialog ported from Radix and presses Escape
- **THEN** the dialog MUST close and focus MUST return to the trigger

### Requirement: No view changes in this change

No existing view, route or user-visible behaviour SHALL change. The primitives are additive until the redesign change consumes them.

#### Scenario: Views untouched

- **WHEN** the app runs after this change
- **THEN** every existing view MUST render and behave exactly as before
