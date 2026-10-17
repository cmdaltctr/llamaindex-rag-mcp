## MODIFIED Requirements

### Requirement: The Profile tab shows the stored profile truthfully
The "New profile" list SHALL offer the ready profiles from `GET /v1/profiles` in two groups, "Built-in profiles" and "Your profiles". A profile that is not ready SHALL NOT be an option; a line under the list SHALL name it with its first reason. The list SHALL pre-select the stored profile when it is an option. Otherwise it SHALL start empty and "Preview profile change" SHALL stay disabled until the user picks one. The status line SHALL show the stored profile as a badge, or "No profile".

#### Scenario: Collection has a stored profile
- **WHEN** a collection with profile `codebase` opens the Profile tab
- **THEN** the list SHALL show `codebase` as selected
- **AND** the status line SHALL show a `codebase` badge

#### Scenario: Collection has no stored profile
- **WHEN** a collection with no profile opens the Profile tab
- **THEN** the list SHALL show the placeholder "Choose a profile"
- **AND** the status line SHALL show the "No profile" badge
- **AND** "Preview profile change" SHALL be disabled

#### Scenario: Stored tag is not a selectable profile
- **WHEN** a collection whose stored tag names no ready profile opens the Profile tab
- **THEN** the status line SHALL show that tag as a badge
- **AND** the list SHALL show the placeholder "Choose a profile"

#### Scenario: User selects a profile
- **WHEN** the user selects `documents` on a collection with no profile
- **THEN** "Preview profile change" SHALL become enabled

#### Scenario: Two groups
- **WHEN** the server lists the built-in profiles `documents` and `codebase` and the ready user profile `papers-search` titled "Papers search"
- **THEN** the list SHALL show a "Built-in profiles" group with Documents and Codebase and a "Your profiles" group with "Papers search"
- **AND** each option SHALL show its profile ID

#### Scenario: Not ready profile is hidden with its reason
- **WHEN** the user profile "Draft notes" is not ready with the reason "The Search pipeline is empty."
- **THEN** the list SHALL NOT offer "Draft notes"
- **AND** the line under the list SHALL read "Draft notes is not ready: The Search pipeline is empty."

#### Scenario: Pick a user profile
- **WHEN** the user picks "Papers search" and selects "Preview profile change"
- **THEN** the client SHALL send `{profile: "papers-search", confirm: false}` to `PATCH /v1/collections/<collection>/profile`

#### Scenario: Profiles cannot load
- **WHEN** the profile listing fails
- **THEN** the tab SHALL show one friendly failure line with a Retry action
- **AND** the status line SHALL still show the stored profile badge
