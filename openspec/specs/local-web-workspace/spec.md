# local-web-workspace Specification

## Purpose
Provide a protected single-user browser workspace on the same machine, with packaged assets and existing document operations delegated to shared core services.

## Requirements

### Requirement: Web launch is optional and self-contained
The system SHALL offer an explicit web launch command and serve packaged application assets. Base imports and existing commands SHALL work without the web extra or a notebook plugin. Runtime web use SHALL not require a frontend development server.

#### Scenario: Installed package launches outside the checkout
- **WHEN** the built package is installed and its web command is run from another directory
- **THEN** the application and asset routes SHALL load from packaged resources
- **AND** a Node runtime SHALL not be required

#### Scenario: Web dependency is missing
- **WHEN** the web command is invoked without its optional dependencies
- **THEN** it SHALL fail with an actionable installation instruction
- **AND** package imports, help, and existing MCP/CLI operations SHALL remain available

### Requirement: Local access is authenticated and origin-bound
The initial web transport SHALL bind only to loopback. Browser requests SHALL use an authenticated local session and validated host/origin policy. Programmatic notebook access SHALL use scoped, revocable credentials. Credentials SHALL not appear in persisted graphs, notebooks, or logs.

#### Scenario: Remote binding is requested
- **WHEN** a user requests a non-loopback bind address
- **THEN** the first-release server SHALL reject it with a local-use explanation

#### Scenario: An unrelated webpage submits work
- **WHEN** an unauthorised origin submits a state-changing request
- **THEN** the request SHALL be rejected before core work is admitted

#### Scenario: Stream endpoint has no credentials
- **WHEN** a client requests run events without valid authorisation
- **THEN** the endpoint SHALL reject access using the same policy as run inspection

#### Scenario: Scoped notebook credential is used
- **WHEN** a notebook credential requests plugin administration or an unapproved workspace
- **THEN** authorisation SHALL reject it before any action

### Requirement: File access requires explicit grants
Browser-selected server paths SHALL be canonicalised against approved roots. Indexed path metadata SHALL not grant source-file access. Uploaded supported files SHALL enter managed storage within configured size limits. Unsupported archives and URL ingestion SHALL be rejected in the initial release.

#### Scenario: Path escapes an approved root
- **WHEN** a path uses traversal or a symlink to reach an unapproved location
- **THEN** the operation SHALL fail before reading or mutating that location

#### Scenario: Indexed source is outside grants
- **WHEN** a user requests the original file from an indexed path outside approved roots
- **THEN** original-file access SHALL be denied
- **AND** authorised stored-chunk inspection SHALL remain available

#### Scenario: Upload exceeds its limit
- **WHEN** an uploaded file exceeds the configured limit
- **THEN** the server SHALL reject it without admitting ingestion or retaining a partial source

### Requirement: Document workflows use existing core behaviour
The workspace SHALL support collection/source listing, supported-file ingestion, metadata-filtered search, cited answering, profile preview/change, and document deletion through existing core behaviour. It SHALL retain machine-local orphan semantics, score kinds, lineage, and answer verification outcomes.

#### Scenario: Library lists sources
- **WHEN** a collection is opened
- **THEN** its sources, chunk counts, stable identifiers, and machine-local availability SHALL be shown
- **AND** unknown availability SHALL not be labelled as global source loss

#### Scenario: Search and answer execute
- **WHEN** a user submits a query with supported controls
- **THEN** the results SHALL use the same profile resolution, ranking, context, and citation rules as the existing operations

#### Scenario: Citation is opened
- **WHEN** a user opens an authorised citation
- **THEN** the referenced stored chunk and its available neighbours SHALL be inspectable
- **AND** original-file availability SHALL not be required for stored evidence

#### Scenario: Codebase mapping retains workspace context
- **WHEN** the workspace requests a codebase map
- **THEN** supplied settings, document thresholds, and store context SHALL reach map/cache operations
- **AND** a cached map from another owner SHALL not replace its result
- **AND** the job SHALL pass the owning Engine's settings and store explicitly to the core map API and SHALL NOT resolve process defaults
- **AND** where the store has no durable version of the `documents` collection, the map SHALL be rebuilt rather than reused from cache

### Requirement: Destructive actions require valid confirmation
Deletion, workspace cleanup, and stored profile changes SHALL present their effect before mutation and require explicit confirmation. Confirmation SHALL be bound to the selected action and observed state. Stale or altered confirmations SHALL require a new preview.

#### Scenario: User requests deletion without confirmation
- **WHEN** a user selects source or collection deletion
- **THEN** the workspace SHALL show the affected scope/counts and preserve data until confirmation

