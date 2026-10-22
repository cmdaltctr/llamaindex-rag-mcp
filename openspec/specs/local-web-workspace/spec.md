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

`omrs web` SHALL choose its port in this order: the `--port` option, then `web_port` in `omrs.jsonc`, then 8765. `--port 0` SHALL pick a free port for that launch. When the chosen port is taken, the command SHALL exit with an error that names the port and tells the user to pass `--port <n>`. `PUT /v1/settings/web-port` with `{ port }` (browser session only, 1024 to 65535, or `null` to clear) SHALL write `web_port` to `omrs.jsonc` for later launches and SHALL NOT rebind the running server. `GET /v1/settings/web-port` (read scope) SHALL return the file port, the bound port and whether they differ. The login item SHALL read the same value.

#### Scenario: Default port

- **WHEN** `omrs web` starts with no `--port` and no `web_port` in `omrs.jsonc`
- **THEN** it MUST listen on port 8765 of the loopback host

#### Scenario: Port taken

- **WHEN** port 8765 is in use and no other port is given
- **THEN** the command MUST exit with a message naming 8765 and the `--port` option

#### Scenario: Saved port applies next launch

- **WHEN** the browser session saves port 9100 and the server restarts without `--port`
- **THEN** `omrs.jsonc` MUST hold `"web_port": 9100`, the server MUST listen on 9100, and the running server MUST NOT have moved before the restart

#### Scenario: Port edited by hand

- **WHEN** the user sets `web_port` to 9200 in `omrs.jsonc` while the server runs on 8765
- **THEN** `GET /v1/settings/web-port` MUST report that the ports differ, and the next launch MUST listen on 9200

#### Scenario: Option wins

- **WHEN** `omrs.jsonc` sets a port and `--port 9200` is given
- **THEN** the server MUST listen on 9200

#### Scenario: Invalid port in the file

- **WHEN** `web_port` holds a value outside 1024 to 65535
- **THEN** the launch MUST ignore it, use 8765, and list the problem in Settings

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

The per-file upload limit SHALL be the `web_max_upload_mib` value of `omrs.jsonc`, in whole MiB from 1 to 2048. With no value the limit SHALL be 50 MiB. `GET /v1/settings/upload-limit` (read scope) SHALL return the limit in force, its source, the file value or `null`, the default, and the allowed range. `PUT /v1/settings/upload-limit` SHALL need a browser session, SHALL take `max_mib` (an integer in range, or `null` to clear the file value), SHALL write it to `omrs.jsonc` before it changes the running server, and SHALL apply it to new uploads at once, with no restart. A hand edit of the file SHALL also apply to new uploads at once. An upload that has already started SHALL keep the limit it started with. Settings › Workspace SHALL show the limit in force and its source, SHALL let the user edit it or return to the default, and SHALL state that the change applies to new uploads straight away.

#### Scenario: Raise the limit

- **WHEN** the user saves 200 MiB in Settings and then uploads a 120 MiB file
- **THEN** the server MUST accept the file without a restart, `omrs.jsonc` MUST hold `"web_max_upload_mib": 200`, and the value MUST still apply after a restart

#### Scenario: Return to the default

- **WHEN** the user clears the value
- **THEN** `omrs.jsonc` MUST no longer hold `web_max_upload_mib`, the limit in force MUST be 50 MiB, and Settings MUST say that the default applies

#### Scenario: Value out of range

- **WHEN** a request sets `max_mib` to 0, to 4096, or to a value that is not a whole number
- **THEN** the server MUST answer 400 with the allowed range and MUST NOT change the file or the running limit, and Settings MUST name the allowed range before it sends such a value

#### Scenario: Bearer credential

- **WHEN** a bearer credential sends `PUT /v1/settings/upload-limit`
- **THEN** the server MUST refuse it and MUST NOT change the limit

#### Scenario: Limit lowered during an upload

- **WHEN** the limit is lowered while a file upload is in progress
- **THEN** that upload MUST finish against the limit it started with, and the next upload MUST use the new limit

### Requirement: A launch option sets the upload limit without the web workspace

