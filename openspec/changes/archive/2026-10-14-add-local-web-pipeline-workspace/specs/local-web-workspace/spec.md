# Local web workspace

## Purpose

Provide a protected single-user browser workspace on the same machine, with packaged assets and existing document operations delegated to shared core services.

## ADDED Requirements

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
