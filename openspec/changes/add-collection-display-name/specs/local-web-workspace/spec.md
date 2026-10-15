## ADDED Requirements

### Requirement: Collections have an editable display name
A collection SHALL have an optional display name stored in its metadata. `GET /v1/collections` SHALL return it as `display_name`, or `null` when none is set. `PATCH /v1/collections/{collection}/display-name` SHALL set it and SHALL return `{collection, display_name}`. It SHALL require a browser session with the `manage` scope, the same guard as the profile change. It SHALL return 404 for an unknown collection and SHALL NOT create one. The server SHALL trim the value and SHALL clear the display name when the trimmed value is empty. It SHALL reject, with status 400, a value longer than 80 Unicode code points or one that contains a control character. The collection name, the stored vectors, retrieval, ingestion and MCP tools SHALL be unaffected.

#### Scenario: Display name is set
- **WHEN** a client sends `{"display_name": "  Project docs "}` for collection `documents`
- **THEN** the response SHALL be `{"collection": "documents", "display_name": "Project docs"}`
- **AND** the collection list SHALL return the same value

#### Scenario: Display name is cleared
- **WHEN** a client sends an empty or whitespace-only value
- **THEN** the response SHALL carry `display_name: null`
- **AND** `display_name` SHALL be `null` in the next collection list

#### Scenario: Value is too long
- **WHEN** a client sends 81 Unicode code points
- **THEN** the server SHALL reject the request with status 400
- **AND** the stored value SHALL stay unchanged

#### Scenario: Value contains a control character
- **WHEN** a client sends a value that contains a line feed or another control character
- **THEN** the server SHALL reject the request with status 400
- **AND** the stored value SHALL stay unchanged

#### Scenario: Retrieval keeps working under the collection name
- **WHEN** a display name is set on `documents`
- **THEN** a search or ingest call that passes `collection="documents"` SHALL behave as before

#### Scenario: Bearer credential
- **WHEN** a bearer token or notebook credential sends the PATCH request
- **THEN** the server SHALL reject it with status 403 before any write

#### Scenario: Unknown collection
- **WHEN** a client sends the PATCH request for a collection that does not exist
- **THEN** the server SHALL return 404
- **AND** no collection SHALL be created

#### Scenario: Metadata cannot be read
- **WHEN** reading a collection's metadata fails during the collection list
- **THEN** that item SHALL carry `display_name: null` and `profile: null`
- **AND** the list SHALL still succeed

### Requirement: The workspace shows the display name and the collection name
The Home card, the project chips in the Knowledge Base and in Chat, and the project header SHALL show the display name when set and the collection name otherwise. The project header SHALL always show the collection name in small grey text under the title. Places where the name is an identifier SHALL keep the collection name: "Sources in <name>", the Chat input and the delete dialog. The header SHALL offer a pencil button that edits the display name in place. Enter SHALL save, Escape SHALL cancel, and an empty value SHALL clear the display name.

#### Scenario: Display name is set
- **WHEN** collection `documents` has display name `Project docs`
- **THEN** the Home card, the Knowledge Base chip, the Chat chip and the header title SHALL read `Project docs`
- **AND** the header SHALL show `Collection name: documents`

#### Scenario: Identifiers keep the collection name
- **WHEN** collection `documents` has display name `Project docs`
- **THEN** the Sources heading SHALL read `Sources in documents`
- **AND** the Chat input SHALL read `Ask documents a question`

#### Scenario: No display name
- **WHEN** a collection has no display name
- **THEN** the title SHALL read the collection name
- **AND** the grey line SHALL still show `Collection name: <name>`

#### Scenario: User edits the name
- **WHEN** the user clicks the pencil, types a new name and presses Enter
- **THEN** the title SHALL update without a page reload
- **AND** the route SHALL keep using the collection name

#### Scenario: User cancels
- **WHEN** the user presses Escape while editing
- **THEN** the title SHALL keep its previous text and no request SHALL be sent

#### Scenario: Name is too long in the editor
- **WHEN** the user types 81 Unicode code points
- **THEN** the editor SHALL block the save and SHALL say the limit
- **AND** no request SHALL be sent

#### Scenario: Save fails
- **WHEN** the server rejects the change
- **THEN** the editor SHALL stay open and SHALL show a friendly error