#### Scenario: Store changes after preview
- **WHEN** an observed validity token changes before confirmation
- **THEN** the system SHALL reject the stale confirmation and request a fresh preview
- **AND** it SHALL disclose backends whose validity guarantee is process-local

#### Scenario: Profile change is confirmed
- **WHEN** a user confirms a stored profile change
- **THEN** query defaults SHALL change through the existing profile contract
- **AND** existing chunks SHALL remain unchanged until an explicit appropriate ingest

### Requirement: HTTP exposes graph and run services without domain logic
The API SHALL expose catalogue discovery, graph validation/revisions, execution submission, run inspection/events/cancellation, source inspection, and plugin lifecycle. It SHALL delegate domain rules to shared services and publish request, response, error, and asynchronous-job contracts.

#### Scenario: Graph is submitted directly to the API
- **WHEN** a client bypasses the canvas and submits an invalid graph
- **THEN** the server SHALL apply core validation and return an actionable error

#### Scenario: Long work is admitted
- **WHEN** ingestion, graph execution, or codebase mapping is admitted as a job
- **THEN** the response SHALL provide a job identifier and status
- **AND** protected polling and event inspection SHALL be available

#### Scenario: Frontend fallback receives an API path
- **WHEN** an unknown API path is requested
- **THEN** the server SHALL return the API error contract
- **AND** it SHALL not serve the application HTML instead

### Requirement: Application lifecycle owns and drains its resources
Web startup SHALL construct its runtime through composition without installing a process-global Engine. Shutdown SHALL stop admission, handle queued work, request active cancellation, drain safe boundaries, and release only owned resources. Optional plugins SHALL not be launched by startup.

#### Scenario: Web and explicit library Engine coexist
- **WHEN** a web runtime and another explicitly constructed Engine coexist
- **THEN** neither SHALL replace the other's store, settings, or caches

#### Scenario: Shutdown has active work
- **WHEN** graceful shutdown begins during an active run
- **THEN** resources SHALL remain owned until active provider calls and entered commits reach safe boundaries
- **AND** queued work SHALL not start

#### Scenario: Optional plugin is absent
- **WHEN** web startup finds no enabled compatible notebook plugin
- **THEN** the workspace SHALL start with an actionable Experiments state
- **AND** it SHALL not install or launch a replacement

### Requirement: The web server listens on a stable port

`omrg web` SHALL choose its port in this order: the `--port` option, then the port saved in the workspace, then 8765. `--port 0` SHALL pick a free port for that launch. When the chosen port is taken, the command SHALL exit with an error that names the port and tells the user to pass `--port <n>`. `PUT /v1/settings/web-port` with `{ port }` (browser session only, 1024 to 65535, or `null` to clear) SHALL save the port for later launches and SHALL NOT rebind the running server. `GET /v1/settings/web-port` (read scope) SHALL return the saved port and the bound port.

#### Scenario: Default port

- **WHEN** `omrg web` starts with no `--port` and no saved port
- **THEN** it MUST listen on port 8765 of the loopback host

#### Scenario: Port taken

- **WHEN** port 8765 is in use and no other port is given
- **THEN** the command MUST exit with a message naming 8765 and the `--port` option

#### Scenario: Saved port applies next launch

- **WHEN** the browser session saves port 9100 and the server restarts without `--port`
- **THEN** the server MUST listen on 9100, and the running server MUST NOT have moved before the restart

#### Scenario: Option wins

- **WHEN** a port is saved and `--port 9200` is given
- **THEN** the server MUST listen on 9200

### Requirement: Workspace settings live in the workspace database

Settings that the web workspace changes at run time SHALL be stored in a `workspace_settings` key-value table of the workspace database, added by a schema migration. Only the keys `mcp_http_enabled` and `web_port` SHALL exist, each validated on read; a value that fails validation SHALL be treated as unset. Provider and engine settings SHALL NOT be stored there.

#### Scenario: Invalid stored value

- **WHEN** `web_port` holds a value outside 1024 to 65535
- **THEN** the launch MUST ignore it and use the next source in the port order

### Requirement: The workspace opens truncated run output

Every preview in the run detail that the server or the browser cut SHALL say that it was cut and SHALL offer one "Open full output" action, unless the server kept no full copy of that output for the run shown. The action SHALL show the full redacted value as plain text, never as markup, up to a stated display limit, and SHALL offer a download of the whole value. A failure to load the value SHALL render as one friendly message with one action.

#### Scenario: Open a cut node summary

- **WHEN** a node summary in the run detail carries `truncated: true` and an `artefact_ref`
- **THEN** the run detail MUST offer "Open full output", and the action MUST show the value that the artefact route returns