`omrs web` SHALL accept `--max-upload-mib <n>` and SHALL read `WEB_MAX_UPLOAD_MIB` from the environment or `.env` when the flag is absent, so the limit can be set when the web workspace cannot be used. The order SHALL be the flag, then the environment variable, then `web_max_upload_mib` in `omrs.jsonc`, then 50 MiB. Both launch forms SHALL take a whole number from 1 to 2048; any other value SHALL stop the launch with exit code 2 and a message that names the option and the range. While a launch option sets the limit, `GET /v1/settings/upload-limit` SHALL report `source: "launch"`, `PUT` SHALL answer 409 and change nothing, and Settings SHALL show the limit as set at launch with no edit control. `.env.example` and the CLI reference SHALL document both.

#### Scenario: Environment variable in .env

- **WHEN** `.env` holds `WEB_MAX_UPLOAD_MIB=300` and `omrs web` starts without `--max-upload-mib`
- **THEN** the limit in force MUST be 300 MiB, and the response MUST report `source: "launch"`

#### Scenario: Flag beats environment and saved value

- **WHEN** `omrs.jsonc` sets 200 MiB, the environment sets 300, and `omrs web --max-upload-mib 400` starts
- **THEN** the limit in force MUST be 400 MiB

#### Scenario: Invalid launch value

- **WHEN** `WEB_MAX_UPLOAD_MIB` is `0`, `5000` or `big`
- **THEN** `omrs web` MUST exit with code 2 before it binds a port and MUST name `WEB_MAX_UPLOAD_MIB` and the range 1 to 2048

#### Scenario: Settings while a launch option is set

- **WHEN** a launch option sets the limit and a browser session sends `PUT /v1/settings/upload-limit`
- **THEN** the server MUST answer 409, MUST keep the file and the running limit, and Settings MUST say the limit was set at launch and how to change it

#### Scenario: No launch option

- **WHEN** neither the flag nor the environment variable is set
- **THEN** the file value MUST apply, else 50 MiB, and the response MUST report `source: "config-file"` or `source: "default"`

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

### Requirement: A login-item server hands over a renewed private sign-in link

When started with `--login-item`, the server SHALL write its one-time sign-in link to `<workspace>/launch-link`, as one line, in a file that only the current user can read (mode 0600), and SHALL NOT print the link to standard output, standard error or any log. After the link is used, or after the failed-attempt limit disables it, the server SHALL create a new link with a new secret and replace the file's content atomically. Each link SHALL work once. The server SHALL remove the file during its shutdown, before the process ends, also when a stop signal ends the process. A login-item server SHALL NOT write access-log lines. Browser sessions SHALL stay in server memory and SHALL end when the server stops. A page that the server served SHALL then sign in again with the workspace sign-in secret, as "The page carries a persistent workspace sign-in secret" states.

#### Scenario: Link file is private

- **WHEN** a login-item server starts
- **THEN** `<workspace>/launch-link` MUST exist with mode 0600 and MUST hold a link for the bound port
- **AND** the link MUST NOT appear in standard output, standard error or the log buffer

#### Scenario: Link renews after sign-in

- **WHEN** a browser signs in with the link in the file
- **THEN** the file MUST then hold a different link
- **AND** the first link MUST be refused if used again

#### Scenario: Link renews after the failure limit

- **WHEN** 20 wrong secrets have been posted
- **THEN** the old secret MUST be refused
- **AND** the file MUST hold a new link that signs in

#### Scenario: A failed renewal is retried

- **WHEN** the server cannot write the renewed link, and a later sign-in attempt arrives
- **THEN** the server MUST write the current link to the file again, and the earlier sign-in MUST NOT fail

#### Scenario: Clean shutdown removes the file

- **WHEN** the server receives SIGTERM
- **THEN** `<workspace>/launch-link` MUST NOT exist once the process has ended

#### Scenario: Foreground launch is unchanged

- **WHEN** the user runs `omrs web` without `--login-item`
- **THEN** the server MUST print the one-time link to the terminal, MUST write no `launch-link` file, and MUST accept that link once, as before

### Requirement: The page carries a persistent workspace sign-in secret

