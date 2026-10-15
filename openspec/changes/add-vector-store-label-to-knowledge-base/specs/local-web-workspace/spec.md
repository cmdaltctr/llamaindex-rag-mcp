## ADDED Requirements

### Requirement: The collection list names the vector database
`GET /v1/collections` SHALL return, for every collection, a `store` object with the registered backend `name` and its `label`. The value SHALL come from the vector-store registry and SHALL NOT include a path, URI, tenant or credential.

#### Scenario: LanceDB is the active store
- **WHEN** the server runs with the default store and a client lists collections
- **THEN** every item SHALL carry `store: {"name": "lancedb", "label": "LanceDB"}`

#### Scenario: Chroma is the active store
- **WHEN** the server runs with `VECTOR_STORE=chroma` and a client lists collections
- **THEN** every item SHALL carry `store: {"name": "chroma", "label": "ChromaDB"}`

#### Scenario: Cloud settings are configured
- **WHEN** Chroma runs in cloud mode and a client lists collections
- **THEN** the `store` object SHALL contain no tenant, database or key

### Requirement: The Knowledge Base shows the database of each project
The project header SHALL show the database logo and label in a box of fixed size, so logos of different shapes never change the row height. The Home card, the project chips and the Sources table SHALL show the label as text only. A backend with no logo file SHALL show its label alone.

#### Scenario: Header shows logo and name
- **WHEN** a user opens a project on LanceDB
- **THEN** the header SHALL show the LanceDB logo and the text `LanceDB`
- **AND** the logo box SHALL have the same width and height for every backend

#### Scenario: Sources table shows the name
- **WHEN** a user opens the Sources section
- **THEN** the table SHALL have a Database column whose cells hold the label as text

#### Scenario: Logo file is missing
- **WHEN** no logo file exists for a registered backend
- **THEN** the header SHALL show the label with no broken image

### Requirement: The Profile tab shows the stored profile truthfully
The Profile tab SHALL pre-select the stored profile in the "New profile" list when the collection has one. When the collection has none, the list SHALL start with no selection and "Preview profile change" SHALL stay disabled until the user picks a profile. The status line SHALL show the profile as a badge, using the neutral "No profile" badge when none is stored.

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
- **WHEN** a collection whose stored tag is not `documents` or `codebase` opens the Profile tab
- **THEN** the status line SHALL show that tag as a badge
- **AND** the list SHALL show the placeholder "Choose a profile"

#### Scenario: User selects a profile
- **WHEN** the user selects `documents` on a collection with no profile
- **THEN** "Preview profile change" SHALL become enabled
