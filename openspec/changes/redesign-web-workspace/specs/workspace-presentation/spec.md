# workspace-presentation delta

## Purpose

The workspace shell: navigation and routes, shared workspace data, friendly failures, icons, colour badges, elevation and contextual detail regions, following the OpenChamber visual system tokenised in `web/src/styles/tokens.css`.

## ADDED Requirements

### Requirement: Navigation follows the seven-area structure

The app navigation SHALL offer exactly Home, Chat, Knowledge Base, Studio, Experiments, Integrations and Settings, in that order, each with its icon, with Home as the landing view. The item for the current route SHALL be marked active.

#### Scenario: Fresh visit

- **WHEN** the app opens with no hash
- **THEN** Home MUST be the active view and the address bar MUST read `#/home`

#### Scenario: Active item follows the route

- **WHEN** the app shows `#/studio/<pipeline-id>`
- **THEN** Studio MUST be the marked navigation item

### Requirement: The URL is the only source of location

The current area, project, pipeline and run SHALL be read from the URL hash only, using these routes: `#/home`, `#/knowledge-base`, `#/knowledge-base/<collection>`, `#/chat`, `#/chat/<collection>`, `#/studio`, `#/studio/<pipeline-id>`, `#/experiments`, `#/experiments/runs/<run-id>`, `#/integrations` and `#/settings`, with each segment URI-encoded. A hash that matches no route SHALL show Home and rewrite the address bar to `#/home`. Back and forward SHALL restore the previous location. A route naming a collection, pipeline or run that the server does not return SHALL show a not-found state with a link back to its picker. Browser storage SHALL hold only the theme preference, the last-used collection as a default for `#/chat` and `#/knowledge-base`, and unsaved canvas drafts; stored values that fail validation SHALL be ignored and removed.

#### Scenario: Reload keeps the location

- **WHEN** the user reloads the page at `#/knowledge-base/research%20notes`
- **THEN** the Knowledge Base for the collection `research notes` MUST be shown

#### Scenario: Unknown route

- **WHEN** the app opens at `#/search`
- **THEN** Home MUST be shown and the address bar MUST read `#/home`

#### Scenario: Back restores the previous location

- **WHEN** the user goes from `#/home` to `#/chat/papers` and presses Back
- **THEN** Home MUST be shown

#### Scenario: Unknown collection in the route

- **WHEN** the app opens at `#/chat/missing` and the server lists no collection named `missing`
- **THEN** the view MUST show a not-found state with a link to `#/chat`

#### Scenario: Stored value with an old shape

- **WHEN** browser storage holds a preferences value that fails validation
- **THEN** the app MUST use the default theme, MUST remove the stored value, and MUST NOT show an error

### Requirement: Workspace data stays consistent across views

Data read from the server SHALL be shared between views through one cache, so a collection list is fetched once for Home, Chat and Knowledge Base. An upload, ingest job completion, source deletion, collection deletion or profile change SHALL refresh the collection list and counts in every view without a page reload. A finished run SHALL refresh the run list and that run's detail.

#### Scenario: Counts update after an ingest

- **WHEN** an ingest job into `papers` completes while the user is in the Knowledge Base
- **THEN** the `papers` card on Home and the `papers` entry in the Chat knowledge base panel MUST show the new document and chunk counts without a reload

#### Scenario: One request for shared data

- **WHEN** the user moves from Home to Chat within the cache freshness window
- **THEN** the collection list MUST NOT be requested again

### Requirement: API failures render as friendly messages with one action

Every view SHALL convert transport and HTTP failures into a single short message naming what failed plus one action, chosen from the failure kind and status: an unreachable server offers Retry; a refused session explains how to open the workspace again; a missing resource links back to its picker; an oversized upload names the limit. Parser output, status dumps and stack text MUST NOT appear in the UI; the raw message SHALL go to the browser console only. Under the Vite dev server, `/v1` requests SHALL proxy to the local web transport.

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

### Requirement: Detail regions open on selection

The top bar SHALL have no Inspector toggle and the app SHALL have no global inspector panel. Views that need detail regions (Chat, Studio, Experiments) SHALL open them on selection within their own layout.

#### Scenario: No global inspector

- **WHEN** the app opens
- **THEN** no Inspector toggle SHALL be present in the top bar and no empty inspector panel SHALL render

### Requirement: The top bar switches the theme in one click

The top bar SHALL hold a theme select with System, Light and Dark, and an icon-only button beside it that shows the theme in effect and switches between Light and Dark in one click. The button's accessible name SHALL state the theme it switches to. Both controls SHALL write the stored theme preference, and the Settings select SHALL show the same value.

#### Scenario: One-click switch

- **WHEN** the theme in effect is light and the user presses the icon button
- **THEN** the app MUST render the dark theme, the select MUST read Dark, and the stored preference MUST be `dark`

#### Scenario: Accessible name follows the target

- **WHEN** the theme in effect is dark
- **THEN** the icon button's accessible name MUST state that it switches to the light theme