The server SHALL keep one sign-in secret in `<workspace>/.auth-token`. It SHALL create the file on its first start with a new random secret of at least 256 bits, in a file that only the current user can read (mode 0600), and SHALL create a missing workspace folder with mode 0700. Every later start with the same workspace SHALL read and use the same secret. A file with a mode looser than 0600 SHALL get a warning, and the server SHALL set the mode to 0600 when the current user owns the file. A file that holds no valid secret SHALL get a warning and SHALL be replaced. Neither case SHALL stop the server.

The server SHALL put the secret into the application page that it serves only when the `Host` header is one of its own loopback names with the bound port, any `Origin` header is the server's own origin or an origin approved with `--allow-origin`, and the fetch metadata shows a same-origin request or a navigation. Any other request SHALL get the page without the secret, or the `Host` refusal. A page that carries the secret SHALL be sent with `Cache-Control: no-store`.

`POST /v1/session` SHALL accept the secret in its `bootstrap` field, with the same `Origin` check, and SHALL set the same session cookie as for the one-time link. A sign-in with the secret SHALL NOT use, renew or disable the one-time link. Wrong values SHALL count toward the failure limit of the one-time link and SHALL NOT disable the secret.

The page SHALL sign in with the secret on load when the address has no one-time link, or when that link is refused. When an API request gets 401, the page SHALL sign in with the secret once and SHALL send the request once more. Requests that get 401 at the same time SHALL share one sign-in.

The secret SHALL NOT appear in a log line, an API response body, an error message, a URL or the terminal.

#### Scenario: First start creates a private secret

- **WHEN** the server starts with a workspace that has no `.auth-token`
- **THEN** `<workspace>/.auth-token` MUST exist with mode 0600
- **AND** a workspace folder that the server created MUST have mode 0700

#### Scenario: Later starts reuse the secret

- **WHEN** two servers start one after the other with the same workspace
- **THEN** both MUST put the same secret into their page

#### Scenario: A loose mode is tightened

- **WHEN** `.auth-token` has mode 0644 at start
- **THEN** the server MUST log a warning that names mode 0600 and MUST NOT log the secret
- **AND** the file MUST then have mode 0600 and MUST hold the same secret

#### Scenario: An open tab survives a restart

- **WHEN** a page signed in, the server restarts with the same workspace, and the page sends its next API request with the old cookie
- **THEN** the request MUST get 401, the page MUST sign in with the secret it holds, and the repeated request MUST succeed
- **AND** no one-time link MUST be needed

#### Scenario: A foreign Host never gets the secret

- **WHEN** a request for the page carries a `Host` that is not one of the server's own loopback names with its port
- **THEN** the server MUST answer 400 and the body MUST NOT hold the secret

#### Scenario: A foreign reader gets the page without the secret

- **WHEN** a request for the page carries a foreign `Origin`, or cross-site or same-site fetch metadata that is not a navigation
- **THEN** the page MUST NOT hold the secret

#### Scenario: An approved preview origin signs in

- **WHEN** the server starts with an approved origin and that origin loads the page and posts the secret
- **THEN** the page MUST hold the secret and the server MUST set the session cookie

#### Scenario: Sign-in with the secret leaves the link unused

- **WHEN** a login-item server signs a page in with the secret
- **THEN** `<workspace>/launch-link` MUST hold the same link as before, and that link MUST still sign in

#### Scenario: Wrong guesses do not lock out the page

- **WHEN** more than 20 wrong values have been posted
- **THEN** the one-time link MUST be refused and the secret MUST still sign in

#### Scenario: One retry only

- **WHEN** an API request gets 401 and the sign-in with the secret is refused
- **THEN** the page MUST report the 401 and MUST NOT send the request again

### Requirement: The answer route can stream its stage

The app SHALL offer `POST /v1/collections/{collection}/answer/stream`. It SHALL take the body of `POST /v1/collections/{collection}/answer`, SHALL need the `read` scope, and SHALL follow the same authentication, Host and Origin rules. A valid request SHALL get `text/event-stream` with `stage` frames, then exactly one `result` frame, then the end. The route SHALL open the stream only when the first stage or the result is ready. A request that fails before the stream opens SHALL get an ordinary HTTP error. A request the Engine rejects as invalid SHALL get the same 400 response as the blocking route.

