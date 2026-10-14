# workspace-presentation delta

## Purpose

The workspace shell: navigation structure, friendly failures, icons, colour badges, elevation and contextual detail panels, following the OpenChamber visual system already tokenised in `web/src/styles/tokens.css`.

## ADDED Requirements

### Requirement: Navigation follows the seven-area structure

The app navigation SHALL offer exactly Home, Chat, Knowledge Base, Studio, Experiments, Integrations and Settings, in that order, with Home as the landing view. The active item SHALL be marked. Legacy hash routes (`#/canvas`, `#/library`, `#/search`, `#/ask`, `#/runs`) SHALL redirect once to their new homes.

#### Scenario: Fresh visit

- **WHEN** the app opens with no hash
- **THEN** Home MUST be the active view

#### Scenario: Legacy hash redirects

- **WHEN** the app opens at `#/search`
- **THEN** the app MUST route to Chat and replace the hash with `#/chat`

### Requirement: API failures render as friendly messages with one action

Every view SHALL convert transport failures into a single short message naming what failed plus one action (Retry, or guidance to start the server). Parser output, status dumps and stack text MUST NOT appear in the UI. Under the Vite dev server, `/v1` requests SHALL proxy to the local web transport.

#### Scenario: Friendly failure

- **WHEN** a listing request fails because the server is down
- **THEN** the view MUST show a short message with a Retry action and MUST NOT show the parser error text

#### Scenario: Dev proxy

- **WHEN** the app runs under `npm run dev` and calls `/v1/collections`
- **THEN** the request MUST be proxied to the local web transport instead of returning the dev server's 404 page

### Requirement: Icons accompany navigation and primary actions

Navigation rows, primary actions and empty states SHALL carry `lucide-react` icons at 16px (empty states larger), rendered in `currentColor` and hidden from assistive technology when text accompanies them. Icon-only controls SHALL carry an accessible name. The Lucide ISC licence notice SHALL appear in `web/THIRD_PARTY_NOTICES.md`.

#### Scenario: Navigation icons

- **WHEN** the navigation renders
- **THEN** each row MUST show its icon before the label and the icon MUST be marked decorative

### Requirement: Category labels render as tinted badges

Run statuses, answer statuses, collection profiles and node kinds SHALL render as badges with a tinted fill, coloured border and coloured text, keeping one colour per label everywhere. Colour SHALL always be paired with text stating the value. Badge text SHALL reach a 4.5:1 contrast ratio against its own tinted fill in both themes, using a label colour mixed from the status colour and the primary text colour where the raw status colour falls short.

#### Scenario: Status badge

- **WHEN** a run with status `succeeded` is listed
- **THEN** the status MUST appear as a badge with consistent tinting and the word `succeeded` visible

#### Scenario: Badge text contrast

- **WHEN** a status badge renders in light or dark theme for each status token
- **THEN** its text MUST reach 4.5:1 against the badge fill

### Requirement: Elevation marks floating surfaces only

The top bar and floating detail panels SHALL carry a subtle shadow in both themes; cards and table surfaces SHALL stay flat with 1px borders. Light and dark themes SHALL remain legible throughout.

#### Scenario: Elevated chrome

- **WHEN** the app renders in dark theme
- **THEN** the top bar MUST be distinguishable from the canvas by border and elevation, not by a new colour

### Requirement: Detail panels open on selection

The global Inspector toggle SHALL be removed from the top bar. Views that need detail regions (Chat, Studio, Experiments) SHALL open them on selection within their own layout.

#### Scenario: No empty global inspector

- **WHEN** the app opens
- **THEN** no Inspector toggle SHALL be present in the top bar and no empty inspector panel SHALL render
