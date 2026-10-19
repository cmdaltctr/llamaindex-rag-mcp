# workspace-presentation Specification

## Purpose
The workspace shell: navigation and routes, shared workspace data, friendly failures, icons, colour badges, elevation and contextual detail regions, following the OpenChamber visual system tokenised in `web/src/styles/tokens.css`.

## Requirements

### Requirement: Navigation follows the seven-area structure

The app navigation SHALL offer exactly Home, Chat, Knowledge Base, Studio, Experiments, Integrations and Settings, in that order, each with its icon, with Home as the landing view. The item for the current route SHALL be marked active.

#### Scenario: Fresh visit

- **WHEN** the app opens with no hash
- **THEN** Home MUST be the active view and the address bar MUST read `#/home`

#### Scenario: Active item follows the route

- **WHEN** the app shows `#/studio/<profile-id>/<purpose>`
- **THEN** Studio MUST be the marked navigation item

### Requirement: The URL is the only source of location

The current area, project, profile, purpose, run and Settings section SHALL be read from the URL hash only, using these routes: `#/home`, `#/knowledge-base`, `#/knowledge-base/<collection>`, `#/chat`, `#/chat/<collection>`, `#/studio`, `#/studio/<profile-id>`, `#/studio/<profile-id>/<purpose>` (purpose `ingest`, `search` or `answer`), `#/experiments`, `#/experiments/runs/<run-id>`, `#/integrations`, `#/settings` and `#/settings/<section>`, with each segment URI-encoded. A hash that matches no route SHALL show Home and rewrite the address bar to `#/home`. Back and forward SHALL restore the previous location. A route naming a collection, profile or run that the server does not return SHALL show a not-found state with a link back to its picker. Browser storage SHALL hold only the theme preference, the last-used collection as a default for `#/chat` and `#/knowledge-base`, and unsaved canvas drafts; stored values that fail validation SHALL be ignored and removed.

#### Scenario: Reload keeps the location

- **WHEN** the user reloads the page at `#/knowledge-base/research%20notes`
- **THEN** the Knowledge Base for the collection `research notes` MUST be shown

#### Scenario: Unknown route

- **WHEN** the app opens at `#/search`
- **THEN** Home MUST be shown and the address bar MUST read `#/home`

#### Scenario: Unknown purpose

- **WHEN** the app opens at `#/studio/papers-search/rerank`
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

#### Scenario: Unknown Settings section

- **WHEN** the app opens at `#/settings/keys`
- **THEN** Home MUST be shown and the address bar MUST read `#/home`

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

### Requirement: The navigation collapses on the canvas sub-page

On the Studio canvas sub-page (`#/studio/<profile-id>` or `#/studio/<profile-id>/<purpose>`) the navigation SHALL show as its icon column from the `md` breakpoint up, whatever the stored per-browser choice is. The user MAY expand it for the current visit with its toggle. That expansion SHALL NOT be stored and SHALL reset the next time the canvas sub-page opens. The stored choice SHALL stay unchanged and SHALL apply on every other route. Below the `md` breakpoint nothing changes.

#### Scenario: Expanded navigation collapses on the canvas

- **WHEN** the stored choice is "expanded" and the user opens `#/studio/<profile-id>`
- **THEN** the navigation MUST render as the icon column

#### Scenario: Stored choice returns on other routes

- **WHEN** the user leaves the canvas sub-page for `#/knowledge-base`
- **THEN** the navigation MUST render as the stored choice says

#### Scenario: Temporary expansion is not stored

- **WHEN** the user expands the navigation on the canvas sub-page and then opens the Knowledge Base
- **THEN** the stored choice MUST be unchanged
- **AND** the next time the canvas sub-page opens the navigation MUST be collapsed again

#### Scenario: Gallery is unaffected

- **WHEN** the user opens `#/studio` (the gallery)
- **THEN** the navigation MUST render as the stored choice says

### Requirement: The navigation foot holds four quick controls

The side navigation SHALL end with a foot of four icon controls in this order: a theme button, a Settings link, a power control and a GitHub link. The foot SHALL have no language control, because the interface is English only. Every control SHALL have an accessible name. The existing top bar theme controls SHALL stay unchanged.