#### Scenario: Stages then result

- **WHEN** a session posts a valid question to the stream route
- **THEN** the response MUST be `text/event-stream`
- **AND** it MUST hold `stage` frames in stage order, then one `result` frame, then end

#### Scenario: The result equals the blocking result

- **WHEN** the same question is posted to the stream route and to `POST .../answer`
- **THEN** the `result` frame MUST hold the same fields as the blocking response, with the same redaction of its `error` text

#### Scenario: The blocking route is unchanged

- **WHEN** a client posts to `POST /v1/collections/{collection}/answer`
- **THEN** the response MUST be the same JSON as before this change
- **AND** the status codes MUST be the same

#### Scenario: Authentication and Origin

- **WHEN** a request has no credential, or a session cookie with a foreign Origin, or a bearer credential without the `read` scope
- **THEN** the route MUST answer 401 or 403 before it admits any work
- **AND** a bearer credential with the `read` scope MUST be accepted

#### Scenario: Bad body

- **WHEN** the body has an unknown field or a question over 4,096 characters
- **THEN** the route MUST answer with the same error as the blocking route and MUST NOT open a stream

#### Scenario: Server is shutting down

- **WHEN** the server has stopped admitting work
- **THEN** the route MUST answer 503 and MUST NOT open a stream

#### Scenario: The Engine rejects the request

- **WHEN** the Engine raises a validation error, for example because the user profile has no saved Answer graph
- **THEN** the route MUST answer 400 with the same body as the blocking route
- **AND** it MUST NOT open a stream

### Requirement: Stage frames carry no content

A `stage` frame SHALL hold only a stage name, a sequence number that starts at 1 and rises by 1, and the elapsed milliseconds since the request was admitted. The frame schema SHALL be closed. A `stage` frame SHALL NOT hold question text, passage text, answer text, model names, provider names, keys, paths or error text. The `result` frame SHALL be the only frame that holds answer content.

#### Scenario: Question text does not leak into stage frames

- **WHEN** the question contains a marker string and the answer fails with an error text that contains a saved key
- **THEN** no `stage` frame MUST contain the marker or the key
- **AND** the `result` frame MUST hold the key-free error text of the blocking route

#### Scenario: Frames match the contract

- **WHEN** a stream is read in full
- **THEN** every frame MUST match the schema that `openapi.yaml` declares for its event name

#### Scenario: Sequence numbers

- **WHEN** a stream reports three stages
- **THEN** their sequence numbers MUST be 1, 2 and 3 and their elapsed times MUST not fall

### Requirement: A stream follows its client

The streaming answer SHALL hold runtime admission from before the first byte until the answer ends or is cancelled. When the client leaves before the `result` frame, the server SHALL cancel the answer and SHALL release admission. The route SHALL watch the client itself, so that a client that leaves while no frame is due is noticed whatever ASGI spec version the server reports. A cancelled answer SHALL write nothing. Each stream SHALL have its own frames. A stream SHALL keep no state after it ends.

#### Scenario: Browser tab closes mid-answer

- **WHEN** the client drops the connection while the answer runs
- **THEN** the server MUST cancel the answer
- **AND** the admission count MUST return to its value before the request

#### Scenario: Client leaves during a long model call

- **WHEN** the client drops the connection while the model call runs and no frame is due
- **THEN** the server MUST cancel the answer within a few seconds
- **AND** it MUST NOT wait for the next frame to notice

#### Scenario: Two answers at once

- **WHEN** two clients start streams at the same time
- **THEN** each stream MUST hold only the stages of its own answer
- **AND** each MUST end with its own `result` frame

#### Scenario: Shutdown while a stream runs

- **WHEN** graceful shutdown begins during a stream
- **THEN** the server MUST wait for the admitted answer as it does for the blocking route
- **AND** the Engine MUST stay open until the answer ends

#### Scenario: Unexpected Engine error

- **WHEN** the Engine raises an error other than a validation error during the stream
- **THEN** the stream MUST end with a `result` frame in the same error shape the blocking route returns for that case
