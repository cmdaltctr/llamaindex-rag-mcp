# Transport separation delta

## MODIFIED Requirements

### Requirement: Thin transports over a shared core

The system SHALL organise delivery mechanisms under `transports/`:
`transports/mcp/`, `transports/cli/`, and the optional
`transports/api/` HTTP runtime. Every transport SHALL validate input,
delegate to shared core/workspace services, and format output. No transport
file SHALL contain RAG algorithms, graph scheduling, or domain mutation
policy. Core SHALL not import a transport or receive transport-specific
objects.

Where a transport is split across modules, its package entry point SHALL own
the shared server/application and register every handler. Existing package
handler re-exports SHALL remain compatible. Importing handlers for decorator
side effects alone SHALL not remove their existing importable names.

#### Scenario: CLI split by command group

- **WHEN** the CLI is inspected after the move
- **THEN** `transports/cli/` MUST retain separate modules per existing
  command group
- **AND** existing `omrg` subcommands MUST retain their behaviour
- **AND** the explicit web command MUST live in its own thin module

#### Scenario: MCP split by tool

- **WHEN** `transports/mcp/` is inspected
- **THEN** it MUST retain separate modules per tool group
- **AND** `__init__.py` MUST own the server instance and import every tool
  module

#### Scenario: MCP server entry unchanged

- **WHEN** `omrg` is run with no arguments
- **THEN** the MCP server MUST start with its existing tool signatures
- **AND** the web workspace or notebook editor MUST not start implicitly

#### Scenario: Tool set stays complete after a transport split

- **WHEN** the running MCP server is asked to list its tools
- **THEN** every existing tool MUST still be present
- **AND** each MUST keep its name, parameters, defaults, and annotations

#### Scenario: Handlers stay importable from the package root

- **WHEN** an existing handler is imported from its transport package root
- **THEN** the import MUST succeed and yield the registered callable

#### Scenario: Core stays transport-agnostic

- **WHEN** core imports are inspected
- **THEN** no core module MUST import a transport, MCP Context, or CLI/web
  framework
- **AND** graph execution MUST remain available to plain Python consumers

#### Scenario: Optional HTTP runtime is launched

- **WHEN** the explicit web command is used with its optional dependencies
- **THEN** the HTTP runtime MUST register all documented handlers
- **AND** those handlers MUST delegate graph and document operations to shared
  services

## REMOVED Requirements

### Requirement: Versioned OpenAPI 3.1 contract for the future REST transport

**Reason**: This change implements the runtime previously deferred by this
temporary contract-only requirement.

**Migration**: Retain and extend the reviewed OpenAPI document, operation
mapping, errors, profile-resolved defaults, destructive previews, and
conformance tests under the replacement runtime requirement below. Existing
MCP/CLI interfaces remain unchanged.

## ADDED Requirements

### Requirement: Versioned OpenAPI 3.1 contract for the REST runtime

The optional HTTP runtime SHALL implement a versioned OpenAPI 3.1 contract.
Every implemented operation SHALL have explicit input, success, error,
authorisation, and job semantics. The contract and runtime SHALL agree on
fields, nullability, required values, and resolved defaults. Automated
conformance checks SHALL detect drift.

#### Scenario: Contract covers the core operations

- **WHEN** the contract is inspected
- **THEN** it SHALL cover ingestion, collection search, grounded answering,
  source/collection listing, document deletion, codebase mapping, and profile
  preview/change through the existing reviewed operation paths

#### Scenario: Graph and workspace routes are declared

- **WHEN** graph catalogue, validation/revision, execution, event, cancellation,
  inspection, session, or plugin routes are implemented
- **THEN** their input/output/error and access contracts SHALL be declared

#### Scenario: Profile change endpoint carries preview/confirm

- **WHEN** a profile change is requested without valid confirmation
- **THEN** the endpoint SHALL return a preview with effect details
- **AND** it SHALL mutate only after explicit valid confirmation

#### Scenario: Deletion endpoint requires a confirmed preview

- **WHEN** a deletion request has no valid preview confirmation
- **THEN** it SHALL not mutate the store
- **AND** its preview/confirmation request and response shapes SHALL be declared

#### Scenario: Explicit success and error schemas

- **WHEN** an HTTP operation is inspected
- **THEN** it SHALL declare success and error schemas
- **AND** errors SHALL retain the existing status/message envelope without
  exposing secrets or raw stack traces

#### Scenario: Authentication schemes declared

- **WHEN** an operation is declared
- **THEN** it SHALL reference the appropriate local-session or bearer security
  requirement
- **AND** any unauthenticated bootstrap/static operation SHALL be explicitly
  identified and constrained

#### Scenario: Long-running operations declared

- **WHEN** ingestion, codebase mapping, or graph execution is admitted
- **THEN** the contract SHALL declare 202 job semantics with an identifier and
  status
- **AND** protected status/event/cancellation routes SHALL be declared

#### Scenario: Runtime routes conform

- **WHEN** the implemented routes and schemas are compared with the reviewed
  OpenAPI contract
- **THEN** every implemented operation SHALL agree with its declared surface

#### Scenario: Contract validated in CI

- **WHEN** CI runs
- **THEN** OpenAPI validation and runtime conformance SHALL pass

#### Scenario: Search request schema covers every optional search parameter

- **WHEN** the search request is compared against the existing MCP search
  operation and core behaviour
- **THEN** every supported optional control SHALL be declared, including
  diagnostics
- **AND** profile-resolved controls SHALL not declare invented fixed defaults

#### Scenario: Document listing schema covers every listing result key

- **WHEN** listing schemas are compared with core output
- **THEN** every key SHALL be declared, including stable source identity and
  nullable machine-local orphan status

#### Scenario: Search result schema covers every default result key

- **WHEN** search-result schemas are compared with core output
- **THEN** metadata, source/chunk lineage, score, and score-kind fields SHALL
  retain their names, types, and required semantics

#### Scenario: Search result schema covers diagnostic keys as optional

- **WHEN** diagnostics are enabled
- **THEN** additional core-produced diagnostic fields SHALL be declared as
  optional rather than required in ordinary responses

#### Scenario: A parameter default disagrees with the implementation

- **WHEN** a declared default differs from the implemented or profile-resolved
  default
- **THEN** conformance SHALL fail with the affected parameter named

#### Scenario: An implemented field is missing from the contract

- **WHEN** an implemented request/result field has no matching contract field
- **THEN** conformance SHALL fail naming the field and expected schema

#### Scenario: A new field is added to an implemented surface

- **WHEN** an implemented surface adds a field without updating its contract
- **THEN** conformance SHALL fail without editing a maintained allow-list

### Requirement: Web packaging preserves optional imports
HTTP dependencies SHALL remain in an explicit optional extra. The package and existing CLI/MCP paths SHALL not import those dependencies eagerly. Static assets SHALL be included in the installed package and independent of the current working directory.

#### Scenario: Base installation has no HTTP extra
- **WHEN** the package is imported or existing help/commands are used
- **THEN** they SHALL remain available without HTTP runtime dependencies
- **AND** only the explicit web launch SHALL report the missing extra

#### Scenario: Release assets are absent
- **WHEN** a web-capable release is prepared without its built assets
- **THEN** packaging qualification SHALL fail before publication
