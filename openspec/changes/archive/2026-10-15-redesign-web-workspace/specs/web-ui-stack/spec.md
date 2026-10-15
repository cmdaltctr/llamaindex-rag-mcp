# web-ui-stack delta

## ADDED Requirements

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

## REMOVED Requirements

### Requirement: Tailwind builds through the Vite plugin with the token bridge

**Reason**: It required hand-written CSS to render unchanged and Tailwind's preflight to stay out. The redesign deletes the hand-written CSS and loads preflight.

**Migration**: Replaced by "Tailwind builds with preflight and the token bridge".

### Requirement: Stylesheets load through one layered entry

**Reason**: It required a `legacy` cascade layer for hand-written stylesheets. The redesign deletes them and the layer.

**Migration**: Replaced by "Only two stylesheets exist, loaded through one layered entry".

### Requirement: Legacy class names never collide with utilities

**Reason**: The redesign deletes every hand-written stylesheet and the `.type-*` classes, so no legacy class names remain to collide with utilities.

**Migration**: Use the bridged `text-page-title`, `text-section-title`, `text-meta` and `text-code` utilities and the primitives in `web/src/components/ui/`.

### Requirement: No view changes in this change

**Reason**: The requirement described the `add-web-ui-stack` change only. This change rebuilds every view on the primitives.

**Migration**: None. The requirements in `workspace-presentation` and the other workspace capabilities define the view behaviour.
