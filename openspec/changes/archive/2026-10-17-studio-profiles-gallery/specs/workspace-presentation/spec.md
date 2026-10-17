## MODIFIED Requirements

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