#### Scenario: No full copy for this run

- **WHEN** a cut node summary has no `artefact_ref`, or its `artefact_ref` names another run or is not valid
- **THEN** the run detail MUST say that the output was cut and why it cannot be opened, and MUST NOT offer "Open full output"

#### Scenario: Value larger than the display limit

- **WHEN** the full value is larger than the display limit
- **THEN** the view MUST show the first part, MUST state that the rest is not shown, and MUST offer a download of the whole value

#### Scenario: Markup in stored output

- **WHEN** the full value contains text that looks like HTML
- **THEN** the view MUST show it as text and MUST NOT create elements from it

### Requirement: The upload limit is set in Settings

The per-file upload limit SHALL be a workspace setting, saved in the workspace database, in whole MiB from 1 to 2048. With no saved value the limit SHALL be 50 MiB. `GET /v1/settings/upload-limit` (read scope) SHALL return the limit in force, its source, the saved value or `null`, the default, and the allowed range. `PUT /v1/settings/upload-limit` SHALL need a browser session, SHALL take `max_mib` (an integer in range, or `null` to clear the saved value), SHALL save it before it changes the running server, and SHALL apply it to new uploads at once, with no restart. An upload that has already started SHALL keep the limit it started with. Settings › Workspace SHALL show the limit in force, SHALL let the user save a new value or return to the default, and SHALL state that the change applies to new uploads straight away.

#### Scenario: Raise the limit

- **WHEN** the user saves 200 MiB in Settings and then uploads a 120 MiB file
- **THEN** the server MUST accept the file without a restart, and the saved value MUST still apply after a restart

#### Scenario: Return to the default

- **WHEN** the user clears the saved value
- **THEN** the limit in force MUST be 50 MiB, and Settings MUST say that the default applies

#### Scenario: Value out of range

- **WHEN** a request sets `max_mib` to 0, to 4096, or to a value that is not a whole number
- **THEN** the server MUST answer 400 and MUST NOT change the saved or the running limit, and Settings MUST name the allowed range before it sends such a value

#### Scenario: Bearer credential

- **WHEN** a bearer credential sends `PUT /v1/settings/upload-limit`
- **THEN** the server MUST refuse it and MUST NOT change the limit

#### Scenario: Limit lowered during an upload

- **WHEN** the limit is lowered while a file upload is in progress
- **THEN** that upload MUST finish against the limit it started with, and the next upload MUST use the new limit

### Requirement: A launch option sets the upload limit without the web workspace

`omrg web` SHALL accept `--max-upload-mib <n>` and SHALL read `WEB_MAX_UPLOAD_MIB` from the environment or `.env` when the flag is absent, so the limit can be set when the web workspace cannot be used. The order SHALL be the flag, then the environment variable, then the value saved in Settings, then 50 MiB. Both SHALL take a whole number from 1 to 2048; any other value SHALL stop the launch with exit code 2 and a message that names the option and the range. While a launch option sets the limit, `GET /v1/settings/upload-limit` SHALL report `source: "launch"`, `PUT` SHALL answer 409 and change nothing, and Settings SHALL show the limit as set at launch with no edit control. `.env.example` and the CLI reference SHALL document both.

#### Scenario: Environment variable in .env

- **WHEN** `.env` holds `WEB_MAX_UPLOAD_MIB=300` and `omrg web` starts without `--max-upload-mib`
- **THEN** the limit in force MUST be 300 MiB, and the response MUST report `source: "launch"`

#### Scenario: Flag beats environment and saved value

- **WHEN** Settings saved 200 MiB, the environment sets 300, and `omrg web --max-upload-mib 400` starts
- **THEN** the limit in force MUST be 400 MiB

#### Scenario: Invalid launch value

- **WHEN** `WEB_MAX_UPLOAD_MIB` is `0`, `5000` or `big`
- **THEN** `omrg web` MUST exit with code 2 before it binds a port and MUST name `WEB_MAX_UPLOAD_MIB` and the range 1 to 2048

#### Scenario: Settings while a launch option is set

- **WHEN** a launch option sets the limit and a browser session sends `PUT /v1/settings/upload-limit`
- **THEN** the server MUST answer 409, MUST keep the saved and the running limit, and Settings MUST say the limit was set at launch and how to change it

#### Scenario: No launch option

- **WHEN** neither the flag nor the environment variable is set
- **THEN** the saved value MUST apply, else 50 MiB, and the response MUST report `source: "saved"` or `source: "default"`

### Requirement: The workspace enforces the server's upload limit