The theme button SHALL show the theme in effect and SHALL switch between Light and Dark in one click. Its accessible name SHALL state the theme it switches to. It SHALL write the stored theme preference, and the Settings theme select SHALL show the same value.

The Settings link SHALL open the Settings view.

The power control SHALL show a light that follows `GET /v1/health`: green while the app answers and grey when it does not. Pressing it SHALL open a panel. The panel SHALL say "Running" with the running version while the app answers, and "Not answering" when it does not. The panel SHALL offer a Turn off button and a Restart button. Each button SHALL open a confirmation dialog that names the action and says that the browser is signed out afterwards. After Turn off the dialog SHALL name `omrg web start`. After Restart it SHALL name `omrg web open`. The buttons SHALL be disabled when `GET /v1/server/power` answers `managed: false` or does not answer. The panel SHALL then show the commands `omrg web restart` and `omrg web open`, and one line that says why the buttons are disabled. When the server answers 409 because work is in progress, the panel SHALL show that reason in one line and SHALL keep the app running. The state SHALL NOT rely on colour alone.

The GitHub link SHALL point to https://github.com/cmdaltctr/llamaindex-rag-mcp, SHALL open in a new tab and SHALL carry a `rel` value with `noopener` and `noreferrer`.

#### Scenario: Four controls in order

- **WHEN** the navigation renders
- **THEN** the foot MUST hold exactly four controls, in this order: theme button, Settings link, power control, GitHub link
- **AND** the foot MUST hold no language control

#### Scenario: Theme in one click, light to dark

- **WHEN** the theme in effect is light and the user presses the theme button
- **THEN** the app MUST render the dark theme, the stored preference MUST be `dark`, and the Settings theme select MUST read Dark
- **AND** the button's accessible name MUST state that it switches to the light theme

#### Scenario: Theme in one click, dark to light

- **WHEN** the theme in effect is dark and the user presses the theme button
- **THEN** the app MUST render the light theme, the stored preference MUST be `light`, and the Settings theme select MUST read Light
- **AND** the button's accessible name MUST state that it switches to the dark theme

#### Scenario: Settings link

- **WHEN** the user presses the Settings control
- **THEN** the address bar MUST read `#/settings`

#### Scenario: Power light follows health

- **WHEN** `GET /v1/health` answers
- **THEN** the power icon MUST be green and its panel MUST say "Running" with the running version
- **AND** when `GET /v1/health` does not answer, the power icon MUST be grey and its panel MUST say "Not answering"
- **AND** the panel text MUST state the state, so the state does not rely on colour alone

#### Scenario: Turn off asks first

- **WHEN** `GET /v1/server/power` answers `managed: true` and the user presses Turn off
- **THEN** a confirmation dialog MUST open and MUST NOT call `POST /v1/server/power` until the user confirms
- **AND** after confirmation the page MUST post `{"action": "off"}` and MUST then say that the app is off and name `omrg web start`

#### Scenario: Restart asks first

- **WHEN** `GET /v1/server/power` answers `managed: true` and the user presses Restart
- **THEN** a confirmation dialog MUST open and MUST NOT call `POST /v1/server/power` until the user confirms
- **AND** after confirmation the page MUST post `{"action": "restart"}` and MUST then say that the browser is signed out and name `omrg web open`

#### Scenario: Power panel names the commands

- **WHEN** the user opens the power panel and `GET /v1/server/power` answers `managed: false`
- **THEN** the Turn off and Restart buttons MUST be disabled
- **AND** the panel MUST show the commands `omrg web restart` and `omrg web open` and the reason in one line

#### Scenario: Work in progress

- **WHEN** the user confirms an action and the server answers 409
- **THEN** the panel MUST show the reason in one line and MUST NOT report the app as off or restarting

#### Scenario: GitHub link

- **WHEN** the navigation renders
- **THEN** the GitHub link MUST point to https://github.com/cmdaltctr/llamaindex-rag-mcp
- **AND** the link MUST open in a new tab and MUST carry a `rel` value with `noopener` and `noreferrer`

#### Scenario: Collapsed navigation

- **WHEN** the navigation shows as its icon column
- **THEN** the four controls MUST render as icons in one column
- **AND** below the `md` breakpoint the four controls MUST stay reachable
