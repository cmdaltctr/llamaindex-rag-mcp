## ADDED Requirements

### Requirement: The navigation collapses on the canvas sub-page

On the Studio canvas sub-page (`#/studio/<pipeline-id>`) the navigation SHALL show as its icon column from the `md` breakpoint up, whatever the stored per-browser choice is. The user MAY expand it for the current visit with its toggle. That expansion SHALL NOT be stored and SHALL reset the next time the canvas sub-page opens. The stored choice SHALL stay unchanged and SHALL apply on every other route. Below the `md` breakpoint nothing changes.

#### Scenario: Expanded navigation collapses on the canvas

- **WHEN** the stored choice is "expanded" and the user opens `#/studio/<pipeline-id>`
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