The Knowledge Base SHALL read the limit from `GET /v1/settings/upload-limit`, SHALL state it in the upload panel, SHALL refuse a selected file larger than it before any bytes are sent, and SHALL name that value in the refusal. The workspace SHALL keep no limit of its own. A save in Settings SHALL update the upload panel without a page reload. When the limit cannot be read, the workspace SHALL leave the size check to the server, which still refuses an oversized file.

#### Scenario: Server with another limit

- **WHEN** the server reports a limit of 100 MiB and the user selects a 60 MiB file
- **THEN** the workspace MUST send the file, and the upload panel MUST state the 100 MiB limit

#### Scenario: File above the reported limit

- **WHEN** the server reports a limit of 10 MiB and the user selects a 12 MiB file
- **THEN** the workspace MUST refuse the file locally, MUST name the 10 MiB limit, and MUST NOT send the file

#### Scenario: Limit changed in Settings

- **WHEN** the user saves a new limit in Settings and then opens the Knowledge Base
- **THEN** the upload panel MUST state the new limit without a page reload

#### Scenario: Limit unknown

- **WHEN** the limit request fails
- **THEN** the workspace MUST NOT refuse the file locally, and a 413 from the server MUST render as one friendly message that does not name a number the server did not report

### Requirement: Extra browser origins are approved only at launch

The operator SHALL be able to approve extra loopback browser origins when the server starts, one exact origin per value. An approved origin SHALL pass every origin check for that run only. The server SHALL accept no other extra origin and SHALL change no other request check.

#### Scenario: An approved origin signs in

- **WHEN** the server starts with an approved loopback origin and a page from that origin posts the one-time bootstrap secret
- **THEN** the server SHALL issue the session cookie, as it does for the server's own address

#### Scenario: An approved origin submits a state-changing request

- **WHEN** a signed-in page from an approved origin sends a state-changing request
- **THEN** the server SHALL admit the request, subject to the same session and scope rules as any other request

#### Scenario: No origin is approved

- **WHEN** the server starts without an approved origin
- **THEN** the server SHALL accept only its own loopback origins, with the same results as before this requirement

#### Scenario: An unapproved origin is rejected

- **WHEN** a page from any origin that is neither the server's own nor approved sends an API request
- **THEN** the server SHALL return 403 before core work is admitted

#### Scenario: A non-loopback origin is requested

- **WHEN** the operator approves an origin whose host is not a loopback name or address
- **THEN** the server SHALL refuse to start, SHALL exit with code 2 and SHALL state the loopback rule

#### Scenario: A malformed or wildcard origin is requested

- **WHEN** the operator approves a value that has a wildcard, a path, a query, a fragment, user information or a scheme other than `http` or `https`
- **THEN** the server SHALL refuse to start, SHALL exit with code 2 and SHALL name the value

#### Scenario: The Host and fetch-metadata checks still apply

- **WHEN** a request from an approved origin carries a foreign `Host` header or cross-site fetch metadata
- **THEN** the server SHALL reject it as it does for any other request

#### Scenario: The operator sees what is approved

- **WHEN** the server starts with approved origins
- **THEN** the server SHALL print each approved origin before it prints the launch link

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
The project header and the Home card SHALL show the database logo and label, with the logo in a box of fixed size so logos of different shapes never change the row height. The project chips and the Sources table SHALL show the label as text only. A backend with no logo file SHALL show its label alone.

#### Scenario: Header shows logo and name
- **WHEN** a user opens a project on LanceDB
- **THEN** the header SHALL show the LanceDB logo and the text `LanceDB`
- **AND** the logo box SHALL have the same width and height for every backend

#### Scenario: Home card shows logo and name
- **WHEN** a user opens Home
- **THEN** each project card SHALL show the database logo and the text `LanceDB`

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
The Home card, the project chips in the Knowledge Base and in Chat, and the project header SHALL show the display name when set and the collection name otherwise. The project header SHALL always show the collection name in small grey text under the title, and each Home card SHALL show it in the same style under the document and chunk counts. Places where the name is an identifier SHALL keep the collection name: "Sources in <name>", the Chat input and the delete dialog. The header SHALL offer a pencil button that edits the display name in place. Enter SHALL save, Escape SHALL cancel, and an empty value SHALL clear the display name.

#### Scenario: Display name is set
- **WHEN** collection `documents` has display name `Project docs`
- **THEN** the Home card, the Knowledge Base chip, the Chat chip and the header title SHALL read `Project docs`
- **AND** the header SHALL show `Collection name: documents`

#### Scenario: Home card shows the collection name
- **WHEN** Home lists collection `documents` with display name `Project docs`
- **THEN** its card SHALL read `Project docs`, then the counts, then `Collection name: documents`
- **AND** a card with no display name SHALL still show `Collection name: <name>`

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
