## Purpose

Define the transport layer separation (MCP, CLI, API), the daemon layer for background processes, the integrations layer for external-tool wrappers, the uniform MCP error contract, FastMCP forward-compatibility, and the versioned OpenAPI 3.1 contract for the future REST transport.

## Requirements

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

### Requirement: Uniform MCP error contract

Every MCP tool handler SHALL catch its failures and return an error payload
carrying `{"status": "error", "message": "..."}`, and SHALL NOT raise from a
tool handler (AGENTS.md gotcha #1), including `ingest_documents`.

The error payload SHALL be carried in the handler's own declared return type,
not coerced into a dictionary. A handler returning a mapping returns the error
mapping directly. A handler returning a list returns a single-element list
containing it. A handler returning a string returns its JSON encoding. What is
uniform is that a failure is caught, reported with that status and message, and
never raised — not the outer container.

#### Scenario: ingest_documents failure returns dict

- **WHEN** `ingest_documents` is invoked with an input that fails during
  ingestion
- **THEN** the handler MUST catch the failure and return an error dict
- **AND** MUST NOT propagate an exception to the MCP runtime

#### Scenario: A list-returning handler reports an error

- **WHEN** `search_documents` fails
- **THEN** it MUST return a single-element list whose element carries the error
  status and message
- **AND** MUST NOT raise, and MUST NOT change its declared list return type

#### Scenario: A string-returning handler reports an error

- **WHEN** `get_codebase_map` fails
- **THEN** it MUST return a JSON-encoded string carrying the error status and
  message
- **AND** MUST NOT raise, and MUST NOT change its declared string return type

#### Scenario: All tools audited

- **WHEN** every tool handler under `transports/mcp/` is reviewed
- **THEN** each MUST have failure handling that produces an error payload in
  its own return type

---

### Requirement: FastMCP lifespan and context forward-compatibility

`transports/mcp/` SHALL preserve the ability to pass a `lifespan=`
parameter to the `FastMCP` constructor, and tool handler signatures SHALL
NOT prevent adding a `ctx: Context` parameter in future. Lifespan/context
usage itself is out of scope for this phase.

#### Scenario: Lifespan slot preserved

- **WHEN** the `FastMCP` constructor call is inspected
- **THEN** it MUST accept a `lifespan=` argument (passed as `None` or a
  context manager) without structural changes to the module

#### Scenario: Context parameter not precluded

- **WHEN** tool handler signatures are inspected
- **THEN** adding `ctx: Context` as a parameter MUST NOT require
  restructuring the handler module

---

### Requirement: Integrations consolidation

All wrappers around external tools and libraries SHALL live under
`integrations/`: local PDF parsers in `integrations/pdf/`, Azure Document
Intelligence in `integrations/azure.py`, and Magika file-type detection in
`integrations/magika.py` (extracted from `codebase_map.py`). The PDF factory
SHALL continue to dispatch to the Azure reader by importing from
`integrations.azure`.

#### Scenario: Azure at integrations root

- **WHEN** the integrations tree is inspected
- **THEN** `integrations/azure.py` MUST sit at the `integrations/` root
  (cloud intelligence service), not inside `pdf/`
- **AND** the lazy-import discipline (ADR-024 — no top-level Azure SDK
  import) MUST be preserved

#### Scenario: Magika extraction

- **WHEN** `codebase_map.py` needs file-type detection
- **THEN** it MUST import from `integrations/magika.py`
- **AND** detection behaviour MUST be unchanged

---

### Requirement: Watcher as daemon

The file watcher SHALL live at `daemon/watcher.py` as the home for
long-running background processes, distinct from request-response
transports.

#### Scenario: Watch behaviour unchanged

- **WHEN** `omrg watch` runs after the move
- **THEN** debouncing, hashing, and ingestion triggering MUST behave
  identically to the pre-refactor watcher

---

### Requirement: Agent-facing documentation reflects the final tree

The refactor SHALL update `AGENTS.md` (architecture invariants #1–#6,
gotchas, and the module list) and `docs/guides/architecture.md` to the
post-refactor structure, and SHALL refresh the graphify knowledge graph, in
the same change. In addition, every architecture decision record and
reference document SHALL be corrected wherever it asserts a property the code
does not have. A decision record SHALL NOT claim conformance that is not
enforced by a test or an import-linter contract.

#### Scenario: AGENTS.md invariants rewritten

- **WHEN** `AGENTS.md` is read after the change
- **THEN** every invariant and gotcha MUST reference the current module paths
  (e.g. `core/retrieval/reranker.py`, `core/codebase/`, `core/documents/`,
  `compose.py`, the `config/` resolver)
- **AND** no invariant MUST describe a superseded layout as current

#### Scenario: Falsified ADR claims corrected

- **WHEN** the ADR set is read after the change
- **THEN** ADR-032's claim that dispatch runs through the strategy registries,
  ADR-033's claim that no import-time settings snapshots remain, ADR-034's
  claim that no consumer reaches ChromaDB APIs directly, ADR-036 §1's claim
  that import-linter contracts already cover the boundaries, and ADR-036 §3's
  claim about the Magika extraction MUST each be either true of the code or
  amended with a correction note
- **AND** ADR-033's reference to `src/omrg/server.py` for reranker wiring
  MUST point at `transports/mcp/`

#### Scenario: Reference documents match the shipped tree

- **WHEN** `docs/brainstorm/refactor-proposal/PROPOSAL.md` is read
- **THEN** §8 Phase 2's "572 → ~150 lines" statement MUST reflect the achieved
  size
- **AND** §12's recorded deviation about top-level graph modules MUST be
  updated to record that the relocation has been completed

#### Scenario: A new decision record captures this change

- **WHEN** the ADR index is read after the change
- **THEN** a new ADR MUST record the conformance work, the nested
  configuration schema, the deletion of the v1 compatibility surface, the
  environment variable migration table, and the v2.0.0 release implication

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
